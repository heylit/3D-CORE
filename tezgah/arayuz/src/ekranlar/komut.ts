// SPEC 62 — "Komut" ekranı: komut paleti (Enter önizler, ikinci Enter uygular, Esc vazgeçer).
// Ctrl+K kabuğundur; kanca gelene kadar palet bu sekmede çalışır. Saf fonksiyonlar vitest ile sınanır.

import type { EkranModulu } from "./tip";

/** Uçuştaki isteklerden yalnız en son gönderilenin yanıtı kullanılır (sira artan). */
export function yanitGecerliMi(_yanitSira: number, _sonGonderilen: number): boolean {
  throw new Error("SPEC 62: yanitGecerliMi uygulanmadı");
}

const EKRAN: EkranModulu = {
  ad: "komut",
  baslik: "Komut",
  async ac() {
    throw new Error("SPEC 62: komut ekranı uygulanmadı");
  },
  kapat() {},
};

export default EKRAN;
