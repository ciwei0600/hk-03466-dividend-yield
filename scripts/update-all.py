#!/usr/bin/env python3
"""Refresh each fund independently so one upstream failure cannot stop the other."""
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    results = [subprocess.run([sys.executable, str(Path(__file__).with_name(name)), *sys.argv[1:]]).returncode
               for name in ("update-data.py", "update-cn-data.py")]
    sys.exit(1 if any(results) else 0)
