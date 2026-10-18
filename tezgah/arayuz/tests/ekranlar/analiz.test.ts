// SPEC 47 K23 (analiz kısmı) — Analiz ekranının saf yardımcıları (src/ekranlar/analiz_yardim.ts).
// Beklenen değerler elle: renk ölçeği doğrusal ve eşit aralıklı duraklı, deforme konumu x + s·u.

import { describe, expect, it } from "vitest";
import { deformeKonum, type Renk, renkOlcegi, sondaOlcegi } from "../../src/ekranlar/analiz_yardim";

const MAVI: Renk = [0, 0, 1];
const YESIL: Renk = [0, 1, 0];
const KIRMIZI: Renk = [1, 0, 0];
const UC: readonly Renk[] = [MAVI, YESIL, KIRMIZI];

function yakin(a: Renk, b: Renk, tol = 1e-12): void {
  expect(a).toHaveLength(3);
  for (let i = 0; i < 3; i++) expect(Math.abs(a[i] - b[i])).toBeLessThanOrEqual(tol);
}

describe("renkOlcegi", () => {
  it("min → ilk renk, max → son renk", () => {
    yakin(renkOlcegi(-5, -5, 15, UC), MAVI);
    yakin(renkOlcegi(15, -5, 15, UC), KIRMIZI);
  });

  it("duraklar eşit aralıklı, aralarında doğrusal", () => {
    yakin(renkOlcegi(5, -5, 15, UC), YESIL);
    yakin(renkOlcegi(0, -5, 15, UC), [0, 0.5, 0.5]);
    yakin(renkOlcegi(12.5, -5, 15, UC), [0.75, 0.25, 0]);
    yakin(renkOlcegi(0.25, 0, 1, [MAVI, KIRMIZI]), [0.25, 0, 0.75]);
  });

  it("aralık dışı değer uca kırpılır", () => {
    yakin(renkOlcegi(-100, 0, 1, UC), MAVI);
    yakin(renkOlcegi(100, 0, 1, UC), KIRMIZI);
    yakin(renkOlcegi(Number.POSITIVE_INFINITY, 0, 1, UC), KIRMIZI);
    yakin(renkOlcegi(Number.NEGATIVE_INFINITY, 0, 1, UC), MAVI);
  });

  it("min = max → tek renk (ilk renk), NaN yok", () => {
    for (const d of [3, 2, 4, 0]) {
      const r = renkOlcegi(d, 3, 3, UC);
      yakin(r, MAVI);
      expect(r.every((c) => Number.isFinite(c))).toBe(true);
    }
  });

  it("çıktı 0..1 içinde, NaN yok", () => {
    for (let k = 0; k <= 200; k++) {
      const r = renkOlcegi(-10 + k * 0.17, -3, 17, UC);
      expect(r.every((c) => Number.isFinite(c) && c >= 0 && c <= 1)).toBe(true);
    }
  });

  it("NaN girdi → Error", () => {
    expect(() => renkOlcegi(Number.NaN, 0, 1, UC)).toThrow(Error);
  });
});

describe("deformeKonum", () => {
  it("x + s·u, düz dizide, girdiyi değiştirmeden", () => {
    const x = new Float32Array([0, 0, 0, 10, 20, 30]);
    const u = new Float32Array([1, -2, 0.5, 0, 0.25, -1]);
    const x0 = x.slice();
    const u0 = u.slice();
    const y = deformeKonum(x, u, 4);
    expect(y).toBeInstanceOf(Float32Array);
    expect(Array.from(y)).toEqual([4, -8, 2, 10, 21, 26]);
    expect(Array.from(x)).toEqual(Array.from(x0));
    expect(Array.from(u)).toEqual(Array.from(u0));
  });

  it("s = 0 → x", () => {
    const x = new Float32Array([1.5, -2, 3, 4, 5, 6]);
    expect(Array.from(deformeKonum(x, new Float32Array(6).fill(7), 0))).toEqual(Array.from(x));
  });

  it("boy farkı → Error", () => {
    expect(() => deformeKonum(new Float32Array(6), new Float32Array(3), 1)).toThrow(Error);
  });
});

describe("sondaOlcegi", () => {
  it("yalnız içerideki noktaların [min, max]'ı", () => {
    const d = new Float64Array([100, -3, 7, 2.5, -50]);
    const ic = new Uint8Array([0, 1, 1, 1, 0]);
    expect(sondaOlcegi(d, ic)).toEqual([-3, 7]);
  });

  it("tek nokta → [d, d]", () => {
    expect(sondaOlcegi(new Float64Array([9, 4]), new Uint8Array([0, 1]))).toEqual([4, 4]);
  });

  it("içeride nokta yok → null", () => {
    expect(sondaOlcegi(new Float64Array([1, 2]), new Uint8Array([0, 0]))).toBeNull();
    expect(sondaOlcegi(new Float64Array([]), new Uint8Array([]))).toBeNull();
  });
});
