# DURUM — SPEC 32 kesme kuvveti, iş mili gücü ve ilerleme optimizasyonu

Dal: `claude/spec-32-kuvvet-5x6f7q` · Oturum: bulut

## Sıradaki adım
SPEC 22 (`simulate_lathe`) ve A0 (`MachineProfile.spindle_power_kw` / `spindle_torque_nm`) main'e girince main'i merge edip 8 uygulanmamış testi yeşile çevirmek, sonra PR #66'yı birleştirmek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 153 SPEC 32 | 1 uygulanmamış | SPEC 22 sonrası; kalan: `from_profile` (A0). |
| 2026-10-18 | 146 SPEC 32 | 8 uygulanmamış | Bağımsız testler (150fd08 + 18db041, cherry-pick) + kod. Kalan 8: torna (SPEC 22) ve `from_profile` (A0) bağımlılıkları. |

## Son oturum
**2026-10-18 — kod**
- `cam/kuvvet.py`: Kienzle, kavrama, güç/tork, `milling_loads` (olay listesinden `ap`, `Q = ΔV/t⁰`, eşdeğer `ae`),
  `lathe_loads` (`section_at` farkından `r_k`), `check_spindle`. `cam/ilerleme_opt.py`: `split_moves`, bölüt yüklerinin
  en kötüsüne indirgeme, `c` kapalı formu, aşağı yuvarlama, `split=True` birleştirme, yeniden simülasyonla doğrulama.
- SPEC 22 (#41) main'e girdi; torna testleri çalıştı. Düzeltme: tornada `c_ince = 1` adayı eklendi (ilerleme yalnız
  düşer, SPEC "İlerleme ayarı" 1); önceden `max_factor`'a kadar artıyordu.

**2026-10-18 — SPEC**
- `specs/32-kuvvet.md` taslağı: Kienzle (`Fc = K·kc1.1·b·h^(1−mc)`), freze kavrama açısı ve `hm`/`hex`,
  `P = Q·kc/10⁶`, `M = 60000·P/(2πn)`, SPEC 05/22 sonucundan hareket başına yük (salt okunur),
  iş mili denetimi (`SpindleLimits`), talaş incelmesi + güç/tork kapalı form ilerleme ayarı, analiz bölütleri.
- Kod bağımlılıkları: SPEC 05 (main), 14 (PR #27), 22 (PR #41), 30, arayüz A0 (`MachineProfile.spindle_power_kw`,
  `spindle_torque_nm`).
- SPEC onaylandı; `NotImplementedError` iskeleti (`cam/kuvvet.py`, `cam/ilerleme_opt.py`) ve örnek malzeme dosyası push edildi.

## Kararlar
- 2026-10-18 11:13 UTC kullanıcı yazılı toplu onayı: SPEC 32 metni önerilerle, A0 arayüz eki onaylı. Önerilen
  varsayılanlar (1 örnek JSON, 2 `eta = 0.8`, 3 `hex` hedefi, 4 `max_factor = 2.0`, 5 `air_feed = None`, 6 `split = False`) geçerli.
- K6 sayısal örneği (koordinatör 11:41, test yazarının yorumu): SPEC Teori'deki `P = 2.99070 kW`, `M = 22.4302 N·m`
  `Vc`'yi dış çapta alır; simülasyonun `Q`'su kesilen halka hacminden gelir (ortalama yarıçap `r_m = R − ap/2`), bu yüzden
  testler `P = 2.99070·r_m/R`, `M = 22.4302·r_m/R` bekler. Kod SPEC formülünü (`Q = ΔV/t⁰`) uygular; SPEC metni
  kullanıcı onayı olmadan değiştirilmedi.
- Her kesme hareketi (havadaki G1/G2/G3 dahil) için bir `FeedChange` kaydı yazılır; değişmeyenlerin gerekçesi `degismedi`.

- K7 testi düzeltildi (kullanıcı 11:14 kuralı "2 dk içinde itiraz yoksa öneriyi kabul et", koordinatör sorusu 11:48):
  beklenen aşırı yük kümesi kanalın devamı olan hareketi de içerir; test commit'i `18db041` (test oturumu).

## Açık sorular
_(yok)_
