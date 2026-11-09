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

## Media

Smoke videos live in `../media/videos/`. Tests resolve them by walking up to the
repository `media/` folder or by setting `MILLIKAN_MEDIA_ROOT`.

`docs/raw_video_smoke.md` records historical outcomes. It is evidence of observed
behavior, not a numerical validation of the elementary charge.

## Scientific validation

Numerical validation uses synthetic fixtures with known truth and explicit
sample sizes, noise, and tolerances. Raw videos validate the software flow,
coordinates, playable evidence, and UI review only.
