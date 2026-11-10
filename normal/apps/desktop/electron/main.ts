import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";
import fsSync from "node:fs";
import path from "node:path";
import { WorkerClient } from "./workerClient";

let mainWindow: BrowserWindow | null = null;
const worker = new WorkerClient();
const transientNormalSessionRoots = new Set<string>();

function createWindow(): void {
  const display = screen.getPrimaryDisplay();
  const workArea = display.workAreaSize;
  const safeWidth = workArea.width - 48;
  const safeHeight = workArea.height - 48;
  const width = Math.min(1480, Math.max(640, safeWidth));
  const height = Math.min(940, Math.max(520, safeHeight));
  mainWindow = new BrowserWindow({
    width,
    height,
    minWidth: Math.min(980, width),
    minHeight: Math.min(700, height),
    center: true,
    show: false,
    title: "密立根油滴实验",
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
  mainWindow.center();

  const devUrl = process.env.VITE_DEV_SERVER_URL || "http://127.0.0.1:5173";
  if (app.isPackaged) {
    void mainWindow.loadFile(path.join(app.getAppPath(), "dist-renderer", "index.html"));
  } else {
    void mainWindow.loadURL(devUrl);
  }
  mainWindow.once("ready-to-show", () => {
    mainWindow?.maximize();
    mainWindow?.show();
  });
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
  cleanupTransientNormalSessions();
  worker.dispose();
});

function registerIpc(): void {
  ipcMain.handle("dialog:openVideo", async () => {
    const options = {
      title: "选择实验视频",
      properties: ["openFile"],
      filters: [
        { name: "视频", extensions: ["mp4", "mov", "avi", "mkv", "m4v"] },
        { name: "所有文件", extensions: ["*"] }
      ]
    } as Electron.OpenDialogOptions;
    const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("normal:initialize", async (_event, payload) => {
    const result = await worker.request("normal.initialize", payload || {});
    trackTransientNormalSession(payload || {}, result);
    return result;
  });
  ipcMain.handle("normal:inspectVideo", (_event, payload) => worker.request("normal.inspectVideo", payload));
  ipcMain.handle("normal:prepareVideo", async (event, payload) => {
    const result = await worker.request("normal.prepareVideo", payload, (progress) => {
      event.sender.send("normal:progress", progress);
    });
    trackTransientNormalSession(payload || {}, result);
    return result;
  });
  ipcMain.handle("normal:confirmBoundary", (_event, payload) => worker.request("normal:confirmBoundary", payload));
  ipcMain.handle("normal:selectTarget", (_event, payload) => worker.request("normal:selectTarget", payload));
  ipcMain.handle("normal:saveMeasurement", (event, payload) =>
    worker.request("normal.saveMeasurement", payload, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );
  ipcMain.handle("normal:prepareCrossingReview", (_event, payload) => worker.request("normal:prepareCrossingReview", payload));
  ipcMain.handle("normal:reviewCrossing", (_event, payload) => worker.request("normal:reviewCrossing", payload));
  ipcMain.handle("normal:updateRecordSelection", (_event, payload) => worker.request("normal:updateRecordSelection", payload));
  ipcMain.handle("normal:startNextDroplet", (_event, payload) => worker.request("normal:startNextDroplet", payload));
  ipcMain.handle("normal:runInversion", (event, payload) =>
    worker.request("normal.runInversion", payload || {}, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );
  ipcMain.handle("normal:exportSession", async (_event, payload) => exportNormalSession(payload || {}));
  ipcMain.handle("shell:openPath", (_event, targetPath: string) => shell.openPath(targetPath));
}

function trackTransientNormalSession(payload: unknown, result: unknown): void {
  const payloadRecord = payload && typeof payload === "object" ? (payload as Record<string, any>) : {};
  const resultRecord = result && typeof result === "object" ? (result as Record<string, any>) : {};
  const explicitSessionRoot =
    typeof payloadRecord.session_root === "string" && payloadRecord.session_root.length > 0
      ? payloadRecord.session_root
      : payloadRecord.config_overrides?.session?.session_root;
  if (explicitSessionRoot) {
    return;
  }
  const session = resultRecord.session && typeof resultRecord.session === "object" ? (resultRecord.session as Record<string, any>) : {};
  if (session.transient === false || typeof resultRecord.session_root !== "string" || resultRecord.session_root.length === 0) {
    return;
  }
  transientNormalSessionRoots.add(path.resolve(resultRecord.session_root));
}

function cleanupTransientNormalSessions(): void {
  for (const root of transientNormalSessionRoots) {
    try {
      fsSync.rmSync(root, { recursive: true, force: true });
    } catch (error) {
      console.warn(`Failed to clean transient Normal session ${root}:`, error);
    }
  }
  transientNormalSessionRoots.clear();
}

async function exportNormalSession(payload: { session_root?: string }): Promise<unknown> {
  const options = {
    title: "选择报告导出位置",
    properties: ["openDirectory", "createDirectory"]
  } as Electron.OpenDialogOptions;
  const result = mainWindow ? await dialog.showOpenDialog(mainWindow, options) : await dialog.showOpenDialog(options);
  if (result.canceled || !result.filePaths[0]) {
    return { canceled: true };
  }
  const destinationDir = result.filePaths[0];
  const workerResult = await worker.request("normal.exportSession", {
    session_root: payload.session_root,
    export_root: destinationDir
  });
  return { canceled: false, destination: destinationDir, package: workerResult };
}
