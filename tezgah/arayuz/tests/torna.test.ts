// SPEC 25 K17 — torna ekranının saf fonksiyonları (src/torna.ts): çap / yarıçap biçimi, devir şeridinde
// n_max bölgeleri, torna sim ikili dizisinin çözülmesi ve k anındaki kesit.
// Beklenen değerler belgedeki tanımlardan elle hesaplanmıştır; ikili dizi testte belgedeki biçimle kurulur.

import { describe, expect, it } from "vitest";
import { capBicim, devirSinirBolgeleri, kesitAt, tornaSimCoz } from "../src/torna";

describe("capBicim", () => {
  it("çap modunda 2·x, yarıçap modunda x", () => {
    expect(Number(capBicim(23, true, 3))).toBe(46);
    expect(Number(capBicim(23, false, 3))).toBe(23);
    expect(Number(capBicim(12.3456, true, 3))).toBe(24.691); // 24.6912 → 3 basamak
    expect(Number(capBicim(12.3456, false, 3))).toBe(12.346);
    expect(Number(capBicim(27, true, 3))).toBe(54);
  });

  it("en fazla `ondalik` basamak (G-code yazıcısıyla aynı yuvarlama)", () => {
    for (const [x, d] of [
      [12.3456, 3],
      [0.123456, 4],
      [7.1, 1],
      [100, 2],
    ] as [number, number][]) {
      const s = capBicim(x, true, d);
      expect(s).toMatch(/^-?\d+(\.\d*)?$/);
      const kesir = s.includes(".") ? s.split(".")[1].length : 0;
      expect(kesir).toBeLessThanOrEqual(d);
      expect(Number(s)).toBe(Number((2 * x).toFixed(d)));
    }
    expect(Number(capBicim(0.0004, true, 2))).toBe(0);
  });

  it("−0 yazılmaz: yuvarlanınca sıfır olan negatif sayı 0", () => {
    for (const x of [-0, -1e-9, -0.0002]) {
      const s = capBicim(x, true, 3);
      expect(s.startsWith("-")).toBe(false);
      expect(Number(s)).toBe(0);
    }
    expect(capBicim(-1.25, false, 3).startsWith("-")).toBe(true);
  });

  it("sonlu olmayan sayı hata", () => {
    expect(() => capBicim(Number.NaN, true, 3)).toThrow();
    expect(() => capBicim(Number.POSITIVE_INFINITY, false, 3)).toThrow();
  });
});

describe("devirSinirBolgeleri", () => {
  const nMax = 3000;

  it("n = n_max olan ardışık noktaların kapalı zaman aralıkları", () => {
    const T = [0, 1, 2, 3, 4, 5];
    const n = [100, 3000, 3000, 200, 3000, 3000];
    expect(devirSinirBolgeleri(T, n, nMax)).toEqual([
      [1, 2],
      [4, 5],
    ]);
  });

  it("tek noktalık bölge [t, t]; hiç yoksa boş", () => {
    expect(devirSinirBolgeleri([0, 1, 2], [100, 3000, 100], nMax)).toEqual([[1, 1]]);
    expect(devirSinirBolgeleri([0, 1, 2], [100, 200, 300], nMax)).toEqual([]);
    expect(devirSinirBolgeleri([], [], nMax)).toEqual([]);
  });

  it("tolerans |n − n_max| ≤ 1e-9·n_max", () => {
    const T = [0, 1, 2, 3];
    const n = [nMax * (1 - 5e-10), nMax * (1 + 5e-10), nMax * (1 - 1e-6), nMax];
    expect(devirSinirBolgeleri(T, n, nMax)).toEqual([
      [0, 1],
      [3, 3],
    ]);
  });

  it("eşit zamanlı noktalar (sıfır süreli adım) ve typed array girdi", () => {
    const T = new Float64Array([0, 1, 1, 2]);
    const n = new Float32Array([3000, 3000, 100, 3000]);
    expect(devirSinirBolgeleri(T, n, nMax)).toEqual([
      [0, 1],
      [2, 2],
    ]);
  });

  it("uzunluk farkı ya da azalan T hata", () => {
    expect(() => devirSinirBolgeleri([0, 1], [3000], nMax)).toThrow();
    expect(() => devirSinirBolgeleri([0, 2, 1], [1, 2, 3], nMax)).toThrow();
  });
});

// ---------------------------------------------------------------- ikili sim dizisi

interface Olay {
  hucre: number;
  k: number;
  dis: number;
  ic: number;
  islem: number;
}

/** tezgah/torna.py `sim_ikili` belgesindeki biçim (little-endian, bloklar 8 baytın katına sıfırla tamamlı). */
function simKur(
  sema: number,
  nz: number,
  izgara: [number, number, number, number],
  olaylar: Olay[],
  hedef: number[],
): ArrayBuffer {
  const hiza = (n: number) => Math.ceil(n / 8) * 8;
  const s = [...olaylar].sort((a, b) => a.hucre - b.hucre || a.k - b.k);
  const m = s.length;
  const boy =
    16 + 32 + hiza(4 * (nz + 1)) + hiza(4 * m) + hiza(4 * m) + hiza(4 * m) + hiza(2 * m) + hiza(4 * nz);
  const buf = new ArrayBuffer(boy);
  const dv = new DataView(buf);
  dv.setUint32(0, sema, true);
  dv.setUint32(4, nz, true);
  dv.setUint32(8, m, true);
  dv.setUint32(12, 0, true);
  let yer = 16;
  izgara.forEach((v, i) => dv.setFloat64(yer + 8 * i, v, true));
  yer += 32;
  for (let i = 0; i <= nz; i++) dv.setUint32(yer + 4 * i, s.filter((o) => o.hucre < i).length, true);
  yer = hiza(yer + 4 * (nz + 1));
  s.forEach((o, j) => dv.setInt32(yer + 4 * j, o.k, true));
  yer = hiza(yer + 4 * m);
  s.forEach((o, j) => dv.setFloat32(yer + 4 * j, o.dis, true));
  yer = hiza(yer + 4 * m);
  s.forEach((o, j) => dv.setFloat32(yer + 4 * j, o.ic, true));
  yer = hiza(yer + 4 * m);
  s.forEach((o, j) => dv.setInt16(yer + 2 * j, o.islem, true));
  yer = hiza(yer + 2 * m);
  hedef.forEach((v, i) => dv.setFloat32(yer + 4 * i, v, true));
  return buf;
}

