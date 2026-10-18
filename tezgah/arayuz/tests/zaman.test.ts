// SPEC 24 K7 — zaman ↔ indeks, şerit ölçeği, onay işareti adımı, kıvılcım grafiği (src/zaman.ts).
// Beklenen değerler belgedeki tanımlardan elle hesaplanmıştır.

import { describe, expect, it } from "vitest";
import { idxAt, kivilcim, konumAt, pxZaman, tickAdimi, zamanPx } from "../src/zaman";

/** Doğrusal tarama: k(t) = max{k : T[k] ≤ t}, t < T[0] → 0. */
function idxTarama(t: number, T: ArrayLike<number>): number {
  let k = 0;
  for (let i = 0; i < T.length; i++) if (T[i] <= t) k = i;
  return k;
}

describe("idxAt", () => {
  const T = [0, 1, 2, 3];

  it("iç noktalar ve tam eşitlik", () => {
    expect(idxAt(0, T)).toBe(0);
    expect(idxAt(0.5, T)).toBe(0);
    expect(idxAt(1, T)).toBe(1);
    expect(idxAt(2.999, T)).toBe(2);
    expect(idxAt(3, T)).toBe(3);
  });

  it("t < t₀ → 0, t > t_son → son indeks", () => {
    expect(idxAt(-5, T)).toBe(0);
    expect(idxAt(10, T)).toBe(3);
    expect(idxAt(-1, [2, 4])).toBe(0);
  });

  it("eşit süreli noktalarda en büyük k", () => {
    const E = [0, 1, 1, 1, 2];
    expect(idxAt(1, E)).toBe(3);
    expect(idxAt(0.999, E)).toBe(0);
    expect(idxAt(1.5, E)).toBe(3);
    expect(idxAt(0, [0, 0, 0])).toBe(2);
    expect(idxAt(2, [0, 2, 2])).toBe(2);
  });

  it("tek noktalı dizi", () => {
    expect(idxAt(-1, [5])).toBe(0);
    expect(idxAt(5, [5])).toBe(0);
    expect(idxAt(7, [5])).toBe(0);
  });

  it("typed array ile ve doğrusal taramayla aynı (rastgele, sabit tohum)", () => {
    let s = 12345;
    const rnd = () => ((s = (s * 1103515245 + 12345) % 2147483648) / 2147483648);
    const n = 2000;
    const F = new Float64Array(n);
    for (let i = 1; i < n; i++) F[i] = F[i - 1] + (rnd() < 0.2 ? 0 : rnd()); // eşit süreler dahil
    for (let j = 0; j < 500; j++) {
      const t = -1 + rnd() * (F[n - 1] + 2);
      expect(idxAt(t, F)).toBe(idxTarama(t, F));
    }
    for (let i = 0; i < n; i += 37) expect(idxAt(F[i], F)).toBe(idxTarama(F[i], F));
  });

  it("boş dizi ya da sonlu olmayan t → Error", () => {
    expect(() => idxAt(0, [])).toThrow();
    expect(() => idxAt(NaN, T)).toThrow();
    expect(() => idxAt(Infinity, T)).toThrow();
    expect(() => idxAt(-Infinity, T)).toThrow();
  });
});

describe("konumAt", () => {
  const T = [0, 2, 4];
  const P = new Float32Array([0, 0, 0, 10, 0, 0, 10, 20, 0]);

  it("k ile k+1 arasında doğrusal ara değer", () => {
    expect(konumAt(1, T, P)).toEqual([5, 0, 0]);
    expect(konumAt(3, T, P)).toEqual([10, 10, 0]);
    expect(konumAt(2, T, P)).toEqual([10, 0, 0]);
  });

  it("uçlarda kırpılır", () => {
    expect(konumAt(-1, T, P)).toEqual([0, 0, 0]);
    expect(konumAt(4, T, P)).toEqual([10, 20, 0]);
    expect(konumAt(99, T, P)).toEqual([10, 20, 0]);
  });

  it("eşit süreli noktalarda son nokta (sıçrama), bölme yok", () => {
    const T2 = [0, 1, 1, 2];
    const P2 = new Float32Array([0, 0, 0, 1, 0, 0, 5, 5, 5, 7, 5, 5]);
    expect(konumAt(1, T2, P2)).toEqual([5, 5, 5]);
    expect(konumAt(1.5, T2, P2)).toEqual([6, 5, 5]);
    const p = konumAt(0.5, T2, P2);
    expect(p.every(Number.isFinite)).toBe(true);
    expect(p).toEqual([0.5, 0, 0]);
  });

  it("ara değer yolun dışına çıkmaz (iki uç arasında)", () => {
    for (let t = 0; t <= 4; t += 0.125) {
      const [x, y, z] = konumAt(t, T, P);
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(10);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(20);
      expect(z).toBe(0);
      if (t <= 2) expect(y).toBe(0);
      else expect(x).toBe(10);
    }
  });
});

