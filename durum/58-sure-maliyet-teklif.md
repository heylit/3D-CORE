# DURUM — SPEC 58 Süre, maliyet ve teklif

Dal: `claude/spec-16-teknik-resim-u8ylv2` (oturumun verdiği dal; SPEC 16 #22 birleşti, dal SPEC 66 iskeleti
`f623ab4` üstünden yeniden başladı) · Oturum: bulut thread "Teknik resim (SPEC 16)"

## Sıradaki adım
B2 (#121) ve SPEC 66 (#127) main'e girince main'i dala merge et, `pytest --uygulanmamis-hata` ile 0 uygulanmamış
gör; GitHub'da pytest + kapı yeşilse #139'u birleştir. K1b'nin tam testi (72 varken) test thread'inden gelirse
cherry-pick et.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet; SPEC 58 testleri henüz yok. |
| 2026-10-18 | 52 + 1 atlandı | 33 uygulanmamış | Testler `27ec4de` (ayrı oturum) cherry-pick; 33'ü yalnız B2 `Malzeme` / SPEC 66 `yerlesik` gövdeleri yüzünden. Geçici `Malzeme.__post_init__ = pass` ile yerelde 84 geçti, yalnız `test_ham_yerlesik_c45` (SPEC 66) kaldı. |

## Son oturum
**2026-10-18 — Kod**
- `maliyet.py`: `Ucretler` (okuma, doğrulama), `ham_hacim`, `maliyet`, `kademeler`; `teklif.py`: `tutar_metni`
  (Decimal ROUND_HALF_UP), `teklif_html` (table#kademe, dokum=False'ta iç kalem yok, yerel firma başlığı).
- Koordinatör kararı (K1b): `maliyet` / `kademeler`'e anahtar kelimeli `ops: list[list[Operation]] | None`. Tezgâhın
  `TimeProfile`'ı ve `ops` verilirse süre `cam.sim.cevrim.cycle_time(ops_b, prof, setup_time=t_yukle).total`'dan
  (tembel import); profil var ama `ops` ya da SPEC 72 yoksa `ModelError`. 72 henüz main'de değil; yol sahte
  `cycle_time` ile elle denendi.

**2026-10-18 — İskelet**
- `specs/58-sure-maliyet-teklif.md`: onaylı metin (16:06) + 72/59 uyum eki (16:19).
- `atolye/maliyet.py`, `atolye/teklif.py` `NotImplementedError` gövdeli; `examples/58_atolye_ucretleri_ornek.json` uydurma.
- `ModelError` `malzeme.model`'den gelir ve `atolye.maliyet`'ten dışa açılır (K11 izinli modüller).

## İskeletteki varsayılanlar (koordinatöre bildirildi)
1. Şemada olmayan `f_fire` için `fire_orani` alanı (varsayılan 0, [0, 1)); örnek dosyanın `aciklama` alanı şemada izinli.
2. `malzeme_maliyeti_eur` `malzeme/baglanti.py`'de, K11 izin listesinde değil: aynı formül (`fiyat · 1000 · m`)
   `maliyet.py`'de yazılır, `baglanti` içe aktarılmaz. Fiyat önceliği: yerel `malzeme_fiyati` > `Malzeme.fiyat`.
3. Takım payı: `asinma` verilirse `c_kenar · D` (Ek 2), yoksa `t_kesme / kenar_omru_dk`; kendi Taylor hesabı yok.
4. `profiller` bağlama başına bir tezgâh; `sureler=None` → her bağlamaya `varsayilan_sureler`.

## Açık sorular
_(yok)_
