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

## Scientific validation is separate

A real video does not validate the numerical accuracy of the elementary charge.
Numerical validation uses fixtures with known truth, stated sample sizes, noise,
and tolerances.

Three accepted q records produce an exploratory inversion. Without a fitted
continuous baseline the app must not report a quantized model winner.
