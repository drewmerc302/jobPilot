#!/usr/bin/env python3
"""Cross-platform Typst binary fetcher.

Downloads platform-appropriate Typst releases into
``src/jobpilot/resources/typst/<platform>/``.

By default fetches every supported platform/arch (arm64 + x86_64 macOS,
linux x86_64, Windows x86_64). Use ``--current`` to fetch only the host
platform — useful for dev setup.

Usage:
    python scripts/fetch_typst.py [--version v0.14.2] [--current]
"""

from __future__ import annotations

import argparse
import io
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_VERSION = "v0.14.2"
RELEASE_BASE = "https://github.com/typst/typst/releases/download"

# (label, target dir, archive name, member basename)
TARGETS = [
    ("macOS arm64", "macos-arm64", "typst-aarch64-apple-darwin.tar.xz", "typst"),
    ("macOS x86_64", "macos-x86_64", "typst-x86_64-apple-darwin.tar.xz", "typst"),
    ("Linux x86_64", "linux", "typst-x86_64-unknown-linux-musl.tar.xz", "typst"),
    ("Windows x86_64", "windows", "typst-x86_64-pc-windows-msvc.zip", "typst.exe"),
]


def host_target() -> str:
    """Return the TARGETS entry id matching the current host."""
    sys_name = platform.system().lower()
    machine = platform.machine().lower()
    if sys_name == "darwin":
        if machine in ("arm64", "aarch64"):
            return "macos-arm64"
        return "macos-x86_64"
    if sys_name == "windows":
        return "windows"
    if sys_name == "linux":
        return "linux"
    raise RuntimeError(f"Unsupported host: {sys_name}/{machine}")


def fetch_one(
    version: str, label: str, outdir: Path, archive: str, member: str
) -> None:
    url = f"{RELEASE_BASE}/{version}/{archive}"
    outdir.mkdir(parents=True, exist_ok=True)
    print(f"-> {label}: {url}")
    with urllib.request.urlopen(url) as resp:
        data = resp.read()

    if archive.endswith(".tar.xz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tf:
            for m in tf.getmembers():
                if Path(m.name).name == member:
                    extracted = tf.extractfile(m)
                    if extracted is None:
                        continue
                    target = outdir / member
                    target.write_bytes(extracted.read())
                    target.chmod(0o755)
                    return
        raise RuntimeError(f"{member} not found in {archive}")

    if archive.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for name in zf.namelist():
                if Path(name).name == member:
                    target = outdir / member
                    with zf.open(name) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return
        raise RuntimeError(f"{member} not found in {archive}")

    raise RuntimeError(f"Unknown archive type: {archive}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=DEFAULT_VERSION, help="Typst release tag")
    parser.add_argument(
        "--current",
        action="store_true",
        help="Only fetch the binary for the current host platform",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    res = root / "src" / "jobpilot" / "resources" / "typst"

    selected = TARGETS
    if args.current:
        host = host_target()
        selected = [t for t in TARGETS if t[1] == host]

    for label, subdir, archive, member in selected:
        fetch_one(args.version, label, res / subdir, archive, member)

    print(f"Done. Binaries in: {res}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
