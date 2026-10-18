# DURUM — SPEC 63 DNC (dosyaya gönderme)

Dal: `claude/spec-38-is-foyu-y2a9bm` (oturumun verdiği dal, güncel `main`'den yeniden başlatıldı) · Oturum: bulut

## Sıradaki adım
Kod hazır (K1–K7, K9 yeşil); PR #130 birleşince K8 Tezgah ucu Tezgah thread'inde
(`/mnt/project-files/dnc-63/tezgah-gonder-ucu.md`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: gövdeler `NotImplementedError` |
| 2026-10-18 | 156 (`tests/atolye`) | 0 | 2 atlama: SPEC 48 `profil_ozeti` yok; K8 Tezgah thread'inde |

## Son oturum
**2026-10-18**
- Onaylı metin `specs/63-dnc-dosyaya-gonderme.md`'ye kondu.
- `atolye/dnc.py` arayüz iskeleti ve `atolye/dnc_kurallari.json` kural tablosu yazıldı.
- Kural tablosundaki satır uzunluğu sınırları (SPEC tablosunda sayı yok) kodlayıcının seçimi: sinumerik 512,
  heidenhain 254, fanuc / haas 256, grbl 80.
- K8 (Tezgah gönder ucu) Tezgah thread'inin dosyalarına dokunur; değişiklik koordinatöre dosya olarak gönderilecek.
- SPEC 48 özet fonksiyonları `main`'de yoksa K6'nın `profil_ozeti` alt koşulu atlanır; özet hesabı `dnc.py`'de.

- Test commit'i 6981a0f (ayrı oturum) cherry-pick edildi; kod ayrı commit'te.
- Kod kararları (SPEC'te yok): Ö2 okunan yolun üretilen her hareketi sırayla içermesi (uç ≤ 0.5·10⁻ᵈ mm, merkez
  ≤ 1e-2 mm); bozuk satır öneklerin okunmasıyla ikili aramada bulunur. Sıra Ö1, Ö4, Ö5, Ö2 (Ö3 `gonder`'de).
  Ad verilmezse Sinumerik `PRG_<no>`, Heidenhain/GRBL `<no>`, Fanuc/Haas `O` + hane. Heidenhain `BEGIN/END PGM`
  adı dosya adına çevrilir; Fanuc/Haas O satırı dosya adıyla aynı olmalı. `profil_ozeti` = `to_dict()` kanonik
  JSON sha256 (SPEC 48 metniyle aynı; 48 birleşince ona bağlanır). Kayıt dosyası yoksa `kayitlari_oku` → `[]`.
- `atolye/dnc_kurallari.json` paket verisi: `pyproject` package-data satırı DURUM thread'inin (editable kurulumda
  gerekmez).

## Açık sorular
_(yok)_
