import { fmtCharge, fmtNumber, fmtPercentValue, fmtScientific } from "../src/lib/format";

describe("scientific formatting", () => {
  it("renders powers with typographic superscripts instead of e notation", () => {
    expect(fmtScientific(1.602176634e-19, 6)).toBe("1.602177 × 10⁻¹⁹");
    expect(fmtNumber(1.83e-5, 3)).toBe("1.83 × 10⁻⁵");
    expect(fmtScientific(-2.4e6, 2)).toBe("-2.4 × 10⁶");
  });

  it("keeps charge and charge uncertainty on the 10^-19 C scale", () => {
    expect(fmtCharge(1.45e-19, 4)).toBe("1.45 × 10⁻¹⁹ C");
    expect(fmtCharge(2.064e-21, 5)).toBe("0.02064 × 10⁻¹⁹ C");
  });

  it("formats backend percentage values without applying another factor of 100", () => {
    expect(fmtPercentValue(1.42356, 3)).toBe("1.424%");
  });
});
