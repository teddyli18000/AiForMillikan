import { app, BrowserWindow, dialog, ipcMain, shell } from "electron";
import fs from "node:fs/promises";
import path from "node:path";
import { WorkerClient } from "./workerClient";

let mainWindow: BrowserWindow | null = null;
const worker = new WorkerClient();

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1480,
    height: 940,
    minWidth: 1180,
    minHeight: 760,
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
  ipcMain.handle("normal:initialize", (_event, payload) => worker.request("normal.initialize", payload || {}));
  ipcMain.handle("normal:inspectVideo", (_event, payload) => worker.request("normal.inspectVideo", payload));
  ipcMain.handle("normal:prepareVideo", (event, payload) =>
    worker.request("normal.prepareVideo", payload, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );
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
  ipcMain.handle("normal:runInversion", (event, payload) =>
    worker.request("normal.runInversion", payload || {}, (progress) => {
      event.sender.send("normal:progress", progress);
    })
  );

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
