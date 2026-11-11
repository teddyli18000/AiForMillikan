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
- `npm run package` produces `release\密立根油滴实验-0.9.1.exe`.

## 界面文案

产品显示名称为“密立根油滴实验”。界面和导出报告使用中文，保留物理符号与标准单位；内部 Normal 名称、IPC 和数据字段不变。流程栏只显示步骤名，处理进度仅在任务执行时显示。计算过程保留，界面不展示前后端实现说明。

顶部显示步骤导航，测量时为视频与操作双栏；计算过程和元电荷结果使用整行空间。窄窗口按可用宽度调整列数，公式与科学计数值不拆行。操作提示位于当前面板，零电压时间标记位于播放进度条；复核帧使用自己的播放控件。

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
