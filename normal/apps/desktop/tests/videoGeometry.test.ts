import { clientPointToVideoPoint, getContainedVideoMetrics, videoBoxToOverlayStyle } from "../src/components/normal/videoGeometry";

describe("Normal video selection geometry", () => {
  it("maps pointer and selection boxes through the video offset inside the overlay", () => {
    const overlayRect = { left: 100, top: 50, width: 1000, height: 700 };
    const videoRect = { left: 180, top: 160, width: 800, height: 450 };
    const metrics = getContainedVideoMetrics({
      overlayRect,
      videoRect,
      sourceWidth: 1920,
      sourceHeight: 1080
    });

    expect(metrics.scale).toBeCloseTo(800 / 1920);
    expect(metrics.displayLeft).toBeCloseTo(80);
    expect(metrics.displayTop).toBeCloseTo(110);

    const point = clientPointToVideoPoint(180 + 400, 160 + 225, overlayRect, metrics);
    expect(point?.x).toBeCloseTo(960);
    expect(point?.y).toBeCloseTo(540);

    const style = videoBoxToOverlayStyle({ x: 96, y: 108, width: 192, height: 216 }, metrics);
    expect(style.left).toBe("120px");
    expect(style.top).toBe("155px");
    expect(style.width).toBe("80px");
    expect(style.height).toBe("90px");
  });

  it("keeps letterboxed video content aligned when the video element aspect differs", () => {
    const overlayRect = { left: 20, top: 40, width: 1000, height: 700 };
    const videoRect = { left: 120, top: 90, width: 800, height: 600 };
    const metrics = getContainedVideoMetrics({
      overlayRect,
      videoRect,
      sourceWidth: 1920,
      sourceHeight: 1080
    });

    expect(metrics.displayLeft).toBeCloseTo(100);
    expect(metrics.displayTop).toBeCloseTo(125);
    expect(metrics.displayWidth).toBeCloseTo(800);
    expect(metrics.displayHeight).toBeCloseTo(450);

    expect(clientPointToVideoPoint(120 + 20, 90 + 20, overlayRect, metrics)).toBeNull();
    expect(clientPointToVideoPoint(120 + 20, 90 + 20, overlayRect, metrics, { clamp: true })).toEqual({ x: 48, y: 0 });
  });
});
