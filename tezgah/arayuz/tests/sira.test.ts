// SPEC 25 K17 — montaj sırası (src/sira.ts): adım ↔ u eşlemesi, T_once → T_sonra ara değeri, serbestlik çipi.
// Elle kurulmuş üç adımlı sıra; T'ler 4x4 satır öncelikli (sunucu biçimi). Sunucu kuralına uygun olarak
// T_once = T_sonra + mesafe·a ötelemesi (dönme aynı).

import { describe, expect, it } from "vitest";
import { adimU, cip, poz, type Adim, type Mat4, type Serbestlik } from "../src/sira";

function T(R: number[][], t: [number, number, number]): Mat4 {
  return [...R[0], t[0], ...R[1], t[1], ...R[2], t[2], 0, 0, 0, 1];
}

const I3 = [
  [1, 0, 0],
  [0, 1, 0],
  [0, 0, 1],
];
const c = Math.cos(Math.PI / 6);
const s = Math.sin(Math.PI / 6);
const Rz30 = [
  [c, -s, 0],
  [s, c, 0],
  [0, 0, 1],
];

function oteleme(M: Mat4): [number, number, number] {
  return [M[3], M[7], M[11]];
}

function donme(M: Mat4): number[] {
  return [M[0], M[1], M[2], M[4], M[5], M[6], M[8], M[9], M[10]];
}

function ileri(M: Mat4, d: number, a: [number, number, number]): Mat4 {
  const N = [...M];
  N[3] += d * a[0];
  N[7] += d * a[1];
  N[11] += d * a[2];
  return N;
}

const BOS: Serbestlik = { sayi: 0, oteleme: [], vida: [], etiketler: [] };

const P = T(I3, [0, 0, 0]); // plaka, sabit
const R1 = T(I3, [0, 0, -10]); // rulman, adım 1 sonrası
const M1 = T(Rz30, [0, 0, -5]); // mil, adım 2 sonrası (dönmüş)
const R2 = T(I3, [0, 0, -10.5]); // rulman: adım 2'de çözücü biraz kaydırdı

const SIRA: Adim[] = [
  {
    i: 0, yol: "plaka", ad: "Plaka", yaklasma: [0, 0, 1], mesafe: 0,
    T_once: { plaka: P }, T_sonra: { plaka: P }, dof_toplam: 0, serbestlik: { plaka: BOS },
  },
  {
    i: 1, yol: "rulman", ad: "Rulman → cep", yaklasma: [0, 0, 1], mesafe: 45,
    T_once: { plaka: P, rulman: ileri(R1, 45, [0, 0, 1]) }, T_sonra: { plaka: P, rulman: R1 },
    dof_toplam: 1, serbestlik: { rulman: { sayi: 1, oteleme: [], vida: [{ yon: [0, 0, 1], nokta: [0, 0, 0], hatve: 0 }], etiketler: ["Rz"] } },
  },
  {
    i: 2, yol: "mil", ad: "Mil → rulman", yaklasma: [0, 0, 1], mesafe: 90,
    T_once: { plaka: P, rulman: R2, mil: ileri(M1, 90, [0, 0, 1]) }, T_sonra: { plaka: P, rulman: R2, mil: M1 },
    dof_toplam: 2, serbestlik: {},
  },
]; // prettier-ignore

function yakin(a: Mat4, b: Mat4, eps = 1e-12): void {
  expect(a.length).toBe(16);
  for (let i = 0; i < 16; i++) expect(Math.abs(a[i] - b[i])).toBeLessThanOrEqual(eps);
}

describe("adimU", () => {
  it("u → (adım, adım içi s)", () => {
    expect(adimU(0, 3)).toEqual({ i: 0, s: 0 });
    expect(adimU(0.25, 3)).toEqual({ i: 0, s: 0.25 });
    expect(adimU(1.5, 3)).toEqual({ i: 1, s: 0.5 });
    expect(adimU(2, 3)).toEqual({ i: 2, s: 0 });
    expect(adimU(3, 3)).toEqual({ i: 2, s: 1 });
  });

  it("u kırpılır", () => {
    expect(adimU(-1, 3)).toEqual({ i: 0, s: 0 });
    expect(adimU(7.5, 3)).toEqual({ i: 2, s: 1 });
    expect(adimU(1, 1)).toEqual({ i: 0, s: 1 });
  });

  it("N < 1 hata", () => {
    expect(() => adimU(0, 0)).toThrow();
  });
});