const OLAYLAR: Olay[] = [
  { hucre: 0, k: 2, dis: 20, ic: 0, islem: 0 },
  { hucre: 0, k: 5, dis: 18, ic: 0, islem: 1 },
  { hucre: 2, k: 3, dis: 22, ic: 5, islem: 1 },
  { hucre: 3, k: 1, dis: 24.5, ic: 0, islem: 0 },
];
const IZGARA: [number, number, number, number] = [10, 0.5, 25, 0];
const HEDEF = [18, Number.NaN, 21.5, 24];

describe("tornaSimCoz", () => {
  it("başlık, ızgara, ofset ve olay blokları", () => {
    const S = tornaSimCoz(simKur(1, 4, IZGARA, OLAYLAR, HEDEF));
    expect(S.nz).toBe(4);
    expect([S.z0, S.dz, S.rDis0, S.rIc0]).toEqual(IZGARA);
    expect(Array.from(S.ofset)).toEqual([0, 2, 2, 3, 4]);
    expect(Array.from(S.k)).toEqual([2, 5, 3, 1]);
    expect(Array.from(S.rDis)).toEqual([20, 18, 22, 24.5]);
    expect(Array.from(S.rIc)).toEqual([0, 0, 5, 0]);
    expect(Array.from(S.islem)).toEqual([0, 1, 1, 0]);
    expect(S.hedef.length).toBe(4);
    expect(S.hedef[0]).toBe(18);
    expect(Number.isNaN(S.hedef[1])).toBe(true);
  });

  it("olaysız dizi", () => {
    const S = tornaSimCoz(simKur(1, 3, IZGARA, [], [Number.NaN, Number.NaN, Number.NaN]));
    expect(S.k.length).toBe(0);
    expect(Array.from(S.ofset)).toEqual([0, 0, 0, 0]);
  });

  it("sürüm ya da uzunluk tutmuyorsa hata", () => {
    expect(() => tornaSimCoz(simKur(2, 4, IZGARA, OLAYLAR, HEDEF))).toThrow();
    const tam = simKur(1, 4, IZGARA, OLAYLAR, HEDEF);
    expect(() => tornaSimCoz(tam.slice(0, tam.byteLength - 8))).toThrow();
    const fazla = new ArrayBuffer(tam.byteLength + 8);
    new Uint8Array(fazla).set(new Uint8Array(tam));
    expect(() => tornaSimCoz(fazla)).toThrow();
  });
});

describe("kesitAt", () => {
  const S = () => tornaSimCoz(simKur(1, 4, IZGARA, OLAYLAR, HEDEF));

  it("olay yoksa ham malzeme (rDis0, rIc0)", () => {
    const { dis, ic } = kesitAt(S(), 0);
    expect(Array.from(dis)).toEqual([25, 25, 25, 25]);
    expect(Array.from(ic)).toEqual([0, 0, 0, 0]);
  });

  it("her hücrede k'si ≤ k olan son olay", () => {
    expect(Array.from(kesitAt(S(), 1).dis)).toEqual([25, 25, 25, 24.5]);
    expect(Array.from(kesitAt(S(), 2).dis)).toEqual([20, 25, 25, 24.5]);
    const k4 = kesitAt(S(), 4);
    expect(Array.from(k4.dis)).toEqual([20, 25, 22, 24.5]);
    expect(Array.from(k4.ic)).toEqual([0, 0, 5, 0]);
    expect(Array.from(kesitAt(S(), 5).dis)).toEqual([18, 25, 22, 24.5]);
    expect(Array.from(kesitAt(S(), 1000).dis)).toEqual([18, 25, 22, 24.5]);
  });

  it("float32 dizi döner, girdi değişmez", () => {
    const s = S();
    const { dis, ic } = kesitAt(s, 3);
    expect(dis).toBeInstanceOf(Float32Array);
    expect(ic).toBeInstanceOf(Float32Array);
    expect(Array.from(s.rDis)).toEqual([20, 18, 22, 24.5]);
  });

  it("bağımsız tarama ile aynı (rastgele olay listesi)", () => {
    let tohum = 7;
    const rnd = () => ((tohum = (tohum * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
    const nz = 30;
    const olaylar: Olay[] = [];
    for (let h = 0; h < nz; h++) {
      let k = 0;
      for (let j = 0; j < Math.floor(rnd() * 4); j++) {
        k += 1 + Math.floor(rnd() * 5);
        olaylar.push({ hucre: h, k, dis: Math.fround(10 + 15 * rnd()), ic: Math.fround(5 * rnd()), islem: j });
      }
    }
    const sim = tornaSimCoz(simKur(1, nz, [0, 1, 25, 0], olaylar, new Array(nz).fill(0)));
    for (const k of [0, 1, 3, 7, 12, 20]) {
      const { dis, ic } = kesitAt(sim, k);
      for (let h = 0; h < nz; h++) {
        const son = olaylar.filter((o) => o.hucre === h && o.k <= k).pop();
        expect(dis[h]).toBe(son ? son.dis : 25);
        expect(ic[h]).toBe(son ? son.ic : 0);
      }
    }
  });
});
