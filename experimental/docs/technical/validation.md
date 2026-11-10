# Experimental Validation

## Automated tests

Python:

```powershell
cd experimental
.venv\Scripts\python -m pytest tests -q
```

Covers config/schema, video metadata, voltage-platform detection, multi-drop
tracking, segment fitting, physics, downstream API, elementary estimation,
plots data, quality adapter, encoding, and version consistency.

Frontend:

```powershell
cd experimental\apps\desktop
npm test
npm run build
```

Encoding:

```powershell
cd experimental
.venv\Scripts\python scripts\check_text_encoding.py
```

The slow synthetic estimator harness is:

```powershell
.venv\Scripts\python scripts\validate_estimator_simulation.py
```

## Packaged acceptance in CI

CI builds the PyInstaller worker and the Electron app, then runs:

```powershell
# from experimental/ (bundled-config probe)
pwsh -NoProfile -File scripts\probe_packaged_worker.ps1

# from experimental/ (end-to-end)
.venv\Scripts\python scripts\probe_packaged_worker.py --worker apps\desktop\dist-worker\millikan-experimental-worker.exe

# from experimental/apps/desktop/ after electron-builder --win dir
node tests\electron-smoke.mjs
```

The end-to-end probe runs the packaged worker over
`../media/videos/2u.mp4` with a temporary fast config:
`video.inspect → analysis.run → analysis.loadRun → report.export`, then reloads
the same persistent run from a fresh worker process. It checks success payloads,
`run_manifest.json`, report/export files, and the persistent run path. It does
not check q or e accuracy.

`electron-smoke.mjs` launches the packaged application with Playwright, waits
for the analysis workspace, and calls `inspectVideo` through the real
preload/IPC path.

## Media

Smoke videos live in `../media/videos/`. Tests resolve them by walking up to the
repository `media/` folder or by setting `MILLIKAN_MEDIA_ROOT`.

`docs/raw_video_smoke.md` records historical outcomes. It is evidence of observed
behavior, not a numerical validation of the elementary charge.

## Scientific validation

Numerical validation uses synthetic fixtures with known truth and explicit
sample sizes, noise, and tolerances. Raw videos validate the software flow,
coordinates, playable evidence, and UI review only.
