import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const desktopRoot = process.cwd();
const projectRoot = findProjectRoot(desktopRoot);
const outDir = path.join(desktopRoot, "dist-worker");
const python = process.env.MILLIKAN_PYTHON || findPython(projectRoot);

fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(outDir, { recursive: true });

const args = [
  "-m",
  "PyInstaller",
  "--clean",
  "--noconfirm",
  "--onefile",
  "--name",
  "millikan-desktop-worker",
  "--distpath",
  outDir,
  "--workpath",
  path.join(desktopRoot, "build-worker"),
  "--specpath",
  path.join(desktopRoot, "build-worker"),
  "--paths",
  path.join(projectRoot, "src"),
  path.join(projectRoot, "src", "millikan_ai", "desktop_worker.py")
];

const result = spawnSync(python, args, {
  cwd: projectRoot,
  stdio: "inherit",
  env: {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
    PYTHONPATH: [path.join(projectRoot, "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter)
  }
});

if (result.status !== 0) {
  console.error("\nPyInstaller failed. Install it into the project .venv with:");
  console.error(`${python} -m pip install pyinstaller`);
  process.exit(result.status ?? 1);
}

function findProjectRoot(start) {
  const candidates = [];
  let cursor = start;
  for (let index = 0; index < 8; index += 1) {
    candidates.push(cursor);
    const parent = path.dirname(cursor);
    if (parent === cursor) break;
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
  throw new Error("Cannot locate project root.");
}

function findPython(root) {
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, "..", ".venv", "Scripts", "python.exe"),
    path.join(root, "..", "..", ".venv", "Scripts", "python.exe")
  ];
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python.exe" : "python3";
}
