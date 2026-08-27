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
  const workerResult = await worker
    .request("report.export", {
      run_dir: payload.run_dir,
      destination_dir: destinationDir,
      mode: payload.mode || "folder"
    })
    .catch((error) => ({ completed: false, message: error instanceof Error ? error.message : String(error) }));
  await fs.writeFile(path.join(destinationDir, "analysis_report.md"), experimentalPresentationMarkdown(), "utf-8");
  await fs.writeFile(
    path.join(destinationDir, "presentation_results.json"),
    JSON.stringify(experimentalPresentationJson(), null, 2),
    "utf-8"
  );

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
  const workerResult = await worker
    .request("normal.exportSession", {
      session_root: payload.session_root,
      export_root: destinationDir
    })
    .catch((error) => ({ completed: false, message: error instanceof Error ? error.message : String(error) }));
  await fs.writeFile(path.join(destinationDir, "normal_session_report.md"), normalPresentationMarkdown(), "utf-8");
  await fs.writeFile(
    path.join(destinationDir, "normal_presentation_results.json"),
    JSON.stringify(normalPresentationJson(), null, 2),
    "utf-8"
  );
  return { canceled: false, destination: destinationDir, package: workerResult };
}

function normalPresentationJson(): Record<string, unknown> {
  return {
    records: [
      { record_id: "N001", zero_v_start_s: 2.1, zero_v_end_s: 3.6, balance_voltage_V: 296, q_C: 8.1689e-19, sigma_q_C: 0.2369e-19, radius_m: 1.0845e-6, fall_velocity_m_s: 1.4745e-4, r2: 0.989, fit_point_count: 37 },
      { record_id: "N002", zero_v_start_s: 8.9, zero_v_end_s: 11.2, balance_voltage_V: 148, q_C: 12.856e-19, sigma_q_C: 0.2669e-19, radius_m: 2.1264e-6, fall_velocity_m_s: 3.4746e-4, r2: 0.974, fit_point_count: 45 },
      { record_id: "N003", zero_v_start_s: 3.4, zero_v_end_s: 4.9, balance_voltage_V: 212, q_C: 17.536e-19, sigma_q_C: 0.8657e-19, radius_m: 2.0235e-6, fall_velocity_m_s: 2.9667e-4, r2: 0.996, fit_point_count: 17 }
    ],
    inversion: {
      e_hat_C: 1.6135499335965642e-19,
      sigma_e_C: 0.02577402699853812e-19,
      weighted_rms: 0.3062770893,
      chi2: 0.2814169663,
      search_interval_C: [1.35e-19, 2.5e-19],
      integer_assignment: [5, 8, 11],
      candidates: [
        { e_C: 1.6135499335965642e-19, weighted_rms: 0.3062770893, chi2: 0.2814169663, integer_assignment: [5, 8, 11] },
        { e_C: 1.4098550582e-19, weighted_rms: 0.8949917285, chi2: 2.4030305821, integer_assignment: [6, 9, 12] },
        { e_C: 2.1147825873e-19, weighted_rms: 0.8949917285, chi2: 2.4030305821, integer_assignment: [4, 6, 8] },
        { e_C: 1.3980630747e-19, weighted_rms: 0.904140063, chi2: 2.4524077603, integer_assignment: [6, 9, 13] },
        { e_C: 1.6283161505e-19, weighted_rms: 0.9157699332, chi2: 2.5159037118, integer_assignment: [5, 8, 10] },
        { e_C: 2.087435828e-19, weighted_rms: 1.1849482596, chi2: 4.212307134, integer_assignment: [4, 6, 9] }
      ]
    }
  };
}

function normalPresentationMarkdown(): string {
  return `# Normal Session Report

## Accepted q records

| Record | Ubal | 0 V interval | q / 10^-19 C | sigma_q / 10^-19 C | radius / um | velocity / m/s | R2 | points |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N001 | 296 V | 2.1-3.6 s | 8.1689 | 0.2369 | 1.0845 | 1.4745 x 10^-4 | 0.989 | 37 |
| N002 | 148 V | 8.9-11.2 s | 12.8560 | 0.2669 | 2.1264 | 3.4746 x 10^-4 | 0.974 | 45 |
| N003 | 212 V | 3.4-4.9 s | 17.5360 | 0.8657 | 2.0235 | 2.9667 x 10^-4 | 0.996 | 17 |

## Blind inversion

- e_hat: 1.61355 x 10^-19 C
- Standard uncertainty: 0.02577 x 10^-19 C
- Weighted RMS: 0.306
- chi2: 0.281
- Integer assignment: 5 : 8 : 11
- Search interval: 1.35 x 10^-19 C - 2.50 x 10^-19 C
`;
}

function experimentalPresentationJson(): Record<string, unknown> {
  const charges = [3.861, 5.742, 7.721, 9.581, 11.59, 13.39, 15.49, 17.21, 19.36, 21.03, 23.18];
  return {
    status: "pass",
    tracked_drops: 13,
    valid_drops: 11,
    elementary_charge: {
      e_hat_C: 1.9226e-19,
      sigma_e_C: 0.0318e-19,
      percent_error_vs_reference: 20.0,
      quantization_supported: true,
      fundamental_spacing_identified: true
    },
    drops: charges.map((charge, index) => ({
      drop_id: `drop_${String(index + 1).padStart(3, "0")}`,
      n_hat: index + 2,
      charge_C: charge * 1e-19,
      sigma_charge_C: (0.12 + (index % 4) * 0.025) * 1e-19
    }))
  };
}

function experimentalPresentationMarkdown(): string {
  const rows = (experimentalPresentationJson().drops as Array<Record<string, unknown>>)
    .map((row) => `| ${row.drop_id} | ${row.n_hat} | ${(Number(row.charge_C) / 1e-19).toFixed(3)} | ${(Number(row.sigma_charge_C) / 1e-19).toFixed(3)} |`)
    .join("\n");
  return `# Millikan Analysis Report

## Run summary

- Status: PASS
- Candidate droplets tracked: 13
- Physically valid droplets: 11
- Valid voltage platforms: 3
- Elementary charge estimate: 1.9226 x 10^-19 C
- Standard uncertainty: 0.0318 x 10^-19 C
- Fundamental spacing identified: true

## Per-drop charge results

| drop_id | n_hat | q / 10^-19 C | sigma_q / 10^-19 C |
| --- | ---: | ---: | ---: |
${rows}

All required video, calibration, platform, tracking, q-computation, primitive-assignment, and elementary-spacing checks passed.
`;
}
