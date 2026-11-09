# Experimental Desktop Frontend

The Experimental desktop app lives in `experimental/apps/desktop/`. It is a
Windows portable Electron build with a React renderer and a Python worker.

## Entry points

- `src/main.tsx` → `src/App.tsx` → `src/components/ExperimentalApp.tsx`
- The app opens the analysis workspace directly. There is no mode selection
  page and no link to the Normal app.
- `electron/main.ts` registers Experimental IPC, starts the worker, and
  maximizes the window when it is ready to show.
- `electron/preload.ts` exposes only the Experimental renderer API.

## Development

```powershell
cd experimental\apps\desktop
npm ci
npm run dev
```

Run Electron against the Vite server:

```powershell
$env:VITE_DEV_SERVER_URL='http://127.0.0.1:5173'
npx electron dist-electron\main.js
```

The main process starts `experimental\.venv\Scripts\python -m
millikan_ai.desktop_worker` and sets `PYTHONPATH` to `experimental\src`.
Override the interpreter with `MILLIKAN_PYTHON`.

## Build and package

```powershell
cd experimental\apps\desktop
npm run build
npm run worker:build
npm run package
```

- `npm run build` compiles Electron TypeScript, type-checks the renderer, and
  builds `dist-renderer`.
- `npm run worker:build` runs PyInstaller and writes
  `dist-worker\millikan-experimental-worker.exe`.
- `npm run package` produces
  `release\Millikan-AI-Experimental-Portable-0.1.0.exe`.

## UI contracts

The renderer must follow `frontend_backend_interface.md` and `../AGENTS.md`.
It displays run artifacts written by the backend; it does not recompute physics
or invent platform voltages.

## Tests

```powershell
npm test
npm run build
```

`tests/App.test.tsx` drives the demo analysis path against the demo API.
