"""Wrapper to run training with output logged to file."""
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

cmd = [
    sys.executable, "training/train.py",
    "--data", "training/data/bfs_structured_cot_v2.jsonl",
    "--output", "training/output/stage_c2v2",
    "--stage", "C",
    "--epochs", "5",
    "--lr", "1e-4",
    "--warmup-steps", "5",
    "--max-seq-length", "2048",
    "--batch-size", "1",
    "--grad-accum", "8",
]

log_path = "training/output/train_v2.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

env = os.environ.copy()
env["PYTHONIOENCODING"] = "utf-8"

print(f"Running: {' '.join(cmd)}")
print(f"Logging to: {log_path}")

with open(log_path, "w", encoding="utf-8") as log_file:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    for line in proc.stdout:
        print(line, end="")
        log_file.write(line)
        log_file.flush()
    proc.wait()

print(f"\nExit code: {proc.returncode}")
print(f"Full log at: {log_path}")
