"""Compile the exact solver (tools/java_bfs) into tools/java_bfs/out. Needs a JDK (javac) on PATH.

    python scripts/build_solver.py
    java -cp tools/java_bfs/out Main --summary < data/floors/hand/hand01.txt
"""
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "tools" / "java_bfs"
OUT = SRC / "out"
OUT.mkdir(exist_ok=True)
r = subprocess.run(["javac", "-d", str(OUT), *map(str, sorted(SRC.glob("*.java")))])
if r.returncode == 0:
    print(f"compiled -> {OUT}")
sys.exit(r.returncode)
