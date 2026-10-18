// SPEC 47b K23 — çok eksen ekranının saf yardımcıları (src/ekranlar/cok_eksen_yardim.ts).
// Beklenen değerler tanımlardan elle hesaplanır: tam sayı k'da sunucu pozu birebir, arada öteleme doğrusal
// ve dönme SLERP (birim dördey, ortonormal R), olay → şerit zamanı, eklem şeridi örneklemesi.
// İkili biçim Python köprüsüyle aynı: başlık uint32 (sema, n, m) 8 baytın katına sıfırla tamamlanır
// (16 bayt; SPEC 24 blok kuralı), ardından float32[n·m·12].

import { describe, expect, it } from "vitest";
import {
  dordey,
  dordeyMatris,
  eklemSeridi,
  olayZamani,
  pozAl,
  pozAraDeger,
  pozlarCoz,
  slerp,
  zamandanIndeks,
} from "../../src/ekranlar/cok_eksen_yardim";
import type { Dordey, Matris3, Olay, Poz, Vek3 } from "../../src/ekranlar/cok_eksen_yardim";

const EPS = 1e-6;

/** u ekseni etrafında θ (radyan) dönme matrisi, satır öncelikli (Rodrigues). */
function rot(u: Vek3, th: number): Matris3 {
  const n = Math.hypot(...u);
  const [x, y, z] = u.map((v) => v / n);
  const c = Math.cos(th);
  const s = Math.sin(th);
  const C = 1 - c;
  return [
    c + x * x * C, x * y * C - z * s, x * z * C + y * s,
    y * x * C + z * s, c + y * y * C, y * z * C - x * s,
    z * x * C - y * s, z * y * C + x * s, c + z * z * C,
  ]; // prettier-ignore
}

function carp(A: Matris3, B: Matris3): Matris3 {
  const C = new Array(9).fill(0) as Matris3;
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++) for (let k = 0; k < 3; k++) C[3 * i + j] += A[3 * i + k] * B[3 * k + j];
  return C;
}

function devrik(A: Matris3): Matris3 {
  return [A[0], A[3], A[6], A[1], A[4], A[7], A[2], A[5], A[8]];
}

function yakin(a: ArrayLike<number>, b: ArrayLike<number>, eps = EPS): void {
  expect(a.length).toBe(b.length);
  for (let i = 0; i < a.length; i++) expect(Math.abs(a[i] - b[i])).toBeLessThanOrEqual(eps);
}

function ortonormal(R: Matris3): void {
  yakin(carp(devrik(R), R), [1, 0, 0, 0, 1, 0, 0, 0, 1]);
  const det =
    R[0] * (R[4] * R[8] - R[5] * R[7]) - R[1] * (R[3] * R[8] - R[5] * R[6]) + R[2] * (R[3] * R[7] - R[4] * R[6]);
  expect(Math.abs(det - 1)).toBeLessThanOrEqual(EPS);
}

/** Dönme açısı (radyan) R'den: cos θ = (iz − 1)/2. */
function aci(R: Matris3): number {
  return Math.acos(Math.min(1, Math.max(-1, (R[0] + R[4] + R[8] - 1) / 2)));
}

/** Sunucu biçiminde `pozlar` ikilisi. */
function ikili(pozlar: Poz[][], sema = 1): ArrayBuffer {
  const n = pozlar.length;
  const m = pozlar[0].length;
  const tampon = new ArrayBuffer(16 + n * m * 12 * 4);
  const dv = new DataView(tampon);
  dv.setUint32(0, sema, true);
  dv.setUint32(4, n, true);
  dv.setUint32(8, m, true);
  let o = 16;
  for (const satir of pozlar)
    for (const p of satir)
      for (const v of [...p.R, ...p.t]) {
        dv.setFloat32(o, v, true);
        o += 4;
      }
  return tampon;
}

const f32 = (x: number[]): number[] => Array.from(Float32Array.from(x));

