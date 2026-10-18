# DURUM — A3 Tezgah ekran kaydı (arayüz)

Dal: `claude/project-thread-c0lzh0` · Oturum: bulut · Metin: `specs/24a-ekran-kaydi.md` (onay 2026-10-18 11:13)

## Sıradaki adım
İskelet pushlandı. Ayrı test thread'i testleri yazar; test commit'i cherry-pick edilir, kod ayrı commit'te.
Kod (freze'nin `tezgah/ekranlar/freze.py` ve `src/ekranlar/freze.ts`'e taşınması dahil) 24, 25, 26 birleşince.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet (`NotImplementedError` / `Error("A3: uygulanmadı")`); test yok. |

## Son oturum
**2026-10-18**
- Python: `tezgah/ekranlar/__init__.py` (Ekran, ekranlar, dogrula, paylasilan_bolum, is_kaydet, KABUK_KISAYOLLARI, ONEK);
  `sunucu.uygulama(dist, ekranlar=None)`, `GET /api/ekranlar`, `POST /api/sifirla` iskeleti.
- TS: `src/ekranlar/tip.ts` (EkranModulu, Kabuk, EkranApi, Komut, Yama, SunucuEkrani, Sekme),
  `src/ekranlar/kayit.ts` (ekranlariSirala, modulleriDogrula, kisayolDogrula, kayitliModuller),
  `api.ts` (degisiklikSonrasi, ekranApi), kanca `katmanlar()` ve `__tezgah.<ad>`.

## Açık sorular
- Yok.
