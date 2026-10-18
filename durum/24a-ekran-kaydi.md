# DURUM — A3 Tezgah ekran kaydı (arayüz)

Dal: `claude/project-thread-c0lzh0` · Oturum: bulut · Metin: `specs/24a-ekran-kaydi.md` (onay 2026-10-18 11:13)

## Sıradaki adım
Kod yazıldı; PR #86 CI'da. Yeşilse birleşir. Sonra SPEC 25/26/37/47 ekranları kendi
`tezgah/ekranlar/<ad>.py` ve `src/ekranlar/<ad>.ts` dosyalarını ekler.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet (`NotImplementedError` / `Error("A3: uygulanmadı")`); test yok. |
| 2026-10-18 | pytest tests/tezgah 165, vitest 88, Playwright 10 (+1 atlandı) | 0 | Atlanan: "sekme değişince katman kalkar" ikinci ekran gerektirir; geçici ikinci ekranla yerelde geçti. |

## Uygulama ayrıntıları (koordinatöre bildirildi, testlerle sabit)
- Sekme kuralı: `router=None` ve `tus=None` ekran sekme değildir; `ekranlar()`'da vardır, `/api/ekranlar`'da yoktur.
  İmportu bozuk modülün yer tutucusu boş `router` taşır, kapalı sekme olarak listelenir.
- Python yardımcı modülleri: `_` ile başlayan modül hiç import edilmez; `EKRAN` tanımlamayan modül atlanır.
- TS: varsayılan dışa aktarımı olmayan `src/ekranlar/*.ts` modülü atlanır; geçersiz varsayılan → Error.
  Saf toplayıcı `modulleriTopla(kayitlar)` (glob eşlemesi → doğrulanmış modüller).
- İş deposu süreç başına tektir (`tezgah/depo.py`); `uygulama()` kurulurken örnek iş parametreleri varsayılana döner,
  dinamik işler (`is_kaydet`) yalnız `POST /api/sifirla` ile silinir.
- Sahne: `katman(ad)`, `katmanBirak(ad)`, `katmanlar()`, `isKatmani(g)`; eski renk katmanı `renkKatmani(ad)`.
  Şerit: `dinle(cb)`, `bosalt()`. Kabuk sekme değişince önceki ekranın katmanını kendisi de kaldırır.
- Palet: desenli komut (`desen: "çap <sayı>"`) yalnız sayıyla yazılınca listelenir; sözcük desenin ilk sözcüğü ya da
  `anahtar_kelimeler`'den biri olabilir ("çap 12", "paso 2").
- SPEC 24 kanca alanları (`hazir` hariç) `window.__tezgah.freze`'ye gider; `hazir` = kabuk hazır ve etkin ekranın
  kancasındaki `hazir` (yoksa true).

## Son oturum
**2026-10-18**
- Python: `tezgah/ekranlar/__init__.py`, `tezgah/ekranlar/freze.py` (bölüm "isler"), `tezgah/depo.py`,
  `tezgah/sunucu.py` (tek hata eşlemesi, 503 bağımlılığı, `kur`, `/api/ekranlar`, `/api/sifirla`).
- TS: `kayit.ts`, `api.ts` (`X-Tezgah-Etiket`, `degisiklikSonrasi`), `ekranlar/freze.ts` (main.ts'den taşındı),
  `main.ts` artık yalnız kabuk; `sahne.ts` ve `serit.ts`'e katman ve dinleyici yardımcıları.

## Açık sorular
- Yok.
