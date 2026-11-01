"""Temperature sources. CPU: coretemp package. GPU: nvidia-smi, only if the dGPU is
already awake (never wake a runtime-suspended GPU just to read its temperature)."""
from __future__ import annotations
import glob, os, subprocess

GPU_PCI = "/sys/bus/pci/devices/0000:01:00.0"


def cpu_temp() -> int:
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        try:
            if open(f"{d}/name").read().strip() == "coretemp":
                return int(open(f"{d}/temp1_input").read()) // 1000
        except OSError:
            continue
    raise FileNotFoundError("coretemp hwmon not found")


def gpu_temp() -> int | None:
    try:
        if open(f"{GPU_PCI}/power/runtime_status").read().strip() != "active":
            return None
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3)
        return int(out.stdout.strip()) if out.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
