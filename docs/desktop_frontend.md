# Electron Desktop Frontend

The desktop app lives in `apps/desktop` and is designed for a Windows portable
Electron build. It renders the Millikan workflow directly in the UI: video
import, platform boundary editing, run progress, diagnostic overlays, validity
checks, elementary-charge inversion, uncertainty, charts, tables, and math
derivation. Backend files are still written under `runs/`, but reports are
displayed natively and exported only when the user chooses a destination.

## Product Modes

The desktop app has two intentionally separated modes.

- `Normal` is the main recommended workflow for the physics-themed experiment.
  It is a human-in-the-loop balance-voltage + `0 V` falling measurement route:
  users import or drag in a video, confirm the automatically suggested `0 V`
  start/end times in seconds, enter the balance voltage, select one droplet,
  review tracking and grid-crossing events, save q records in the current
  launch, and run blind elementary-charge inversion after at least three kept
  records. Every app start begins a fresh Normal measurement session; previous
  records are not auto-loaded.
- `Experimental` is the existing automatic multi-drop / multi-platform route.
  It remains available as an experimental half-finished workflow and should not
  share mutable state or backend business logic with Normal.

The startup page may reuse the visual idea of visible initialization progress
and mode selection. The button text must use `Normal` and `Experimental`.

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

The main process also owns the worker text boundary. Requests and responses are
UTF-8 JSON Lines. Worker launch sets `PYTHONUTF8=1` and
`PYTHONIOENCODING=utf-8`; stdout and stderr are decoded incrementally so a
Chinese character split across pipe chunks remains intact. Do not replace the
streaming decoder with per-chunk `String(buffer)` conversion.

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

For a formal release, verify the packaged worker directly with Chinese progress
and error payloads, then launch the portable EXE and inspect the Normal workflow
and exported Markdown. A successful source-level test alone is not sufficient.

## Documentation And Release Layout

Version 1.0 documentation is split by audience:

- `docs/technical/`: architecture, state/worker contracts, tracking geometry,
  UTF-8 packaging, and reproducible validation.
- `docs/academic/`: the balance-fall method, q calculation, uncertainty
  propagation, blind inversion, and scientific limitations.
- `docs/archive/`: superseded designs and historical research notes. These
  files remain evidence of the project history but are not current contracts.

The root English README is a product showcase and operation guide rather than a
copy of these implementation documents. Formal Windows releases include the
portable EXE, a SHA256 file, release notes, and an explicit unsigned-app
SmartScreen warning.

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

## Normal Development Notes

Normal-specific worker operations should use a `normal.*` prefix and talk to a
Normal backend module rather than the Experimental `analysis.*` flow. The
renderer should expose only seconds for user time editing, with coarse `±1 s`
and fine `±0.1 s` controls. Frame indices may still be stored in artifacts for
reproducibility.

Normal drag-and-drop is required, not a cosmetic target. Dropping a local video
must populate the real file path, inspect fps/frame count/resolution/duration,
and show the video in the preview area where later droplet selection happens.

Physical constants default from config. Balance voltage is required for each
measurement; plate distance, measurement distance, viscosity/temperature,
pressure, oil density, and Cunningham correction parameters belong in a
collapsed advanced panel. Advanced overrides apply only to the current Normal
measurement record unless the user explicitly saves them elsewhere.

Normal "return/adjust" must be a real adjustment workflow. Rejected,
diagnostic, and crossing-rejected records stay visible in the current session
with their boundary, target rectangle, selection time, voltage, parameter
overrides, q, fit, and crossing evidence. Selecting one for adjustment should
restore those inputs, let the user micro-adjust them, and create a new linked
record on retracking instead of mutating the old record.

Target selection time is constrained near the confirmed `0V_start_s`. The
renderer should display the allowed second-based range and clamp its controls to
that range. The worker must reject out-of-range `target_time_s` or
`target_frame` even if a frontend bug sends it.

The target-selection preview must be the main video player paused at the current
`selection_time_s`. The side panel may show controls and coordinates, but it
must not replace the video-frame preview with a detached screenshot. In Stage 3,
the selection-time input, `±1 s` / `±0.1 s` buttons, scrubber, visible frame,
and submitted backend `target_frame` must refer to the same frame.

Returning from target/review/results to `0V` must show the user's previous
confirmed boundary for that measurement. It must not restore the original
automatic suggestion after the user has already confirmed a different boundary.

Crossing review uses a renderer-owned frame player over backend-generated
review frames. The player must show a real current frame, play/pause state,
looping progress, and current time. A generated MP4 may be exported or kept as
an artifact, but the UI must not present an unplayable black video control as
valid review evidence.

After a q record is accepted, the results panel should offer "下一颗油滴".
The confirmation dialog has two routes and both must call the backend before
changing stage. Same video returns to target selection only after the worker has
reset `active_video.state` to `boundary_confirmed` with the current video,
metadata, grid, boundary, voltage, and parameters available while clearing the
current target/tracking/review draft. Different video clears backend
`active_video` and returns to the empty import panel while keeping accepted q
records in the current session for blind inversion.

The review/results main media should prefer backend-generated full-frame track
review frames over MP4 overlay playback. The frame player should expose
play/pause, scrubber, current time/frame, and show the original video frame with
backend-drawn target/missing labels, trajectory, and pixel axes. The renderer
must not draw a separate trajectory overlay on top of a scaled video.

The session record list must be readable at narrow inspector widths. Long
record IDs, q values, and status labels should occupy separate lines or columns
that cannot overlap.

After at least three accepted q records, clicking "运行 Normal 盲反演" must
open a dedicated Normal inversion result stage rather than leaving the user on
the per-drop results panel. This stage should make the final estimate visually
obvious (`e_hat_C`, `sigma_e_C`, status, flags, used q count) and then show the
evidence that produced it: candidate solutions, integer assignments, residuals,
and quantized-alignment charts. The page should feel like a scientific result
dashboard: information-dense but readable, with restrained controls and no
model-victory wording until a real continuous baseline exists.

The Stage 6 main area is the canonical result summary. It shows the elementary
charge estimate, uncertainty, relative uncertainty, percentage error versus the
exact SI defining constant, used-q count, and weighted residual evidence. The
right inspector must not repeat the same e/sigma result card; it is reserved for
convergence, boundary hits, flags, scientific limitations, export, rerun, and
navigation.

At Stage 5, the space below the full-track review should show the calculation
path from user-confirmed balance voltage and 0 V interval through trajectory
fit, velocity, Cunningham-corrected radius, effective viscosity, q, and
sigma_q. Formulas should be rendered as structured mathematical typography,
not raw code strings. Values come from the backend record calculation trace;
the frontend does not recalculate the physics.

All scientific numbers visible to a person use shared formatting. Prefer
`a × 10ⁿ` with superscript exponents, and display charge quantities on the
`10⁻¹⁹ C` scale. Raw `1.23e-19` notation is not acceptable in UI text, chart
labels, tables, tooltips, or exported Markdown.