describe("zamanPx / pxZaman", () => {
  it("doğrusal ölçek", () => {
    expect(zamanPx(5, 0, 10, 200)).toBe(100);
    expect(zamanPx(12, 2, 22, 400)).toBe(200);
    expect(zamanPx(0, 0, 10, 200)).toBe(0);
    expect(zamanPx(10, 0, 10, 200)).toBe(200);
  });

  it("[0, genişlik]'e kırpılır", () => {
    expect(zamanPx(-3, 0, 10, 200)).toBe(0);
    expect(zamanPx(30, 0, 10, 200)).toBe(200);
  });

  it("t1 ≤ t0 → Error", () => {
    expect(() => zamanPx(1, 5, 5, 200)).toThrow();
    expect(() => zamanPx(1, 5, 4, 200)).toThrow();
  });

  it("pxZaman tersidir ve [t0, t1]'e kırpılır", () => {
    expect(pxZaman(100, 0, 10, 200)).toBe(5);
    expect(pxZaman(-50, 0, 10, 200)).toBe(0);
    expect(pxZaman(999, 0, 10, 200)).toBe(10);
    for (let t = 2; t <= 22; t += 0.75) {
      expect(pxZaman(zamanPx(t, 2, 22, 640), 2, 22, 640)).toBeCloseTo(t, 9);
    }
  });
});

describe("tickAdimi", () => {
  /** {1, 2, 5}·10^m dizisinden mi? */
  function dizide(a: number): boolean {
    const m = Math.floor(Math.log10(a) + 1e-9);
    const r = a / 10 ** m;
    return [1, 2, 5, 10].some((c) => Math.abs(r - c) < 1e-9);
  }

  it("elle hesaplanan değerler", () => {
    // 100 s, 1000 px → 10 px/s; ≥ 60 px için adım ≥ 6 s → 10
    expect(tickAdimi(100, 1000)).toBe(10);
    // 10 s, 1000 px → 100 px/s; adım ≥ 0.6 → 1
    expect(tickAdimi(10, 1000)).toBe(1);
    // 3600 s, 400 px → 1/9 px/s; adım ≥ 540 → 1000
    expect(tickAdimi(3600, 400)).toBe(1000);
    // 1 s, 1000 px → adım ≥ 0.06 → 0.1
    expect(tickAdimi(1, 1000)).toBeCloseTo(0.1, 12);
    // 100 s, 1000 px, minPx 25 → adım ≥ 2.5 → 5
    expect(tickAdimi(100, 1000, 25)).toBe(5);
    // 100 s, 1000 px, minPx 15 → adım ≥ 1.5 → 2
    expect(tickAdimi(100, 1000, 15)).toBe(2);
  });

  it("sınır dahil: tam minPx aralık yeterli", () => {
    // 100 s, 1000 px, minPx 50 → adım ≥ 5 → 5 (aralık tam 50 px)
    expect(tickAdimi(100, 1000, 50)).toBe(5);
    expect(tickAdimi(100, 1000, 20)).toBe(2);
  });

  it("en küçük uygun adım (özellik)", () => {
    for (const sure of [0.37, 4.2, 59, 333, 7200, 86400]) {
      for (const g of [320, 400, 1440]) {
        const a = tickAdimi(sure, g);
        expect(dizide(a)).toBe(true);
        expect((a * g) / sure).toBeGreaterThanOrEqual(60 - 1e-9);
        // dizide bir önceki aday yetersiz olmalı
        const m = Math.floor(Math.log10(a) + 1e-9);
        const r = Math.round(a / 10 ** m);
        const onceki = r === 1 ? 5 * 10 ** (m - 1) : r === 2 ? 10 ** m : 2 * 10 ** m;
        expect((onceki * g) / sure).toBeLessThan(60);
      }
    }
  });

  it("geçersiz girdi → Error", () => {
    expect(() => tickAdimi(0, 1000)).toThrow();
    expect(() => tickAdimi(10, 0)).toThrow();
    expect(() => tickAdimi(10, 1000, 0)).toThrow();
    expect(() => tickAdimi(-1, 1000)).toThrow();
  });
});

describe("kivilcim", () => {
  it("kova başına en büyük değer", () => {
    // [0, 4] → iki kova: [0, 2) ve [2, 4]
    const T = [0, 0.5, 1.5, 2.5, 4];
    const Y = [1, 5, 2, 0, 3];
    const K = kivilcim(T, Y, 2);
    expect(K).toBeInstanceOf(Float32Array);
    expect(Array.from(K)).toEqual([5, 3]);
  });

  it("son nokta (t = T[son]) son kovaya düşer", () => {
    expect(Array.from(kivilcim([0, 1, 4], [0, 0, 9], 4))).toEqual([0, 0, 0, 9]);
  });

  it("boş kova bir önceki kovanın değerini alır", () => {
    const T = [0, 0.1, 3.9, 4];
    const Y = [2, 7, 1, 4];
    expect(Array.from(kivilcim(T, Y, 4))).toEqual([7, 7, 7, 4]);
  });

  it("tek kova: genel en büyük", () => {
    expect(Array.from(kivilcim([0, 1, 2], [0.25, 0.75, 0.5], 1))).toEqual([0.75]);
  });

  it("uzunluk kova sayısı", () => {
    const n = 1000;
    const T = Float64Array.from({ length: n }, (_, i) => i * 0.01);
    const Y = Float32Array.from({ length: n }, (_, i) => (i % 10) / 10);
    const K = kivilcim(T, Y, 64);
    expect(K.length).toBe(64);
    for (const v of K) expect(v).toBeCloseTo(0.9, 6);
  });

  it("geçersiz girdi → Error", () => {
    expect(() => kivilcim([0, 1], [0, 1], 0)).toThrow();
    expect(() => kivilcim([0, 1], [0, 1], 1.5)).toThrow();
    expect(() => kivilcim([0, 1], [0], 2)).toThrow();
  });
});
