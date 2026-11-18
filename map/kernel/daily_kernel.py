import os
import subprocess
import sys

REPOSITORY = "__REPOSITORY__"
COMMIT = "__COMMIT__"
CUTOFF = "__CUTOFF__"
OUTPUT = "/kaggle/working/daily"
MAKANI = (
    "makani @ git+https://github.com/NVIDIA/makani.git"
    "@b38fcb2799d7dbc146fa60459f3f9823394a8bf1"
)


def run(*command: str, **options) -> None:
    subprocess.run(list(command), check=True, **options)


run(
    sys.executable,
    "-m",
    "pip",
    "install",
    "-q",
    MAKANI,
    "earth2studio[data,sfno]==0.20.0",
)
run(sys.executable, "-m", "pip", "install", "-q", "python-dotenv")
run("git", "clone", "--quiet", REPOSITORY, "project")
run("git", "-C", "project", "checkout", "--quiet", COMMIT)
run(
    sys.executable,
    "project/scripts/map/run_daily_forecast.py",
    "--cutoff",
    CUTOFF,
    "--output",
    OUTPUT,
    "--lean-imports",
    env={
        **os.environ,
        "PYTHONPATH": "project/ml/src",
        "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
    },
)
