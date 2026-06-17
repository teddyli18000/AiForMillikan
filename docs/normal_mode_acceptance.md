# Normal Mode V2 Acceptance

## Branch And Isolation

- Work starts from `develop` commit `d3704a4` or a later explicitly recorded `develop` commit.
- Branch: `feature/normal-balance-fall-mode-v2`.
- Worktree: `.worktrees/normal-balance-fall-mode-v2`.
- Do not merge, rebase shared branches, force-push, or push.
- Do not modify unrelated raw data changes in the main checkout.

## Documentation Gate

Before functional code:

- `docs/normal_mode_v2_design.md` records the full UX, states, disabled reasons, player interactions, mode isolation, and Windows adaptation.
- `docs/normal_mode_reference_mapping.md` maps teammate reference files/functions to V2 files/functions and records the frame-gap velocity bug fix.
- `docs/normal_mode_acceptance.md` records this checklist.

These docs are committed before ordinary implementation commits.

## Backend Acceptance

- `src/millikan_ai/normal_v2/` exists and owns Normal mode.
- A test scans `normal_v2` imports and rejects:
  - `millikan_ai.tracking.*`
  - `millikan_ai.segments.*`
  - `millikan_ai.pipeline`
  - `millikan_ai.physics.*`
  - `millikan_ai.quality.*`
- Only the experimental elementary adapter may call `millikan_ai.elementary.estimate`.
- Normal voltage operation detector merges short consecutive jumps.
- Tracking status values include `tracking`, `missing`, and `reacquired`.
- Reacquired velocity is divided by true frame gap.
- Missing predicted points never enter velocity fitting.
- The second-to-penultimate horizontal grid span defines `scale_y = 1.5e-3 / pixel_span`.
- First crossing below the penultimate horizontal line truncates the fit region permanently.
- Grid calibration failure blocks formal q unless the user supplies an explicit correction artifact.
- q uncertainty is not a fixed placeholder and changes with track noise.
- q record IDs are unique for repeated same-video measurements.
- Session save/load restores records and selection state.

## Frontend Acceptance

- Normal mode is default after real initialization.
- Experimental first entry shows risk confirmation.
- Production renderer has no automatic Demo API fallback.
- Opening and dragging video call the same inspect path.
- Player supports play, pause, seek, and boundary second controls.
- Suggested boundary generation seeks the player.
- Start/end review seeks to the corresponding time and does not auto-loop.
- Target box selection stores the current real frame.
- Crossing event review loops only the selected crossing segment and stops on exit.
- q/e/velocity/radius fields show `-` before data exists.
- Advanced tracking/config parameters are hidden by default.
- Same-video multiple q records can be shown, selected, deleted, persisted, and restored.
- Dual algorithm results use the same selected q set and switch on the same page.

## Report And Export Acceptance

- Final report is session-based, not just last run-based.
- Blind inversion section is omitted when fewer than three selected valid q records exist.
- Empty inversion sections are not emitted.
- Bounded diagnostic candidates are not labeled as identified elementary charge.
- Export bundle includes:
  - session/project file;
  - selected q records;
  - measurement inputs and source video/time window info;
  - track CSV/JSON;
  - tracking/missing/reacquired data;
  - overlay or review video;
  - single q results and uncertainty;
  - dual inversion results if run;
  - Markdown/PDF report;
  - manifest and file list.

## Verification Acceptance

Required command evidence:

```powershell
..\..\.venv\Scripts\python -m pytest tests -q --basetemp runs\pytest_tmp_work -o cache_dir=runs\pytest_cache_work
cd apps\desktop
npm test
npm run package
```

Required real-data evidence:

- Run teammate reference on `C:\Users\Teddy\Desktop\追踪\raw_videos\test.mp4`.
- Save reference CSV/screenshot/overlay and parameters.
- Run V2 with the same video, target, frame, and key parameters.
- Save comparison under `runs/normal_v2_reference_comparison/`.
- Compare duration, detected point count, missing/reacquired count, cross-grid continuity, path deviation, and velocity.

Required packaged EXE E2E evidence under `runs/normal_v2_e2e/`:

- operation log;
- screenshots for startup, mode select, empty state, load, target box, boundary review, overlay, crossing review, q result, records, dual algorithms, formula, report preview, error/retry state;
- necessary recording;
- final session/run paths;
- export bundle file list;
- EXE path, size, and SHA256.

## Final Packaging Acceptance

Before final report, create a zip on the desktop containing:

- final engineering report;
- command outputs or summaries;
- screenshot/recording references;
- E2E log;
- reference comparison report;
- export bundle file list;
- EXE metadata;
- branch/base/final commit information.

The zip must be placed on the user's desktop and named with the branch and date.
