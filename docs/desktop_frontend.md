# Electron Desktop Frontend

The desktop app lives in `apps/desktop` and is designed for a Windows portable
Electron build. It renders the Millikan workflow directly in the UI: video
import, platform boundary editing, run progress, diagnostic overlays, validity
checks, elementary-charge inversion, uncertainty, charts, tables, and math
derivation. Backend files are still written under `runs/`, but reports are
displayed natively and exported only when the user chooses a destination.

## Development

Install Node dependencies locally inside the app folder:

```powershell
cd apps\desktop
npm install
```

Run the renderer dev server:

```powershell
npm run dev
```

Run Electron against the Vite server:

```powershell
$env:ELECTRON_RENDERER_URL='http://127.0.0.1:5173'
npx electron dist-electron\main.js
```

In development the main process starts the project-local Python worker from
`.venv\Scripts\python` and sets `PYTHONPATH` to the repository `src` directory.
No global Python installation is required by the app logic.

## Build And Package

Build renderer and Electron TypeScript:

```powershell
npm run build
```

Build the bundled backend worker:

```powershell
npm run worker:build
```

Create the Windows portable artifact:

```powershell
npm run package
```

`worker:build` uses PyInstaller from the project `.venv` and writes a onefile
`dist-worker\millikan-desktop-worker.exe`. `electron-builder` copies that file
into the portable app resources under `worker\`.

## Test Commands

Backend regression:

```powershell
.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
```

Desktop worker tests:

```powershell
.venv\Scripts\python -m pytest tests\test_desktop_worker.py -q --basetemp runs\pytest_tmp_frontend_worker -o cache_dir=runs\pytest_cache_frontend_worker
```

Renderer tests:

```powershell
cd apps\desktop
npm test
```

The UI must keep voltage OCR disabled on mainline. Automatic platform detection
only suggests frame boundaries; voltage values are user-supplied. The final
scientific success badge must use `fundamental_spacing_identified`, not the
legacy bounded-fit `valid` field.

## Normal Mode UX

Normal mode is the default desktop route for formal single-drop measurement. It
uses an embedded annotation workspace: video preview, target droplet box/point,
suggested fall-window markers, second-based start/end nudge controls, tracking
status overlay, q record basket, and a blind-inversion switch.

The UI should keep the workflow dynamic. Users add q records one at a time from
one or more videos; the app must not require an up-front video count. Before
final report/export, show the count of selected q records that are actually
usable for blind inversion.

Formula presentation must be readable math, not raw code identifiers. Prefer
code-native SVG/math components; locally rendered LaTeX images are acceptable
when they have been visually checked.
