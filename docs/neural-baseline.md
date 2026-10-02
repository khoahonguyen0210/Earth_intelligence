# Neural Network Baseline

A research comparison: does a neural network beat the served XGBoost
model on the same data? It does not. The network is kept as a
measured baseline and never replaces calibrated XGBoost in service.

## Setup

`research/neural.py`, PyTorch on CPU:

- **Same inputs and splits as the benchmark.** The 12 numeric features
  and land-cover one-hot from the locked feature set, through the same
  preprocessor. Train 2019 to 2022, validation 2023, test 2024.
- **Network:** a multilayer perceptron, 23 inputs, hidden layers of 64
  and 32 units with ReLU and 10% dropout, one output logit.
- **Class imbalance:** fires are under 1% of rows, so the positive class
  is weighted by the train split's negative-to-positive ratio in the
  binary cross-entropy loss.
- **Training:** Adam, learning rate 0.001, batches of 4,096, fixed seed.
  Early stopping keeps the epoch with the best validation PR-AUC and
  stops after 4 epochs without improvement. The test year is only
  scored, never used for any choice.

Reproduce with:

```bash
uv sync --group research          # adds PyTorch, kept out of CI and Docker
python scripts/research/run_neural_baseline.py
```

## Result

Training ran 15 epochs in 107 seconds; epoch 11 had the best validation
PR-AUC (0.426). On the 2024 test year, with 95% intervals from the same
bootstrap over forecast dates as `docs/evaluation.md`:

| Model | Test PR-AUC | 95% interval |
|---|---|---|
| XGBoost | 0.451 | 0.374 to 0.521 |
| Neural network | 0.388 | 0.308 to 0.459 |
| Neural minus XGBoost | -0.064 | -0.095 to -0.031 |

What this shows:

- **XGBoost is clearly better.** The whole interval of the difference is
  below zero.
- **The network is no better than the no-model rule.** Its 0.388 matches
  the 0.384 of predicting fire where it burned in the last 24 hours.
- **The gap is at the top of the ranking.** ROC-AUC is nearly equal
  (0.965 against XGBoost's 0.967). The network orders cells about as
  well overall but is worse at picking out the few riskiest ones, which
  is what PR-AUC measures and what matters for a fire forecast.

This matches what is widely reported for tabular data: gradient-boosted
trees usually beat neural networks on a few dozen engineered features,
especially when the target is rare. Here the trees can split cleanly
on fire counts that are zero for most cells, which a network has to
learn through smooth weights.

## Limits

- One architecture with untuned hyperparameters. A larger search could
  narrow the gap, but would have to be judged on validation data, not
  the test year.
- The network's scores are not calibrated probabilities, because of the
  weighted loss. It is compared on ranking (PR-AUC) only.
- PyTorch lives in the separate `research` dependency group, so CI and
  the Docker image do not install it, and its tests skip when it is
  absent.
