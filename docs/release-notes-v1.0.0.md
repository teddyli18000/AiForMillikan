# Millikan AI 1.0

Millikan AI 1.0 is the first formal Windows release of the project's
human-in-the-loop Millikan oil-drop measurement workflow.

## Highlights

- A guided `Normal` workflow for balance-voltage plus `0 V` falling
  measurements.
- Drag-and-drop video import, second-based boundary adjustment, and
  letterbox-aware rectangular droplet selection.
- Project-local Trackpy single-droplet tracking with backend-rendered
  target, missing, trajectory, time, and pixel-coordinate evidence.
- On-demand crossing review that blocks acceptance until the experimenter
  confirms droplet identity.
- An inspectable single-drop calculation trace from fitted velocity to `q`
  and its currently included random uncertainty.
- Transient multi-video sessions with explicit record acceptance and export.
- A dedicated blind-inversion result page with candidate integer assignments,
  residual diagnostics, `e_hat`, `sigma_e`, and reference percentage error.
- UTF-8 worker transport, exports, source policy, and regression tests for
  Chinese text and scientific symbols.

## Basic use

1. Open `Millikan-AI-Portable-1.0.0.exe`.
2. Choose `Normal`.
3. Import a video and click the processing action.
4. Review and confirm the `0 V` boundaries.
5. Enter the balance voltage, confirm the balance condition, and rectangle
   select one droplet near the confirmed `0 V` start.
6. Review tracking and every crossing event.
7. Review the calculation and explicitly accept or reject the record.
8. Repeat until at least three records are accepted, then run the blind
   inversion.
9. Export the session when long-term retention is required.

## System requirements

- Windows 10 or Windows 11, 64-bit
- CPU-only execution; no CUDA runtime is required
- Sufficient free disk space for transient tracking and review artifacts

## Verification

The Release includes:

- `Millikan-AI-Portable-1.0.0.exe`
- `Millikan-AI-Portable-1.0.0.exe.sha256`

Verify the EXE against the checksum before running it. The executable is not
code-signed, so Windows SmartScreen may display an unrecognized-app warning.

## Scientific boundaries

- Balance is user-confirmed; the program does not automatically prove the
  droplet was stationary under the entered voltage.
- Normal 1.0 currently includes random uncertainty from the velocity fit.
  Other physical uncertainty sources are listed as not included.
- Three accepted records produce an exploratory inversion.
- No continuous baseline model is fitted, so the software does not claim that
  one model defeats another.
- Experimental mode remains an experimental multi-drop route and its quality
  adapter is not a trained ML model.

## Test video

The formal 1.0 Release does not include the test video. A dedicated test-video
Release will be linked from the root README after publication.
