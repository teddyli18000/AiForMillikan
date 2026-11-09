# Normal Documentation

Current contracts and physics notes for the Normal app. Experimental material
lives in `experimental/docs/`.

## Technical

- [Architecture](technical/architecture.md): renderer, Electron main, Python
  worker, and transient session.
- [Normal workflow](technical/normal-workflow.md): stages, state machine,
  session and record status.
- [Tracking and review](technical/tracking-and-review.md): selection box, video
  coordinates, Trackpy, crossing events, and trajectory evidence.
- [Validation](technical/validation.md): automated tests and packaged checks.
- [Encoding, build, release](technical/encoding-build-release.md): UTF-8
  transport, PyInstaller, Electron packaging, and release gates.
- [Frontend/backend interface](frontend_backend_interface.md): the complete
  `normal.*` worker contract.
- [Desktop frontend](desktop_frontend.md): local development and packaging.

## Academic

- [Experiment method](academic/experiment-method.md)
- [Charge measurement](academic/charge-measurement.md)
- [Uncertainty](academic/uncertainty.md)
- [Blind inversion](academic/blind-inversion.md)
- [Scientific boundaries](academic/scientific-boundaries.md)

## Reading order

Start with `../README.md`, then `technical/normal-workflow.md` for the user flow
and `frontend_backend_interface.md` for the machine contract. Academic notes are
reference material, not implementation specs.
