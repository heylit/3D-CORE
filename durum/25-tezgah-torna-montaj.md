# DURUM — SPEC 25 tezgah-torna-montaj

Dal: `claude/project-thread-udniip` · Oturum: bulut

## Sıradaki adım
Testler ayrı oturumda (iskelet push edildi). Kod, SPEC 24 iskeleti ile 21, 22, 09 `main`'e girince başlar.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/25-tezgah-torna-montaj.md` taslağı yazıldı: torna ekranı (çap DRO, devir şeridi, 270° kesit, torna sim olayları),
  montaj ekranı (ağaç, BOM, montaj sırası, parça serbestliği ve vida eksenleri, yaklaşma yönü, girişim),
  tek iplik (parametre bağı, ikiye bölme önerisi). Prototipin "Torna" ve "Montaj" sekmelerine dayanır.
- SPEC kullanıcı onayı: 2026-10-18 10:24 UTC, proje sohbetindeki kart ("Önerilerle onayla"); yazılı onay 10:38 UTC.
- İskelet: SPEC 24 dalı (PR #40) bu dala merge edildi; `tezgah/torna.py`, `montaj.py`, `iplik.py`, `ornekler_25.py`,
  `sunucu_25.py` (uçlar kayıtlı, gövdeler `NotImplementedError`), `arayuz/src/torna.ts`, `sira.ts`; `sunucu.py`'ye tek satır
  (`sunucu_25.ekle(app)`, SPEC 24 uçlarından önce). İmzalar 21 (`cam.gcode.lathe`), 22 (`cam.sim`), 09 (`assy.girisim`,
  `geometry.boolean`) ve 28 (`Part.axial_section`) dallarındaki iskeletlere göre; bunlar henüz main'de değil, import'lar
  yalnız tip denetiminde.

## Açık sorular
- SPEC 21 kontrolör çevrimi (`G71`/`G70`/`G76`) yazmıyor: K2'deki çevrim satırı maddesi boş kalır (her satır tek hareket grubu).
- Parçadan dönel profil çıkarma SPEC 22'den SPEC 28'e taşındı (`Part.axial_section`, `turn_profile`); örnek mil profili oradan alınır.
- 24'e eklenen `tur` alanı ve parametre deposu koordinatör üzerinden "Tezgah uygulaması" thread'ine iletildi.
