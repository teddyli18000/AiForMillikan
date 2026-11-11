# Normal Validation

## Automated tests

Python:

```powershell
cd normal
.venv\Scripts\python -m pytest tests -q
```

Covers grid detection, boundary seconds semantics, selection window, target
frame, local tracking, crossing blocking, q calculation, uncertainty
propagation, Normal inversion, session state, and version consistency.

Frontend:

```powershell
cd normal\apps\desktop
npm test
npm run build
```

Covers direct Normal entry, second-based player controls, selection geometry,
return/adjust, next droplet, crossing player, q trace, inversion page, and
scientific notation.

`tests/ipcRouting.test.ts` checks that all twelve `normal:<operation>` Electron
channels map to the matching `normal.<operation>` worker names, including
progress forwarding and export-folder handling. It mocks Electron and the
worker client; the packaged smoke below exercises the real path.

Encoding:

```powershell
cd normal
.venv\Scripts\python scripts\check_text_encoding.py
```

## Manual acceptance path

```text
import → preview → start → 0 V boundary → target box → tracking
→ crossing / trajectory review → q → accept
→ session accumulation → blind inversion → export
```

Use a real recording for flow, coordinates, playable evidence, and UI review.
Use a synthetic crossing video when the real recording has no crossing event.

## Packaged acceptance in CI

CI builds the PyInstaller worker and the Electron app, then runs:

```powershell
# from normal/
.venv\Scripts\python scripts\probe_packaged_worker.py --worker apps\desktop\dist-worker\millikan-normal-worker.exe

# from normal/apps/desktop/ after electron-builder --win dir
node tests\electron-smoke.mjs
```

`probe_packaged_worker.py` generates a deterministic synthetic video and drives
the packaged worker through initialize, prepare, boundary, target, measurement,
crossing review, acceptance, inversion, and export. It checks response contracts
and exported files, not physical accuracy.

`electron-smoke.mjs` launches the packaged application with Playwright and
calls all twelve operations through the real preload, Electron handlers, and
packaged worker. It uses a generated synthetic video to review crossings, keep
three records, exclude a record, check same-video continuation and clearing the
active video while keeping records, run inversion, and export. Electron's native
file and folder dialogs are stubbed. The smoke checks the Chinese report,
inversion JSON, and export manifest; it does not measure physical accuracy.

The smoke uses an explicit temporary session root and export folder, which it
removes afterward; it does not exercise cleanup of implicit app sessions.

## Scientific validation is separate

A real video does not validate the numerical accuracy of the elementary charge.
Numerical validation uses fixtures with known truth, stated sample sizes, noise,
and tolerances.

Three accepted q records produce an exploratory inversion. Without a fitted
continuous baseline the app must not report a quantized model winner.
