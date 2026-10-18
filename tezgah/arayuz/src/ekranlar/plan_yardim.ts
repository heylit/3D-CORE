// SPEC 47a — Plan ekranının saf yardımcıları (vitest ile test edilir). Hesap yapmaz: sunucu sözlüklerini biçimler.

export interface Fark {
  eklenen: string[];
  cikan: string[];
  takimi_degisen: { adres: string; once: number; sonra: number }[];
  yeni_planlanamayan: { adres: string; kod: string }[];
  kurtulan: string[];
  sure_farki: number;
  takim_degisimi_farki: number;
}

export interface Rozet {
  tur: "eklendi" | "cikti" | "takim" | "planlanamadi" | "kurtuldu" | "sure" | "takim_degisimi";
  isaret: "+" | "−" | "~" | "0";
  metin: string;
}

/** SPEC 29 §1 gerekçe ve not kodu → düz Türkçe metin. Bilinmeyen kod → Error (sessiz yok). */
export function gerekceMetni(_kod: string): string {
  throw new Error("SPEC 47a: gerekceMetni uygulanmadı");
}

/** Fark → rozet listesi (sunucunun sayıları; işaret yalnız sayının işaretidir, 0 → "0"). */
export function farkRozetleri(_fark: Fark): Rozet[] {
  throw new Error("SPEC 47a: farkRozetleri uygulanmadı");
}

/** Özellik satırları: önce planlanamayanlar, sonra adres sırası (sunucu sırası korunur). */
export function ozellikSirala<T extends { adres: string; durum: string }>(_satirlar: T[]): T[] {
  throw new Error("SPEC 47a: ozellikSirala uygulanmadı");
}
