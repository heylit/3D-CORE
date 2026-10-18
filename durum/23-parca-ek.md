# DURUM — SPEC 23 parca-ek

Dal: `claude/spec-23-parca-ek-die5mp` · Oturum: bulut

## Sıradaki adım
PR'ın kullanıcı tarafından incelenip `main`'e birleştirilmesi; sonra DURUM.md'de 23-parca-ek "tamamlandı" yapılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |
| 2026-10-18 | 127 (SPEC 23) | 0 | Tüm depo 1306 passed, 12 skipped; `--uygulanmamis-hata` ile |

## Son oturum
**2026-10-18**
- SPEC 23 taslağı yazıldı. Tüm formüller OCCT ile ön denendi (build123d 0.13.0): fillet dikey / üst / tüm
  kenar, silindir ve delik ağzı Pappus, havşa, eğimli boydan boya ve kör delik; hepsi rel ≤ 2e-10.

- SPEC kullanıcı tarafından onaylandı (proje sohbeti kartı, 08:28 UTC, "Lamba da ekle"); `counterbore_hole`,
  ISO 4762 / DIN 974-1 lamba tablosu ve K5b eklendi. Lamba formülü OCCT ile ön denendi (rel ≤ 1.2e-14).
- Arayüz eki (`Hole`, `Part.holes`) "Dalga 2 arayüz ekleri" thread'inde PR #23 olarak açıldı; part.py sahibi o thread.

- Testler ayrı oturumda yazıldı (dal `claude/spec-23-parca-ek-testler-3kww4p`, commit `5659c9b`), bu dala
  cherry-pick edildi; kod ayrı commit'te, testlere dokunulmadı.
- `fillet_vertical` kenar seçimi: kenara dik küçük çemberde 8 nokta; içeride kalan < 4 ise dışbükey. Dikiş
  (seam) ve teğet geçişler 4/8, içbükey 6/8 verdiği için seçilmez.
- `inclined_hole` kesicisi giriş ve çıkışta `PAY + r tan θ` uzar (θ: eksen ile yüzey normali). SPEC metni
  sadece PAY diyor; 30°'de PAY = 1 < r tan θ = 2.3 olduğu için ağızda ince bir şerit kesilmeden kalıyordu
  (K7 bunu yakaladı). Davranış SPEC'in formülleriyle aynı, sadece kesici uzunluğu. θ > ~87° reddedilir.
- SPEC 02 `hole`, `pocket`, `chamfer_top` artık girdi kayıtlarını taşıyor; `hole` kendi kaydını ekliyor.

## Açık sorular
- Lamba (counterbore) kullanıcı kararıyla eklendi (kart, 08:28 UTC: "Lamba da ekle"), SPEC bu ekle onaylı.
