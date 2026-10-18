// SPEC 47b — çok eksen ekranının saf yardımcıları (vitest ile sınanır, DOM'suz).
// Ön yüz mühendislik sayısı hesaplamaz: pozlar ve eklem değerleri sunucudan gelir; burada yalnız iki
// sunucu değeri arasında görsel ara değer (öteleme doğrusal, dönme SLERP) ve zaman eşlemesi yapılır.

/** Satır öncelikli 3×3 dönme matrisi (9 sayı). */
export type Matris3 = [number, number, number, number, number, number, number, number, number];
/** Birim dördey (w, x, y, z). */
export type Dordey = [number, number, number, number];
export type Vek3 = [number, number, number];

export interface Poz {
  R: Matris3;
  t: Vek3;
}

/** Sunucunun `pozlar` ikilisi çözülmüş hâli: n nokta, m gövde, `veri` float32[n·m·12] (R 9 + t 3). */
export interface PozDizisi {
  n: number;
  m: number;
  veri: Float32Array;
}

/** Ekrana gelen olay (SPEC 44 MachineEvent sözlüğü). */
export interface Olay {
  kind: "tezgah_carpma" | "eksen_siniri";
  k: number;
  t: number;
  a: string;
  b: string;
  distance: number;
  detail: string;
  /** Şerit zamanı [s], sunucudan: zaman[k−1] + t·(zaman[k] − zaman[k−1]) (t hareket içi parametre). */
  zaman: number;
}

function birim(q: Dordey): Dordey {
  const r = Math.hypot(...q);
  return q.map((v) => v / r) as Dordey;
}

/** `pozlar` ikilisi (başlık uint32 sema, n, m, 8 baytın katına tamamlanmış: 16 bayt; + float32[n·m·12]) → PozDizisi. Sürüm / boy hatası → Error. */
export function pozlarCoz(tampon: ArrayBuffer, sema = 1): PozDizisi {
  const dv = new DataView(tampon);
  if (tampon.byteLength < 16) throw new Error(`pozlar dizisi çok kısa (${tampon.byteLength} bayt)`);
  const surum = dv.getUint32(0, true);
  if (surum !== sema) throw new Error(`pozlar dizisi sürümü ${surum}, beklenen ${sema}`);
  const n = dv.getUint32(4, true);
  const m = dv.getUint32(8, true);
  const beklenen = 16 + n * m * 12 * 4;
  if (tampon.byteLength !== beklenen)
    throw new Error(`pozlar dizisi boyu tutmuyor (${tampon.byteLength} bayt, beklenen ${beklenen})`);
  const veri = new Float32Array(n * m * 12);
  for (let i = 0; i < veri.length; i++) veri[i] = dv.getFloat32(16 + 4 * i, true);
  return { n, m, veri };
}

/** k. noktada b. gövdenin sunucu pozu (birebir; ara değer yok). Aralık dışı → Error. */
export function pozAl(pozlar: PozDizisi, k: number, b: number): Poz {
  const { n, m, veri } = pozlar;
  if (!Number.isInteger(k) || k < 0 || k >= n) throw new Error(`nokta indeksi ${k} aralık dışında (n = ${n})`);
  if (!Number.isInteger(b) || b < 0 || b >= m) throw new Error(`gövde indeksi ${b} aralık dışında (m = ${m})`);
  const o = (k * m + b) * 12;
  const v = Array.from(veri.subarray(o, o + 12));
  return { R: v.slice(0, 9) as Matris3, t: v.slice(9, 12) as Vek3 };
}

/** Dönme matrisi → birim dördey (w ≥ 0). */
export function dordey(R: Matris3): Dordey {
  // Shepperd: en büyük köşegen bileşenden (sayısal kararlılık).
  const [a, b, c, d, e, f, g, h, i] = R;
  const iz = a + e + i;
  let q: Dordey;
  if (iz > 0) {
    const S = 2 * Math.sqrt(1 + iz);
    q = [S / 4, (h - f) / S, (c - g) / S, (d - b) / S];
  } else if (a > e && a > i) {
    const S = 2 * Math.sqrt(1 + a - e - i);
    q = [(h - f) / S, S / 4, (b + d) / S, (c + g) / S];
  } else if (e > i) {
    const S = 2 * Math.sqrt(1 + e - a - i);
    q = [(c - g) / S, (b + d) / S, S / 4, (f + h) / S];
  } else {
    const S = 2 * Math.sqrt(1 + i - a - e);
    q = [(d - b) / S, (c + g) / S, (f + h) / S, S / 4];
  }
  if (q[0] < 0) q = q.map((v) => -v) as Dordey;
  return birim(q);
}

/** Birim dördey → ortonormal dönme matrisi. */
export function dordeyMatris(q: Dordey): Matris3 {
  const [w, x, y, z] = birim(q);
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y),
    2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x),
    2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y),
  ]; // prettier-ignore
}

