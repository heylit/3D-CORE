# DURUM — SPEC 05 talaş simülasyonu, süre, çakma ve çarpışma

Dal: `claude/spec-05-cam-sim-ch33p2` · Oturum: bulut

## Sıradaki adım
SPEC metninin kullanıcı onayı; onaydan sonra `NotImplementedError` gövdeli `cam/sim/` iskeleti push edilir ve
test dosyaları listesi bağımsız test oturumuna verilir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/05-cam-sim.md` taslağı yazıldı: z-haritası, süpürme zarfı (düz kapalı form, küresel/köşe radyüslü
  dışbükey minimizasyon), gövde basamakları ile sap/tutucu çarpışması, hızlı çarpma, mesh'ten parça z-haritası
  ile çakma, trapez süre, SPEC 24 için olay listesi (CSR).
- Kararlar koordinatöre gönderildi (aşağıda).

## Açık sorular
- Dexel bu SPEC'te mi? Öneri: hayır; 3 eksende z-haritası tam, dexel ayrı SPEC.
- Yol haritasında 05 satırındaki "parçadan işleme özelliği okuma": öneri ayrı SPEC.
- Matkap uç açısı modelde yok; matkap düz uçlu kabul edildi.
