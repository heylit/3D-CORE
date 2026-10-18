# DURUM — SPEC 32 kesme kuvveti, iş mili gücü ve ilerleme optimizasyonu

Dal: `claude/spec-32-kuvvet-5x6f7q` · Oturum: bulut

## Sıradaki adım
SPEC metninin kullanıcı onayı (koordinatör üzerinden). Onaydan sonra `NotImplementedError` iskeleti.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18 — SPEC**
- `specs/32-kuvvet.md` taslağı: Kienzle (`Fc = K·kc1.1·b·h^(1−mc)`), freze kavrama açısı ve `hm`/`hex`,
  `P = Q·kc/10⁶`, `M = 60000·P/(2πn)`, SPEC 05/22 sonucundan hareket başına yük (salt okunur),
  iş mili denetimi (`SpindleLimits`), talaş incelmesi + güç/tork kapalı form ilerleme ayarı, analiz bölütleri.
- Kod bağımlılıkları: SPEC 05 (main), 14 (PR #27), 22 (PR #41), 30, arayüz A0 (`MachineProfile.spindle_power_kw`,
  `spindle_torque_nm`).

## Açık sorular
1. Malzeme verisi: kodda yerleşik tablo yok; `examples/kienzle_malzemeler.json` kaynaklı örnek değerlerle
   (öneri) mi, yoksa kodda küçük yerleşik tablo mu?
2. İş mili verimi `η` varsayılanı 0.8 (öneri, temkinli) mi, 1.0 mı?
3. Talaş incelmesi hedefi: programlanan `fz`'i `hex` (en büyük talaş kalınlığı) kabul etmek (öneri, Sandvik) mi,
   ortalama `hm` sabit tutmak mı?
4. `max_factor` varsayılanı 2.0 (öneri): ilerleme en çok iki katına çıkar.
5. Hava hareketleri: `air_feed` varsayılanı `None` (öneri, değiştirme) mi, `feed_max` mı?
6. Varsayılan `split=False` (öneri: hareket sayısı korunur, en kötü bölüte göre temkinli) mi, `True` (daha çok süre kazancı) mı?
