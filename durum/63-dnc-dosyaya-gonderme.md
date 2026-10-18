# DURUM — SPEC 63 DNC (dosyaya gönderme)

Dal: `claude/spec-38-is-foyu-y2a9bm` (oturumun verdiği dal, güncel `main`'den yeniden başlatıldı) · Oturum: bulut

## Sıradaki adım
İskelet hazır; bağımsız test oturumunun `tests/atolye/test_dnc.py` commit'i bekleniyor, sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: gövdeler `NotImplementedError` |

## Son oturum
**2026-10-18**
- Onaylı metin `specs/63-dnc-dosyaya-gonderme.md`'ye kondu.
- `atolye/dnc.py` arayüz iskeleti ve `atolye/dnc_kurallari.json` kural tablosu yazıldı.
- Kural tablosundaki satır uzunluğu sınırları (SPEC tablosunda sayı yok) kodlayıcının seçimi: sinumerik 512,
  heidenhain 254, fanuc / haas 256, grbl 80.
- K8 (Tezgah gönder ucu) Tezgah thread'inin dosyalarına dokunur; değişiklik koordinatöre dosya olarak gönderilecek.
- SPEC 48 özet fonksiyonları `main`'de yoksa K6'nın `profil_ozeti` alt koşulu atlanır; özet hesabı `dnc.py`'de.

## Açık sorular
_(yok)_
