# DURUM — SPEC 58 Süre, maliyet ve teklif

Dal: `claude/spec-16-teknik-resim-u8ylv2` (oturumun verdiği dal; SPEC 16 #22 birleşti, dal SPEC 66 iskeleti
`f623ab4` üstünden yeniden başladı) · Oturum: bulut thread "Teknik resim (SPEC 16)"

## Sıradaki adım
Bağımsız test commit'ini cherry-pick et, kodu ayrı commit'te yaz. B2 (#121) ve SPEC 66 main'e girmeden birleştirme yok.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet; SPEC 58 testleri henüz yok. |

## Son oturum
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
