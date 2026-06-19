import { contextBridge, ipcRenderer, webUtils } from "electron";

const api = {
  openVideoDialog: () => ipcRenderer.invoke("dialog:openVideo"),
  openRunDialog: () => ipcRenderer.invoke("dialog:openRun"),
  getDroppedFilePath: (file: File) => webUtils.getPathForFile(file),
  inspectVideo: (payload: unknown) => ipcRenderer.invoke("video:inspect", payload),
  detectPlatformBoundaries: (payload: unknown) => ipcRenderer.invoke("platform:detectBoundaries", payload),
  runAnalysis: (payload: unknown) => ipcRenderer.invoke("analysis:run", payload),
  runAutoAnalysis: (payload: unknown) => ipcRenderer.invoke("analysis:runAuto", payload),
  loadRun: (payload: unknown) => ipcRenderer.invoke("analysis:loadRun", payload),
  validateRun: (payload: unknown) => ipcRenderer.invoke("analysis:validate", payload),
  runDownstream: (payload: unknown) => ipcRenderer.invoke("downstream:run", payload),
  exportReport: (payload: unknown) => ipcRenderer.invoke("report:export", payload),
  normalInitialize: (payload: unknown) => ipcRenderer.invoke("normal:initialize", payload),
  normalInspectVideo: (payload: unknown) => ipcRenderer.invoke("normal:inspectVideo", payload),
  normalPrepareVideo: (payload: unknown) => ipcRenderer.invoke("normal:prepareVideo", payload),
  normalConfirmBoundary: (payload: unknown) => ipcRenderer.invoke("normal:confirmBoundary", payload),
  normalSelectTarget: (payload: unknown) => ipcRenderer.invoke("normal:selectTarget", payload),
  normalSaveMeasurement: (payload: unknown) => ipcRenderer.invoke("normal:saveMeasurement", payload),
  normalPrepareCrossingReview: (payload: unknown) => ipcRenderer.invoke("normal:prepareCrossingReview", payload),
  normalReviewCrossing: (payload: unknown) => ipcRenderer.invoke("normal:reviewCrossing", payload),
  normalSelectRecord: (payload: unknown) => ipcRenderer.invoke("normal:updateRecordSelection", payload),
  normalRunInversion: (payload: unknown) => ipcRenderer.invoke("normal:runInversion", payload),
  normalExportSession: (payload: unknown) => ipcRenderer.invoke("normal:exportSession", payload),
  setModeFullscreen: (enabled: boolean) => ipcRenderer.invoke("window:setModeFullscreen", enabled),
  openPath: (targetPath: string) => ipcRenderer.invoke("shell:openPath", targetPath),
  onAnalysisProgress: (callback: (progress: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: unknown) => callback(progress);
    ipcRenderer.on("analysis:progress", listener);
    return () => ipcRenderer.removeListener("analysis:progress", listener);
  },
  onNormalProgress: (callback: (progress: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: unknown) => callback(progress);
    ipcRenderer.on("normal:progress", listener);
    return () => ipcRenderer.removeListener("normal:progress", listener);
  }
};

contextBridge.exposeInMainWorld("millikan", api);

export type MillikanDesktopApi = typeof api;
