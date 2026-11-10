import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { _electron as electron } from "playwright-core";

const appRoot = path.resolve(import.meta.dirname, "..");
const executable = path.join(appRoot, "release", "win-unpacked", "密立根油滴实验.exe");
if (!fs.existsSync(executable)) {
  throw new Error(`packaged app not found: ${executable}. Run "npx electron-builder --win dir" first.`);
}

const video = process.env.MILLIKAN_SMOKE_VIDEO || path.resolve(appRoot, "..", "..", "..", "media", "videos", "2u.mp4");
if (!fs.existsSync(video)) {
  throw new Error(`smoke video not found: ${video}`);
}

const app = await electron.launch({ executablePath: executable });
try {
  const window = await app.firstWindow();
  await window.waitForSelector("text=选择视频", { timeout: 60000 });

  const metadata = await window.evaluate(async (videoPath) => {
    const response = await window.millikan.normalInspectVideo({ video_path: videoPath });
    return response.metadata;
  }, video);

  if (!metadata || metadata.readable !== true || !(metadata.frame_count > 0)) {
    throw new Error(`normalInspectVideo returned unusable metadata: ${JSON.stringify(metadata)}`);
  }
  console.log(JSON.stringify({ ok: true, app: "normal", metadata }));
} finally {
  await app.close();
}
