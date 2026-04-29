"""jobPilot — Briefcase packaging spike.

Runs a local FastAPI server and opens the user's default browser.
Used to validate that a Briefcase .app bundle can:
  1. Launch a Python webserver
  2. Bundle a non-Python binary (Typst) and shell out to it
"""

import platform
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse

PORT = 8765
RESOURCES_DIR = Path(__file__).parent / "resources"

api = FastAPI(title="jobPilot")


def _typst_binary() -> Path:
    """Locate the bundled Typst binary for the current OS."""
    system = platform.system().lower()
    if system == "darwin":
        return RESOURCES_DIR / "typst" / "macos" / "typst"
    if system == "windows":
        return RESOURCES_DIR / "typst" / "windows" / "typst.exe"
    return RESOURCES_DIR / "typst" / "linux" / "typst"


@api.get("/", response_class=HTMLResponse)
def root() -> str:
    typst_bin = _typst_binary()
    typst_status = "found" if typst_bin.exists() else f"MISSING at {typst_bin}"
    return f"""<!doctype html>
<html><head><title>jobPilot spike</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 640px; margin: 60px auto; padding: 0 20px; color: #1a1a1a; }}
  h1 {{ color: #0d6efd; }}
  code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 0.9em; }}
  .ok {{ color: #198754; }} .bad {{ color: #dc3545; }}
</style></head>
<body>
<h1>jobPilot is running</h1>
<p>Briefcase packaging spike — confirms FastAPI works inside a bundled .app.</p>
<ul>
  <li>Python: <code>{sys.version.split()[0]}</code></li>
  <li>Resources dir: <code>{RESOURCES_DIR}</code></li>
  <li>Resources exists: <span class="{"ok" if RESOURCES_DIR.exists() else "bad"}">{RESOURCES_DIR.exists()}</span></li>
  <li>Typst binary: <code>{typst_bin}</code> — <span class="{"ok" if typst_bin.exists() else "bad"}">{typst_status}</span></li>
</ul>
<p><a href="/typst-test">Render bundled hello.typ → PDF</a></p>
</body></html>"""


@api.get("/typst-test")
def typst_test() -> FileResponse:
    typst_bin = _typst_binary()
    sample_typ = RESOURCES_DIR / "hello.typ"
    out_pdf = Path.home() / "Downloads" / "jobpilot-hello.pdf"
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(typst_bin), "compile", str(sample_typ), str(out_pdf)],
        check=True,
        capture_output=True,
    )
    return FileResponse(
        out_pdf, media_type="application/pdf", filename="jobpilot-hello.pdf"
    )


def _serve() -> None:
    uvicorn.run(api, host="127.0.0.1", port=PORT, log_level="warning")


def main() -> None:
    threading.Thread(target=_serve, daemon=True).start()
    time.sleep(0.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
