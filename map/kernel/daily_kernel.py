import os
import subprocess
import sys

REPOSITORY = "__REPOSITORY__"
COMMIT = "__COMMIT__"
CUTOFF = "__CUTOFF__"
OUTPUT = "/kaggle/working/daily"


def run(*command: str, **options) -> None:
    subprocess.run(list(command), check=True, **options)


run(sys.executable, "-m", "pip", "install", "-q", "earth2studio[data,sfno]")
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
    env={**os.environ, "PYTHONPATH": "project/ml/src"},
)
