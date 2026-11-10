# Experimental Documentation

Current contracts and research notes for the Experimental app. Normal material
lives in `normal/docs/`.

## Technical

- [Architecture](technical/architecture.md): renderer, Electron main, Python
  worker, and run directory.
- [Validation](technical/validation.md): automated tests, media resolution, and
  the synthetic estimator harness.
- [Encoding, build, release](technical/encoding-build-release.md): UTF-8
  transport, PyInstaller, Electron packaging, and release gates.
- [Frontend/backend interface](frontend_backend_interface.md): the complete
  `video.*`, `platform.*`, `analysis.*`, `downstream.*`, and `report.*` contract.
- [Desktop frontend](desktop_frontend.md): local development and packaging.

## Academic

- [Experiment method](academic/experiment-method.md)
- [Charge measurement](academic/charge-measurement.md)
- [Uncertainty](academic/uncertainty.md)
- [Blind inversion](academic/blind-inversion.md)
- [Scientific boundaries](academic/scientific-boundaries.md)

## History

- [Raw video smoke records](raw_video_smoke.md)
- [Version repair log](archive/版本修复记录.md)
- [1.0.0 release notes](archive/release-notes-v1.0.0.md)
- [archive/](archive/): early designs, failed routes, and undelivered research
  ideas. Historical evidence only; not current contracts.

## Reading order

Start with `../README.md`, then `technical/architecture.md` for the pipeline and
`frontend_backend_interface.md` for the machine contract. `archive/` is for
context on why the current design changed.
