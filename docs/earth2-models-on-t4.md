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

In the table above, SFNO ran with PyTorch's default memory settings and
failed with 11.57 GB in use. With
`PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, which lets PyTorch
reuse freed GPU memory with less fragmentation, it still failed: the
GELU activation of an MLP needed 2.97 GiB more while 11.59 GiB were in
use (the "as released" run below).

SFNO works on the full 721 × 1440 grid. One float32 channel of that grid
takes 4.2 MB, so a tensor with hundreds of channels takes gigabytes.
`earth2/memory.py` makes these tensors smaller. It changes how two kinds
of layers run, not what they compute:

- **Per-pixel layers in row blocks.** The encoder, the MLPs and the
  decoder are 1 × 1 convolutions with activations: each output point
  depends only on the same input point. They now run on blocks of 64
  latitude rows. A layer is changed only if every part of it is a
  1 × 1 convolution or an element-wise activation.
- **Spherical harmonic transforms in channel blocks.** The forward and
  inverse transforms treat each channel on its own. They now run on
  blocks of 32 channels.

In both cases, each block's result is written into one output tensor, so
only one block's temporary tensors exist at a time. The model and its
weights do not change.

`ml/tests/earth2/test_memory.py` checks that a small network gives the
same output before and after the changes, that blocks have the given
size, and that layers that mix neighboring points are not changed.

### Result

Measured in the daily pipeline runs (`ml/artifacts/daily_pipeline/`),
all with `expandable_segments`:

| SFNO setting | Result | Peak memory (GB) |
|---|---|---:|
| As released | Out of memory in an MLP (needed 2.97 GiB more, 11.59 GiB in use) | – |
| Row blocks only | Ran | 15.07 |
| Row blocks and channel blocks | Ran | 12.76 |

With row blocks only, the run fits with about 0.5 GB to spare on the
15.6 GB T4. The first daily runs with row blocks only failed, because
the run also kept full-grid fields from the index step. The channel
blocks lower the peak by 2.3 GB more, so the default uses both.

The run with row blocks only and the runs with both gave exactly the
same daily features. One SFNO step takes about 3 s on the T4 (31 to 37 s
for 11 steps). See [Daily Risk Map](daily-risk-map.md#pipeline-profile)
for the full stage times.
