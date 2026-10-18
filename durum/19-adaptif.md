# DURUM — SPEC 19 Adaptif ve trokoidal kaba

Dal: `claude/spec-19-adaptif-1kvh62` · Oturum: bulut

## Sıradaki adım
Kullanıcı SPEC metnini onaylayınca `cam/adaptive.py` için `NotImplementedError` iskeleti; iskelet hash'i koordinatöre.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni, kod yok |

## Son oturum
**2026-10-18**
- `specs/19-adaptif.md` taslağı yazıldı. Temas açısı formülleri (düz duvar, içbükey daire, trokoid ön noktası)
  ve ızgara hata sınırı `tol(φ)` sayısal olarak denetlendi.

## Açık sorular
1. φ_t tutulamayan dar bölgeler: kalan olarak raporla (öneri) / CamError / aşarak kes.
2. Giriş: yerel basit helis, center_cutting=False reddedilir (öneri) / 03c'yi bekle.
3. Malzeme modeli: ızgara h = D/100 (öneri) / kesin analitik.
4. Kapsam: trokoidal düz kanal dahil (öneri) / yalnız adaptif cep.
