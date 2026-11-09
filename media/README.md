# Media Inventory

Shared read-only media for both applications. Nothing here is a build input.
Do not edit or duplicate these files inside `normal/` or `experimental/`.

## `videos/`

Raw smoke-test recordings captured from the experiment.

| File | Used by | Notes |
| --- | --- | --- |
| `2u.mp4` | Experimental | Two-platform smoke case; also the demo path in both renderers. |
| `3u1.mp4` | Experimental | Three-platform smoke case; historically produced invalid q. |
| `3u2.mp4` | Experimental | Three-platform smoke case with a short middle platform. |
| `single.mp4` | Experimental | Minimal video used by metadata/schema and diagnostic-frame tests. |
| `AGENTS.md` | Experimental | Guide voltage values recorded during capture. |

Tests resolve this directory by walking up from the test file to `media/videos`,
or by setting `MILLIKAN_MEDIA_ROOT`.

## `screenshots/`

| File | Used by | Notes |
| --- | --- | --- |
| `q-calculation.png` | Normal | Normal Stage 5 q-calculation evidence flow. |
| `tracking-review.png` | Normal | Normal trajectory / crossing review. |
| `inversion-results.png` | Normal | Normal blind inversion result page. |
| `mode-selection.png` | none | Legacy screenshot of the removed dual-mode splash screen. Kept for history only. |

## `diagrams/`

| File | Used by | Notes |
| --- | --- | --- |
| `pipeline.svg` | Experimental | Experimental analysis pipeline diagram. |
| `build-journey.svg` | none | Historical build-history diagram from the combined app. |

## Adding media

- Put new recordings under `videos/` and update this table.
- Reference media from app documentation with a repository-relative path, for
  example `../media/screenshots/q-calculation.png` from `normal/README.md`.
- Do not commit generated run artifacts, overlays, or review frames here.
