# Experimental Architecture

The Experimental app is a Windows portable Electron application backed by a
project-local Python worker. It analyzes a whole video with automatic multi-drop
tracking and a bounded elementary-charge estimator.

```mermaid
flowchart LR
    UI["Electron + React renderer"] --> IPC["Electron IPC"]
    IPC --> W["Experimental Python worker"]
    W --> API["millikan_ai.api / pipeline"]
    W --> DS["millikan_ai.downstream"]
    API --> R["Run directory + run_manifest.json"]
    DS --> R
```

## Processes

### Renderer

`apps/desktop/src/` owns the setup, analysis, and results views: platform table,
progress, overlay layers, validity checks, multi-drop tables, elementary-charge
diagnostics, charts, and export.

### Electron main

`apps/desktop/electron/` owns video and run-directory dialogs, Experimental IPC
dispatch, worker startup, progress forwarding, report export, and maximum-width
window on startup.

### Python worker

`src/millikan_ai/desktop_worker.py` speaks UTF-8 JSON Lines and exposes
`video.inspect`, `platform.detectBoundaries`, `analysis.run`,
`analysis.runAuto`, `analysis.loadRun`, `analysis.validate`, `downstream.run`,
and `report.export`.

It does not import the Normal package and does not expose `normal.*`
operations.

## Source of truth

- The run directory and `run_manifest.json` are the frontend entry point.
- CSV, JSON, and MP4 artifacts are the machine-readable contract.
- The renderer displays artifacts and never recomputes physics.

## Storage

Every analysis writes a run directory. `runs/` is ignored by Git. Users export a
package through `report.export`, optionally as a ZIP or PDF.
