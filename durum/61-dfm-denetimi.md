# DURUM — SPEC 61 dfm-denetimi

Dal: `claude/project-thread-aeemx5` · Oturum: bulut

## Sıradaki adım
`atolye/dfm.py` main'de (PR #131). K11: `GET /api/ekran/model/dfm` ayrı modülde (`tezgah/ekranlar/dfm.py`, sekme
olmayan ekran kaydı, `kur(app)` ile bağlanır; model ekranının dosyasına dokunulmaz). İskelet push edildi; testi
SPEC 61 test oturumu yazar (`tests/tezgah/test_dfm_ucu.py`), sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 25 | 0 | `tests/atolye/test_dfm.py`, `test_dfm_hiz.py` (test commit 23fece2, ayrı oturum) |

## Son oturum
**2026-10-18**
- SPEC onaylı metni `specs/61-dfm-denetimi.md`'ye kondu (kullanıcı, 16:06 UTC).
- Uygulama notları (koordinatör onayı, 16:45 UTC; SPEC metni değişmedi):
  1. Erişim ve kalınlık ışını `raymesh.part_intervals` yerine `_Baglam.isin` ile: ağ ışın yönüne dik düzleme
     izdüşürülür, 2B barisentrik test + en yakın isabet. raymesh'in Möller–Trumbore'u 850 üçgende ~0,9 s sürüyordu;
     yeni yolla 3800 üçgen ~0,5 s. Yüz örnekleri ve ışın ağı aynı tek üçgenlemeden (parçanın derin kopyası) gelir;
     kalınlıkta çıkış üçgeninin normali ve yüz indisi doğrudan bilinir.
  2. Torna denetimi K12 yüzünden `cam.turn_profile` / `turn_features` yerine `Part.axial_section(axis="auto")`
     kesitinden: kanal = iki ucu içbükey dönüşlü yatay kenar; iç çap L/D erişilebilen uçtan; iç yay yarıçapı < en
     küçük burun yarıçapı → hata. Keskin iç köşe SPEC 20 kabul ettiği için bulgu değil.
  3. Sınır kutusu düzlemindeki (ham parça) düzlemsel yüzler erişim denetimine girmez (bağlama / ham yüz).
  4. Dönel parçada freze özellik ve erişim denetimleri atlanır; `recognize` 2.5D değil diye hata verirse yalnız
     özellik denetimleri atlanır.
  5. Bütçe aşımı: kalan adımlar atlanır, `tamam=False` ve "kısmi denetim" uyarısı (kural "butce").

## Açık sorular
_(yok)_ — B2 (malzeme) `main`'de yok: `malzeme_grubu=None` iken ince duvar için en sıkı sınır (1,5) kullanılır.
