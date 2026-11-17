# Earth-2 Models on a T4

Which NVIDIA Earth2Studio weather models run on a free Kaggle T4 GPU,
how long they take, and which inputs of the
[Hot-Dry-Windy Index](hot-dry-windy-index.md) they output. The answer
decides the weather model for the [multi-day experiment](multi-day-risk.md)
and the [daily map](daily-risk-map.md).

Run with `notebooks/earth2_models_on_t4.ipynb`. Results:
`ml/artifacts/earth2_models/earth2_models_t4.json`.

## Environment

| Item | Value |
|---|---|
| GPU | Tesla T4, 15.6 GB |
| Driver | 580.178.04 |
| PyTorch | 2.11.0+cu130 (CUDA 13.0) |
| Earth2Studio | 0.20.0 |
| Python | 3.13.16 |

## Official example

The deterministic workflow from the Earth2Studio examples (DLWP from GFS
initial conditions, 20 steps of 6 hours) ran in 15.5 s, including loading
the model and downloading the initial conditions.

## Model table

Each global model runs 12 steps of 6 hours (3 days) from
2024-07-01 06:00 UTC, starting from ERA5 on Google Cloud (ARCO).
StormCast runs 12 steps of 1 hour from 2022-11-04 18:00 UTC with HRRR.
Peak memory is the most GPU memory PyTorch held. For a run that failed,
it is the memory in use when the run stopped.

| Model | Fits on a T4 | Peak memory (GB) | Load (s) | Initial conditions (s) | Index inputs |
|---|---|---:|---:|---:|---|
| FourCastNet 3 (FCN3) | No, out of memory | 13.56 | 166.7 | 12.8 | 2 m temperature, 10 m wind, 13 levels. No 2 m dew point, no surface pressure. |
| SFNO | No, out of memory | 11.57 | 204.7 | 7.1 | 2 m temperature, 10 m wind, surface pressure, 13 levels. No 2 m dew point. |
| Atlas | Not measured | – | – | – | Earth2Studio could not import one of its optional packages. |
| StormCast (US) | Not measured | 5.10 | 108.5 | 10.5 | 2 m temperature, 10 m wind, no levels. The input did not match the model's grid. |

"13 levels" means temperature, humidity and wind at 1000, 925, 850, 700,
600, 500, 400, 300, 250, 200, 150, 100 and 50 hPa.

Atlas and StormCast were not run again. Earth2Studio lists Atlas for
GPUs with 80 GB, and StormCast covers the United States at 3 km with no
pressure levels, so neither would replace a global model with levels
here.

## What the table means

- **No model outputs a 2 m dew point.** Every index from these models is
  the HDWI approximation (`hdwi_approx_v1`, see
  [Multi-Day Wildfire Risk](multi-day-risk.md#index-version)).
- **SFNO has every other input.** FourCastNet 3 has no surface pressure,
  which the index needs to find the levels above the ground.
- **Neither global model fits as released.** The next section explains
  how SFNO was made to fit.

## Fitting SFNO on a T4

SFNO does most of its work on a coarser internal grid. Its first layers
(the encoder), the last block's MLP and its last layers (the decoder)
work on the full 721 × 1440 grid, one point at a time: each is a 1 × 1
convolution with an activation, so an output point depends only on the
same input point. On the full grid, one float32 channel takes 4.2 MB
(721 × 1440 × 4 bytes), so a hidden tensor with hundreds of channels
takes gigabytes. These tensors are the most likely cause of the
failure.

`earth2/memory.py` changes how these layers run, not what they compute:

- Each per-pixel layer runs on blocks of 64 latitude rows, and each
  block's result is written into one output tensor. Only one block's
  temporary tensors exist at a time.
- A layer is changed only if every part of it is a 1 × 1 convolution or
  an element-wise activation. Layers that mix neighboring points are left
  as they are.
- The model and its weights do not change. The results match the
  unchanged layers up to floating-point rounding.

The GPU runs also set `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`,
so that PyTorch can reuse freed GPU memory with less fragmentation.

`ml/tests/earth2/test_memory.py` checks that a network gives the same
output before and after the change, that no block has more than the
given number of rows, and that layers that mix neighboring points are
not changed.

The daily pipeline notebook (`notebooks/daily_pipeline_on_t4.ipynb`)
measures SFNO with and without this change on the same date. Its results
are in [Daily Risk Map](daily-risk-map.md#pipeline-profile).
