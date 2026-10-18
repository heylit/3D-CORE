# DURUM — SPEC 00 Arayüzler ve ortak kurulum

Dal: `claude/project-thread-dall9z` · Oturum: bulut

## Sıradaki adım
PR birleşince Dalga 1'deki beş SPEC (01, 02, 03, 04, 08) ayrı oturumlarda aynı anda başlar.
CAM SPEC'leri (03, 04) "CAM algoritmaları ve matematiği" araştırması bitince yazılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 117 (+29 uygulanmamış, SPEC 01) | 0 | cam 38, assy 30, geometry 8 yeni test; testler SPEC'ten ayrı ajanla yazıldı |

## Son oturum
**2026-10-18**
- `cam/model.py`, `assy/model.py`, `geometry/part.py` arayüzleri yazıldı.
- Kök `conftest.py`: `occt` testleri build123d yoksa atlanıyor; sadece NotImplementedError ile düşen test "uygulanmamış" sayılıyor.
- Bulut oturumu için SessionStart kurulum betiği; CI `.[dev,cad]` kuruyor.

## Açık sorular
_(yok)_
