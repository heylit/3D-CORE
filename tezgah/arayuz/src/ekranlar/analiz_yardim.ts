// SPEC 47c — Analiz ekranının saf yardımcıları (vitest ile sınanır). Mühendislik sayısı hesaplamaz:
// yalnız sunucunun gönderdiği değerleri renge, ekran konumuna ve grafik ölçeğine çevirir.

/** RGB, her bileşen 0..1. */
export type Renk = [number, number, number];

/** Gerilme haritasının varsayılan durakları: mavi → camgöbeği → yeşil → sarı → kırmızı. */
export const GERILME_RENKLERI: readonly Renk[] = [
  [0.18, 0.33, 0.85],
  [0.1, 0.75, 0.85],
  [0.2, 0.8, 0.3],
  [0.95, 0.85, 0.15],
  [0.9, 0.2, 0.15],
];

/**
 * Değer → renk (doğrusal, `renkler` eşit aralıklı duraklar). min → renkler[0], max → son renk;
 * min = max → tek renk (renkler[0]); aralık dışı değer uca kırpılır. NaN döndürmez; NaN girdi → Error.
 */
export function renkOlcegi(deger: number, min: number, max: number, renkler: readonly Renk[]): Renk {
  if (Number.isNaN(deger) || Number.isNaN(min) || Number.isNaN(max)) throw new Error("Renk ölçeğinde NaN");
  if (renkler.length === 0) throw new Error("Renk ölçeğinde durak yok");
  const ilk = renkler[0];
  if (!(max > min) || renkler.length === 1) return [ilk[0], ilk[1], ilk[2]];
  const t = Math.min(1, Math.max(0, (deger - min) / (max - min)));
  const k = t * (renkler.length - 1);
  const i = Math.min(Math.floor(k), renkler.length - 2);
  const f = k - i;
  const a = renkler[i];
  const b = renkler[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** Deforme konumu x + s·u, düz dizilerde (uzunluk nd·3). Boy farkı → Error. */
export function deformeKonum(x: Float32Array, u: Float32Array, s: number): Float32Array {
  if (x.length !== u.length) throw new Error(`Konum (${x.length}) ve yer değiştirme (${u.length}) boyları farklı`);
  const y = new Float32Array(x.length);
  for (let i = 0; i < x.length; i++) y[i] = x[i] + s * u[i];
  return y;
}

/** Sonda grafiği ekseni: içeride bayrağı 1 olan değerlerin [min, max]'ı; hiç yoksa null. */
export function sondaOlcegi(deger: Float64Array, iceride: Uint8Array): [number, number] | null {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (let i = 0; i < deger.length; i++) {
    if (!iceride[i]) continue;
    if (deger[i] < min) min = deger[i];
    if (deger[i] > max) max = deger[i];
  }
  return min <= max ? [min, max] : null;
}
