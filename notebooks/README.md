# Notebooks

GPU work runs on a free Kaggle T4, because the development machine has
no NVIDIA GPU. Each notebook saves its results to `/kaggle/working/`.
Download them and copy them to the path in the table.

| Notebook | Purpose | Copy results to |
|---|---|---|
| `earth2_models_on_t4.ipynb` | Which Earth2Studio models fit on a T4, their run time and memory, and which index inputs they output | `ml/artifacts/earth2_models/` |
| `gpu_kernels_on_t4.ipynb` | GPU tests and the kernel benchmark | `ml/artifacts/gpu_perf/` |

To run one on Kaggle:

1. Create a notebook and choose **File → Import Notebook**.
2. In **Settings**, set **Accelerator** to **GPU T4 x2** and turn
   **Internet** on. A Kaggle account needs a verified phone number to
   use GPUs.
3. Choose **Run All**, then download the output files.
