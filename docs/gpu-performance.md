# GPU Performance

Faster versions of the [Hot-Dry-Windy Index](hot-dry-windy-index.md):
`torch.compile`, a Triton kernel and a CUDA C++ kernel, measured on an
NVIDIA T4.

## Why the index is a good kernel

The index reads nine fields for every grid column (five surface fields
and four fields on each pressure level), does a few operations per
value, and writes one number. Almost all the time goes into moving
data, not into math. A kernel like this is **memory-bound**: its speed
limit is the GPU's memory bandwidth.

Plain PyTorch runs the index as dozens of separate operations. Each one
reads its inputs from GPU memory and writes a full-size result back.
A fused kernel reads each input once, keeps running maxima in
registers, and writes one value per column.

## Correctness rules

These limits were set before any faster version was written. Every
version is compared with the float64 reference on random columns and on
every edge case.

| Check | Limit |
|---|---|
| Absolute error | 0.001 |
| Relative error | 0.0001 |
| Missing values | NaN in exactly the same columns as the reference |

A version that breaks any limit is not benchmarked.

## Versions

| Version | File | How it works |
|---|---|---|
| Eager PyTorch | `kernels/hdwi_reference.py` | The reference itself, run in float32. |
| `torch.compile` | `kernels/hdwi_compiled.py` | The reference compiled with mode `max-autotune-no-cudagraphs`. PyTorch generates its own fused Triton kernels. |
| Triton | `kernels/hdwi_triton.py` | One program handles 256 columns and loops over the levels inside the kernel. |
| CUDA C++ | `kernels/hdwi_cuda.cu`, `hdwi_cuda.cpp`, `hdwi_cuda.py` | One thread per column, built with `torch.utils.cpp_extension.load`. Bounds are checked, and launch errors are raised as Python errors. |

The hand-written kernels follow the reference exactly:

- They use the same levels: every level above the ground, up to and
  including the first level more than 50 hPa above the surface. They
  stop reading at that level.
- They return NaN when any value the column uses is missing. Missing
  values below the ground or above the layer are ignored.
- They convert surface pressure from Pa to hPa by dividing by 100, not
  by multiplying by 0.01. Division is exact for whole numbers, so a
  surface that sits exactly on a pressure level picks the same levels as
  the float64 reference.

## Memory layout

Earth2Studio returns fields with longitude as the fastest-changing
dimension. `kernels/layout.py` keeps that order and only flattens the
grid:

```text
surface fields   (batch, columns)
level fields     (batch, levels, columns)
columns = latitude × longitude
```

Thread `i` handles column `i`, so at each level, neighboring threads
read neighboring addresses. The GPU can then combine the reads of a
whole warp into a few memory transactions (coalesced access). For
float32 inputs that are already contiguous, packing makes no copy.

## Tests

`tests/kernels/test_hdwi_gpu.py` runs all four versions against the
float64 reference:

- every edge case: calm wind, saturated air, missing values in used and
  unused levels, extreme values and high terrain;
- random columns on two level sets: the 13 levels of FourCastNet 3 and a
  dense set of 12 levels between 1000 and 700 hPa;
- surfaces that sit exactly on a level, or exactly 50 hPa below one.

The tests skip on a machine without a CUDA GPU.

## Benchmark method

`kernels/bench.py` and `scripts/research/run_gpu_benchmark.py`:

- **Sizes:** one global 0.25° field (721 × 1440 columns, 13 levels),
  12 fields (3 days of 6-hour steps) and 16 fields (an ensemble). A size
  that runs out of memory is recorded as such.
- **Timing:** CUDA events, 10 warmup runs, then 50 timed runs. The table
  reports the median and the 90th percentile.
- **Bytes moved:** the minimum the index needs: each surface field read
  once, each used level read once, and the output written once.
- **Effective bandwidth:** bytes moved divided by the median time.
- **Peak bandwidth:** measured on the same GPU by timing a 1 GiB
  device-to-device copy (bytes moved = 2 × size). Each version is
  reported as a share of this measured peak, not of the 320 GB/s on the
  datasheet.
- **Errors:** the maximum absolute and relative error against the
  float64 reference are saved for every run.

Run on a machine with a CUDA GPU:

```bash
cd ml
uv sync --group research
cd ..
python scripts/research/run_gpu_benchmark.py
```

Results go to `ml/artifacts/gpu_perf/<run_id>/`: `kernel_benchmark.csv`,
`summary.json` with the GPU, driver, CUDA, PyTorch and Triton versions,
and `percent_of_peak.png`.

Without a local GPU, run `notebooks/gpu_kernels_on_t4.ipynb` on a free
Kaggle T4 (see [notebooks/README.md](../notebooks/README.md)). It runs the
tests, the benchmark and, if the container allows it, Nsight Compute.

## Kernel speed is not pipeline speed

The index is one small step after a weather model that runs for many
seconds. A faster index kernel only matters as much as the index's share
of the full run. Kernel results are always shown next to that share,
which comes from the stage times of the daily run (see
[Daily Risk Map](daily-risk-map.md#pipeline-profile)).
