# Screenshot Shot List

Take each screenshot at ~1440px wide browser window for consistent sizing.
Save as PNG into this `screenshots/` folder with the exact filename shown.

| File | URL / State | Notes |
|------|-------------|-------|
| `01-wizard-welcome.png` | `/wizard/step/0` | Welcome card, before clicking anything |
| `02-wizard-upload.png` | `/wizard/step/1` | With a file selected (green filename visible) |
| `03-wizard-confirm.png` | `/wizard/step/2` | Fully populated with your real data |
| `04-wizard-search.png` | `/wizard/step/3` | With location, keywords, and a few target companies filled in |
| `05-first-run.png` | `/wizard/step/4` | Progress spinner mid-run |
| `06-matches-list.png` | `/matches` | A full list of results with scores visible |
| `07-job-detail.png` | Any job detail page | With full description visible, before clicking Generate |
| `08-tailor-modal.png` | Same job, tailor modal open | With analysis results showing (key requirements + suggested edits) |
| `09-resume-editor.png` | `/profile` | Scrolled to show Contact + Summary + Skills sections |
| `10-settings.png` | `/settings` | With API keys redacted / blurred |

## Adding screenshots to the PDF

Once screenshots are in the `screenshots/` folder, open `user_guide.typ` and
replace each `placeholder("XX-name.png")` call with:

```typst
image("screenshots/XX-name.png", width: 100%)
```

Then rebuild:

```bash
cd docs/user_guide
typst compile user_guide.typ user_guide.pdf
```
