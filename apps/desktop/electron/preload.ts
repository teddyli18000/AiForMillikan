import { contextBridge, ipcRenderer } from "electron";

const api = {
  initializeApp: () => ipcRenderer.invoke("app:initialize"),
  runtimePaths: () => ipcRenderer.invoke("app:runtimePaths"),
  openVideoDialog: () => ipcRenderer.invoke("dialog:openVideo"),
  openRunDialog: () => ipcRenderer.invoke("dialog:openRun"),
  inspectVideo: (payload: unknown) => ipcRenderer.invoke("video:inspect", payload),
  detectPlatformBoundaries: (payload: unknown) => ipcRenderer.invoke("platform:detectBoundaries", payload),
  runAnalysis: (payload: unknown) => ipcRenderer.invoke("analysis:run", payload),
  runAutoAnalysis: (payload: unknown) => ipcRenderer.invoke("analysis:runAuto", payload),
  loadRun: (payload: unknown) => ipcRenderer.invoke("analysis:loadRun", payload),
  validateRun: (payload: unknown) => ipcRenderer.invoke("analysis:validate", payload),
  runDownstream: (payload: unknown) => ipcRenderer.invoke("downstream:run", payload),
  normalInitialize: (payload: unknown) => ipcRenderer.invoke("normal:initialize", payload),
  normalPrepareVideo: (payload: unknown) => ipcRenderer.invoke("normal:prepareVideo", payload),
  normalSaveMeasurement: (payload: unknown) => ipcRenderer.invoke("normal:saveMeasurement", payload),
  normalSelectRecord: (payload: unknown) => ipcRenderer.invoke("normal:selectRecord", payload),
  normalRunInversion: (payload: unknown) => ipcRenderer.invoke("normal:runInversion", payload),
  normalCreateQaFixture: (payload: unknown) => ipcRenderer.invoke("normal:createQaFixture", payload),
  normalExportSession: (payload: unknown) => ipcRenderer.invoke("normal:exportSession", payload),
  exportReport: (payload: unknown) => ipcRenderer.invoke("report:export", payload),
  openPath: (targetPath: string) => ipcRenderer.invoke("shell:openPath", targetPath),
  onAnalysisProgress: (callback: (progress: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: unknown) => callback(progress);
    ipcRenderer.on("analysis:progress", listener);
    return () => ipcRenderer.removeListener("analysis:progress", listener);
  }
};

contextBridge.exposeInMainWorld("millikan", api);

export type MillikanDesktopApi = typeof api;
