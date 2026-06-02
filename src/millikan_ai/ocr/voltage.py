from __future__ import annotations

from dataclasses import dataclass
import re

import cv2
import numpy as np

from millikan_ai.calibration.grid import Roi


@dataclass(frozen=True)
class OcrReading:
    text: str
    voltage_V: float | None
    confidence: float
    source: str = "template_ocr"

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "voltage_V": self.voltage_V,
            "confidence": self.confidence,
            "source": self.source,
        }


def _normalize_glyph(image: np.ndarray) -> np.ndarray:
    _, binary = cv2.threshold(image, 20, 255, cv2.THRESH_BINARY)
    points = cv2.findNonZero(binary)
    canvas = np.zeros((42, 28), dtype=np.uint8)
    if points is None:
        return canvas
    x, y, w, h = cv2.boundingRect(points)
    glyph = binary[y : y + h, x : x + w]
    scale = min(24 / max(w, 1), 38 / max(h, 1))
    resized = cv2.resize(glyph, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
    y0 = (42 - resized.shape[0]) // 2
    x0 = (28 - resized.shape[1]) // 2
    canvas[y0 : y0 + resized.shape[0], x0 : x0 + resized.shape[1]] = resized
    return canvas


def _make_templates() -> dict[str, list[np.ndarray]]:
    templates: dict[str, list[np.ndarray]] = {}
    for char in "0123456789+-V":
        variants = []
        for scale in (0.95, 1.15, 1.35, 1.55):
            for thickness in (1, 2, 3):
                canvas = np.zeros((70, 54), dtype=np.uint8)
                cv2.putText(canvas, char, (4, 52), cv2.FONT_HERSHEY_SIMPLEX, scale, 255, thickness, cv2.LINE_AA)
                variants.append(_normalize_glyph(canvas))
        templates[char] = variants
    return templates


TEMPLATES = _make_templates()
VOLTAGE_TEXT_PATTERN = re.compile(r"^[+-]?\d{1,3}V?$")

SEVEN_SEGMENT_DIGITS = {
    frozenset("abcfed"): "0",
    frozenset("bc"): "1",
    frozenset("abged"): "2",
    frozenset("abgcd"): "3",
    frozenset("fgbc"): "4",
    frozenset("afgcd"): "5",
    frozenset("afgecd"): "6",
    frozenset("abc"): "7",
    frozenset("abcdefg"): "8",
    frozenset("abfgcd"): "9",
}


def preprocess_voltage_roi(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # The instrument digits and grid are blue-purple; this mask suppresses warm reflections.
        color_mask = cv2.inRange(hsv, (95, 30, 45), (155, 255, 255))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if cv2.countNonZero(color_mask) > max(10, image.shape[0] * image.shape[1] * 0.002):
            gray = cv2.bitwise_and(gray, gray, mask=color_mask)
    else:
        gray = image
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def find_voltage_roi(frame: np.ndarray) -> Roi:
    height, width = frame.shape[:2]
    # Search the upper-right screen area. The camera position changes, so this is broad by design.
    sx0, sy0 = int(width * 0.45), 0
    sx1, sy1 = int(width * 0.95), int(height * 0.28)
    search = frame[sy0:sy1, sx0:sx1]
    hsv = cv2.cvtColor(search, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (95, 25, 45), (160, 255, 255))
    # Remove long grid lines; seven-segment digits are short broken components.
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (45, 3))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 35))
    grid_like = cv2.morphologyEx(mask, cv2.MORPH_OPEN, horizontal_kernel) | cv2.morphologyEx(mask, cv2.MORPH_OPEN, vertical_kernel)
    mask = cv2.subtract(mask, grid_like)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if area < 2 or h < 3 or w < 2:
            continue
        if w > 45 or h > 45:
            continue
        if x + w / 2 < search.shape[1] * 0.32:
            continue
        boxes.append((x, y, w, h))
    if not boxes:
        return Roi(int(width * 0.55), 0, int(width * 0.32), int(height * 0.12))
    rows: list[list[tuple[int, int, int, int]]] = []
    for box in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        cy = box[1] + box[3] / 2
        for row in rows:
            row_cy = sum(b[1] + b[3] / 2 for b in row) / len(row)
            if abs(cy - row_cy) <= 28:
                row.append(box)
                break
        else:
            rows.append([box])
    candidates = []
    for row in rows:
        xs = [x for x, _, _, _ in row] + [x + w for x, _, w, _ in row]
        ys = [y for _, y, _, _ in row] + [y + h for _, y, _, h in row]
        x_span = max(xs) - min(xs)
        if len(row) >= 2 and x_span >= 45:
            candidates.append((min(ys), min(xs), max(xs), min(ys), max(ys)))
    if not candidates:
        row = max(rows, key=len)
        xs = [x for x, _, _, _ in row] + [x + w for x, _, w, _ in row]
        ys = [y for _, y, _, _ in row] + [y + h for _, y, _, h in row]
        candidates.append((min(ys), min(xs), max(xs), min(ys), max(ys)))
    _, x_min, x_max, y_min, y_max = min(candidates, key=lambda item: item[0])
    row_width = x_max - x_min
    # Keep a generous horizontal band once the voltage row is found; component boxes may
    # miss broken seven-segment strokes under blur/reflection.
    x0 = max(0, x_min - max(40, row_width))
    x1 = min(search.shape[1], x_max + max(45, int(row_width * 0.35)))
    y0, y1 = max(0, y_min - 14), min(search.shape[0], y_max + 16)
    return Roi(sx0 + x0, sy0 + y0, x1 - x0, y1 - y0)


