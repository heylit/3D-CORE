// SPEC 25 — montaj sırası: adım ↔ u eşlemesi, poz ara değeri, serbestlik çipi (K17). Saf fonksiyonlar.
// Dönüşümler sunucudan gelir (4x4, satır öncelikli, 16 sayı); burada yalnızca görsel ara değer var.

export type Mat4 = number[]; // 16 eleman, satır öncelikli

export interface Serbestlik {
  sayi: number;
  oteleme: [number, number, number][];
  vida: { yon: [number, number, number]; nokta: [number, number, number]; hatve: number }[];
  etiketler: string[];
}

export interface Adim {
  i: number;
  yol: string;
  ad: string;
  yaklasma: [number, number, number];
  mesafe: number;
  T_once: Record<string, Mat4>;
  T_sonra: Record<string, Mat4>;
  dof_toplam: number;
  serbestlik: Record<string, Serbestlik>;
}

/** u ∈ [0, N] → (adım i, adım içi s ∈ [0, 1]); u = N → (N − 1, 1). u kırpılır; N < 1 ise Error. */
export function adimU(_u: number, _N: number): { i: number; s: number } {
  throw new Error("SPEC 25: adimU uygulanmadı");
}

/**
 * u anında `yol` bileşeninin pozu. Bileşen henüz gelmemişse (u < adımı) ilk adımın T_once'u;
 * kendi adımında T_once → T_sonra arasında yalnız öteleme yumuşatılır (dönme T_sonra'nınki);
 * sonraki adımlarda o adımın T_sonra'sı. u tam sayıda sunucunun T'si birebir döner.
 */
export function poz(_sira: Adim[], _yol: string, _u: number): Mat4 {
  throw new Error("SPEC 25: poz uygulanmadı");
}

/** Serbestlik çipi: 6 kare; ilk `6 − sayi` dolu (kilitli), etiketler sunucudan sırasıyla. */
export function cip(_s: Serbestlik): { kilitli: boolean; etiket: string }[] {
  throw new Error("SPEC 25: cip uygulanmadı");
}