/** Kısa yoldan SLERP, s ∈ [0, 1]; sonuç birim dördey. */
export function slerp(q0: Dordey, q1: Dordey, s: number): Dordey {
  let b = q1;
  let c = q0[0] * q1[0] + q0[1] * q1[1] + q0[2] * q1[2] + q0[3] * q1[3];
  if (c < 0) {
    // kısa yol: −q aynı dönmedir
    b = q1.map((v) => -v) as Dordey;
    c = -c;
  }
  if (c > 1 - 1e-12) return birim(q0.map((v, i) => v + s * (b[i] - v)) as Dordey);
  const om = Math.acos(Math.min(1, c));
  const k0 = Math.sin((1 - s) * om) / Math.sin(om);
  const k1 = Math.sin(s * om) / Math.sin(om);
  return birim(q0.map((v, i) => k0 * v + k1 * b[i]) as Dordey);
}

/**
 * Kesirli nokta indeksi `kf`'de b. gövdenin görsel pozu: k = ⌊kf⌋, s = kf − k; öteleme t_k + s·(t_{k+1} − t_k),
 * dönme SLERP. `kf` tam sayıysa sunucu pozu birebir döner. `kf` [0, n−1] dışına kırpılmaz → Error.
 */
export function pozAraDeger(pozlar: PozDizisi, kf: number, b: number): Poz {
  if (!(kf >= 0 && kf <= pozlar.n - 1)) throw new Error(`kesirli indeks ${kf} aralık dışında (n = ${pozlar.n})`);
  const k = Math.floor(kf);
  const s = kf - k;
  const a = pozAl(pozlar, k, b);
  if (s === 0) return a;
  const c = pozAl(pozlar, k + 1, b);
  return {
    R: dordeyMatris(slerp(dordey(a.R), dordey(c.R), s)),
    t: a.t.map((v, i) => v + s * (c.t[i] - v)) as Vek3,
  };
}

/** Zaman `t` [s] → kesirli nokta indeksi (zaman dizisi azalmayan; eşit zamanlı ardışık noktalarda ilki). */
export function zamandanIndeks(t: number, zaman: ArrayLike<number>): number {
  const n = zaman.length;
  if (n === 0 || !(t >= zaman[0] && t <= zaman[n - 1]))
    throw new Error(`zaman ${t} şerit aralığı dışında`);
  // İlk k: zaman[k] ≥ t (ikili arama).
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const orta = (lo + hi) >> 1;
    if (zaman[orta] >= t) hi = orta;
    else lo = orta + 1;
  }
  if (zaman[lo] === t || lo === 0) return lo;
  return lo - 1 + (t - zaman[lo - 1]) / (zaman[lo] - zaman[lo - 1]);
}

/**
 * Olay → şerit zamanı: sunucunun `zaman` alanı. Adım k, k−1 noktasından k noktasına gider (SPEC 05);
 * `1 ≤ k ≤ n−1` ve `zaman[k−1] ≤ olay.zaman ≤ zaman[k]` değilse Error (tutarsız sunucu verisi).
 */
export function olayZamani(olay: Olay, zaman: ArrayLike<number>): number {
  const { k, zaman: t } = olay;
  if (!Number.isInteger(k) || k < 1 || k >= zaman.length || !(zaman[k - 1] <= t && t <= zaman[k]))
    throw new Error(`olay zamanı tutarsız: k = ${k}, zaman = ${t}`);
  return t;
}

/**
 * Eklem şeridi örneklemesi: j. eklem sütununun (q satır öncelikli n·(3+k)) `genislik` piksele indirgenmiş
 * eğrisi. Her piksel sütunu için o zaman aralığındaki en küçük ve en büyük değer (uçlar kaybolmaz).
 */
export function eklemSeridi(
  zaman: ArrayLike<number>,
  q: ArrayLike<number>,
  sutun: number,
  j: number,
  genislik: number,
): { t: Float64Array; min: Float64Array; max: Float64Array } {
  const n = zaman.length;
  if (n === 0 || genislik < 1 || !Number.isInteger(genislik)) throw new Error("eklem şeridi: boş dizi ya da genişlik");
  if (q.length !== n * sutun || j < 0 || j >= sutun) throw new Error("eklem şeridi: q boyu ya da sütun");
  const t0 = zaman[0];
  const dt = (zaman[n - 1] - t0) / genislik;
  const t = new Float64Array(genislik);
  const min = new Float64Array(genislik).fill(Infinity);
  const max = new Float64Array(genislik).fill(-Infinity);
  for (let p = 0; p < genislik; p++) t[p] = t0 + (p + 0.5) * dt;
  for (let i = 0; i < n; i++) {
    const p = dt > 0 ? Math.min(genislik - 1, Math.floor((zaman[i] - t0) / dt)) : 0;
    const v = q[i * sutun + j];
    if (v < min[p]) min[p] = v;
    if (v > max[p]) max[p] = v;
  }
  // Nokta düşmeyen piksel: komşu noktalar arasında doğrusal değer (yalnız görsel).
  for (let p = 0; p < genislik; p++) {
    if (min[p] <= max[p]) continue;
    const kf = zamandanIndeks(t[p], zaman);
    const k = Math.min(Math.floor(kf), n - 2);
    const s = kf - k;
    const v = q[k * sutun + j] + s * (q[(k + 1) * sutun + j] - q[k * sutun + j]);
    min[p] = v;
    max[p] = v;
  }
  return { t, min, max };
}
