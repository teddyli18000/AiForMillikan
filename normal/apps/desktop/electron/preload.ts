import { contextBridge, ipcRenderer, webUtils } from "electron";

const api = {
  openVideoDialog: () => ipcRenderer.invoke("dialog:openVideo"),
  getDroppedFilePath: (file: File) => webUtils.getPathForFile(file),
  normalInitialize: (payload: unknown) => ipcRenderer.invoke("normal:initialize", payload),
  normalInspectVideo: (payload: unknown) => ipcRenderer.invoke("normal:inspectVideo", payload),
  normalPrepareVideo: (payload: unknown) => ipcRenderer.invoke("normal:prepareVideo", payload),
  normalConfirmBoundary: (payload: unknown) => ipcRenderer.invoke("normal:confirmBoundary", payload),
  normalSelectTarget: (payload: unknown) => ipcRenderer.invoke("normal:selectTarget", payload),
  normalSaveMeasurement: (payload: unknown) => ipcRenderer.invoke("normal:saveMeasurement", payload),
  normalPrepareCrossingReview: (payload: unknown) => ipcRenderer.invoke("normal:prepareCrossingReview", payload),
  normalReviewCrossing: (payload: unknown) => ipcRenderer.invoke("normal:reviewCrossing", payload),
  normalSelectRecord: (payload: unknown) => ipcRenderer.invoke("normal:updateRecordSelection", payload),
  normalStartNextDroplet: (payload: unknown) => ipcRenderer.invoke("normal:startNextDroplet", payload),
  normalRunInversion: (payload: unknown) => ipcRenderer.invoke("normal:runInversion", payload),
  normalExportSession: (payload: unknown) => ipcRenderer.invoke("normal:exportSession", payload),
  onNormalProgress: (callback: (progress: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, progress: unknown) => callback(progress);
    ipcRenderer.on("normal:progress", listener);
    return () => ipcRenderer.removeListener("normal:progress", listener);
  }
};

contextBridge.exposeInMainWorld("millikan", api);

export type MillikanNormalApi = typeof api;
