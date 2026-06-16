#!/usr/bin/env bash
# Replace tls_client's macOS arm64 dylib with a build that loads on modern macOS.
#
# Why: the tls_client 1.0.1 wheel (pulled in by python-jobspy) bundles an old
# Go-compiled tls-client-arm64.dylib. macOS 15+ / Darwin 24+ dyld rejects it
# with "chained fixups, seg_count does not match number of segments", so
# `from jobspy import scrape_jobs` fails and the jobspy aggregator dies. The
# Python FFI surface is unchanged across bogdanfinn/tls-client versions, so we
# drop in the matching native lib from a recent upstream release and ad-hoc sign
# it. (A later `briefcase package` re-signs it with the Developer ID.)
#
# Fetched at build time, not checked into git (~11 MB).
#
# Usage: ./scripts/fetch_tls_client.sh [target_dependencies_dir] [version]
#   target_dependencies_dir defaults to the built app's tls_client/dependencies
#   version defaults to 1.15.1

set -euo pipefail

VERSION="${2:-1.15.1}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEFAULT_DIR="$ROOT/build/jobpilot/macos/app/jobPilot.app/Contents/Resources/app_packages/tls_client/dependencies"
TARGET_DIR="${1:-$DEFAULT_DIR}"
DYLIB="$TARGET_DIR/tls-client-arm64.dylib"
URL="https://github.com/bogdanfinn/tls-client/releases/download/v${VERSION}/tls-client-darwin-arm64-${VERSION}.dylib"

if [ ! -d "$TARGET_DIR" ]; then
    echo "ERROR: tls_client dependencies dir not found: $TARGET_DIR" >&2
    echo "       (build the app first, or pass the dir explicitly)" >&2
    exit 1
fi

echo "→ Fetching tls-client v${VERSION} (darwin arm64)"
tmp="$(mktemp)"
curl -fsSL -o "$tmp" "$URL"

# Sanity: must be a Mach-O arm64 dylib, not an HTML error page.
ftype="$(file "$tmp")"
if [[ "$ftype" != *"Mach-O 64-bit dynamically linked shared library arm64"* ]]; then
    echo "ERROR: downloaded file is not a Mach-O arm64 dylib: $ftype" >&2
    rm -f "$tmp"
    exit 1
fi

mv "$tmp" "$DYLIB"
codesign --force --sign - "$DYLIB"
echo "Patched + ad-hoc signed: $DYLIB"
