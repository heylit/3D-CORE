// A3 — ön yüz ekran kaydı: src/ekranlar/*.ts modüllerini toplar, sunucunun listesiyle kesiştirir.
// Saf fonksiyonlar (ekranlariSirala, modulleriDogrula, kisayolDogrula) vitest ile sınanır.

import type { EkranModulu, Sekme, SunucuEkrani } from "./tip";

/**
 * Sunucu listesi ∩ ön yüz modülleri → sekmeler. Sıra: sunucunun `sira`'sı, eşitse `ad`.
 * Sunucuda olup ön yüzü olmayan ya da `hazir` olmayan ekran kapalı sekmedir (neden ipucu);
 * ön yüzde olup sunucuda olmayan gösterilmez (çağıran konsola uyarı yazar).
 */
export function ekranlariSirala(sunucu: SunucuEkrani[], onYuz: EkranModulu[]): Sekme[] {
  void sunucu;
  void onYuz;
  throw new Error("A3: uygulanmadı");
}

/** Çift `ad`, çift `tus`, tek rakam olmayan `tus` → Error. */
export function modulleriDogrula(moduller: EkranModulu[]): void {
  void moduller;
  throw new Error("A3: uygulanmadı");
}

/** Kabuğa ait kısayol (KABUK_KISAYOLLARI, büyük/küçük harf ve sıra farkı gözetmeden) → Error. */
export function kisayolDogrula(kisayol: string): void {
  void kisayol;
  throw new Error("A3: uygulanmadı");
}

/** src/ekranlar/*.ts (tip.ts ve kayit.ts hariç) varsayılan dışa aktarımları; yüklemede doğrulanır. */
export function kayitliModuller(): EkranModulu[] {
  throw new Error("A3: uygulanmadı");
}
