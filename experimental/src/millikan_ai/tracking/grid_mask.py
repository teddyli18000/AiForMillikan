from __future__ import annotations

import cv2
import numpy as np

from millikan_ai.calibration.grid import GridCalibration, Roi


GRID_SAMPLE_FRAMES = 40
GRID_SAMPLE_STRIDE = 3
GRID_MIN_HORIZONTAL_LINE_LEN_PX = 600
GRID_MIN_VERTICAL_LINE_LEN_PX = 360
GRID_MASK_DILATE_PX = 5
GRID_INPAINT_RADIUS = 4
GRID_MASK_MIN_COVERAGE = 0.005
GRID_MASK_MAX_COVERAGE = 0.45
GRID_MASK_HARD_MAX_COVERAGE = 0.45
GRID_TOPHAT_KERNEL = 31
GRID_ADAPTIVE_BLOCK_SIZE = 51
GRID_ADAPTIVE_BRIGHT_C = 8
GRID_TOPHAT_PERCENTILE = 75.0
GRID_MIN_TOPHAT_RESPONSE = 8


def ensure_odd(value: int, minimum: int = 3) -> int:
    value = max(int(value), int(minimum))
    if value % 2 == 0:
        value += 1
    return value


def crop_frame_to_roi(frame, roi):
    if roi is None:
        return frame
    x, y, w, h = roi
    frame_h, frame_w = frame.shape[:2]
    if w <= 0 or h <= 0:
        raise ValueError(f"ROI width and height must be positive, got {roi}")
    if x < 0 or y < 0 or x + w > frame_w or y + h > frame_h:
        raise ValueError(f"ROI out of frame bounds: ROI={roi}, frame_size={(frame_w, frame_h)}")
    return frame[y : y + h, x : x + w]


def read_grid_sample_bgr_frames(
    video_path,
    start_frame: int = 0,
    max_frames: int | None = None,
    roi=None,
):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    start_frame = max(0, int(start_frame))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    samples = []
    local_frame_index = 0
    while len(samples) < GRID_SAMPLE_FRAMES:
        if max_frames is not None and local_frame_index >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        if local_frame_index % GRID_SAMPLE_STRIDE == 0:
            samples.append(crop_frame_to_roi(frame, roi))
        local_frame_index += 1
    cap.release()
    if not samples:
        raise RuntimeError(f"Cannot read frames for grid mask from {video_path}")
    return samples


