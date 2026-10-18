# DURUM — A3 Tezgah ekran kaydı (arayüz)

Dal: `claude/project-thread-c0lzh0` · Oturum: bulut · Metin: `specs/24a-ekran-kaydi.md` (onay 2026-10-18 11:13)

## Sıradaki adım
Kod yazıldı; PR #86 CI'da. Yeşilse birleşir. Sonra SPEC 25/26/37/47 ekranları kendi
`tezgah/ekranlar/<ad>.py` ve `src/ekranlar/<ad>.ts` dosyalarını ekler.

## Nerede kaldı (2026-10-18 19:15, kullanıcı isteğiyle durduruldu)
Dal `claude/project-thread-c0lzh0` (PR henüz açılmadı; #128 birleşti aa8a683). Daldaki commit'ler:
Ctrl K komut ekranı kancası (005ee4d), komut ekranı sekme değil + SPEC 63 gönder ucu iskeleti (1326921),
SPEC 63 K8 bağımsız testi (95445e6, 288f9cd'den), Google Fonts kaldırıldı (84894a1), açılışta build123d
yüklenmez + URL satırı flush (3ea4930).
Sırada:
1. #130 (atolye.dnc) main'e girince main'i dala merge et; gönder ucu kodu
   `/mnt/project-files/tezgah-kanca/gonder-ucu-kodu.patch` (git apply) ayrı commit; #130 dalıyla 8/8 geçti.
2. PR aç (kanca + gönder + yazı tipi + açılış), GitHub'da pytest + kapi yeşilse birleştir.
3. Ctrl K kancasının bağımsız e2e testi (SPEC 62 test thread'i) gelince cherry-pick.
4. #150 (B1) birleşince kabukta B1'in iki yeni proje alanını taşı (iskelet → ayrı test thread'i → kod).

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
