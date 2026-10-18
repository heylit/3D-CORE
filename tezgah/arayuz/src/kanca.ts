// SPEC 24 — uçtan uca test kancası (K8): window.__tezgah. Yalnızca okuma; uygulama durumunu değiştirmez.

import type { Nokta3 } from "./tipler";

export interface TezgahKanca {
  /** İş yüklendi ve ilk kare çizildi. */
  hazir: boolean;
  /** G-code satırının üstüne gelinince hayalet takımın konumu; hayalet yoksa null. */
  hayaletKonum(): Nokta3 | null;
  /** DRO'da gösterilen koordinat (torna: [X, 0, Z], X çap modunda çap). */
  dro(): Nokta3;
  /** Oynatıcının şu anki zamanı [s]. */
  zaman(): number;
  /** Gösterilen G-code satır sayısı. */
  gcodeSatirSayisi(): number;
  /** Gösterilen toplam süre [s] (sunucu yanıtından). */
  toplamSure(): number;
  /** Şu anki zamandaki simülasyon yüzeyi (ny·nx float32); sim yoksa null. */
  yuzey(): Float32Array | null;
  // SPEC 25
  /** Açık (yüklenmiş) çalışma alanı. */
  ekran(): "freze" | "torna" | "montaj";
  /** Torna sahnesinde 270° kesit görünümü açık mı (S). */
  kesitAcik(): boolean;
  /** DRO çap modunda mı (varsayılan true; R yarıçap). */
  capModu(): boolean;
  /** Torna ekranında seçili işlem indeksi. */
  seciliIslem(): number | null;
  /** Montaj şeridinin konumu u ∈ [0, N]. */
  montajU(): number;
  /** Sahnede gösterilen bileşen dönüşümü (16 sayı, satır öncelikli); bilinmeyen yolda boş dizi. */
  montajPoz(yol: string): number[];
}

declare global {
  interface Window {
    __tezgah?: TezgahKanca;
  }
}
