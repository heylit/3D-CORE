# DURUM — SPEC 46 Uçtan uca altın senaryo

Dal: `claude/spec-46-uctan-uca-9q6dbf` · Oturum: bulut (Dalga 5, hat H17) · PR #83

## Sıradaki adım
H1–H15'in hepsi yazıldı ve yeşil (H11 + H14 üçüncü PR'da). Bu PR birleşince K18: Dalga 5 biter, DURUM sahibine bildirilir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 25 | 0 | H1–H7; 2 atlama: `rs274` yerelde kurulu değil (CI kapsayıcısında var) |
| 2026-10-18 | 29 | 0 | + H8 (09), H9 (21), H12 (27); uygulama hatası yok |
| 2026-10-18 | 30 | 0 | + H13 (28); `outer` alın doğrusunu da içerir (pah + silindir elle profille aynı) |
| 2026-10-18 | 40 | 0 | + H15 (30): 3 yerleşik profil; freze takımlarına uydurma ER32 tutucu + sarkma eklendi (Z kursu denetimi ölçü boyu ister); `gcode_ref` G53 desteklemediğinden G53 satırları karşılaştırmadan önce atılır |
| 2026-10-18 | 45 | 0 | + H10 (22), dz 0.5 / 0.25; torna kalemine uydurma `edge_len = 8` (SPEC 22 kesici bölge ister). Not: CI'daki rs274 adımı yalnız `tests/reference`'ı koşturur, H5'in rs274 testi CI'da da atlanır (ortak `.github` dosyası; koordinatöre iletildi) |
| 2026-10-18 | 56 | 0 | + H11 (17 + 26): tam kısıtlı eskiz (dof 0) → `regions` → `extrude`; H1 flanşıyla hacim, kutu ve simetrik fark eşit. + H14 (29): freze ve torna planı, `verify_*`, K4 / K5 / K9 / K10 denetimleri. İki test tarafı seçimi: (1) flanşın Ø20 deliği delik kaydı taşır, SPEC 29 kayıtlı deliği yalnız matkapla planlar → H14 kendi kütüphanesine uydurma Ø20 matkap (T4) ekler, §1 kütüphanesi değişmez; (2) `plan_turn` alından başlayan profil ister → `turn_profile(mil).outer` (SPEC 28) verilir |

## Son oturum
**2026-10-18**
- SPEC 46 yazıldı, kullanıcının 11:14 "2 dk kuralı" ile önerilerle onaylandı.
- `tests/uctan_uca/` H1–H7 yazıldı, hepsi yeşil. Uygulama hatası bulunmadı.
- 09, 21, 27 birleşince H8, H9, H12 eklendi; `montaj` fikstürü conftest'e taşındı (H8 çözülmüş ağacı kullanır).
- Testler yazılırken SPEC'te iki tutarsızlık düzeltildi (SPEC başındaki not): delme dibi `z = 0` (SPEC 14),
  K7 burun merkezi ölçütü (SPEC 20 hayali uç). Alın sonrası çubuk `zmax = 60` (SPEC 20: profil ön yüzden başlar).
- z-map kaldırılan hacim farkı ~60 mm³, sınır 1749 mm³ (sınır gevşek; daha sıkısı H10 / 22 ile değil, SPEC 05'in işi).

## Açık sorular
_(yok)_
