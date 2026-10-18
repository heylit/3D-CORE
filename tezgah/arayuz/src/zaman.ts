// SPEC 24 — zaman ↔ indeks, şerit ölçeği, kıvılcım grafiği örnekleme. Saf fonksiyonlar (K7).
// Arayüz hesap yapmaz: süreler sunucudan gelir; burada yalnızca arama ve görsel ara değer var.

import type { Nokta3 } from "./tipler";

/**
 * k(t) = max{k : T[k] ≤ t}, ikili arama. T azalmayan, uzunluk ≥ 1.
 * t < T[0] → 0; t ≥ T[son] → son indeks; eşit süreli noktalarda en büyük k.
 * T boşsa ya da t sonlu değilse Error.
 */
export function idxAt(t: number, T: ArrayLike<number>): number {
  const n = T.length;
  if (n === 0) throw new Error("idxAt: zaman dizisi boş");
  if (!Number.isFinite(t)) throw new Error(`idxAt: t sonlu olmalı (${t})`);
  if (t < T[0]) return 0;
  // değişmez: T[lo] ≤ t, (hi = n ya da T[hi] > t)
  let lo = 0;
  let hi = n;
  while (hi - lo > 1) {
    const m = (lo + hi) >>> 1;
    if (T[m] <= t) lo = m;
    else hi = m;
  }
  return lo;
}

/**
 * t anında takımın görsel konumu: k = idxAt(t) ile k+1 arasında doğrusal ara değer
 * (T[k+1] = T[k] ise ya da k son indeksse P[k]). P = Float32Array(n·3).
 */
export function konumAt(t: number, T: ArrayLike<number>, P: ArrayLike<number>): Nokta3 {
  const k = idxAt(t, T);
  const nokta = (i: number): Nokta3 => [P[3 * i], P[3 * i + 1], P[3 * i + 2]];
  if (k >= T.length - 1 || T[k + 1] <= T[k]) return nokta(k);
  const u = Math.min(1, Math.max(0, (t - T[k]) / (T[k + 1] - T[k])));
  const a = nokta(k);
  const b = nokta(k + 1);
  return [a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u];
}

function aralik(t0: number, t1: number, genislik: number): void {
  if (!(t1 > t0)) throw new Error(`Şerit: t1 > t0 olmalı (${t0}, ${t1})`);
  if (!(genislik > 0)) throw new Error(`Şerit: genişlik pozitif olmalı (${genislik})`);
}

/** Zaman → şerit pikseli: x = (t − t0) / (t1 − t0) · genislik, [0, genislik]'e kırpılır. t1 ≤ t0 ise Error. */
export function zamanPx(t: number, t0: number, t1: number, genislik: number): number {
  aralik(t0, t1, genislik);
  const x = ((t - t0) / (t1 - t0)) * genislik;
  return Math.min(genislik, Math.max(0, x));
}

/** Şerit pikseli → zaman (zamanPx'in tersi), [t0, t1]'e kırpılır. */
export function pxZaman(x: number, t0: number, t1: number, genislik: number): number {
  aralik(t0, t1, genislik);
  const t = t0 + (x / genislik) * (t1 - t0);
  return Math.min(t1, Math.max(t0, t));
}

/**
 * Onay işareti adımı [s]: {1, 2, 5}·10^m dizisinden, iki işaret arası ≥ minPx piksel olan en küçük adım.
 * sure > 0, genislik > 0, minPx > 0; aksi halde Error.
 */
export function tickAdimi(sure: number, genislik: number, minPx = 60): number {
  if (!(sure > 0) || !(genislik > 0) || !(minPx > 0) || !Number.isFinite(sure + genislik + minPx)) {
    throw new Error(`tickAdimi: sure, genislik ve minPx pozitif olmalı (${sure}, ${genislik}, ${minPx})`);
  }
  const enAz = (sure * minPx) / genislik; // adım ≥ enAz saniye
  let m = Math.floor(Math.log10(enAz)) - 1;
  for (;;) {
    for (const c of [1, 2, 5]) {
      const adim = c * 10 ** m;
      // kayan nokta: 10^m tam değil; göreli tolerans
      if (adim >= enAz * (1 - 1e-12)) return adim;
    }
    m += 1;
  }
}

/**
 * Kıvılcım grafiği örnekleme: [T[0], T[son]] aralığı `kova` eşit zaman kovasına bölünür; her kovaya
 * düşen Y değerlerinin en büyüğü (boş kovada bir önceki kovanın değeri, ilk kova boşsa 0).
 * Dönen dizi uzunluğu `kova`. kova ≥ 1 tam sayı; T ve Y aynı uzunlukta; aksi halde Error.
 */
export function kivilcim(T: ArrayLike<number>, Y: ArrayLike<number>, kova: number): Float32Array {
  if (!Number.isInteger(kova) || kova < 1) throw new Error(`kivilcim: kova ≥ 1 tam sayı olmalı (${kova})`);
  if (T.length !== Y.length) throw new Error(`kivilcim: T (${T.length}) ve Y (${Y.length}) aynı uzunlukta olmalı`);
  const out = new Float32Array(kova);
  const dolu = new Uint8Array(kova);
  const n = T.length;
  if (n === 0) return out;
  const t0 = T[0];
  const sure = T[n - 1] - t0;
  for (let i = 0; i < n; i++) {
    const b = sure > 0 ? Math.min(kova - 1, Math.floor(((T[i] - t0) / sure) * kova)) : 0;
    if (!dolu[b] || Y[i] > out[b]) out[b] = Y[i];
    dolu[b] = 1;
  }
  for (let b = 1; b < kova; b++) if (!dolu[b]) out[b] = out[b - 1];
  return out;
}
