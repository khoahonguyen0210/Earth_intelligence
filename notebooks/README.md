# Notebooks

GPU work runs on a free Kaggle T4, because the development machine has
no NVIDIA GPU. Each notebook saves its results to `/kaggle/working/`.
Download them and copy them to the path in the table.

| Notebook | Purpose | Copy results to |
|---|---|---|
| `earth2_models_on_t4.ipynb` | Which Earth2Studio models fit on a T4, their run time and memory, and which index inputs they output | `ml/artifacts/earth2_models/` |
| `gpu_kernels_on_t4.ipynb` | GPU tests and the kernel benchmark | `ml/artifacts/gpu_perf/` |
| `e7_forecasts_on_t4.ipynb` | Weather forecasts and daily index values for the [multi-day experiment](../docs/multi-day-risk.md) | `ml/artifacts/e7_forecasts/` |
| `daily_pipeline_on_t4.ipynb` | Stage times and peak memory of one [daily map](../docs/daily-risk-map.md) run, for each index version | `ml/artifacts/daily_pipeline/` |
| `pipeline_changes_on_t4.ipynb` | Before and after times of each [pipeline change](../docs/daily-risk-map.md#pipeline-changes) | `ml/artifacts/pipeline_changes/` |
| `ensemble_on_t4.ipynb` | Ensemble throughput on one and two T4 GPUs, with 1, 2 or 4 members per batch | `ml/artifacts/ensemble_on_t4/` |
| `import_times_on_t4.ipynb` | Import times of the daily run, and default against [lean imports](../docs/daily-risk-map.md#imports) | `ml/artifacts/import_times/`, `ml/artifacts/lean_imports/` |

To run one on Kaggle:

1. Create a notebook and choose **File → Import Notebook**.
2. In **Settings**, set **Accelerator** to **GPU T4 x2** and turn
   **Internet** on. A Kaggle account needs a verified phone number to
   use GPUs.
3. Choose **Run All**, then download the output files.

The notebooks get the project from GitHub. To run code that is not on
GitHub yet, upload the repository as a private Kaggle dataset named
`earth-intelligence` and add it to the notebook with **Add Input**. The
notebooks use the uploaded copy when it is there.