describe("poz", () => {
  it("u tam sayıda sunucunun T'si birebir", () => {
    // Bileşen kendi adımının başında T_once, sonunda T_sonra.
    yakin(poz(SIRA, "rulman", 1), SIRA[1].T_once.rulman, 0);
    yakin(poz(SIRA, "mil", 2), SIRA[2].T_once.mil, 0);
    yakin(poz(SIRA, "mil", 3), SIRA[2].T_sonra.mil, 0);
    yakin(poz(SIRA, "plaka", 0), P, 0);
    yakin(poz(SIRA, "plaka", 3), P, 0);
  });

  it("şerit başında bütün bileşenler T_once'da, sonunda son adımın T_sonra'sında", () => {
    for (const a of SIRA) yakin(poz(SIRA, a.yol, 0), a.T_once[a.yol], 0);
    for (const yol of ["plaka", "rulman", "mil"]) yakin(poz(SIRA, yol, 3), SIRA[2].T_sonra[yol], 0);
  });

  it("henüz gelmemiş bileşen kendi adımının T_once'unda bekler", () => {
    yakin(poz(SIRA, "mil", 0.5), SIRA[2].T_once.mil, 0);
    yakin(poz(SIRA, "mil", 1.7), SIRA[2].T_once.mil, 0);
  });

  it("sonraki adımlarda o adımın T_sonra'sı", () => {
    yakin(poz(SIRA, "rulman", 2.5), R2, 0);
    yakin(poz(SIRA, "rulman", 2.99), R2, 0);
  });

  it("kendi adımında: dönme T_sonra'nınki, öteleme T_once–T_sonra doğrusu üstünde ve ilerleyen", () => {
    const t0 = oteleme(SIRA[2].T_once.mil);
    const t1 = oteleme(SIRA[2].T_sonra.mil);
    let onceki = -1;
    for (const u of [2.1, 2.25, 2.5, 2.75, 2.9]) {
      const M = poz(SIRA, "mil", u);
      const R = donme(M);
      const R1 = donme(SIRA[2].T_sonra.mil);
      for (let i = 0; i < 9; i++) expect(Math.abs(R[i] - R1[i])).toBeLessThanOrEqual(1e-12);
      expect(M.slice(12)).toEqual([0, 0, 0, 1]);
      const t = oteleme(M);
      const d = [t1[0] - t0[0], t1[1] - t0[1], t1[2] - t0[2]];
      const v = [t[0] - t0[0], t[1] - t0[1], t[2] - t0[2]];
      const dd = d[0] ** 2 + d[1] ** 2 + d[2] ** 2;
      const lam = (v[0] * d[0] + v[1] * d[1] + v[2] * d[2]) / dd;
      for (let i = 0; i < 3; i++) expect(Math.abs(v[i] - lam * d[i])).toBeLessThanOrEqual(1e-9); // doğru üstünde
      expect(lam).toBeGreaterThanOrEqual(0);
      expect(lam).toBeLessThanOrEqual(1);
      expect(lam).toBeGreaterThanOrEqual(onceki); // T_once'tan T_sonra'ya doğru ilerler
      onceki = lam;
    }
    expect(onceki).toBeGreaterThan(0);
  });

  it("bilinmeyen yol hata", () => {
    expect(() => poz(SIRA, "yok", 1)).toThrow();
  });
});

describe("cip", () => {
  it("6 kare; ilk 6 − sayi kilitli, serbest kareler sunucunun etiketleri sırasıyla", () => {
    const s: Serbestlik = {
      sayi: 2,
      oteleme: [[0, 0, 1]],
      vida: [{ yon: [0, 0, 1], nokta: [5, 3, 0], hatve: 0 }],
      etiketler: ["Tz", "Rz"],
    };
    const C = cip(s);
    expect(C.length).toBe(6);
    expect(C.map((k) => k.kilitli)).toEqual([true, true, true, true, false, false]);
    expect(C.filter((k) => !k.kilitli).map((k) => k.etiket)).toEqual(["Tz", "Rz"]);
  });

  it("tam kilitli ve tam serbest", () => {
    expect(cip(BOS).every((k) => k.kilitli)).toBe(true);
    const serbest: Serbestlik = {
      sayi: 6,
      oteleme: [
        [1, 0, 0],
        [0, 1, 0],
        [0, 0, 1],
      ],
      vida: [],
      etiketler: ["Tx", "Ty", "Tz", "Rx", "Ry", "Rz"],
    };
    const C = cip(serbest);
    expect(C.every((k) => !k.kilitli)).toBe(true);
    expect(C.map((k) => k.etiket)).toEqual(["Tx", "Ty", "Tz", "Rx", "Ry", "Rz"]);
  });
});
