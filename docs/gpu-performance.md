# GPU Performance

Faster versions of the [Hot-Dry-Windy Index](hot-dry-windy-index.md):
`torch.compile`, a Triton kernel and a CUDA C++ kernel, measured on an
NVIDIA T4.

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
