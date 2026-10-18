// SPEC 25 — çalışma alanlarının ortak arayüzü (kabuk ile ekranlar arasında) ve komut çubuğu satırı.

export interface Komut {
  ad: string;
  aciklama: string;
  calistir: () => void;
  dinamik?: boolean;
}

/** Komut çubuğunda "anahtar sayı" biçimi: ("paso", 2); değilse null. */
export function anahtarSayi(sorgu: string): { anahtar: string; deger: number } | null {
  const m = /^\s*([^\d\s-]+)\s*(-?\d+(?:[.,]\d+)?)\s*$/.exec(sorgu.toLocaleLowerCase("tr"));
  return m ? { anahtar: m[1], deger: Number(m[2].replace(",", ".")) } : null;
}

export const OYNAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M4 2.5v11l9-5.5z"/></svg>`;
export const DURAKLAT_SVG = `<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M3.5 2.5h3v11h-3zM9.5 2.5h3v11h-3z"/></svg>`;
