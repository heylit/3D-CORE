// A3 — ön yüz ekran kaydı: src/ekranlar/*.ts modüllerini toplar, sunucunun listesiyle kesiştirir.
// Saf fonksiyonlar (ekranlariSirala, modulleriDogrula, kisayolDogrula, modulleriTopla) vitest ile sınanır.

import { KABUK_KISAYOLLARI, type EkranModulu, type Sekme, type SunucuEkrani } from "./tip";

/**
 * Sunucu listesi ∩ ön yüz modülleri → sekmeler. Sıra: sunucunun `sira`'sı, eşitse `ad`.
 * Sunucuda olup ön yüzü olmayan ya da `hazir` olmayan ekran kapalı sekmedir (neden ipucu);
 * ön yüzde olup sunucuda olmayan gösterilmez (çağıran konsola uyarı yazar).
 */
export function ekranlariSirala(sunucu: SunucuEkrani[], onYuz: EkranModulu[]): Sekme[] {
  const moduller = new Map(onYuz.map((m) => [m.ad, m]));
  const sirali = [...sunucu].sort((a, b) => a.sira - b.sira || (a.ad < b.ad ? -1 : a.ad > b.ad ? 1 : 0));
  return sirali.map((s): Sekme => {
    const modul = moduller.get(s.ad) ?? null;
    let neden: string | null = null;
    if (!s.hazir) neden = s.neden ?? `${s.baslik} kullanılamıyor`;
    else if (modul === null) neden = `${s.baslik}: ön yüz modülü yok (src/ekranlar/${s.ad}.ts)`;
    return { ad: s.ad, baslik: s.baslik, tus: s.tus, acik: neden === null, neden, modul };
  });
}

/** Çift `ad`, çift `tus`, tek rakam olmayan `tus` → Error. */
export function modulleriDogrula(moduller: EkranModulu[]): void {
  const adlar = new Set<string>();
  const tuslar = new Map<string, string>();
  for (const m of moduller) {
    if (adlar.has(m.ad)) throw new Error(`Ekran adı iki kez kayıtlı: ${m.ad}`);
    adlar.add(m.ad);
    if (m.tus === undefined) continue;
    if (!/^[0-9]$/.test(m.tus)) throw new Error(`'${m.ad}': sekme tuşu tek rakam olmalı, ${JSON.stringify(m.tus)} verildi`);
    const onceki = tuslar.get(m.tus);
    if (onceki !== undefined) throw new Error(`Sekme tuşu ${m.tus} iki ekranda: ${onceki} ve ${m.ad}`);
    tuslar.set(m.tus, m.ad);
  }
}

/** Kısayolun karşılaştırma biçimi: parçalar küçük harf ve sıralı ("Shift+Ctrl+Z" = "ctrl+shift+z"). */
function kisayolAnahtari(k: string): string {
  return k
    .split("+")
    .map((p) => p.trim().toLowerCase())
    .sort()
    .join("+");
}

const KABUK = new Set(KABUK_KISAYOLLARI.map(kisayolAnahtari));

/** Kabuğa ait kısayol (KABUK_KISAYOLLARI, büyük/küçük harf ve sıra farkı gözetmeden) → Error. */
export function kisayolDogrula(kisayol: string): void {
  if (KABUK.has(kisayolAnahtari(kisayol))) throw new Error(`${kisayol} kabuğa ait kısayol`);
}

function ekranModuluMu(x: unknown): x is EkranModulu {
  if (typeof x !== "object" || x === null) return false;
  const m = x as Record<string, unknown>;
  return (
    typeof m.ad === "string" &&
    typeof m.baslik === "string" &&
    (m.tus === undefined || typeof m.tus === "string") &&
    typeof m.ac === "function" &&
    typeof m.kapat === "function"
  );
}

/**
 * Dosya yolu → modül (import.meta.glob biçimi) eşlemesinden ekran modülleri. tip.ts ve kayit.ts atlanır;
 * varsayılan dışa aktarımı olmayan modül (yardımcı) atlanır; varsayılanı EkranModulu olmayan → Error.
 * Sonuç modulleriDogrula'dan geçer.
 */
export function modulleriTopla(kayitlar: Record<string, unknown>): EkranModulu[] {
  const M: EkranModulu[] = [];
  for (const yol of Object.keys(kayitlar).sort()) {
    if (/(^|\/)(tip|kayit)\.ts$/.test(yol)) continue;
    const modul = kayitlar[yol] as { default?: unknown } | null;
    if (modul === null || typeof modul !== "object" || modul.default === undefined) continue;
    if (!ekranModuluMu(modul.default)) throw new Error(`${yol}: varsayılan dışa aktarım bir EkranModulu değil`);
    M.push(modul.default);
  }
  modulleriDogrula(M);
  return M;
}

/** src/ekranlar/*.ts (tip.ts ve kayit.ts hariç) varsayılan dışa aktarımları; yüklemede doğrulanır. */
export function kayitliModuller(): EkranModulu[] {
  return modulleriTopla(import.meta.glob("./*.ts", { eager: true }));
}
