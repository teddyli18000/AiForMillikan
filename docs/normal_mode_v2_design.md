# Normal Mode V2 Design

## Purpose

Normal mode is the default desktop workflow for formal single-droplet balance-fall measurements. It keeps user-visible inputs limited to video, balance voltage, optional time adjustment, target box selection, and q-record selection. Experimental remains available as a separate advanced route with an explicit risk confirmation.

The visual direction is restrained laboratory instrumentation: dense enough for repeated scientific work, but with a single obvious next action at each step. Motion is limited to state changes that help orientation: startup initialization, video load, automatic seek, tracking completion, and result generation.

## User Journey

1. Launch the app.
2. See real initialization states: renderer ready, preload API ready, worker ready, config readable.
3. Land on mode selection with Normal selected by default.
4. Open or drag in a video.
5. Enter balance voltage.
6. Run automatic balance-to-0V window suggestion.
7. Player seeks to the suggested start review time.
8. User reviews start and end with second-level controls, without entering frame numbers.
9. User boxes one droplet on the current real video frame.
10. App runs single-drop tracking across frames and grid occlusions.
11. User reviews tracking/missing/reacquired overlay and optional crossing loop.
12. User saves a unique q record.
13. User measures another droplet or another time window in the same or another video.
14. User selects valid q records for blind inversion.
15. With at least three selected valid q records, user runs Normal and Experimental inversion on the same q set.
16. User exports the session report and complete bundle.

## Screen Model

The Normal workspace uses one primary screen with progressive sections, not scattered pages:

- Session rail: record count, valid count, selected-for-inversion count, save/load status.
- Video stage: player, timeline, boundary chips, frame/second readout, target box overlay.
- Step strip: import, voltage, suggest window, review window, select target, track, save q, invert/export.
- Review panel: current step details, disabled reasons, warnings, and primary action.
- Records panel: persisted q records with source video, time interval, q validity, selection toggle, delete, and open review.
- Results panel: single q details and dual inversion tabs.

Experimental uses its existing workspace and state. Switching modes never reuses Normal video, target, session, q records, run directories, or results.

## Step States

Every step exposes one of:

- `idle`: not started.
- `running`: worker or UI operation in progress.
- `complete`: usable output exists.
- `needs_confirmation`: suggestion or result requires user review.
- `failed_retryable`: clear failure with retry action.
- `complete_with_warnings`: result exists but flags must be visible.

Disabled controls must show concise disabled reasons before click. Examples:

- "Add a video first."
- "Enter a positive balance voltage."
- "Confirm the fall window before selecting a droplet."
- "Select a target on the current frame."
- "At least three selected valid q records are required."

## Video Player Interaction

The player is the center of Normal mode.

- Opening and drag-drop both call the same backend inspect path.
- Playback, pause, and seek are native player actions reflected in app state.
- After window suggestion, the player seeks to the suggested start review time.
- Start review and end review each seek to their own time.
- Boundary controls provide `-1.0s`, `-0.1s`, `+0.1s`, `+1.0s`.
- Boundary adjustment updates player `currentTime`, current frame, overlay, and text immediately.
- Boundary review does not loop automatically.
- Target box selection always stores `target_frame` from the current player time and FPS.
- User can cancel and reselect the target.
- The displayed grid comes from detected grid lines, not decoration.

Crossing review is the only automatic loop:

- Clicking a missing-to-reacquired event seeks to a short pre-event time.
- The player loops through the event window.
- The event path and reacquired point are highlighted.
- Leaving crossing review stops looping and restores normal playback state.

## Success, Failure, Partial Success, Retry

- Video inspect success enables voltage input and boundary suggestion.
- Boundary suggestion success creates editable suggested start/end seconds and seeks the player.
- Boundary suggestion failure leaves video loaded and allows retry after changing ROI/config only through hidden advanced controls.
- Tracking success with valid physics enables saving q.
- Tracking success with physics failure still allows saving a diagnostic record, but it is not selectable for inversion.
- Partial tracking with warnings shows q only when formal validity rules pass.
- Any worker integration failure is shown as a production integration error, never as demo data.
- Retrying a step preserves earlier user inputs unless they are directly invalidated.

## Measurement Rules

- The physical operation is always balance voltage `U_balance -> 0V`.
- Consecutive visual voltage jumps inside the merge window are one operation.
- A recovery sequence such as `0 -> 235 -> 240` is one recovery operation, not a measurement platform.
- Fall start is first operation end plus stable guard, editable in seconds.
- Fall end is recovery start when present; otherwise after tracking, the last reliable tracking/reacquired point.
- Fitting never extends beyond the first crossing of the penultimate horizontal grid line.
- Missing predicted points are never fitted.

## Visual System

The interface should feel like precise desktop lab software:

- Background: quiet neutral gray, not a decorative gradient.
- Accent: one high-contrast blue-green for primary flow; amber for warnings; red for blocking errors.
- Typography: existing app fonts are acceptable, but control typography must be explicit and consistent.
- Cards: only for repeated records and modals. Main workflow sections use panels/bands, not nested cards.
- Radius: 6-8 px for controls and records.
- Icons: lucide icons for actions when available; labels remain short.
- Motion: 160-260 ms transitions for step completion and panel reveal; reduced-motion media query disables nonessential animation.

Overlay semantics:

- `tracking`: solid green point/path.
- `missing`: amber hollow predicted point/dashed path.
- `reacquired`: cyan point with short pulse on entry.
- fit interval: blue vertical/time band.
- detected grid lines: thin white/gray lines derived from backend data.

## Windows Desktop Adaptation

The app must remain usable on Windows desktop at 100%, 125%, and 150% display scaling, and on high-resolution monitors.

- Minimum supported window remains close to current desktop app minimum, but Normal mode must not require horizontal scrolling at that size.
- Video stage uses stable aspect ratio and max height, with controls below it.
- Dense record tables collapse to summary rows on narrow windows.
- Hit targets stay at least 32 px high.
- Text must not rely on viewport-width font scaling.
- High-DPI screenshots and overlay canvases must use device-pixel-ratio aware drawing.

## State Isolation

Normal state contains:

- active session path and persisted session JSON;
- loaded video metadata;
- current player state;
- suggested/confirmed fall window;
- selected target;
- normal run and review artifacts;
- q records and selected-for-inversion flags;
- dual inversion result.

Experimental state contains its existing platform inputs, runs, artifacts, and results. Switching mode hides but does not mutate the other mode. Experimental first entry requires a risk confirmation explaining that it uses the existing experimental multi-drop pipeline.
