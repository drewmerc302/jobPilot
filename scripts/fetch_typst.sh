#!/usr/bin/env bash
# Download Typst binaries into src/jobpilot/resources/typst/{macos,linux,windows}/
# These are vendored at build time, not checked into git, since each is ~40 MB.
#
# Usage: ./scripts/fetch_typst.sh [version]
#   version defaults to v0.14.2

set -euo pipefail

VERSION="${1:-v0.14.2}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$ROOT/src/jobpilot/resources/typst"

fetch() {
    local arch="$1" outdir="$2" archive_name="$3" extract_pattern="$4"
    local archive_url="https://github.com/typst/typst/releases/download/${VERSION}/${archive_name}"
    local target_dir="$RES/$outdir"

    mkdir -p "$target_dir"
    echo "→ $arch: $archive_url"
    local tmp
    tmp="$(mktemp -d)"
    curl -sL -o "$tmp/archive" "$archive_url"

    case "$archive_name" in
        *.tar.xz) tar -xJf "$tmp/archive" -C "$tmp" ;;
        *.zip)    unzip -q "$tmp/archive" -d "$tmp" ;;
    esac

    cp "$tmp"/$extract_pattern "$target_dir/"
    chmod +x "$target_dir/typst" 2>/dev/null || true
    rm -rf "$tmp"
}

fetch "macOS arm64" "macos"   "typst-aarch64-apple-darwin.tar.xz"   "typst-aarch64-apple-darwin/typst"
fetch "Linux x64"   "linux"   "typst-x86_64-unknown-linux-musl.tar.xz" "typst-x86_64-unknown-linux-musl/typst"
fetch "Windows x64" "windows" "typst-x86_64-pc-windows-msvc.zip"    "typst-x86_64-pc-windows-msvc/typst.exe"

echo "Done. Binaries in: $RES"
