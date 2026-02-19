#!/usr/bin/env python3
"""Build the claudetini-sidecar binary using PyInstaller."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_target_triple() -> str:
    """Detect the current platform's Tauri target triple."""
    machine = platform.machine().lower()
    system = platform.system().lower()

    if system == "darwin":
        arch = "aarch64" if machine == "arm64" else "x86_64"
        return f"{arch}-apple-darwin"
    elif system == "linux":
        arch = "aarch64" if machine == "aarch64" else "x86_64"
        return f"{arch}-unknown-linux-gnu"
    elif system == "windows":
        return "x86_64-pc-windows-msvc"
    else:
        raise RuntimeError(f"Unsupported platform: {system} {machine}")


def main() -> None:
    sidecar_dir = Path(__file__).parent
    tauri_binaries = sidecar_dir.parent / "src-tauri" / "binaries"
    tauri_binaries.mkdir(parents=True, exist_ok=True)

    triple = get_target_triple()
    binary_name = f"claudetini-sidecar-{triple}"
    if platform.system() == "Windows":
        binary_name += ".exe"

    print(f"Building sidecar for {triple}...")

    # Run PyInstaller
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(sidecar_dir / "claudetini-sidecar.spec"),
        ],
        cwd=str(sidecar_dir),
    )
    if result.returncode != 0:
        print("PyInstaller build failed!")
        sys.exit(1)

    # Copy binary to Tauri binaries directory
    dist_binary = sidecar_dir / "dist" / "claudetini-sidecar"
    if platform.system() == "Windows":
        dist_binary = dist_binary.with_suffix(".exe")

    dest = tauri_binaries / binary_name
    shutil.copy2(str(dist_binary), str(dest))
    print(f"Sidecar binary copied to {dest}")


if __name__ == "__main__":
    main()
