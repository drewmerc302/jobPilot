# Building jobPilot for Windows

Briefcase Windows builds must run on a Windows host — cross-compilation from macOS is not supported. This guide covers three paths when you don't have a Windows machine at hand.

---

## Quick reference

| Path | Cost | Setup time | Best for |
|------|------|-----------|---------|
| [GitHub Actions](#option-a-github-actions-recommended) | Free (public repo) / included minutes (private) | ~15 min | Recurring builds, CI |
| [Free Microsoft VM](#option-b-free-windows-11-developer-vm) | Free (90-day eval) | ~30 min | Local iteration |
| [Cloud VM](#option-c-cloud-vm) | ~$0.05/hr (EC2 t3.medium) | ~10 min | Ad-hoc one-off |

---

## Option A: GitHub Actions (Recommended)

The `windows-latest` runner is Windows Server 2022 with Python, Visual Studio, and WiX Toolset pre-installed — everything Briefcase needs.

### 1. Create the workflow file

Create `.github/workflows/build-windows.yml`:

```yaml
name: Build Windows installer

on:
  workflow_dispatch:        # run manually from the Actions tab
  push:
    tags:
      - "v*"               # or trigger on version tags

jobs:
  build-windows:
    runs-on: windows-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Briefcase
        run: pip install briefcase

      - name: Create app bundle
        run: briefcase create windows

      - name: Build
        run: briefcase build windows

      - name: Package (MSI)
        run: briefcase package windows

      - name: Upload installer artifact
        uses: actions/upload-artifact@v4
        with:
          name: jobpilot-windows-installer
          path: dist\*.msi
          retention-days: 30
```

### 2. Trigger the build

1. Push the workflow file to GitHub: `git add .github && git commit -m "ci: add Windows build workflow" && git push`
2. Go to **Actions → Build Windows installer → Run workflow**
3. Wait ~8–12 minutes for the build to complete
4. Download the `.msi` from the **Artifacts** section of the run

### 3. Optional: publish to GitHub Releases automatically

Replace the upload step with:

```yaml
      - name: Create GitHub Release
        if: startsWith(github.ref, 'refs/tags/')
        uses: softprops/action-gh-release@v2
        with:
          files: dist\*.msi
          draft: true
```

Then tag a release with `git tag v0.1.0 && git push --tags` and the MSI will appear as a draft release asset.

---

## Option B: Free Windows 11 Developer VM

Microsoft distributes free 90-day evaluation VMs for exactly this purpose.

### 1. Download the VM image

Go to <https://developer.microsoft.com/windows/downloads/virtual-machines/> and download the **VMware** or **VirtualBox** image (whichever you have, or install VirtualBox free).

The image includes Windows 11 Enterprise with a dev toolchain already installed.

### 2. Set up the VM

1. Import the `.ova` or `.zip` into VirtualBox / VMware
2. Boot the VM — it logs in automatically as the dev user
3. Open **PowerShell** (right-click Start → Terminal)

### 3. Install prerequisites

```powershell
# Install Python 3.12 via winget (pre-installed on the dev VM)
winget install --id Python.Python.3.12 --source winget

# Reload PATH
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# Install Briefcase
pip install briefcase
```

### 4. Get the source code

Option A — clone from GitHub:
```powershell
git clone https://github.com/<your-username>/jobPilot.git
cd jobPilot
```

Option B — copy from your Mac via a shared folder (VirtualBox: Devices → Shared Folders).

### 5. Build

```powershell
briefcase create windows
briefcase build windows
briefcase package windows
```

The `.msi` appears in `dist\`.

---

## Option C: Cloud VM

Spin up a Windows Server instance on AWS, Azure, or GCP for a one-off build (~$0.05–$0.10 total cost for a 1-hour session).

### AWS EC2 quickstart

```bash
# Launch a Windows Server 2022 t3.medium instance via the console or CLI
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-windows-latest/Windows_Server-2022-English-Full-Base \
  --instance-type t3.medium \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxxxxx   # allow RDP port 3389

# Get the password
aws ec2 get-password-data --instance-id i-xxx --priv-launch-key your-key.pem
```

RDP in, then follow the same steps as Option B from "Install prerequisites" onward.

**Remember to terminate the instance when done** — `aws ec2 terminate-instances --instance-ids i-xxx`.

---

## What the build produces

```
dist/
  jobPilot-0.0.1.msi      ← the installer
```

The MSI:
- Installs to `C:\Users\<user>\AppData\Local\jobPilot\`
- Creates a Start menu shortcut
- Adds an entry to Add/Remove Programs
- Bundles a self-contained Python interpreter (no system Python required)

App data (SQLite DB, profile, config) lives in `%APPDATA%\jobPilot\` — it survives uninstall/reinstall.

---

## SmartScreen warning

Because the binary is unsigned, Windows Defender SmartScreen will block it on first run with: **"Windows protected your PC"**.

Tell your users:

1. Click **"More info"** (below the warning text)
2. Click **"Run anyway"**
3. Windows remembers the choice — the warning won't appear again for this file

This is a one-time friction. To eliminate it entirely see [Code Signing](#code-signing-optional) below.

---

## Distributing the MSI

**Simplest:** email or share the `.msi` directly. It's a single file.

**Via GitHub Releases:**

1. Create a release on GitHub (tag `v0.1.0`, draft)
2. Drag the `.msi` into the assets
3. Publish — users download via a stable URL like:
   `https://github.com/<you>/jobPilot/releases/latest/download/jobPilot-0.0.1.msi`

**Via a direct-download link:** host the `.msi` on any file host (Dropbox, S3, Google Drive). The SmartScreen warning is the same regardless of where the file comes from.

---

## Updating the version

The version in `pyproject.toml` (`version = "0.0.1"`) is embedded in the MSI name and installer metadata. Bump it before packaging:

```toml
[tool.briefcase]
version = "0.2.0"
```

---

## Code signing (optional)

Code signing eliminates the SmartScreen warning entirely and is required if you ever distribute through corporate channels.

| Option | Cost | Notes |
|--------|------|-------|
| Self-signed cert | Free | Removes the "unknown publisher" text but SmartScreen still warns |
| OV (Organization Validation) code-signing cert | ~$70–$200/yr | Removes SmartScreen after sufficient reputation builds (~hundreds of installs) |
| EV (Extended Validation) cert | ~$300–$500/yr | Instant SmartScreen trust from first install |

To wire up signing in Briefcase, add to `[tool.briefcase.app.jobpilot.windows]`:

```toml
[tool.briefcase.app.jobpilot.windows]
certificate = "path/to/cert.pfx"
```

Or pass `--identity` on the command line:

```powershell
briefcase package windows --identity "CN=Your Name"
```

For a personal tool shared with a small group, unsigned is entirely fine.

---

## Troubleshooting

**`pywin32` import error at runtime**
Briefcase installs `pywin32` but it requires a post-install script to register DLLs. If the tray icon fails to appear, add to the workflow or build script:

```powershell
python -c "import win32con"   # smoke test
# If this fails:
python Scripts/pywin32_postinstall.py -install
```

**`ModuleNotFoundError: No module named 'jobspy'`**
`python-jobspy` pulls in Playwright on some platforms. If the build fails during `briefcase create`, pin to a version without the Playwright dependency or add Playwright to the build environment:

```powershell
pip install playwright
playwright install chromium
```

**WiX Toolset not found**
`windows-latest` GitHub Actions runners include WiX 3.x. If building on a local VM and WiX is missing:

```powershell
winget install WiXToolset.WiXToolset
```

**Build succeeds but app doesn't start**
Run from a PowerShell window to see the startup traceback:

```powershell
& "$env:LOCALAPPDATA\jobPilot\jobpilot.exe"
```
