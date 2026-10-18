// SPEC 47b — Çok eksen ekranı (A3 EkranModulu). Sunucu: /api/ekran/cok_eksen (tezgah/ekranlar/cok_eksen.py).
// Davranış: eklem şeridi + olay işaretleri, V ile göreli görünüm (parça sabit ↔ tezgâh sabit), sapma şeridi,
// TCP kapalı uç yolu, tri-dexel ışın görünümü, eklem tablosu ("postprosesör yok"). Kanca: window.__tezgah.cok_eksen.

import type { EkranModulu, Kabuk } from "./tip";

const modul: EkranModulu = {
  ad: "cok_eksen",
  baslik: "Çok eksen",
  tus: "5",
  async ac(alan: HTMLElement, kabuk: Kabuk, secim?: string): Promise<void> {
    void alan;
    void kabuk;
    void secim;
    throw new Error("SPEC 47b: uygulanmadı");
  },
  kapat(): void {
    throw new Error("SPEC 47b: uygulanmadı");
  },
};

export default modul;
