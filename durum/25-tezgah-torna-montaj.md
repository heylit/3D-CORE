# DURUM — SPEC 25 tezgah-torna-montaj

Dal: `claude/project-thread-udniip` · Oturum: bulut

## Sıradaki adım
İskelet (`NotImplementedError`), SPEC 24'ün `tezgah/` iskeleti `main`'e girince. Kod, SPEC 24 iskeleti ile 21, 22, 09 `main`'e girince başlar.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/25-tezgah-torna-montaj.md` taslağı yazıldı: torna ekranı (çap DRO, devir şeridi, 270° kesit, torna sim olayları),
  montaj ekranı (ağaç, BOM, montaj sırası, parça serbestliği ve vida eksenleri, yaklaşma yönü, girişim),
  tek iplik (parametre bağı, ikiye bölme önerisi). Prototipin "Torna" ve "Montaj" sekmelerine dayanır.
- SPEC kullanıcı onayı: 2026-10-18 10:24 UTC, proje sohbetindeki kart ("Önerilerle onayla").

## Açık sorular
- 21, 22, 09'un fonksiyon adları onaylarından sonra bağlanacak. 22'den gereken: hareket başına kesit durumu,
  `G96`/`G50` altında süre, çene/punta çarpması, parçadan profil. 21'den: çevrim satırlarının kanonik açılımı.
  09'dan: kesişim katısı (ağ için) ve hacmi, boşluk, `common`.
- SPEC 24'e eklenen `tur` alanı ve sunucu parametre deposu "Tezgah uygulaması" thread'ine bildirilmeli.