// 3 nokta, 2 gövde: gövde 0 z etrafında 0°, 60°, 120°; gövde 1 sabit dönme, ötelenen.
const POZLAR: Poz[][] = [0, 1, 2].map((k) => [
  { R: rot([0, 0, 1], (k * Math.PI) / 3), t: [k * 10, 0, 1] as Vek3 },
  { R: rot([1, 1, 0], 0.3 + 0.2 * k), t: [5, -k, 2 * k] as Vek3 },
]);

describe("pozlarCoz / pozAl", () => {
  it("başlık ve boyutlar", () => {
    const P = pozlarCoz(ikili(POZLAR));
    expect(P.n).toBe(3);
    expect(P.m).toBe(2);
    expect(P.veri.length).toBe(3 * 2 * 12);
  });

  it("tam sayı k'da sunucu pozu birebir (float32)", () => {
    const P = pozlarCoz(ikili(POZLAR));
    for (let k = 0; k < 3; k++)
      for (let b = 0; b < 2; b++) {
        const p = pozAl(P, k, b);
        expect(Array.from(p.R)).toEqual(f32(POZLAR[k][b].R));
        expect(Array.from(p.t)).toEqual(f32(POZLAR[k][b].t));
      }
  });

  it("sürüm ve boy hataları, aralık dışı indeks", () => {
    expect(() => pozlarCoz(ikili(POZLAR, 2))).toThrow();
    expect(() => pozlarCoz(ikili(POZLAR).slice(0, 40))).toThrow();
    const P = pozlarCoz(ikili(POZLAR));
    expect(() => pozAl(P, 3, 0)).toThrow();
    expect(() => pozAl(P, -1, 0)).toThrow();
    expect(() => pozAl(P, 0, 2)).toThrow();
  });
});

describe("dordey / dordeyMatris / slerp", () => {
  const ornekler: Matris3[] = [
    rot([0, 0, 1], 0),
    rot([0, 0, 1], Math.PI / 2),
    rot([1, 0, 0], Math.PI),
    rot([1, 2, 3], 2.5),
    rot([-1, 0.5, 0.2], -1.2),
    rot([0, 1, 0], 3.1),
  ];

  it("dördey birim, w ≥ 0, matrise geri dönüş", () => {
    for (const R of ornekler) {
      const q = dordey(R);
      expect(Math.abs(Math.hypot(...q) - 1)).toBeLessThanOrEqual(EPS);
      expect(q[0]).toBeGreaterThanOrEqual(0);
      const R2 = dordeyMatris(q);
      ortonormal(R2);
      yakin(R2, R);
    }
  });

  it("birim dönme ↔ (1, 0, 0, 0); z etrafında 90° ↔ (cos 45°, 0, 0, sin 45°)", () => {
    yakin(dordey(rot([0, 0, 1], 0)), [1, 0, 0, 0]);
    const s = Math.SQRT1_2;
    yakin(dordey(rot([0, 0, 1], Math.PI / 2)), [s, 0, 0, s]);
  });

  it("slerp uçları ve orta nokta (z etrafında 0° → 90°: 45°)", () => {
    const q0 = dordey(rot([0, 0, 1], 0));
    const q1 = dordey(rot([0, 0, 1], Math.PI / 2));
    yakin(dordeyMatris(slerp(q0, q1, 0)), rot([0, 0, 1], 0));
    yakin(dordeyMatris(slerp(q0, q1, 1)), rot([0, 0, 1], Math.PI / 2));
    yakin(dordeyMatris(slerp(q0, q1, 0.5)), rot([0, 0, 1], Math.PI / 4));
    yakin(dordeyMatris(slerp(q0, q1, 0.25)), rot([0, 0, 1], Math.PI / 8));
  });

  it("kısa yol: −q ile aynı dönme, ara değer büyük yay üstünden gitmez", () => {
    const q0 = dordey(rot([1, 0, 0], 0.2));
    const q1 = dordey(rot([1, 0, 0], 0.6));
    const q1Eksi = q1.map((v) => -v) as Dordey;
    yakin(dordeyMatris(slerp(q0, q1Eksi, 0.5)), rot([1, 0, 0], 0.4));
  });

  it("her s'de birim dördey ve ortonormal R", () => {
    const q0 = dordey(rot([1, 2, 3], 2.5));
    const q1 = dordey(rot([-1, 0.5, 0.2], -1.2));
    for (let i = 0; i <= 20; i++) {
      const q = slerp(q0, q1, i / 20);
      expect(Math.abs(Math.hypot(...q) - 1)).toBeLessThanOrEqual(EPS);
      ortonormal(dordeyMatris(q));
    }
  });
});

