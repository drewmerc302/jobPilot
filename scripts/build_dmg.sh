#!/usr/bin/env bash
#
# build_dmg.sh — Reproducible signed+notarized macOS DMG build
#
# Usage:
#   ./scripts/build_dmg.sh
#
# Prerequisites:
#   - Briefcase installed (uv tool install briefcase)
#   - "Developer ID Application: Andrew Mercurio (9247884EWA)" cert in Keychain
#   - Notarization credentials stored: xcrun notarytool store-credentials "notarytool" ...
#   - Dev venv bootstrapped: briefcase dev (run once to create .briefcase/jobpilot/dev.*)
#
# Why the jobspy patch:
#   python-jobspy >=1.1.75 pins NUMPY==1.26.3 which has no cp313 binary wheel.
#   Briefcase macOS enforces --only-binary :all:, so pip can't build numpy from source.
#   The dev venv (briefcase dev) CAN build from source, so we let Briefcase install
#   the old jobspy 1.1.13 (which resolves), then swap in the working 1.1.82 from
#   the dev venv. This is the only known workaround until python-jobspy relaxes
#   its numpy pin or numpy 1.26.3 ships cp313 wheels.
#
# Why the tls_client dylib fix (Step 3b):
#   tls_client 1.0.1 (pulled in by jobspy) bundles an old Go-built
#   tls-client-arm64.dylib that macOS 15+/Darwin 24+ dyld rejects ("chained
#   fixups, seg_count does not match"), breaking `from jobspy import scrape_jobs`.
#   fetch_tls_client.sh drops in a modern upstream build and signs it.
#
set -euo pipefail

IDENTITY="Developer ID Application: Andrew Mercurio (9247884EWA)"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

DEV_SITE_PACKAGES="$(find .briefcase/jobpilot/dev.cpython-*-darwin/lib -maxdepth 2 -name site-packages -type d | head -1)"
APP_PACKAGES="build/jobpilot/macos/app/jobPilot.app/Contents/Resources/app_packages"

if [ -z "$DEV_SITE_PACKAGES" ]; then
    echo "ERROR: Dev venv not found. Run 'briefcase dev' once first to bootstrap it."
    exit 1
fi

# Verify dev venv has the right jobspy
if ! "$DEV_SITE_PACKAGES/../../../bin/python3" -c "from jobspy import scrape_jobs" 2>/dev/null; then
    echo "Installing python-jobspy into dev venv..."
    "$DEV_SITE_PACKAGES/../../../bin/pip" install python-jobspy
fi

echo "=== Step 1: Create/update build ==="
if [ -d "build/jobpilot/macos/app" ]; then
    briefcase update macOS
else
    echo "y" | briefcase create macOS
fi

echo "=== Step 2: Build (ad-hoc sign stub) ==="
briefcase build macOS

echo "=== Step 3: Patch jobspy (swap 1.1.13 → dev venv version) ==="
# Remove old versions installed by Briefcase
for pkg in jobspy tls_client; do
    if [ -d "$APP_PACKAGES/$pkg" ]; then
        rm -rf "$APP_PACKAGES/$pkg"
    fi
done

# Copy working versions from dev venv
for pkg in jobspy tls_client markdownify regex; do
    if [ -d "$DEV_SITE_PACKAGES/$pkg" ]; then
        cp -r "$DEV_SITE_PACKAGES/$pkg" "$APP_PACKAGES/"
    fi
done
echo "Patched jobspy + deps from dev venv"

echo "=== Step 3b: Fix tls_client arm64 dylib (modern-dyld build) ==="
"$PROJECT_DIR/scripts/fetch_tls_client.sh" "$APP_PACKAGES/tls_client/dependencies"

echo "=== Step 4: Package (sign + notarize + staple) ==="
briefcase package macOS -i "$IDENTITY" -p dmg

echo ""
echo "=== Done ==="
ls -lh dist/jobPilot-*.dmg | tail -1
