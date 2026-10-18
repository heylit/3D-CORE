# DURUM — SPEC 00 Arayüzler ve ortak kurulum

Dal: `claude/project-thread-dall9z` · Oturum: bulut

## Sıradaki adım
PR birleşince Dalga 1'deki beş SPEC (01, 02, 03, 04, 08) ayrı oturumlarda aynı anda başlar.
CAM SPEC'leri (03, 04) "CAM algoritmaları ve matematiği" araştırması bitince yazılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 117 (+29 uygulanmamış, SPEC 01) | 0 | cam 38, assy 30, geometry 8 yeni test; testler SPEC'ten ayrı ajanla yazıldı |
| 2026-10-18 | 1098 | 0 | Ek 2: 139 yeni test (K11–K16), ayrı thread'de yazıldı (`fb50139`) |

## Son oturum
**2026-10-18 — Ek 2 (Dalga 2 CAM arayüzü)**
- `cam/model.py`: kesme verisi, takım tutucu, torna takımı, takım kütüphanesi, silindir stok, iş sıfırı, kurulum; `Toolpath` G18 / G95 / G96 alanları.
- `cam/gcode/writer.py`: G18 / G95 / G96 / torna yollarını reddeden geçici koruma (SPEC 21 kaldırır).
- Sıradaki: PR birleşince 05, 14 ve 20 başlar.

**2026-10-18**
- `cam/model.py`, `assy/model.py`, `geometry/part.py` arayüzleri yazıldı.
- Kök `conftest.py`: `occt` testleri build123d yoksa atlanıyor; sadece NotImplementedError ile düşen test "uygulanmamış" sayılıyor.
- Bulut oturumu için SessionStart kurulum betiği; CI `.[dev,cad]` kuruyor.

## Açık sorular
_(yok)_