describe("pozAraDeger", () => {
  it("tam sayı kf'de sunucu pozu birebir", () => {
    const P = pozlarCoz(ikili(POZLAR));
    for (let k = 0; k < 3; k++)
      for (let b = 0; b < 2; b++) {
        const p = pozAraDeger(P, k, b);
        const s = pozAl(P, k, b);
        expect(Array.from(p.R)).toEqual(Array.from(s.R));
        expect(Array.from(p.t)).toEqual(Array.from(s.t));
      }
  });

  it("arada öteleme doğruda, dönme SLERP (birim, ortonormal)", () => {
    const P = pozlarCoz(ikili(POZLAR));
    for (const kf of [0.25, 0.5, 1.1, 1.9]) {
      const k = Math.floor(kf);
      const s = kf - k;
      for (let b = 0; b < 2; b++) {
        const p = pozAraDeger(P, kf, b);
        const a = pozAl(P, k, b);
        const c = pozAl(P, k + 1, b);
        yakin(
          p.t,
          [0, 1, 2].map((i) => a.t[i] + s * (c.t[i] - a.t[i])),
          1e-5,
        );
        ortonormal(p.R);
        const beklenen = dordeyMatris(slerp(dordey(a.R), dordey(c.R), s));
        yakin(p.R, beklenen);
      }
    }
    // Gövde 0: z etrafında 0° → 60° arası; kf = 0.5'te 30°.
    yakin(pozAraDeger(P, 0.5, 0).R, rot([0, 0, 1], Math.PI / 6));
    expect(Math.abs(aci(pozAraDeger(P, 1.5, 0).R) - Math.PI / 2)).toBeLessThanOrEqual(EPS);
  });

  it("aralık dışı kf → hata (kırpma yok)", () => {
    const P = pozlarCoz(ikili(POZLAR));
    expect(() => pozAraDeger(P, -0.1, 0)).toThrow();
    expect(() => pozAraDeger(P, 2.01, 0)).toThrow();
    expect(() => pozAraDeger(P, 1, 5)).toThrow();
  });
});

