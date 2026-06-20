import { app, BrowserWindow, dialog, ipcMain, screen, shell } from "electron";
import fsSync from "node:fs";
import fs from "node:fs/promises";
import path from "node:path";
import { WorkerClient } from "./workerClient";

let mainWindow: BrowserWindow | null = null;
const worker = new WorkerClient();
const transientNormalSessionRoots = new Set<string>();

function createWindow(): void {
  const display = screen.getPrimaryDisplay();
  const workArea = display.workAreaSize;
  const scaleFactor = Math.max(1, display.scaleFactor || 1);
  const safeWidth = Math.floor(workArea.width / scaleFactor) - 48;
  const safeHeight = Math.floor(workArea.height / scaleFactor) - 48;
  const width = Math.min(1480, Math.max(640, safeWidth));
  const height = Math.min(940, Math.max(520, safeHeight));
  mainWindow = new BrowserWindow({
    width,
    height,
    minWidth: Math.min(980, width),
    minHeight: Math.min(700, height),
    center: true,
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
  mainWindow.center();

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
  cleanupTransientNormalSessions();
  worker.dispose();
});

function registerIpc(): void {
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
  ipcMain.handle("normal:confirmBoundary", (_event, payload) => worker.request("normal.confirmBoundary", payload));
  ipcMain.handle("normal:selectTarget", (_event, payload) => worker.request("normal.selectTarget", payload));
  ipcMain.handle("normal:saveMeasurement", (event, payload) =>
    worker.request("normal.saveMeasurement", payload, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );
  ipcMain.handle("normal:prepareCrossingReview", (_event, payload) => worker.request("normal.prepareCrossingReview", payload));
  ipcMain.handle("normal:reviewCrossing", (_event, payload) => worker.request("normal.reviewCrossing", payload));
  ipcMain.handle("normal:updateRecordSelection", (_event, payload) => worker.request("normal.updateRecordSelection", payload));
  ipcMain.handle("normal:startNextDroplet", (_event, payload) => worker.request("normal.startNextDroplet", payload));
  ipcMain.handle("normal:runInversion", (event, payload) =>
    worker.request("normal.runInversion", payload || {}, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );
  ipcMain.handle("window:setModeFullscreen", (_event, enabled: boolean) => {
    if (!mainWindow) return false;
    if (enabled) {
      mainWindow.maximize();
    } else {
      mainWindow.unmaximize();
      mainWindow.center();
    }
    return mainWindow.isMaximized();
  });

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

async function exportNormalSession(payload: { session_root?: string }): Promise<unknown> {
  const options = {
    title: "选择 Normal session 导出位置",
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
