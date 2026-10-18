# DURUM — SPEC 03 cam-2d

Dal: `claude/project-thread-pzzbar` · Oturum: bulut · PR #5

## Sıradaki adım
Ek A (cep güvenliği, ikinci inceleme H1/H6) onaylandı ve uygulandı: testler 95d273c (ayrı oturum), kod ayrı commit'te. Ek olarak dar dikdörtgende (30×12, D=6, s=3) yaprak ek halkası ofset kararsızlığı düzeltildi (`MIN_EXTRA`); testi ayrı oturumdan gelecek. · Dal: `claude/project-thread-ulgwqc`. Bulgu: yaprak olmayan halkada (L cep) `s > r` iken kolların ortası kesilmiyor; öneri cepte `s ≤ r`.

SPEC 03 tamam (PR #5 kullanıcı onayıyla birleşiyor); sıradaki: 03b (rampa / helis giriş, giriş-çıkış yayları).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 (birleşme öncesi) | 221 (SPEC 03) | 0 | Tüm depo 896, `--uygulanmamis-hata` ile |
| 2026-10-18 | 221 (SPEC 03) | 0 | Tüm depo: 787 passed in 7.30s |

## Son oturum
**2026-10-18**
- SPEC onaylandı (kullanıcı, proje sohbetindeki kart).
- `cam/geom2d.py`, `cam/profile.py`, `cam/offset.py`, `cam/ops2d.py` yazıldı.
- Testler dogrulayici ile bağımsız yazıldı (`tests/cam/test_profile.py`, `test_offset.py`, `test_ops2d.py`, yardımcı `ref2d.py`).
- SPEC'te tek ince ayar: yaprak halka iç yarıçap hassasiyeti 1e-6·D → 1e-9·D (+ LINK_TOL pay); kalan malzeme testi 1e-9 toleransını tutsun diye.

## Test bağımsızlığı
- Testler kodu okumayan ayrı bir dogrulayici alt ajanında yazıldı, ama kodla aynı oturumda ve aynı commit'te (6fd5331) girdi; CLAUDE.md'nin sonradan eklenen kuralına göre PR "bağımsız değil" sayılır. Mutasyon denemesi (halka silme, 0,1 mm kaydırma) K13/K14 testlerini kırdı.

## Notlar
- Profil/ofset kodu düzlemden bağımsız (u, v); torna (SPEC 20) XZ profili için yeniden kullanabilir.
- Çökmek üzere olan ofset şeritleri (kalınlık ≤ 1e-6 mm) boş sayılır; daha kalın kapanmayan zincir CamError.

## Açık sorular
_(yok)_