describe("zamandanIndeks / olayZamani", () => {
  const zaman = [0, 1, 1, 3, 4];

  it("kesirli indeks; eşit zamanlı ardışık noktalarda ilki", () => {
    expect(zamandanIndeks(0, zaman)).toBe(0);
    expect(zamandanIndeks(0.5, zaman)).toBeCloseTo(0.5, 12);
    expect(zamandanIndeks(1, zaman)).toBe(1);
    expect(zamandanIndeks(2, zaman)).toBeCloseTo(2.5, 12);
    expect(zamandanIndeks(3, zaman)).toBe(3);
    expect(zamandanIndeks(3.25, zaman)).toBeCloseTo(3.25, 12);
    expect(zamandanIndeks(4, zaman)).toBe(4);
  });

  // Olay k: SPEC 05 adım indeksi; adım k, k−1 noktasından k noktasına gider. t hareket içi parametre (0–1),
  // `zaman` [s] sunucudan: zaman[k−1] + t·(zaman[k] − zaman[k−1]).
  const olay = (k: number, t: number, saniye?: number): Olay & { zaman: number } => ({
    kind: "eksen_siniri",
    k,
    t,
    a: "A",
    b: "",
    distance: 0,
    detail: "A > max",
    zaman: saniye ?? zaman[k - 1] + t * (zaman[k] - zaman[k - 1]),
  });

  it("olayın şerit zamanı sunucunun `zaman` alanı", () => {
    expect(olayZamani(olay(1, 0.4), zaman)).toBeCloseTo(0.4, 12);
    expect(olayZamani(olay(2, 0.5), zaman)).toBe(1);
    expect(olayZamani(olay(3, 1), zaman)).toBe(3);
    expect(olayZamani(olay(4, 0.7), zaman)).toBeCloseTo(3.7, 12);
    const carpma = { ...olay(4, 0.25), kind: "tezgah_carpma" as const, a: "kafa", b: "fikstur" };
    expect(olayZamani(carpma, zaman)).toBeCloseTo(3.25, 12);
  });

  it("zaman, zaman[k−1]..zaman[k] dışında ya da k aralık dışı → hata (tutarsız sunucu verisi)", () => {
    expect(() => olayZamani(olay(1, 0.5, 2), zaman)).toThrow();
    expect(() => olayZamani(olay(4, 0.5, 2.9), zaman)).toThrow();
    expect(() => olayZamani(olay(0, 0, 0), zaman)).toThrow();
    expect(() => olayZamani(olay(5, 0, 4), zaman)).toThrow();
  });
});

describe("eklemSeridi", () => {
  // n = 101 nokta, sütun = 5 (X Y Z A C); A = 30·sin(t), C = 3.6·t (sarma çözülmüş, 360°'yi aşar).
  const n = 101;
  const sutun = 5;
  const zaman = Array.from({ length: n }, (_, i) => i * 0.1);
  const q = new Float64Array(n * sutun);
  for (let i = 0; i < n; i++) {
    q[i * sutun + 3] = 30 * Math.sin(zaman[i]);
    q[i * sutun + 4] = 36 * zaman[i] * 10;
  }
  q[57 * sutun + 3] = 95; // tek noktalık uç değer: kaybolmamalı

  it("boylar, artan zaman, min ≤ max", () => {
    const s = eklemSeridi(zaman, q, sutun, 3, 20);
    expect(s.t.length).toBe(20);
    expect(s.min.length).toBe(20);
    expect(s.max.length).toBe(20);
    for (let i = 0; i < 20; i++) {
      expect(s.min[i]).toBeLessThanOrEqual(s.max[i]);
      expect(Number.isFinite(s.min[i]) && Number.isFinite(s.max[i])).toBe(true);
      if (i) expect(s.t[i]).toBeGreaterThan(s.t[i - 1]);
    }
    expect(s.t[0]).toBeGreaterThanOrEqual(zaman[0]);
    expect(s.t[19]).toBeLessThanOrEqual(zaman[n - 1]);
  });

  it("uçlar kaybolmaz: piksel min/max'ları sütunun gerçek min/max'ı", () => {
    for (const [j, gen] of [
      [3, 20],
      [3, 7],
      [4, 13],
      [3, 101],
    ]) {
      const s = eklemSeridi(zaman, q, sutun, j, gen);
      let gmin = Infinity;
      let gmax = -Infinity;
      for (let i = 0; i < n; i++) {
        gmin = Math.min(gmin, q[i * sutun + j]);
        gmax = Math.max(gmax, q[i * sutun + j]);
      }
      expect(Math.min(...s.min)).toBe(gmin);
      expect(Math.max(...s.max)).toBe(gmax);
    }
    // 95'lik tek nokta, içine düştüğü pikselin max'ında.
    const s = eklemSeridi(zaman, q, sutun, 3, 10);
    const piksel = s.max.findIndex((v) => v === 95);
    expect(piksel).toBeGreaterThanOrEqual(0);
  });
});
