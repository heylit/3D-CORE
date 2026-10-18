# DURUM — SPEC 29 islem-plani

Dal: `claude/project-thread-k667wt` · Oturum: bulut

## Sıradaki adım
SPEC metni onaylandı (kullanıcı, 2026-10-18 10:46, "SPEC 29 onaylandı"); kod, bağımlılıklar (SPEC 27, 14, 05, 21, 22) `main`'e
birleşince yazılır (test bağımsızlığı akışıyla).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | K1–K13, K15 | K14 | K8 test düzeltmesi 5de7159 (onaylı, 11:55); K14 SPEC 22 iskeletini bekliyor |

## Son oturum
**2026-10-18**
- SPEC 29 taslağı yazıldı: freze (yüz alma, açık bölge, cep + kalan malzeme, delik, lamba, alt yüz için ikinci
  bağlama) ve torna (alın, kaba, finiş, kanal, iç işlem) işlem planı; takım seçimi ve kesme verisi SPEC 14'ten;
  doğrulama SPEC 05 / 22; G-code SPEC 04 / 14 / 21.
- Arayüz (`*/model.py`, `geometry/part.py`) değişikliği gerekmiyor.
- SPEC metni onaylandı (2026-10-18 10:46). SPEC 05 `main`'de; kod 27, 14, 21, 22'yi bekliyor.

- İskelet: `cam/plan.py`, `cam/plan_turn.py`, `cam/plan_verify.py` (`NotImplementedError`); dal main + SPEC 27
  (`claude/project-thread-ysr96h`) + SPEC 22 iskeleti (`claude/project-thread-012y8t`) üstünde. Testler ayrı oturumda.

## Koordinatör yorumları (2026-10-18 11:27, test thread'inin kapattığı boşluklar; SPEC metni değişmedi)
1. K13 torna: alın planlandıysa sonraki SPEC 20 çağrıları alnı alınmış stokla, `CylinderStock(D, zmin, z_face, d)`
   ile yapılır; `tf.rough` kaba profili sonundan ham yüzeye dik doğruyla uzatılır (dışta `D/2`, içte `d/2`).
2. K14: §7 kesiti profil ucunda kapandığı için rest üst sınırına `V_arka = π(D/2)²(z_son − zmin)` eklenir.
3. K12: stok aynen kalır; SPEC 27 parçanın çevresinde 2 mm açık bölge tanır, oraya yalnız Ø4 sığar ve boyu
   yetmez → `opens[0]` `kesici_boy_yetmez`; kalan / kaldırılan hacimlere bu şeridin hacmi girer.
4. GRBL `length_offsets`: Ek A freze takımlarına ortak tutucu (`gauge_length = 60`), `stickout = flute_length + 10`.

- Kod yazıldı (`cam/plan.py`, `cam/plan_turn.py`, `cam/plan_verify.py`); testler ayrı oturumdan cherry-pick
  (01dac32), kod dokunmadı.

## Açık sorular
_(yok; K8 test ölçüsü 5de7159 ile düzeltildi, kullanıcı onayı 11:55 kartı)_
