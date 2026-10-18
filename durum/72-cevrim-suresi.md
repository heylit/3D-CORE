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

## Açık sorular
_(yok)_
