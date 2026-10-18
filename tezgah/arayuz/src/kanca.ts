// SPEC 24 — uçtan uca test kancası (K8): window.__tezgah. Yalnızca okuma; uygulama durumunu değiştirmez.

import type { Nokta3 } from "./tipler";

export interface TezgahKanca {
  /** İş yüklendi ve ilk kare çizildi. */
  hazir: boolean;
  /** G-code satırının üstüne gelinince hayalet takımın konumu; hayalet yoksa null. */
  hayaletKonum(): Nokta3 | null;
  /** DRO'da gösterilen koordinat. */
  dro(): Nokta3;
  /** Oynatıcının şu anki zamanı [s]. */
  zaman(): number;
  /** Gösterilen G-code satır sayısı. */
  gcodeSatirSayisi(): number;
  /** Gösterilen toplam süre [s] (sunucu yanıtından). */
  toplamSure(): number;
  /** Şu anki zamandaki simülasyon yüzeyi (ny·nx float32); sim yoksa null. */
  yuzey(): Float32Array | null;
  /** A3: sahnedeki ekran katmanlarının adları (yalnız etkin ekranınki olmalı). */
  katmanlar(): string[];
  /** A3: ekran başına kanca, window.__tezgah.<ad>. */
  [ekran: string]: unknown;
}

declare global {
  interface Window {
    __tezgah?: TezgahKanca;
  }
}
