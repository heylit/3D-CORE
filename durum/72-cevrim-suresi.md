# DURUM — SPEC 72 cevrim-suresi

Dal: `claude/project-thread-pzzbar` · Oturum: bulut (kod)

## Sıradaki adım
Test thread'inin test commit'ini cherry-pick et, sonra kodu ayrı commit'te yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: arayüz NotImplementedError gövdeli |

## Son oturum
**2026-10-18**
- Onaylı metin `specs/72-cevrim-suresi.md`'ye kondu.
- İskelet: `cam/sim/sure.py`, `cam/sim/cevrim.py`, `cam/sim/zaman_profili.py`.

## Arayüzde metne eklenenler (test thread'i için)
- `TimeProfile.spindle_overlap: str = "max"` ("max" / "toplam"): Karar 4'teki profil bayrağı.
- `Dwell(P)`: işlem listesinde G4 P bekleme (modelde G4 hareketi yok; K10 için).
- `load_time_profile(path, machine=None)`: K12'deki ad eşleşmesi, verilen `MachineProfile` ile denetlenir.

## Koordinatör yorumları (SPEC metni değişmedi)
- **K3 (2026-10-18):** eksen bazlı sınırda çapraz doğruda a_yol = min a_i/|u_i| > a olur. Bu yüzden SPEC 05 `move_time` ile tam eşitlik sadece eksene paralel doğrularda ve yaylarda aranır. Çapraz doğru `toolpath_time ≤ move_time` olarak sınanır.
- **Test thread'i arayüz soruları (2026-10-18):**
  - K8: `toolpath_time(tp, dyn, *, q=None, tcp=False, inv_feed=None)`. q (n+1, 3+k) SPEC 42 biçiminde; döner sütunlar derece, `rot_v` sırasıyla. Döner sınır saf hız sınırı: t_r = |Δq_r|/(rot_v_r/60). G0 ve G1'de t = max(t_doğrusal, max t_r). G93'te `inv_feed` [1/dk] verilirse t = 60/F_inv.
  - K9: `toolpath_time` G18 torna yolunu doğrudan alır. Referans `Machine(rapid=v_max, accel=a)` (accel=None değil). Eşitlik eksene paralel doğrularda ve ZX yaylarında aranır; konikte ≤.
  - `plan_speeds`: 3B (x, y, z) noktalar, F mm/dk. Döner eksen yoksa sınır tuple'ları 3 uzunlukta.

## Açık sorular
_(yok)_