def build_static_bright_grid_mask_from_bgr_samples(bgr_samples):
    if not bgr_samples:
        raise ValueError("bgr_samples must not be empty")
    first_shape = bgr_samples[0].shape
    for index, frame in enumerate(bgr_samples):
        if frame.shape != first_shape:
            raise ValueError(f"Grid mask sample frame sizes differ: frame0={first_shape}, frame{index}={frame.shape}")

    stack = np.stack(bgr_samples, axis=0).astype(np.uint8)
    background_bgr = np.median(stack, axis=0).astype(np.uint8)
    gray = cv2.cvtColor(background_bgr, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray_blur = cv2.GaussianBlur(gray_eq, (3, 3), 0)

    tophat_kernel_size = ensure_odd(GRID_TOPHAT_KERNEL)
    adaptive_block_size = ensure_odd(GRID_ADAPTIVE_BLOCK_SIZE)
    tophat_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (tophat_kernel_size, tophat_kernel_size))
    tophat = cv2.morphologyEx(gray_blur, cv2.MORPH_TOPHAT, tophat_kernel)
    nz = tophat[tophat > 0]
    percentile_threshold = float(np.percentile(nz, float(GRID_TOPHAT_PERCENTILE))) if nz.size else 0.0
    tophat_threshold = max(float(GRID_MIN_TOPHAT_RESPONSE), percentile_threshold)
    bright_seed_tophat = np.where(tophat >= tophat_threshold, 255, 0).astype(np.uint8)
    bright_seed_adaptive = cv2.adaptiveThreshold(
        gray_blur,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        adaptive_block_size,
        -int(GRID_ADAPTIVE_BRIGHT_C),
    )
    small_clean_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    bright_seed_tophat = cv2.morphologyEx(bright_seed_tophat, cv2.MORPH_OPEN, small_clean_kernel, iterations=1)
    bright_seed_adaptive = cv2.morphologyEx(bright_seed_adaptive, cv2.MORPH_OPEN, small_clean_kernel, iterations=1)
    bright_seed_combined = cv2.bitwise_or(bright_seed_tophat, bright_seed_adaptive)

    height, width = bright_seed_combined.shape[:2]
    horizontal_len = max(int(GRID_MIN_HORIZONTAL_LINE_LEN_PX), width // 12)
    vertical_len = max(int(GRID_MIN_VERTICAL_LINE_LEN_PX), height // 8)
    horizontal_seed = cv2.morphologyEx(
        bright_seed_combined,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3)),
        iterations=1,
    )
    vertical_seed = cv2.morphologyEx(
        bright_seed_combined,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 15)),
        iterations=1,
    )
    horizontal_lines = cv2.morphologyEx(
        horizontal_seed,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_len, 3)),
        iterations=1,
    )
    vertical_lines = cv2.morphologyEx(
        vertical_seed,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, vertical_len)),
        iterations=1,
    )
    grid_mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
    if GRID_MASK_DILATE_PX > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * GRID_MASK_DILATE_PX + 1, 2 * GRID_MASK_DILATE_PX + 1))
        grid_mask = cv2.dilate(grid_mask, kernel, iterations=1)
    grid_mask = np.where(grid_mask > 0, 255, 0).astype(np.uint8)
    stats = {
        "tophat_threshold": float(tophat_threshold),
        "tophat_percentile_threshold": float(percentile_threshold),
        "horizontal_len": float(horizontal_len),
        "vertical_len": float(vertical_len),
        "coverage": float(np.count_nonzero(grid_mask)) / float(grid_mask.size),
    }
    return grid_mask, stats


def build_static_grid_mask(
    video_path,
    start_frame: int = 0,
    max_frames: int | None = None,
    roi=None,
):
    bgr_samples = read_grid_sample_bgr_frames(video_path, start_frame=start_frame, max_frames=max_frames, roi=roi)
    grid_mask, stats = build_static_bright_grid_mask_from_bgr_samples(bgr_samples)
    if stats["coverage"] > GRID_MASK_HARD_MAX_COVERAGE:
        return None
    return grid_mask


def build_grid_mask_from_calibration(shape: tuple[int, int], grid: GridCalibration | None, dilate_px: int = 0) -> np.ndarray | None:
    if grid is None:
        return None
    height, width = shape
    mask = np.zeros((height, width), dtype=np.uint8)
    for x in grid.grid_lines_x:
        cv2.line(mask, (int(round(x)), 0), (int(round(x)), height - 1), 255, 1)
    for y in grid.grid_lines_y:
        cv2.line(mask, (0, int(round(y))), (width - 1, int(round(y))), 255, 1)
    if np.count_nonzero(mask) == 0:
        return None
    if dilate_px > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * int(dilate_px) + 1, 2 * int(dilate_px) + 1))
        mask = cv2.dilate(mask, kernel, iterations=1)
    return mask


def remove_static_grid_from_gray(gray, grid_mask):
    if grid_mask is None:
        return gray
    if gray.shape[:2] != grid_mask.shape[:2]:
        raise ValueError(f"grid_mask shape mismatch: frame={gray.shape[:2]}, mask={grid_mask.shape[:2]}")
    mask = np.where(grid_mask > 0, 255, 0).astype(np.uint8)
    if np.count_nonzero(mask) == 0:
        return gray
    return cv2.inpaint(gray, mask, inpaintRadius=GRID_INPAINT_RADIUS, flags=cv2.INPAINT_TELEA)
