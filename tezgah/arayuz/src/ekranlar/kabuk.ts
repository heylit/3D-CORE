// SPEC 37 — kabuk ön yüzü: proje çubuğu, komut paleti (Ctrl K), etki kartı, sekme rozetleri,
// genel kısayollar (Ctrl Z / Ctrl Shift Z / Ctrl Y / Ctrl S / Ctrl Shift S / Ctrl O).
// Hesap yapmaz: etki kartındaki sayılar /api/proje yanıtlarından gelir.

import type { EkranModulu, Kabuk, Komut } from "./tip";

/** Etki satırı (sunucunun Etki biçimi). */
export interface EtkiSatiri {
  bolum: string;
  ekran: string;
  once: Record<string, number | string>;
  sonra: Record<string, number | string>;
  fark: Record<string, number>;
}

/** GET /api/proje yanıtı. */
export interface ProjeDurumu {
  sema: number;
  ad: string;
  yol: string | null;
  kirli: boolean;
  geri_al: string | null;
  yinele: string | null;
  bolumler: string[];
  uyarilar: unknown[];
  son_etki: EtkiSatiri[] | null;
}

/** Kabuğun kendi komutları (Yeni, Aç, Kaydet, Farklı kaydet, İndir, Yükle, Geri al, Yinele, örnekler). */
export function kabukKomutlari(kabuk: Kabuk): Komut[] {
  void kabuk;
  throw new Error("SPEC 37: uygulanmadı");
}

/** Sekme rozeti metni: ekranın ozet sırasındaki ilk sayısal farkı (işaretli). */
export function rozetMetni(satir: EtkiSatiri): string | null {
  void satir;
  throw new Error("SPEC 37: uygulanmadı");
}

/** Odak metin kutusundaysa (input, textarea, contenteditable) Ctrl Z / Ctrl Y tarayıcıya bırakılır. */
export function metinOdagi(hedef: EventTarget | null): boolean {
  void hedef;
  throw new Error("SPEC 37: uygulanmadı");
}

const ekran: EkranModulu = {
  ad: "kabuk",
  baslik: "Proje",
  async ac(alan, kabuk) {
    void alan;
    void kabuk;
    throw new Error("SPEC 37: uygulanmadı");
  },
  kapat() {
    throw new Error("SPEC 37: uygulanmadı");
  },
};

export default ekran;
