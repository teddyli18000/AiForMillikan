# Normal Desktop Frontend

The Normal desktop app lives in `normal/apps/desktop/`. It is a Windows portable
Electron build with a React renderer and a Python worker.

## Entry points

- `src/main.tsx` → `src/App.tsx` → `src/components/normal/NormalWorkspace.tsx`
- The app opens the Normal workspace directly. There is no mode selection page.
- `electron/main.ts` registers Normal IPC, starts the worker, and maximizes the
  window when it is ready to show.
- `electron/preload.ts` exposes only the Normal renderer API.

## Development

```powershell
cd normal\apps\desktop
npm ci
npm run dev
```

Run Electron against the Vite server:

```powershell
$env:VITE_DEV_SERVER_URL='http://127.0.0.1:5173'
npx electron dist-electron\main.js
```

The main process starts `normal\.venv\Scripts\python -m
millikan_ai.desktop_worker` and sets `PYTHONPATH` to `normal\src`. Override the
interpreter with `MILLIKAN_PYTHON`.

## Build and package

```powershell
cd normal\apps\desktop
npm run build
npm run worker:build
npm run package
```

- `npm run build` compiles Electron TypeScript, type-checks the renderer, and
  builds `dist-renderer`.
- `npm run worker:build` runs PyInstaller and writes
  `dist-worker\millikan-normal-worker.exe`.
- `npm run package` produces `release\Millikan-AI-Normal-Portable-0.9.0.exe`.

## UI contracts

The renderer must follow `../frontend_backend_interface.md` and
`../AGENTS.md`. In particular:

- all user-facing time controls are in seconds (`±1 s`, `±0.1 s`);
- the target preview is the main video player paused at the selection frame;
- review frames and trajectory overlays are backend-rendered;
- Stage 5 formula values come from the record calculation trace;
- Stage 6 has one canonical result card;
- scientific numbers use readable typography such as `1.602 × 10⁻¹⁹ C`.

## Tests

```powershell
npm test
npm run build
```

`tests/App.test.tsx` drives the Normal workflow against the demo API. It does
not require the Electron shell or a real video.
