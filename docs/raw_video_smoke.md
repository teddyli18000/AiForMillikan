# Raw Video Smoke Results

This document records raw-video smoke tests run with manual voltage platforms. These platform values and ranges are visual estimates from frame crops, not calibrated OCR output.

## Verified Commands

Use the project-local environment:

```powershell
.venv\Scripts\python run_millikan.py
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\<video>.mp4 --config <manual_config.yaml> --run-dir runs\<run_dir>
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
.venv\Scripts\python -m millikan_ai.cli validate --run-dir runs\<run_dir> --config <manual_config.yaml>
```

The current `develop`/`main` backend does not run voltage OCR. The platform values below must be entered manually through the root wizard, CLI flags, API, or a generated config.

## Results

| Date | Video | Manual platforms | Result | Notes |
|---|---|---|---|---|
| 2026-06-07 | `raw_data/2u.mp4` | `0:180:0`, `181:468:175` | valid q for 1 droplet | `tracking.max_drops=3` selected 2 tracks; 1 was physically valid and 1 failed `non_positive_alpha`. |
| 2026-06-07 | `raw_data/3u1.mp4` | `0:170:91`, `200:380:176`, `420:571:302` | invalid q | Selected track produced `non_positive_alpha`; all stable fitted velocities were upward under the current `+Y down` convention. |
| 2026-06-07 | `raw_data/3u2.mp4` | `0:160:241`, `175:185:245`, `205:439:376` | invalid q | The short middle platform is correctly marked too short; the selected track had insufficient stable platforms. |
| 2026-06-08 | `raw_data/2u.mp4` | `0:180:0`, `181:468:175` | 20 tracked, 15 q-valid, 8 kept | Jump and morphology rules rejected 7 otherwise q-valid trajectories. Elementary estimation used only the 8 kept results. |
| 2026-06-08 | `raw_data/3u2.mp4` | `0:160:241`, `175:185:245`, `205:439:376` | 20 tracked, 1 q-valid, 0 kept | The sole q-valid candidate failed the frame-jump rule, so elementary estimation remained invalid. |

## Current Interpretation

- `2u.mp4` is the current positive raw smoke case for real q calculation.
- `3u1.mp4` and `3u2.mp4` are useful negative/stability tests. They should not be reported as valid unless platform choices, direction convention, or tracking evidence changes enough to satisfy the physics checks.
- `candidate_tracks_summary.csv.selected_for_multi_drop=true` means the candidate was evaluated. Use `q_valid=true`, `multi_drop_results.valid_drop_count`, or `run_manifest.counts.valid_drops` for physically valid droplets.
- Use `trajectory_quality_scores.csv.keep=true` together with `q_valid=true` for results allowed into elementary-charge estimation.
- Short or transient-cropped platforms must retain their source `track_id` in `drop_track_segments.csv`; blank `track_id` rows can create fake drops and are a regression.
