# Raw Video Smoke Results

This document records raw-video smoke tests run with manual voltage platforms and automatic voltage-display boundary suggestions. Platform values are user/guide supplied, not calibrated OCR output.

## Verified Commands

Use the project-local environment:

```powershell
.venv\Scripts\python run_millikan.py
.venv\Scripts\python -m millikan_ai.cli detect-platforms --video raw_data\<video>.mp4 --config configs\default.yaml --count 3
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\<video>.mp4 --config <manual_config.yaml> --run-dir runs\<run_dir>
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\5.mp4 --config configs\default.yaml --auto-platform-count 3 --platform-value 0 --platform-value 150 --platform-value 259
.venv\Scripts\python -m millikan_ai.cli analyze --video raw_data\2u.mp4 --config configs\default.yaml --platform 0:180:0 --platform 181:468:175
.venv\Scripts\python -m millikan_ai.cli validate --run-dir runs\<run_dir> --config <manual_config.yaml>
```

The current `develop`/`main` backend does not run voltage OCR. It may suggest platform boundaries by detecting visual changes in the voltage display, but the platform voltage values below must still be entered manually through the root wizard, CLI flags, API, or a generated config.

## Results

| Date | Video | Manual platforms | Result | Notes |
|---|---|---|---|---|
| 2026-06-07 | `raw_data/2u.mp4` | `0:180:0`, `181:468:175` | valid q for 1 droplet | `tracking.max_drops=3` selected 2 tracks; 1 was physically valid and 1 failed `non_positive_alpha`. |
| 2026-06-07 | `raw_data/3u1.mp4` | `0:170:91`, `200:380:176`, `420:571:302` | invalid q | Selected track produced `non_positive_alpha`; all stable fitted velocities were upward under the current `+Y down` convention. |
| 2026-06-07 | `raw_data/3u2.mp4` | `0:160:241`, `175:185:245`, `205:439:376` | invalid q | The short middle platform is correctly marked too short; the selected track had insufficient stable platforms. |
| 2026-06-08 | `raw_data/2u.mp4` | `0:180:0`, `181:468:175` | 20 tracked, 15 q-valid, 8 kept | Jump and morphology rules rejected 7 otherwise q-valid trajectories. Elementary estimation used only the 8 kept results. |
| 2026-06-08 | `raw_data/3u2.mp4` | `0:160:241`, `175:185:245`, `205:439:376` | 20 tracked, 1 q-valid, 0 kept | The sole q-valid candidate failed the frame-jump rule, so elementary estimation remained invalid. |
| 2026-06-08 | `raw_data/1.mp4` | guide values `0,175,248` | auto boundary rejected | Suggested first platforms were too short; use manual boundary input. |
| 2026-06-08 | `raw_data/2.mp4` | guide values `0,239,362` | auto boundary accepted | `0-320`, `325-695`, `700-930`; method `descriptor_kmeans_runs`. |
| 2026-06-08 | `raw_data/3.mp4` | guide values `0,96,258` | auto boundary accepted with caution | `0-393`, `412-468`, `492-915`; middle platform is short for downstream fitting review. |
| 2026-06-08 | `raw_data/4.mp4` | guide values `0,103,203` | auto boundary accepted with caution | `0-298`, `317-348`, `367-923`; middle platform is short for downstream fitting review. |
| 2026-06-08 | `raw_data/5.mp4` | guide values `0,150,259` | auto boundary accepted | `0-350`, `355-625`, `630-918`; method `descriptor_kmeans_runs`. |
| 2026-06-08 | `raw_data/6.mp4` | guide values `0,131,334` | auto boundary rejected | Suggested first platform was too short; use manual boundary input. |
| 2026-06-08 | `raw_data/7.mp4` | guide values `0,172,257` | auto boundary accepted with caution | `0-93`, `112-198`, `217-914`; early platforms are short for downstream fitting review. |
| 2026-06-08 | `raw_data/8.mp4` | guide values `0,165,269` | auto boundary rejected | Suggested middle platform was too short; use manual boundary input. |

## Current Interpretation

- `raw_data/2.mp4` and `raw_data/5.mp4` are the current positive smoke cases for automatic voltage-boundary suggestions.
- `2u.mp4` in `raw_data_old/` was the earlier positive raw smoke case for real q calculation.
- `3u1.mp4` and `3u2.mp4` are useful negative/stability tests. They should not be reported as valid unless platform choices, direction convention, or tracking evidence changes enough to satisfy the physics checks.
- Auto boundary suggestions are accepted only when the detected count matches the user-provided count and no suggested platform has a reject reason. Rejected suggestions should fall back to manual boundary input.
- `candidate_tracks_summary.csv.selected_for_multi_drop=true` means the candidate was evaluated. Use `q_valid=true`, `multi_drop_results.valid_drop_count`, or `run_manifest.counts.valid_drops` for physically valid droplets.
- Use `trajectory_quality_scores.csv.keep=true` together with `q_valid=true` for results allowed into elementary-charge estimation.
- Short or transient-cropped platforms must retain their source `track_id` in `drop_track_segments.csv`; blank `track_id` rows can create fake drops and are a regression.