def _first_text_line(binary: np.ndarray) -> np.ndarray:
    projection = binary.mean(axis=1)
    rows = np.where(projection > max(8, projection.max(initial=0) * 0.15))[0]
    if len(rows) == 0:
        return binary
    groups: list[list[int]] = [[int(rows[0])]]
    for row in rows[1:]:
        if int(row) - groups[-1][-1] <= 5:
            groups[-1].append(int(row))
        else:
            groups.append([int(row)])
    best_score = -1.0
    best_group = groups[0]
    for group in groups:
        y0, y1 = max(0, group[0] - 4), min(binary.shape[0], group[-1] + 5)
        candidate = binary[y0:y1, :]
        contours, _ = cv2.findContours(candidate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = cv2.contourArea(contour)
            if area < 4 or h < 6 or w < 3:
                continue
            if h > candidate.shape[0] * 0.95 and w < 8:
                continue
            boxes.append((x, y, w, h))
        if boxes:
            xs = [x for x, _, _, _ in boxes] + [x + w for x, _, w, _ in boxes]
            span = max(xs) - min(xs)
        else:
            span = 0
        score = len(boxes) * 3.0 + min(span, binary.shape[1] * 0.5) / max(binary.shape[1], 1)
        score += min(len(group), 120) / 120.0
        if score > best_score:
            best_score = score
            best_group = group
    top = best_group
    y0, y1 = max(0, top[0] - 6), min(binary.shape[0], top[-1] + 7)
    return binary[y0:y1, :]


def _segments(binary: np.ndarray) -> list[np.ndarray]:
    line = _first_text_line(binary)
    column_projection = line.mean(axis=0)
    active = np.where(column_projection > max(5, column_projection.max(initial=0) * 0.08))[0]
    if len(active) == 0:
        return []
    groups: list[list[int]] = [[int(active[0])]]
    for col in active[1:]:
        if int(col) - groups[-1][-1] <= 6:
            groups[-1].append(int(col))
        else:
            groups.append([int(col)])
    boxes = []
    for group in groups:
        x0, x1 = group[0], group[-1]
        if x1 - x0 < 4:
            continue
        patch_cols = line[:, max(0, x0 - 2) : min(line.shape[1], x1 + 3)]
        points = cv2.findNonZero(patch_cols)
        if points is None:
            continue
        _, y, _, h = cv2.boundingRect(points)
        if h < 8:
            continue
        boxes.append((max(0, x0 - 2), y, min(line.shape[1], x1 + 3) - max(0, x0 - 2), h))
    chars = []
    for x, y, w, h in boxes:
        patch = line[max(0, y - 2) : min(line.shape[0], y + h + 2), max(0, x - 2) : min(line.shape[1], x + w + 2)]
        chars.append(cv2.resize(patch, (28, 42), interpolation=cv2.INTER_AREA))
    return chars


def _match_char(patch: np.ndarray) -> tuple[str, float]:
    candidate = _normalize_glyph(patch)
    contours, hierarchy = cv2.findContours(candidate, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hole_count = 0
    if hierarchy is not None:
        hole_count = sum(1 for item in hierarchy[0] if item[3] != -1)
    upper_right = float((candidate[8:21, 17:27] > 0).mean())
    lower_left = float((candidate[22:35, 1:11] > 0).mean())
    middle = float((candidate[18:25, 6:22] > 0).mean())
    best_char = ""
    best_score = -1.0
    for char, variants in TEMPLATES.items():
        for template in variants:
            intersection = np.logical_and(candidate > 0, template > 0).sum()
            union = np.logical_or(candidate > 0, template > 0).sum()
            iou = float(intersection / union) if union else 0.0
            corr = float(cv2.matchTemplate(candidate, template, cv2.TM_CCOEFF_NORMED)[0][0])
            score = 0.65 * iou + 0.35 * max(0.0, corr)
            if hole_count > 0 and char in {"1", "2", "3", "4", "5", "7", "+", "-", "V"}:
                score *= 0.75
            if hole_count == 0 and char in {"0", "6", "8", "9"}:
                score *= 0.90
            if char == "6" and upper_right > 0.18:
                score *= 0.78
            if char == "0" and middle > 0.28:
                score *= 0.82
            if char == "9" and lower_left > 0.18:
                score *= 0.78
            if score > best_score:
                best_char = char
                best_score = score
    fallback = _match_seven_segment_char(patch)
    if best_score < 0.45 and fallback[1] >= 0.95:
        return fallback
    return best_char, max(0.0, min(1.0, best_score))


def _match_seven_segment_char(patch: np.ndarray) -> tuple[str, float]:
    glyph = _normalize_glyph(patch)
    on = glyph > 0
    fill_ratio = float(on.mean())
    if fill_ratio > 0.42 or fill_ratio < 0.04:
        return "", 0.0
    regions = {
        "a": on[2:8, 6:22].mean(),
        "b": on[6:18, 18:27].mean(),
        "c": on[22:36, 18:27].mean(),
        "d": on[34:41, 6:22].mean(),
        "e": on[22:36, 1:10].mean(),
        "f": on[6:18, 1:10].mean(),
        "g": on[18:25, 6:22].mean(),
    }
    active = frozenset(segment for segment, value in regions.items() if value >= 0.12)
    inactive_values = [value for segment, value in regions.items() if segment not in active]
    active_values = [value for segment, value in regions.items() if segment in active]
    if active_values and inactive_values and (np.mean(active_values) - np.mean(inactive_values)) < 0.08:
        return "", 0.0
    if not active:
        return "", 0.0
    best_digit = ""
    best_distance = 99
    for expected, digit in SEVEN_SEGMENT_DIGITS.items():
        distance = len(active.symmetric_difference(expected))
        if distance < best_distance:
            best_distance = distance
            best_digit = digit
    confidence = max(0.0, 1.0 - best_distance / 5.0)
    # Plus and V are not seven-segment digits; keep them for fallback matching.
    return best_digit, confidence


def read_voltage_from_image(image: np.ndarray) -> OcrReading:
    binary = preprocess_voltage_roi(image)
    chars = []
    scores = []
    for patch in _segments(binary):
        char, score = _match_char(patch)
        if char:
            chars.append(char)
            scores.append(score)
    text = "".join(chars)
    candidate_text = text.strip()
    digits = ""
    if VOLTAGE_TEXT_PATTERN.match(candidate_text) and ("V" in candidate_text or candidate_text[:1] in "+-"):
        digits = candidate_text.rstrip("V")
    voltage = None
    if digits not in {"", "+", "-"}:
        try:
            voltage = float(digits)
        except ValueError:
            voltage = None
    confidence = float(np.mean(scores)) if scores else 0.0
    return OcrReading(text=text, voltage_V=voltage, confidence=confidence)


def read_voltage_from_frame(frame: np.ndarray, roi: Roi) -> OcrReading:
    return read_voltage_from_image(roi.crop(frame))
