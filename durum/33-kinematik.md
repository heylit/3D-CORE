# DURUM — SPEC 33 Montaj kinematiği

Dal: `claude/spec-33-kinematik-m2o4g7` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayında. Onaydan sonra: A1 arayüzü (`Joint`, `Assembly.joints`) üstüne
`NotImplementedError` iskeleti, ayrı test thread'i, kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Henüz kod/test yok (yalnız SPEC metni) |

## Son oturum
**2026-10-18**
- `specs/33-kinematik.md` taslağı yazıldı (K1–K16). Analitik değerler (Freudenstein, dönen kol `θ*`) sayısal
  olarak kontrol edildi.

## Açık sorular
- A1 `Joint` arayüzü (SPEC'teki "Ön koşul" bölümü) arayüz sahibine iletildi; onay bekliyor.
- Eklemlerin yönlü olması (`z_b = +z_a`), sınırda `drag`'in durması, `ignore_joined=True` varsayılanı onaya açık.
