# DURUM — SPEC 72 cevrim-suresi

Dal: `claude/project-thread-pzzbar` · Oturum: bulut (kod)

## Sıradaki adım
Main'i dala al, push et; pytest + kapi yeşilse PR #143'ü birleştir ve hash'i koordinatöre gönder (58 ve 62 bekliyor).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: arayüz NotImplementedError gövdeli |
| 2026-10-18 | 151 | 0 | Test düzeltmesi 72a21de alındı (K3 cep yolu eksene paralel) |
| 2026-10-18 | 148 | 3 | Kod yazıldı (test f281e47). Kırmızı: `test_reduces_to_spec05[*-cep]`; testteki çapraz G1 (5,5)→(10,10), K3 kararıyla çelişiyor; düzeltme test thread'inde |

## Son oturum
**2026-10-18**
- Onaylı metin `specs/72-cevrim-suresi.md`'ye kondu.
- İskelet: `cam/sim/sure.py`, `cam/sim/cevrim.py`, `cam/sim/zaman_profili.py`.

- Kod: `sure.py` (kapalı formlar v₀ = v₁ = 0; genel durumda ikiye bölme; tol > 0'da aynı doğrultudaki
  ardışık G1'ler tek segmentte birleşir: blok sınırında ivme sıfırlanmaz, K5/K6 tam), `cevrim.py`, `zaman_profili.py`,
  `cam/post/profiles/zaman/*.json` (3 uydurma örnek, `aciklama` alanında "UYDURMA, ölçülmedi").
- Uygulama kararları: tol = 0 → φ = 0 dahil her blok sınırında tam duruş (K3 için gerekli). İleri bakış ufku N:
  her blok başında hız, sonraki N bloğun boyunda durabilecek kadar; ufku zincir sonuna uzanan bloklarda atlanır.
  Döner hareketli, G93'lü ve G0 blokları duruştan duruşa. İş mili: bağlama değişiminde ve program sonunda M5 duruşu
  sayılır. Bekleme önceki işleme yazılır. Torna takımı değişiminde `turret_index`, frezede `tool_change`.

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
