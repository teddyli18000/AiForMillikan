import { describe, expect, it } from "vitest";
import { createUtf8WorkerEnv, Utf8StreamDecoder } from "../electron/utf8StreamDecoder";

describe("Utf8StreamDecoder", () => {
  it("preserves a Chinese character split across pipe chunks", () => {
    const decoder = new Utf8StreamDecoder();
    const bytes = Buffer.from("正在处理：σ = 10⁻¹⁹ C", "utf8");
    const split = bytes.indexOf(Buffer.from("在", "utf8")) + 1;

    const text = decoder.write(bytes.subarray(0, split)) + decoder.write(bytes.subarray(split)) + decoder.end();

    expect(text).toBe("正在处理：σ = 10⁻¹⁹ C");
    expect(text).not.toContain("\uFFFD");
  });

  it("forces the Python worker process to use UTF-8 standard streams", () => {
    const env = createUtf8WorkerEnv({ PYTHONIOENCODING: "cp1252", PYTHONUTF8: "0" });

    expect(env.PYTHONIOENCODING).toBe("utf-8");
    expect(env.PYTHONUTF8).toBe("1");
  });
});
