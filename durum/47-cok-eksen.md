# DURUM — SPEC 47b Tezgah çok eksen ekranı

Dal: `claude/project-thread-ol2w60` · PR #93 · Oturum: bulut · Metin: `specs/47-tezgah-ekranlari.md` (onay 2026-10-18 11:13)
Kapsam (SPEC 47 "Alt PR'lar"): K1 (çok eksen), K8–K13, K21, K22–K25 (çok eksen kısmı).

## Sıradaki adım
Kod yazıldı (Python köprü, örnekler, uçlar; TS ekranı). Test thread'inin K8 / G93 düzeltmesi (aşağıdaki kararlar)
cherry-pick edilince tam test, push, CI yeşilse birleştirme.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet (`NotImplementedError` / `Error("SPEC 47b: uygulanmadı")`); test yok. |
| 2026-10-18 | 28 + vitest 136 | 3 | `test_eklemler` ×2, `test_sapma`: test düzeltmesini bekliyor (karar 1, 2). |

## Son oturum
**2026-10-18 (kod)**
- Örnekler: `egik_yuz_3arti2` (iki işlem aynı çerçevede: "pah" SPEC 03 yüz alma, "cep" 30×20×3; yaysız),
  `kubbe_5eksen` (R40 kapak, 2 mm ızgaralı kapalı yükseklik alanı ağı; finish5 + linearize), `kubbe_carpisma`
  (+ `Setup.fixtures` kutusu, SPEC 44 otomatik gövdesi `fikstur_0`; tutucu ve sap çarpar). İş sıfırı C tablası
  üstünde (`G54` = (0, 0, −350)); Ø6 takımlar uydurma tutucuyla (L = 100). `ac_besik_dar`: A ∈ [−40, 40].
- Köprü: nokta dizisi işlem başına (başlangıç + her `Move.end`), zaman SPEC 05 `move_time` (varsayılan `Machine`),
  pahalı hesaplar (eklem, olay, sapma) işin içeriğine göre önbellekli; `simule` uçta parmak izine göre (K21).
- TS: eklem şeridi (döner eksen başına bant, sınır bantları, olay işaretleri; tık → o an), olay listesi (tık →
  çarpışan gövdeler vurgulu), V ile parça sabit ↔ tezgâh sabit (gövde pozları sunucudan, ara değer SLERP),
  TCP kapalı uç yolu, sapma şeridi, eklem tablosu ("postprosesör yok"), simülasyon sonrası dexel ışın çizgileri.

## Kararlar (koordinatör, 2026-10-18 15:55)
1. **Sınır dışı nokta (K8 ↔ K10):** `ac_besik_dar`'da bazı noktalarda A sınır içinde çözümsüz; SPEC 41 `inverse`
   orada hata verir. Ekranın `q`'su SPEC 44 `check` kuralıyla: önce `inverse(kin)`, olmazsa sınırsız kinematik,
   öncekinin açılarından devam (her nokta sınır içindeyse `to_machine` / `joint_path` ile birebir). Kubbe yolu
   sınırsız kinematikle doğrusallaştırılır. SPEC 47 K8 metnine "sınır dışı noktada SPEC 44 kuralı" eki SPEC metni
   sahibine iletildi (kodu yazan oturum SPEC'i değiştirmez).
2. **G93 hızlı hareket:** SPEC 42 `inverse_time` ilerlemesiz G0'ı reddeder; G93 yalnız ilerlemeli hareketlerde:
   G0'lar `feed = 1` ile hesaba girer, sonra 0 yazılır.

## Uygulama notları (SPEC'in açık bıraktığı)
- `kubbe_5eksen` varsayılan profili `ac_besik_dar`; `/dexel` simülasyon yokken 409; dexel ikilisinde görüntü
  başına ızgara başlığı.
- Gövde listesi = tezgâh gövdeleri + SPEC 44'ün otomatik gövdeleri (ham malzeme, fikstür, takım, sap, tutucu);
  `govde_ikili(model, ad)` ikisini de çizebilsin diye işin modeli `MachineModel` alt sınıfı (`otomatik` alanı;
  çekirdek okumaz).
- finish5 `max_dangle = 5 + 2(|lead| + |tilt|)`: zikzak dönüşünde ilerleme yönü tersine döner, eğim de onunla.
- Kubbe raster sıraları A = 0 tekilliğinden uzak seçilir (`kubbe_y`): tekil noktadan geçen sıra C'yi çok hızlı
  döndürür, doğrusallaştırma çok kısa hareket üretir ve G93 99999 sınırını aşar. Büyük tilt (≥ 20°) değerinde
  çekirdek yine G93 sınırı hatası verebilir (uç 422 + metin).
- Ekran biçimi `cok_eksen.ts` içinde (`<style>` ekran açıkken eklenir).

## Açık sorular
- Yok. Bilgi: bazı çok eksen testleri 10 s'yi aşıyor (kubbe kurulumu ~15 s, `check` ~8 s); `@slow` işareti
  test thread'inin kararı.
