// SPEC 47c — Analiz ekranının saf yardımcıları (vitest ile sınanır). Mühendislik sayısı hesaplamaz:
// yalnız sunucunun gönderdiği değerleri renge, ekran konumuna ve grafik ölçeğine çevirir.

/** RGB, her bileşen 0..1. */
export type Renk = [number, number, number];

/**
 * Değer → renk (doğrusal, `renkler` eşit aralıklı duraklar). min → renkler[0], max → son renk;
 * min = max → tek renk (renkler[0]); aralık dışı değer uca kırpılır. NaN döndürmez; NaN girdi → Error.
 */
export function renkOlcegi(deger: number, min: number, max: number, renkler: readonly Renk[]): Renk {
  void deger;
  void min;
  void max;
  void renkler;
  throw new Error("SPEC 47c: uygulanmadı");
}

/** Deforme konumu x + s·u, düz dizilerde (uzunluk nd·3). Boy farkı → Error. */
export function deformeKonum(x: Float32Array, u: Float32Array, s: number): Float32Array {
  void x;
  void u;
  void s;
  throw new Error("SPEC 47c: uygulanmadı");
}

/** Sonda grafiği ekseni: içeride bayrağı 1 olan değerlerin [min, max]'ı; hiç yoksa null. */
export function sondaOlcegi(deger: Float64Array, iceride: Uint8Array): [number, number] | null {
  void deger;
  void iceride;
  throw new Error("SPEC 47c: uygulanmadı");
}
