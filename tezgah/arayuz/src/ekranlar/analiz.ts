// SPEC 47c — Analiz ekranı (A3 EkranModulu). Ağ, seçim, koşul, çözüm, sonda ve yakınsama
// sunucudan (/api/ekran/analiz/...) gelir; bu modül çizer ve girdiyi iletir.

import type { EkranModulu, Kabuk } from "./tip";

const analiz: EkranModulu = {
  ad: "analiz",
  baslik: "Analiz",
  tus: "6",
  async ac(alan: HTMLElement, kabuk: Kabuk, secim?: string): Promise<void> {
    void alan;
    void kabuk;
    void secim;
    throw new Error("SPEC 47c: uygulanmadı");
  },
  kapat(): void {
    throw new Error("SPEC 47c: uygulanmadı");
  },
};

export default analiz;
