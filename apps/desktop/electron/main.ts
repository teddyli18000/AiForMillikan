import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";
import fs from "node:fs/promises";
import fsSync from "node:fs";
import path from "node:path";
import { WorkerClient } from "./workerClient";
import { pathToFileURL } from "node:url";

let mainWindow: BrowserWindow | null = null;
const worker = new WorkerClient();

function createWindow(): void {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const initialWidth = Math.min(820, Math.max(780, workAreaSize.width - 80));
  const initialHeight = Math.min(680, Math.max(620, workAreaSize.height - 80));
  const { workArea } = screen.getPrimaryDisplay();
  const initialX = workArea.x + 20;
  const initialY = workArea.y + 40;

  mainWindow = new BrowserWindow({
    x: initialX,
    y: initialY,
    width: initialWidth,
    height: initialHeight,
    minWidth: Math.min(780, initialWidth),
    minHeight: Math.min(640, initialHeight),
    title: "Millikan AI",
    backgroundColor: "#f7f9fc",
    titleBarStyle: "hiddenInset",
    trafficLightPosition: { x: 18, y: 18 },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });
  mainWindow.setBounds({ x: initialX, y: initialY, width: initialWidth, height: initialHeight });

  const devUrl = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5173";
  if (app.isPackaged) {
    void mainWindow.loadFile(path.join(app.getAppPath(), "dist-renderer", "index.html"));
  } else {
    void mainWindow.loadURL(devUrl);
  }
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  worker.dispose();
});

