// SPEC 26 — "Model" ekranı (A3 kaydı): eskiz katmanı, serbestlik haritası, çelişki kartı, ekstrüzyon tutamacı,
// geçmiş şeridi. Uçlar kabuk.api ile /api/ekran/model/ altındadır (SPEC 26 Ek A). Saf hesaplar ../eskiz.ts'te.

import type { EkranModulu, Kabuk } from "./tip";

const ekran: EkranModulu = {
  ad: "model",
  baslik: "Model",
  tus: "7",
  async ac(alan: HTMLElement, kabuk: Kabuk, secim?: string): Promise<void> {
    void [alan, kabuk, secim];
    throw new Error("SPEC 26: model ekranı uygulanmadı");
  },
  kapat(): void {},
};

export default ekran;
