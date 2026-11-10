# Millikan AI

Two independent Windows desktop applications for the Millikan oil-drop
experiment, kept in one repository.

| App | Version | Product | Purpose |
| --- | --- | --- | --- |
| [Normal](normal/) | `0.9.0` | `Millikan AI Normal` | The mainline human-in-the-loop measurement: balance voltage + `0 V` falling, single-drop tracking, crossing review, q calculation, and blind elementary-charge inversion. |
| [Experimental](experimental/) | `0.1.0` | `Millikan AI Experimental` | The research route: automatic multi-drop / multi-platform analysis with a full run directory and downstream diagnostics. |

The two apps are fully standalone. They do not import each other, do not share
a Python package, do not share worker operations, and there is no runtime mode
switch. Identical low-level code is intentionally duplicated so each app can be
installed, tested, built, and packaged from its own directory.

## Repository layout

```
AiForMillikan/
├── normal/          # standalone Normal Electron + Python worker
├── experimental/    # standalone Experimental Electron + Python worker
├── media/           # shared raw videos, screenshots, and diagrams
├── .github/         # independent CI and release workflows per app
└── README.md
```

## Build and test

Each app owns its own toolchain. Run the commands from the app directory.

```powershell
# Normal
cd normal
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest tests -q
cd apps\desktop
npm ci
npm test
npm run build
npm run worker:build
npx electron-builder --win portable
```

```powershell
# Experimental
cd experimental
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
.venv\Scripts\python -m pytest tests -q
cd apps\desktop
npm ci
npm test
npm run build
npm run worker:build
npx electron-builder --win portable
```

Windows portable artifacts:

- `Millikan-AI-Normal-Portable-0.9.0.exe`
- `Millikan-AI-Experimental-Portable-0.1.0.exe`

CI runs the full pipeline for each app on every relevant push and pull request,
and uploads the portable EXE as a build artifact.

## Releases and tags

Each app has its own tag namespace and workflow:

- `normal-vX.Y.Z` → `normal-release.yml`
- `experimental-vX.Y.Z` → `experimental-release.yml`

The historical `v1.0.0` tag belongs to the pre-split combined app and is not
rewritten.

## Documentation

- Normal contracts: [normal/docs/](normal/docs/)
- Experimental contracts: [experimental/docs/](experimental/docs/)
- Media inventory: [media/README.md](media/README.md)

## License

MIT. See [LICENSE](LICENSE).
