import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { _electron as electron } from "playwright-core";

const appRoot = path.resolve(import.meta.dirname, "..");
const normalRoot = path.resolve(appRoot, "..", "..");
const executable = path.join(appRoot, "release", "win-unpacked", "密立根油滴实验.exe");
const video = process.env.MILLIKAN_SMOKE_VIDEO || path.resolve(normalRoot, "..", "media", "videos", "2u.mp4");
const python = process.env.MILLIKAN_SMOKE_PYTHON || path.join(normalRoot, ".venv", "Scripts", "python.exe");
assert.ok(fs.existsSync(executable), `packaged app not found: ${executable}`);
assert.ok(fs.existsSync(video), `smoke video not found: ${video}`);
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "millikan-electron-ipc-"));
const synthetic = path.join(tmp, "synthetic.mp4");
execFileSync(python, ["-c", "import sys; from pathlib import Path; from scripts.probe_packaged_worker import make_video; make_video(Path(sys.argv[1]))", synthetic], {
  cwd: normalRoot,
  env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" }
});
const overrides = {
  grid: { measurement_distance_m: 0.0015, mask_dilate_px: 1 },
  tracking: { minmass: 20, memory_frames: 4, grid_occlusion_radius_px: 1 },
  fit: { min_points: 8, min_duration_s: 0.4, min_displacement_px: 2, min_r2: 0.2 }
};
const app = await electron.launch({ executablePath: executable });
try {
  const window = await app.firstWindow();
  window.setDefaultTimeout(60000);
  await window.getByRole("button", { name: "选择视频", exact: true }).waitFor();
  // Stub only the native folder/file chooser; every operation uses the real preload,
  // Electron handler and packaged Python worker, without the renderer demo API.
  await app.evaluate(({ dialog }, selected) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [selected] });
  }, video);
  await window.getByRole("button", { name: "选择视频", exact: true }).click();
  await window.getByPlaceholder("拖入视频或粘贴绝对路径").waitFor();
  await window.waitForFunction(() => ![...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "开始处理").disabled);
  assert.equal(await window.getByPlaceholder("拖入视频或粘贴绝对路径").inputValue(), video);

  const checked = new Set();
  const invoke = async (method, payload) => {
    console.log(`IPC ${method}`);
    checked.add(method);
    return window.evaluate(({ method, payload }) => window.millikan[method](payload), { method, payload });
  };
  const initialized = await invoke("normalInitialize", { session_root: path.join(tmp, "session"), config_overrides: overrides });
  const session_root = initialized.session_root;
  const inspected = await invoke("normalInspectVideo", { video_path: synthetic });
  assert.equal(inspected.metadata.readable, true);
  await window.evaluate(() => {
    window.ipcSmokeProgress = [];
    window.millikan.onNormalProgress((event) => window.ipcSmokeProgress.push(event));
  });
  const prepared = await invoke("normalPrepareVideo", { session_root, video_path: synthetic, config_overrides: overrides });
  assert.equal(prepared.grid.valid, true);
  const boundary = await invoke("normalConfirmBoundary", { session_root, boundary: { zero_v_start_s: 0, zero_v_end_s: 3.8, source: "electron_smoke" } });
  assert.equal(boundary.active_video.state, "boundary_confirmed");

  const target = {
    session_root, balance_voltage_V: 239, balance_confirmed: true,
    target: { target_frame: 0, target_time_s: 0, source_center: { x: 92, y: 52 }, source_video_box: { x: 78, y: 38, width: 28, height: 28 } },
    parameter_overrides: overrides
  };
  const records = [];
  for (let index = 0; index < 3; index += 1) {
    const selected = await invoke("normalSelectTarget", { ...target, balance_voltage_V: 239 + index * 10, parameter_overrides: { ...overrides, physics: { air_viscosity_Pa_s: 1.83e-5 + index * 1e-7 } } });
    assert.equal(selected.active_video.state, "target_selected");
    const measured = await invoke("normalSaveMeasurement", { session_root, config_overrides: overrides });
    assert.ok(measured.record.q_C > 0 && measured.record.sigma_q_C > 0);
    assert.ok(measured.record.track_review_frames.length > 0);
    assert.ok(measured.record.crossings.length > 0);
    if (index === 0) {
      await assert.rejects(() => invoke("normalConfirmBoundary", { session_root, boundary: { zero_v_start_s: 0, zero_v_end_s: 3.8 } }), /当前步骤/);
    }
    for (const crossing of measured.record.crossings) {
      const payload = { session_root, record_id: measured.record.record_id, event_id: crossing.event_id };
      const review = await invoke("normalPrepareCrossingReview", payload);
      assert.ok(review.event.review_frames.length > 0);
      const reviewed = await invoke("normalReviewCrossing", { ...payload, result: "same_drop" });
      assert.equal(reviewed.record.crossings.find((event) => event.event_id === crossing.event_id).review_result, "same_drop");
    }
    const kept = await invoke("normalSelectRecord", { session_root, record_id: measured.record.record_id, kept: true });
    assert.equal(kept.counts.kept_valid, index + 1);
    records.push(measured.record.record_id);
    if (index < 2) {
      const next = await invoke("normalStartNextDroplet", { session_root, record_id: measured.record.record_id, mode: "same_video" });
      assert.equal(next.active_video.state, "boundary_confirmed");
      const adjusted = await invoke("normalConfirmBoundary", { session_root, boundary: { zero_v_start_s: 0, zero_v_end_s: 3.8 } });
      assert.equal(adjusted.active_video.state, "boundary_confirmed");
    }
  }
  const inversion = await invoke("normalRunInversion", { session_root, config_overrides: overrides });
  assert.equal(inversion.inversion.valid_q_count, 3);
  assert.ok(inversion.inversion.e_hat_C > 0 && inversion.inversion.sigma_e_C > 0);
  const exportRoot = path.join(tmp, "export");
  fs.mkdirSync(exportRoot);
  await app.evaluate(({ dialog }, selected) => {
    dialog.showOpenDialog = async () => ({ canceled: false, filePaths: [selected] });
  }, exportRoot);
  const exported = await invoke("normalExportSession", { session_root });
  assert.equal(exported.canceled, false);
  const destination = exported.package.destination;
  for (const file of ["normal_session_report.md", "normal_inversion.json", "export_manifest.json"]) {
    assert.ok(fs.existsSync(path.join(destination, file)), `export missing ${file}`);
  }
  assert.match(fs.readFileSync(path.join(destination, "normal_session_report.md"), "utf8"), /密立根油滴实验记录/);

  // Review rejection and explicit exclusion must preserve the accepted collection.
  const historical = await invoke("normalStartNextDroplet", { session_root, record_id: records[0], mode: "same_video" });
  assert.equal(historical.active_video.previous_balance_voltage_V, 239);
  assert.equal(historical.active_video.previous_parameter_overrides.physics.air_viscosity_Pa_s, 1.83e-5);
  assert.equal(historical.active_video.path, synthetic);
  await invoke("normalSelectTarget", target);
  const rejectedCandidate = await invoke("normalSaveMeasurement", { session_root, config_overrides: overrides });
  assert.ok(rejectedCandidate.record.crossings.length > 0);
  const rejected = await invoke("normalReviewCrossing", {
    session_root, record_id: rejectedCandidate.record.record_id,
    event_id: rejectedCandidate.record.crossings[0].event_id, result: "different_drop"
  });
  assert.equal(rejected.record.status, "rejected_crossing_identity");
  await assert.rejects(() => invoke("normalSelectRecord", { session_root, record_id: rejectedCandidate.record.record_id, kept: true }), /不能保留/);
  const excluded = await invoke("normalSelectRecord", { session_root, record_id: records[2], kept: false });
  assert.equal(excluded.counts.kept_valid, 2);
  const changedVideo = await invoke("normalStartNextDroplet", { session_root, mode: "different_video" });
  assert.equal(changedVideo.active_video, null);
  assert.equal(changedVideo.session.counts.kept_valid, 2);
  const progress = await window.evaluate(() => window.ipcSmokeProgress);
  assert.ok(progress.some((event) => event.operation === "prepare_video"));
  assert.ok(progress.some((event) => event.operation === "save_measurement"));
  assert.ok(progress.every((event) => !event.label.includes("\uFFFD")));
  assert.equal(checked.size, 12);
  console.log(JSON.stringify({ ok: true, checked_operations: checked.size, accepted_records: 3, crossing_rejection: true, export_verified: true }));
} finally {
  await app.close();
  fs.rmSync(tmp, { recursive: true, force: true });
}
