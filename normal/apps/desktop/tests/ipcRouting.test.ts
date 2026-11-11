const mocks = vi.hoisted(() => ({
  handlers: new Map<string, (...args: any[]) => unknown>(),
  workerRequest: vi.fn(),
  showOpenDialog: vi.fn()
}));

vi.mock("electron", () => ({
  app: {
    whenReady: () => Promise.resolve(),
    on: vi.fn(),
    quit: vi.fn(),
    isPackaged: false
  },
  BrowserWindow: class {
    static getAllWindows() {
      return [];
    }

    center() {}
    loadURL() { return Promise.resolve(); }
    loadFile() { return Promise.resolve(); }
    once() {}
    maximize() {}
    show() {}
  },
  dialog: { showOpenDialog: mocks.showOpenDialog },
  ipcMain: {
    handle(channel: string, handler: (...args: any[]) => unknown) {
      mocks.handlers.set(channel, handler);
    }
  },
  screen: { getPrimaryDisplay: () => ({ workAreaSize: { width: 1920, height: 1080 } }) },
  shell: { openPath: vi.fn() }
}));

vi.mock("../electron/workerClient", () => ({
  WorkerClient: class {
    request(...args: unknown[]) {
      return mocks.workerRequest(...args);
    }

    dispose() {}
  }
}));

import "../electron/main";

const workerRoutes = [
  ["normal:initialize", "normal.initialize", false],
  ["normal:inspectVideo", "normal.inspectVideo", false],
  ["normal:prepareVideo", "normal.prepareVideo", true],
  ["normal:confirmBoundary", "normal.confirmBoundary", false],
  ["normal:selectTarget", "normal.selectTarget", false],
  ["normal:saveMeasurement", "normal.saveMeasurement", true],
  ["normal:prepareCrossingReview", "normal.prepareCrossingReview", false],
  ["normal:reviewCrossing", "normal.reviewCrossing", false],
  ["normal:updateRecordSelection", "normal.updateRecordSelection", false],
  ["normal:startNextDroplet", "normal.startNextDroplet", false],
  ["normal:runInversion", "normal.runInversion", true],
  ["normal:exportSession", "normal.exportSession", false]
] as const;

describe("Normal Electron worker IPC routes", () => {
  beforeAll(async () => {
    await vi.waitFor(() => expect(mocks.handlers.size).toBeGreaterThan(0));
  });

  beforeEach(() => {
    mocks.workerRequest.mockReset().mockResolvedValue({});
    mocks.showOpenDialog.mockReset().mockResolvedValue({ canceled: false, filePaths: ["C:/reports"] });
  });

  it.each(workerRoutes)("forwards %s to worker operation %s", async (channel, operation, hasProgress) => {
    const handler = mocks.handlers.get(channel);
    expect(handler).toBeDefined();

    const payload = { route: channel, session_root: "session-root" };
    const event = { sender: { send: vi.fn() } };
    await handler!(event, payload);

    expect(mocks.workerRequest).toHaveBeenCalledTimes(1);
    const [actualOperation, actualPayload, progress] = mocks.workerRequest.mock.calls[0];
    expect(actualOperation).toBe(operation);
    if (channel === "normal:exportSession") {
      expect(actualPayload).toEqual({ session_root: "session-root", export_root: "C:/reports" });
    } else {
      expect(actualPayload).toBe(payload);
    }

    if (hasProgress) {
      const progressEvent = { task: "测试进度" };
      expect(progress).toEqual(expect.any(Function));
      progress(progressEvent);
      expect(event.sender.send).toHaveBeenCalledWith("normal:progress", progressEvent);
    } else {
      expect(mocks.workerRequest.mock.calls[0]).toHaveLength(2);
      expect(event.sender.send).not.toHaveBeenCalled();
    }
  });
});
