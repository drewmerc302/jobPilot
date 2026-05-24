# Installing jobPilot on macOS

You received a `.dmg` file containing jobPilot. This guide covers installation, daily use, and upgrades.

---

## Install

1. **Open the `.dmg`** — double-click the file. A Finder window appears with the jobPilot app icon.
2. **Drag jobPilot to Applications** — drag the `jobPilot.app` icon into your `Applications` folder (or the alias shown in the window).
3. **Eject the DMG** — right-click the mounted volume in Finder's sidebar and choose Eject, or drag it to the Trash.

### First launch

The app is signed and notarized with Apple — it should open without any warnings. If macOS asks "Are you sure you want to open it?", click **Open**. This only happens the first time.

---

## Running jobPilot

- **Launch:** Double-click `jobPilot` in Applications (or Spotlight → type "jobPilot").
- **What happens:** Your default browser opens to `http://127.0.0.1:8765`. That's the app — everything runs locally on your machine.
- **If port 8765 is busy:** jobPilot automatically picks the next available port and opens the browser to it. No action needed.

### First-run setup

The first time you open jobPilot in the browser, a setup wizard walks you through:

1. Uploading your resume (PDF or DOCX)
2. Setting your job search preferences

---

## Stopping jobPilot

In the browser, go to **Settings** → scroll to the bottom → click **Quit**.

The page will confirm jobPilot has stopped. You can close the browser tab.

There is also a blue circle (●) in the menu bar you can click → **Quit**, but it may be hidden if your menu bar is crowded.

---

## Upgrading

When you receive a new `.dmg`:

1. **Quit the running instance first** — Settings → Quit (bottom of page).
2. Open the new `.dmg`.
3. Drag `jobPilot.app` to Applications. Finder will ask _"An item named jobPilot already exists. Do you want to replace it?"_ → click **Replace**.
4. Eject the DMG.
5. Launch jobPilot from Applications.

Your data (resume, settings, match history) is stored in `~/.jobpilot/`, separate from the app — upgrades never touch it.

### What if I forget to quit the old version first?

Finder will show: _"The operation can't be completed because the item 'jobPilot.app' is in use."_

**Fix:** Go back to the browser tab and use **Settings → Quit**. Then drag the new app to Applications and replace.

If the browser tab is closed, open **Activity Monitor** (Spotlight → type "Activity Monitor"), search for "jobPilot", select it, and click the ✕ stop button. Then retry the install.

---

## Uninstalling

1. Quit jobPilot (Settings → Quit).
2. Drag `jobPilot.app` from Applications to the Trash.
3. To also remove your data: delete `~/.jobpilot/` — open Terminal and run:

   ```
   rm -rf ~/.jobpilot
   ```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "The item 'jobPilot.app' is in use" | Quit via Settings → Quit in the browser, or open Activity Monitor and stop "jobPilot". Then retry. |
| Browser opens but page won't load | Wait a few seconds — the server needs a moment to start. Refresh the page. |
| "This site can't be reached" | jobPilot may not be running. Relaunch from Applications. |
| Port conflict after upgrade | Quit the old instance (Settings → Quit), then relaunch. |
| Gatekeeper blocks every launch | Run once in Terminal: `xattr -cr /Applications/jobPilot.app` then relaunch. |
