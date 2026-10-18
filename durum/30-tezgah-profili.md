# DURUM — SPEC 30 tezgah-profili

Dal: `claude/project-thread-t2yott` · Oturum: bulut ("Postprosesörler ve tezgâh profilleri" thread'i)

## Sıradaki adım
Kod yazıldı (testler 62a03ea, ayrı thread). `test_K2_blocks_carry_rounded_values` test verisi geçersiz yay
üretiyor (yay başı 0.0002 mm kaydırılmış, ARC_TOL = 1e-6): düzeltme test thread'inden istendi (altın kural 2).
`cam/gcode/writer.py` henüz `format(plan())`'a çevrilmedi (#27 / #42 çakışmasın diye); eşdeğerlik K1 altın testiyle denetleniyor.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 173 | 1 | SPEC 30 testleri; kalan: K2 yuvarlama testinin geçersiz yayı. Tüm paket 2660 geçti |

## SPEC 04b blok ekleri (2026-10-18, ayrı PR)
`Cycle.p`, `RigidTap`, `Dwell`; `Dialect.rigid_tap` ("m29" Fanuc, "g84" Haas, "" GRBL) ve `dwell_ms` (Fanuc);
`hole_moves` G82 / G84; `plan()` ve `cam.gcode.write` G82 / G84 op'larını (`kind` + `to_toolpath`, `cam/cevrimler.py`'yi
import etmeden) kabul eder; `write` bu op'lar varsa `format(plan())` ile yazar (eski yazıcı diğer işlerde aynen).
Okuyucu: G82 (P zorunlu), G84 (M3, Fanuc'ta M29 S, Q yok), `M29 S`, `G4 P`. `check_machine` kılavuz F'yi açılımıyla denetler.
SPEC 04b altın metinleri (Örnek A / B; Fanuc, Haas, GRBL) uydurma op'larla yerelde denendi; 04b testleri A0 ve
`cam/cevrimler.py` gelince çalışır.

## Son oturum
**2026-10-18**
- SPEC taslağı yazıldı (`specs/30-tezgah-profili.md`).
- Kod: `cam/post/` (check, machine, post, plan/format), `HAAS` dili, okuyucuda `G53 G0 Z`, örnek Haas `rpm_max = 12000`.
- SPEC 30 Ek A (SPEC 40 Ek E2, torna profili) metne işlendi (kullanıcı onayı 11:13).
- Karar: `post` güvenli Z'yi (op başı / geri çekme) her op'un takım boyuyla Z kursunda ayrıca denetler.

## Açık sorular
SPEC dosyasının "Açık sorular" / "Varsayımlar" bölümüne bakınız.

## Sıradaki işler (not)
- SPEC 40 Ek E2 (PR #75, onay bekliyor): SPEC 30 bittikten sonra ayrı küçük PR. Torna kurs denetimi
  (X_m = 2(x + o_x) çap, Z_m = z + o_z, yay eksen noktaları, tool_change kurs içinde), devir
  rpm_min ≤ S ≤ rpm_max (G96'da G50 değeri), ilerleme feed·S ≤ feed_max, taret 1 ≤ T ≤ tool_slots,
  freze yolu + torna profili → CamError; `post_lathe(ops, machine, setup, spindle, tool_change, program_no)`
  = check + write_lathe + iki POST yorumu; `cam/post/profiles/ornek-fanuc-torna.json`. Testler
  `tests/cam/test_post_lathe.py` (SPEC 40 K14–K16, SPEC 40 test thread'i).
- SPEC 04b (kılavuz / punta / havşa çevrimleri) biçimleyicilere blok türü isteyecek.
- SPEC 04b (PR #81, onay bekliyor) blok ekleri, SPEC 30 bittikten sonra ayrı PR: `Cycle.kind` ∈ {G81, G82, G83, G84}
  ve `p` (bekleme, s); `RigidTap(rpm)` (Fanuc `M29 S<rpm>`, Haas'ta satır yok); `Dwell(seconds)` (GRBL `G4 P`,
  Sinumerik `G4 F`, Heidenhain `CYCL DEF 9.0/9.1`); `plan()` DwellDrillOp / TapOp kabul eder (çevrimsiz dilde
  TapOp → CamError); `Dialect.rigid_tap` ("m29" Fanuc, "g84" Haas, "" diğer); biçim `G98 G82 X Y Z R P F`
  (Fanuc P ms tam sayı, Haas P ondalıklı s), `G98 G84 X Y Z R F`; okuyucu G82 (P zorunlu), G84, M29 S, G4 P;
  M3'süz / M4'lü G84, G84 Q, Fanuc'ta M29'suz G84 → CamError; `check_machine` kılavuz F'yi feed_max'e tabi tutar.
  Sinumerik / Heidenhain'de kılavuz şimdilik CamError.
- Kullanıcının tezgâhları DMG MORI (büyük olasılıkla Sinumerik 840D sl veya Heidenhain TNC 640): SPEC 31 öncelikli.

## SPEC 40 Ek E2 — torna profili (2026-10-18)
- İskelet: `cam/post/lathe.py` (`check_lathe`, `post_lathe`; NotImplementedError), `cam.post`'tan dışa açık.
- Bağımlılık: E1 (`MachineProfile.validate()` `kind = "lathe"`, #107) birleşmeden örnek torna profili
  (`ornek-fanuc-torna.json`) eklenemez (`builtin_machines()` yüklerken düşer); K16'nın eksenel delme kısmı E3'e (#88) bağlı.
- Testler `tests/cam/test_post_lathe.py` (SPEC 40 K14–K16) ayrı test thread'inde; `test_post_machine.py` örnek listesi dörde çıkar.
- Testler 3ba81cb (cherry-pick); kod ayrı commit'te: `check_lathe` (kurs, devir, feed·S, taret, freze yolu, G54),
  `post_lathe` = `check_lathe` + `write_lathe` + başlığın 3 satırından sonra iki yorum; `post()` torna profilinde
  CamError ("post_lathe kullanın"), `dialect_for` torna profilinde `FANUC_TORNA`.
- Test durumu: 46 / 47 geçti; `test_K16_axial_drill_post_equals_write_lathe` E3 (#88) birleşene kadar uygulanmamış
  (CI'da kırmızı). PR #111, #88'den sonra main alınıp birleştirilir.