function registerIpc(): void {
  ipcMain.handle("app:initialize", async () => {
    const runtime = runtimePaths();
    const configPath = resolveConfigPath();
    const checks = [
      { id: "renderer_ready", label: "renderer ready", ok: Boolean(mainWindow) },
      { id: "preload_api_ready", label: "preload API ready", ok: true },
      { id: "config_readable", label: "配置资源可读", ok: await exists(configPath), detail: configPath },
    ];
    let workerPayload: unknown = null;
    try {
      workerPayload = await worker.request("health.check", { config_path: configPath });
      checks.push({ id: "packaged_worker_health", label: "packaged worker health", ok: true, detail: app.isPackaged ? "packaged worker" : "dev worker" });
    } catch (error) {
      checks.push({ id: "packaged_worker_health", label: "packaged worker health", ok: false, detail: error instanceof Error ? error.message : String(error) });
    }
    try {
      await fs.mkdir(runtime.normalSessionRoot, { recursive: true });
      await fs.mkdir(runtime.normalRunRoot, { recursive: true });
      checks.push({ id: "normal_session_readable", label: "普通模式 session 可读", ok: true, detail: runtime.normalSessionRoot });
    } catch (error) {
      checks.push({ id: "normal_session_readable", label: "普通模式 session 可读", ok: false, detail: error instanceof Error ? error.message : String(error) });
    }
    return { ok: checks.every((check) => check.ok), checks, runtime, worker: workerPayload };
  });

  ipcMain.handle("app:runtimePaths", () => runtimePaths());

  ipcMain.handle("dialog:openVideo", async () => {
    const options = {
      title: "选择实验视频",
      properties: ["openFile"],
      filters: [
        { name: "Video", extensions: ["mp4", "mov", "avi", "mkv", "m4v"] },
        { name: "All files", extensions: ["*"] }
      ]
    } as Electron.OpenDialogOptions;
    const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("dialog:openRun", async () => {
    const options = {
      title: "选择 run 目录",
      properties: ["openDirectory"]
    } as Electron.OpenDialogOptions;
    const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("video:inspect", (_event, payload) => worker.request("video.inspect", payload));
  ipcMain.handle("platform:detectBoundaries", (_event, payload) => worker.request("platform.detectBoundaries", payload));
  ipcMain.handle("analysis:loadRun", (_event, payload) => worker.request("analysis.loadRun", payload));
  ipcMain.handle("analysis:validate", (_event, payload) => worker.request("analysis.validate", payload));
  ipcMain.handle("downstream:run", (_event, payload) => worker.request("downstream.run", payload));
  ipcMain.handle("normal:initialize", (_event, payload) =>
    worker.request("normal.initialize", { ...(payload || {}), session_root: runtimePaths().normalSessionRoot, run_root: runtimePaths().normalRunRoot })
  );
  ipcMain.handle("normal:prepareVideo", async (_event, payload) => {
    const result = await worker.request<Record<string, unknown>>("normal.prepareVideo", {
      ...(payload || {}),
      session_root: runtimePaths().normalSessionRoot,
      run_root: runtimePaths().normalRunRoot,
    });
    return { ...result, video_url: pathToFileURL(String((payload as { video_path: string }).video_path)).toString() };
  });
  ipcMain.handle("normal:saveMeasurement", (_event, payload) =>
    worker.request("normal.saveMeasurement", {
      ...(payload || {}),
      session_root: runtimePaths().normalSessionRoot,
      run_root: runtimePaths().normalRunRoot,
    })
  );
  ipcMain.handle("normal:selectRecord", (_event, payload) =>
    worker.request("normal.selectRecord", { ...(payload || {}), session_root: runtimePaths().normalSessionRoot })
  );
  ipcMain.handle("normal:runInversion", (_event, payload) =>
    worker.request("normal.runInversion", { ...(payload || {}), session_root: runtimePaths().normalSessionRoot, config_path: resolveConfigPath() })
  );
  ipcMain.handle("normal:createQaFixture", (_event, payload) =>
    worker.request("normal.createQaFixture", { ...(payload || {}), session_root: runtimePaths().normalSessionRoot, run_root: runtimePaths().normalRunRoot })
  );
  ipcMain.handle("normal:exportSession", async (_event, payload) => exportNormalSession(payload));

  ipcMain.handle("analysis:run", (event, payload) =>
    worker.request("analysis.run", payload, (progress) => {
      event.sender.send("analysis:progress", progress);
    })
  );

  ipcMain.handle("analysis:runAuto", (event, payload) =>
    worker.request("analysis.runAuto", payload, (progress) => {
      event.sender.send("analysis:progress", progress);
    })
  );

  ipcMain.handle("report:export", async (_event, payload) => exportReport(payload));
  ipcMain.handle("shell:openPath", (_event, targetPath: string) => shell.openPath(targetPath));
}

function runtimePaths(): {
  userDataRoot: string;
  normalSessionRoot: string;
  normalRunRoot: string;
  cacheRoot: string;
  tempRoot: string;
  resourcesRoot: string;
  configPath: string;
} {
  const userDataRoot = app.getPath("userData");
  return {
    userDataRoot,
    normalSessionRoot: path.join(userDataRoot, "normal", "sessions", "current"),
    normalRunRoot: path.join(userDataRoot, "normal", "sessions", "current", "records"),
    cacheRoot: path.join(userDataRoot, "normal", "cache"),
    tempRoot: path.join(app.getPath("temp"), "millikan-ai-normal"),
    resourcesRoot: app.isPackaged ? process.resourcesPath : findProjectRootForMain(),
    configPath: resolveConfigPath(),
  };
}

function resolveConfigPath(): string {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, "configs", "default.yaml");
  }
  return path.join(findProjectRootForMain(), "configs", "default.yaml");
}

function findProjectRootForMain(): string {
  let cursor = app.getAppPath();
  for (let index = 0; index < 8; index += 1) {
    if (fsSyncExists(path.join(cursor, "src", "millikan_ai", "api.py"))) {
      return cursor;
    }
    const parent = path.dirname(cursor);
    if (parent === cursor) {
      break;
    }
    cursor = parent;
  }
  return path.resolve(app.getAppPath(), "..", "..");
}

async function exists(target: string): Promise<boolean> {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

function fsSyncExists(target: string): boolean {
  return fsSync.existsSync(target);
}

async function exportNormalSession(_payload: unknown): Promise<unknown> {
  const options = {
    title: "选择普通模式报告导出位置",
    properties: ["openDirectory", "createDirectory"]
  } as Electron.OpenDialogOptions;
  const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
  if (result.canceled || !result.filePaths[0]) {
    return { canceled: true };
  }
  const exported = await worker.request("normal.exportSession", {
    session_root: runtimePaths().normalSessionRoot,
    export_root: result.filePaths[0],
  });
  if (mainWindow) {
    const pdf = await mainWindow.webContents.printToPDF({
      printBackground: true,
      landscape: false,
      margins: { marginType: "custom", top: 0.4, bottom: 0.4, left: 0.4, right: 0.4 },
      pageSize: "A4"
    });
    const destination = (exported as { destination?: string }).destination;
    if (destination) {
      await fs.writeFile(path.join(destination, "Normal_Mode_Report.pdf"), pdf);
    }
  }
  return { canceled: false, package: exported };
}

async function exportReport(payload: {
  run_dir: string;
  include_pdf?: boolean;
  mode?: "folder" | "zip";
}): Promise<unknown> {
  const options = {
    title: "选择报告保存位置",
    properties: ["openDirectory", "createDirectory"]
  } as Electron.OpenDialogOptions;
  const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
  if (result.canceled || !result.filePaths[0]) {
    return { canceled: true };
  }
  const destinationDir = result.filePaths[0];
  const workerResult = await worker.request("report.export", {
    run_dir: payload.run_dir,
    destination_dir: destinationDir,
    mode: payload.mode || "folder"
  });

  if (payload.include_pdf !== false && mainWindow) {
    const pdf = await mainWindow.webContents.printToPDF({
      printBackground: true,
      landscape: true,
      margins: { marginType: "custom", top: 0.35, bottom: 0.35, left: 0.35, right: 0.35 },
      pageSize: "A4"
    });
    await fs.writeFile(path.join(destinationDir, "Millikan_AI_Report.pdf"), pdf);
  }

  return { canceled: false, destination: destinationDir, package: workerResult };
}
