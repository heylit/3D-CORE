// SPEC 26 K10 — eskiz katmanının saf fonksiyonları (src/eskiz.ts): imleç ışını → düzlem uv, yakalama önerileri.
// Beklenen değerler SPEC 26 ve sketch.model.Plane tanımından elle hesaplanmıştır:
// P = origin + u·xdir + v·ydir, ydir = normal × xdir. Ekran pikselinde y aşağı doğrudur; yatay / dikey
// yalnız doğrultunun açısına bakar, işarete bakmaz.

import { describe, expect, it } from "vitest";
import { type Duzlem, isinDuzlemUv, type Oneri, VARSAYILAN_ESIK, yakalamaOnerileri } from "../src/eskiz";
import type { Nokta3 } from "../src/tipler";

const S2 = Math.SQRT1_2;
const XY: Duzlem = { origin: [0, 0, 0], normal: [0, 0, 1], xdir: [1, 0, 0] };

function uvYakin(g: [number, number] | null, b: [number, number], tol = 1e-9): void {
  expect(g).not.toBeNull();
  expect(Math.abs(g![0] - b[0])).toBeLessThanOrEqual(tol);
  expect(Math.abs(g![1] - b[1])).toBeLessThanOrEqual(tol);
}

function ekle(a: Nokta3, b: Nokta3, k = 1): Nokta3 {
  return [a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2]];
}

describe("isinDuzlemUv", () => {
  it("XY düzlemine yukarıdan dik ışın", () => {
    uvYakin(isinDuzlemUv([3, 4, 10], [0, 0, -1], XY), [3, 4]);
  });

  it("ışın yönü birim olmak zorunda değil", () => {
    uvYakin(isinDuzlemUv([3, 4, 10], [0, 0, -7], XY), [3, 4]);
  });

  it("eğik ışın: kesişim noktası doğru hesaplanır", () => {
    // o = (0, 0, 10), d = (1, 2, −2): t = 5 → P = (5, 10, 0)
    uvYakin(isinDuzlemUv([0, 0, 10], [1, 2, -2], XY), [5, 10]);
  });

  it("ofsetli düzlem: uv origin'e göre", () => {
    const D: Duzlem = { origin: [1, 2, 5], normal: [0, 0, 1], xdir: [1, 0, 0] };
    uvYakin(isinDuzlemUv([3, 4, 10], [0, 0, -1], D), [2, 2]);
  });

  it("düzlemin altından gelen ışın da keser", () => {
    uvYakin(isinDuzlemUv([3, 4, -10], [0, 0, 1], XY), [3, 4]);
  });

  it("döndürülmüş xdir: u ve v eksenleri", () => {
    // xdir = Y → ydir = Z × Y = −X; P = (−2, 5, 0) → u = 5, v = 2
    const D: Duzlem = { origin: [0, 0, 0], normal: [0, 0, 1], xdir: [0, 1, 0] };
    uvYakin(isinDuzlemUv([-2, 5, 3], [0, 0, -1], D), [5, 2]);
  });

  it("XZ düzlemi (normal −Y): ydir = (−Y) × X = +Z", () => {
    const D: Duzlem = { origin: [0, 0, 0], normal: [0, -1, 0], xdir: [1, 0, 0] };
    uvYakin(isinDuzlemUv([4, -20, 7], [0, 1, 0], D), [4, 7]);
  });

  it("eğik düzlem: normal (0, 1, 1)/√2, xdir X → ydir (0, 1, −1)/√2", () => {
    const n: Nokta3 = [0, S2, S2];
    const D: Duzlem = { origin: [1, 2, 3], normal: n, xdir: [1, 0, 0] };
    const y: Nokta3 = [0, S2, -S2];
    // P = origin + 2·xdir + 3·ydir; ışın P + 5n'den −2n yönünde ve eğik bir yönde
    const P = ekle(ekle(D.origin, D.xdir, 2), y, 3);
    uvYakin(isinDuzlemUv(ekle(P, n, 5), [0, -2 * S2, -2 * S2], D), [2, 3], 1e-9);
    const d: Nokta3 = [0.3, -1, -0.4];
    uvYakin(isinDuzlemUv(ekle(P, d, -4), d, D), [2, 3], 1e-9);
  });

  it("düzleme paralel ışın → null", () => {
    expect(isinDuzlemUv([0, 0, 10], [1, 0, 0], XY)).toBeNull();
    expect(isinDuzlemUv([0, 0, 0], [0, 1, 0], XY)).toBeNull(); // düzlemin içinde, paralel
    const D: Duzlem = { origin: [0, 0, 0], normal: [0, S2, S2], xdir: [1, 0, 0] };
    expect(isinDuzlemUv([0, 0, 5], [0, S2, -S2], D)).toBeNull();
  });

  it("kesişim ışının gerisinde → null", () => {
    expect(isinDuzlemUv([3, 4, 10], [0, 0, 1], XY)).toBeNull();
    expect(isinDuzlemUv([0, 0, -10], [1, 2, -2], XY)).toBeNull();
  });
});

