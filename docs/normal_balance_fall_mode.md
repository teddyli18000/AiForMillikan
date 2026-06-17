# Normal Balance-Fall Mode

This document records the implementation contract for the normal single-drop
workflow. It is intentionally separate from the existing Experimental
multi-platform pipeline.

## User Flow

Normal mode is the default entry path for formal measurement:

1. Select or drag in one experiment video.
2. Enter the balance voltage `U_balance`.
3. Mark the target droplet directly in the video workspace.
4. Let the backend suggest the `U_balance -> 0 V` fall window from voltage-display
   change events.
5. Review start/end times with second-based controls. The user never has to type
   frame numbers.
6. Track the marked droplet through the fall window and show `tracking`,
   `missing`, and `reacquired` states in the overlay.
7. Compute one q record from measured tracking points only.
8. Save that q record into a session basket and choose whether it is included in
   blind inversion.
9. Repeat with more videos or another droplet when useful. The app must not ask
   for the number of videos up front.

Before showing or exporting a final report, the UI must state how many selected
q records are usable for blind inversion. Blind inversion is enabled only when at
least three selected records have finite positive q and uncertainty.

## Mode Isolation

Normal mode owns independent request state, output semantics, report sections,
and frontend panels. It may reuse the app shell, file dialogs, shared formatting,
and elementary-charge display components, but it must not call the existing
Experimental tracker, segment fitter, q pipeline, or quality adapter.

Experimental mode keeps the existing backend and output contract. Improvements
to voltage-display change grouping may be shared at the boundary suggestion
layer, but not by rewriting Experimental tracking or q computation.

## Video Annotation Workspace

The desktop UI should use an embedded annotation workspace instead of a separate
system dialog by default. The normal-mode workspace contains:

- video preview with stable aspect ratio;
- draggable target box or click target marker;
- suggested fall-start and fall-end markers;
- second-based nudges such as `-1 s`, `-0.1 s`, `+0.1 s`, and `+1 s`;
- an explicit "usable q records" count;
- a compact q basket with include/exclude controls;
- a cross-grid review entry that can loop a short local clip around
  missing/reacquired events.

The overlay styling must distinguish:

- `tracking`: real detected point used for fitting when inside the accepted
  calculation interval;
- `missing`: prediction-only point, shown for continuity but excluded from
  velocity fitting;
- `reacquired`: the first real detection after one or more missing frames;
- `fit_interval`: the final interval used for velocity, radius, q, and
  uncertainty.

The calculation interval must end no later than the last real detected tracking
point before the penultimate horizontal grid line. The tracker may continue for
visual review after this point, but those points are not eligible q endpoints.

## Backend Contract

Normal mode introduces a normal-result bundle with `mode="normal_balance_fall"`.
The bundle should include:

- video metadata;
- balance voltage and uncertainty provenance;
- user target box/point;
- voltage-change event suggestions;
- confirmed fall-start and fall-end times;
- grid calibration and the second/penultimate horizontal line pair;
- per-point tracking rows with `status`, `detected`, prediction coordinates, and
  source frame/time;
- missing/reacquired event summaries;
- final fit interval;
- velocity fit diagnostics;
- radius, q, random/systematic/total uncertainty, and 95 percent intervals;
- one q record suitable for the frontend basket;
- optional normal and Experimental blind-inversion outputs when the selected q
  basket has at least three usable records.

Recommended worker operations:

- `normal.suggestWindow`: inspect the video and suggest the balance-to-fall
  window without running tracking.
- `normal.runSingleDrop`: run single-drop tracking and q computation from a
  video path, balance voltage, target point/box, and reviewed fall window.
- `normal.estimateElementary`: run both blind inversion algorithms on selected
  q records.

`normal.runSingleDrop` must write an isolated run directory so normal-mode
artifacts do not overwrite Experimental artifacts.

## Voltage Event Grouping

Normal mode detects display-change operations, not exact voltage OCR values.
Short consecutive changes such as `0 V -> 235 V -> 240 V` are merged into one
recovery operation. The first stable section after `U_balance -> 0 V` becomes the
suggested fall start. If recovery exists, the first frame that starts leaving
0 V becomes the suggested fall end. If no recovery exists, the suggested end is
the last reliable detected tracking point.

The expected platform count is not a normal-mode input. A normal-mode video
contains at most one fall measurement window for one selected droplet; users add
more q records dynamically by analyzing more clips or repeated droplets.

## Tracking Rules

Normal mode adapts the teammate single-drop local Trackpy tracker. The required
bug fix is:

```text
velocity = (current_detected_position - last_detected_position) / frame_gap
```

`frame_gap` is the number of source frames between real detections. Prediction
may bridge missing frames, but prediction-only rows never enter velocity fitting.

The tracker may expand search radius and memory conservatively with current
velocity and missing count, bounded by config values. Do not introduce a new
global MOT, Hungarian assignment, or ML tracker in normal mode.

## Formula Rendering

Frontend formulas must not be shown as raw programming identifiers such as
`a_i`, `q_i`, or `e_hat`. The desktop UI should render formulas as readable math
using inline SVG/math components or pre-rendered LaTeX assets. Machine fields
may keep identifier names; user-facing math should use symbols such as
`t = k / f_s`, `y(t) = y_0 + v_g t`, `q_i = n_i e + epsilon_i`, and
`hat e`.

The implementation should prefer code-native SVG/math blocks so they scale
cleanly in Electron and screenshots. Raster LaTeX images are acceptable only if
they are generated locally and checked visually.

## Blind Inversion Display

The same selected q basket feeds two algorithms:

- Normal algorithm: weighted integer multiple fitting over the fixed internal
  physical e interval, with boundary, primitive-assignment, harmonic, residual,
  and leave-one-out checks.
- Experimental algorithm: adapter to the existing bounded profile likelihood
  estimator. The adapter converts normal q records into the minimal drop-result
  shape and must not call Experimental tracking, segmentation, q computation, or
  quality filtering.

The inversion view uses a two-option switch:

```text
Normal algorithm | Experimental algorithm
```

Normal algorithm is shown by default. If fewer than three usable selected q
records exist, the inversion panel stays disabled and reports the current usable
count. Reports omit blind-inversion sections entirely when there is insufficient
or unreliable evidence.

