import { app } from "electron";
import { ChildProcessWithoutNullStreams, spawn } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import readline from "node:readline";

type WorkerMessage = {
  id: string;
  type: "result" | "error" | "progress";
  payload?: unknown;
  error?: { message: string; traceback?: string };
};

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (reason?: unknown) => void;
  onProgress?: (payload: unknown) => void;
};

let sequence = 0;

export class WorkerClient {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending = new Map<string, PendingRequest>();
  private stderrBuffer: string[] = [];

  request<T>(op: string, payload: unknown, onProgress?: (payload: unknown) => void): Promise<T> {
    const id = `req_${Date.now()}_${++sequence}`;
    this.ensureStarted();
    const child = this.child;
    if (!child) {
      return Promise.reject(new Error("Worker process is unavailable."));
    }
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject, onProgress });
      child.stdin.write(JSON.stringify({ id, op, payload }) + "\n", "utf-8", (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  dispose(): void {
    for (const pending of this.pending.values()) {
      pending.reject(new Error("Worker process closed."));
    }
    this.pending.clear();
    if (this.child) {
      this.child.kill();
      this.child = null;
    }
  }

  private ensureStarted(): void {
    if (this.child) {
      return;
    }
    const { command, args, cwd, env } = resolveWorkerLaunch();
    this.child = spawn(command, args, {
      cwd,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true
    });
    const reader = readline.createInterface({ input: this.child.stdout });
    reader.on("line", (line) => this.handleLine(line));
    this.child.stderr.on("data", (chunk) => {
      this.stderrBuffer.push(String(chunk));
      if (this.stderrBuffer.length > 80) {
        this.stderrBuffer.shift();
      }
    });
    this.child.on("exit", (code, signal) => {
      const detail = this.stderrBuffer.join("").trim();
      const error = new Error(`Worker exited with code=${code} signal=${signal}${detail ? `\n${detail}` : ""}`);
      for (const pending of this.pending.values()) {
        pending.reject(error);
      }
      this.pending.clear();
      this.child = null;
    });
  }

  private handleLine(line: string): void {
    let message: WorkerMessage;
    try {
      message = JSON.parse(line) as WorkerMessage;
    } catch {
      return;
    }
    const pending = this.pending.get(message.id);
    if (!pending) {
      return;
    }
    if (message.type === "progress") {
      pending.onProgress?.(message.payload);
      return;
    }
    this.pending.delete(message.id);
    if (message.type === "error") {
      const error = new Error(message.error?.message || "Unknown worker error");
      (error as Error & { traceback?: string }).traceback = message.error?.traceback;
      pending.reject(error);
      return;
    }
    pending.resolve(message.payload);
  }
}

function resolveWorkerLaunch(): { command: string; args: string[]; cwd: string; env: NodeJS.ProcessEnv } {
  if (app.isPackaged) {
    const executable = path.join(process.resourcesPath, "worker", "millikan-desktop-worker.exe");
    return {
      command: executable,
      args: [],
      cwd: path.dirname(executable),
      env: process.env
    };
  }
  const projectRoot = findProjectRoot();
  const python = process.env.MILLIKAN_PYTHON || findPython(projectRoot);
  const pythonPath = [path.join(projectRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  return {
    command: python,
    args: ["-m", "millikan_ai.desktop_worker"],
    cwd: projectRoot,
    env: { ...process.env, PYTHONPATH: pythonPath }
  };
}

function findProjectRoot(): string {
  if (process.env.MILLIKAN_PROJECT_ROOT) {
    return process.env.MILLIKAN_PROJECT_ROOT;
  }
  const candidates: string[] = [];
  let cursor = app.getAppPath();
  for (let index = 0; index < 8; index += 1) {
    candidates.push(cursor);
    const parent = path.dirname(cursor);
    if (parent === cursor) {
      break;
    }
    cursor = parent;
  }
  for (const candidate of [...candidates]) {
    if (path.basename(path.dirname(candidate)) === ".worktrees") {
      candidates.push(path.dirname(path.dirname(candidate)));
    }
  }
  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "src", "millikan_ai", "api.py"))) {
      return candidate;
    }
  }
  return path.resolve(app.getAppPath(), "..", "..");
}

function findPython(projectRoot: string): string {
  const local = path.join(projectRoot, ".venv", "Scripts", "python.exe");
  const parentLocal = path.join(projectRoot, "..", ".venv", "Scripts", "python.exe");
  const worktreeParentLocal = path.join(projectRoot, "..", "..", ".venv", "Scripts", "python.exe");
  for (const candidate of [local, parentLocal, worktreeParentLocal]) {
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return process.platform === "win32" ? "python.exe" : "python3";
}