function turler(o: Oneri[]): string[] {
  return o.map((x) => x.tur).sort();
}

describe("yakalamaOnerileri", () => {
  it("öneri yoksa boş", () => {
    expect(yakalamaOnerileri([0, 0], [100, 60], [])).toEqual([]);
    expect(yakalamaOnerileri([0, 0], [100, 60], [{ kimlik: "p", px: [300, 300] }])).toEqual([]);
  });

  it("yatay: açı eşiği içinde, iki yönde", () => {
    // atan(2/100) ≈ 1.15° < 3°
    expect(yakalamaOnerileri([0, 0], [100, 2], [])).toEqual([{ tur: "yatay" }]);
    expect(yakalamaOnerileri([50, 50], [-50, 47], [])).toEqual([{ tur: "yatay" }]);
  });

  it("dikey: açı eşiği içinde, iki yönde (ekran y aşağı)", () => {
    expect(yakalamaOnerileri([0, 0], [1, 100], [])).toEqual([{ tur: "dikey" }]);
    expect(yakalamaOnerileri([10, 200], [12, 20], [])).toEqual([{ tur: "dikey" }]);
  });

  it("açı eşiği dışında yatay / dikey yok", () => {
    // atan(10/100) ≈ 5.7° > 3°
    expect(yakalamaOnerileri([0, 0], [100, 10], [])).toEqual([]);
    expect(yakalamaOnerileri([0, 0], [10, 100], [])).toEqual([]);
  });

  it("uç noktaya çakışık: piksel eşiği içinde en yakını", () => {
    const uclar = [
      { kimlik: "uzak", px: [400, 400] as [number, number] },
      { kimlik: "p2", px: [103, 64] as [number, number] }, // uzaklık 5
      { kimlik: "p1", px: [101, 61] as [number, number] }, // uzaklık √2
    ];
    const o = yakalamaOnerileri([0, 0], [100, 60], uclar);
    expect(o).toEqual([{ tur: "cakisik", kimlik: "p1" }]);
  });

  it("piksel eşiği dışında çakışık yok", () => {
    // uzaklık 10 > 8
    expect(yakalamaOnerileri([0, 0], [100, 60], [{ kimlik: "p", px: [106, 68] }])).toEqual([]);
  });

  it("yatay ve çakışık birlikte", () => {
    const o = yakalamaOnerileri([0, 0], [100, 1], [{ kimlik: "q", px: [104, 1] }]);
    expect(turler(o)).toEqual(["cakisik", "yatay"]);
    expect(o).toContainEqual({ tur: "cakisik", kimlik: "q" });
  });

  it("varsayılan eşik VARSAYILAN_ESIK", () => {
    expect(VARSAYILAN_ESIK.aciDerece).toBeGreaterThan(0);
    expect(VARSAYILAN_ESIK.piksel).toBeGreaterThan(0);
    const uclar = [{ kimlik: "p", px: [104, 3] as [number, number] }];
    for (const imlec of [
      [100, 2],
      [100, 10],
      [3, 100],
    ] as [number, number][]) {
      expect(yakalamaOnerileri([0, 0], imlec, uclar)).toEqual(
        yakalamaOnerileri([0, 0], imlec, uclar, VARSAYILAN_ESIK),
      );
    }
  });

  it("özel eşikler: geniş açı, dar piksel", () => {
    const esik = { aciDerece: 10, piksel: 2 };
    // 5.7° < 10° → yatay; p 5 px uzakta > 2 → çakışık yok
    const o = yakalamaOnerileri([0, 0], [100, 10], [{ kimlik: "p", px: [103, 14] }], esik);
    expect(o).toEqual([{ tur: "yatay" }]);
  });

  it("girdiler değişmez", () => {
    const bas: [number, number] = [0, 0];
    const imlec: [number, number] = [100, 1];
    const uclar = [{ kimlik: "q", px: [104, 1] as [number, number] }];
    const kopya = JSON.stringify([bas, imlec, uclar]);
    yakalamaOnerileri(bas, imlec, uclar);
    expect(JSON.stringify([bas, imlec, uclar])).toBe(kopya);
  });
});
