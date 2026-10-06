from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import torch
from sklearn.metrics import average_precision_score
from torch import nn

from ai_earth_intelligence_and_forecasting_engine.forecast.build_dataset import (
    DatasetRow,
)
from ai_earth_intelligence_and_forecasting_engine.models.preprocessing import (
    Preprocessor,
    extract_targets,
    fit_preprocessor,
    transform,
)

SEED = 20241004
HIDDEN_UNITS = (64, 32)
DROPOUT = 0.1
LEARNING_RATE = 1e-3
WEIGHT_DECAY = 1e-5
BATCH_SIZE = 4096
MAX_EPOCHS = 30
PATIENCE = 4


@dataclass
class NeuralResult:
    network: nn.Module
    preprocessor: Preprocessor
    best_epoch: int
    validation_pr_auc: float
    history: list[dict[str, float]] = field(default_factory=list)


def build_network(n_features: int) -> nn.Module:
    layers: list[nn.Module] = []
    width = n_features
    for units in HIDDEN_UNITS:
        layers += [nn.Linear(width, units), nn.ReLU(), nn.Dropout(DROPOUT)]
        width = units
    layers.append(nn.Linear(width, 1))
    return nn.Sequential(*layers)


def _scores(network: nn.Module, x: torch.Tensor) -> np.ndarray:
    network.eval()
    with torch.no_grad():
        logits = torch.cat(
            [network(x[i : i + BATCH_SIZE]) for i in range(0, len(x), BATCH_SIZE)]
        )
    return torch.sigmoid(logits).squeeze(1).numpy()


def fit_neural(
    train_rows: list[DatasetRow],
    validation_rows: list[DatasetRow],
    max_epochs: int = MAX_EPOCHS,
) -> NeuralResult:
    torch.manual_seed(SEED)
    generator = torch.Generator().manual_seed(SEED)

    preprocessor = fit_preprocessor(train_rows)
    x_train = torch.tensor(transform(preprocessor, train_rows), dtype=torch.float32)
    y_train = torch.tensor(extract_targets(train_rows), dtype=torch.float32)
    x_validation = torch.tensor(
        transform(preprocessor, validation_rows), dtype=torch.float32
    )
    y_validation = extract_targets(validation_rows)

    positives = float(y_train.sum())
    if positives == 0 or y_validation.sum() == 0:
        raise ValueError("train and validation splits both need positive rows")
    pos_weight = torch.tensor([(len(y_train) - positives) / positives])

    network = build_network(x_train.shape[1])
    optimizer = torch.optim.Adam(
        network.parameters(), lr=LEARNING_RATE, weight_decay=WEIGHT_DECAY
    )
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    best_state = {k: v.clone() for k, v in network.state_dict().items()}
    best_pr_auc, best_epoch, stale = -1.0, 0, 0
    history: list[dict[str, float]] = []
    for epoch in range(1, max_epochs + 1):
        network.train()
        order = torch.randperm(len(x_train), generator=generator)
        total = 0.0
        for start in range(0, len(order), BATCH_SIZE):
            batch = order[start : start + BATCH_SIZE]
            optimizer.zero_grad()
            loss = loss_fn(network(x_train[batch]).squeeze(1), y_train[batch])
            loss.backward()
            optimizer.step()
            total += loss.item() * len(batch)

        pr_auc = float(
            average_precision_score(y_validation, _scores(network, x_validation))
        )
        history.append(
            {
                "epoch": epoch,
                "train_loss": total / len(order),
                "validation_pr_auc": pr_auc,
            }
        )
        if pr_auc > best_pr_auc:
            best_pr_auc, best_epoch, stale = pr_auc, epoch, 0
            best_state = {k: v.clone() for k, v in network.state_dict().items()}
        else:
            stale += 1
            if stale >= PATIENCE:
                break

    network.load_state_dict(best_state)
    return NeuralResult(network, preprocessor, best_epoch, best_pr_auc, history)


def predict_neural(result: NeuralResult, rows: list[DatasetRow]) -> list[float]:
    x = torch.tensor(transform(result.preprocessor, rows), dtype=torch.float32)
    return _scores(result.network, x).tolist()
