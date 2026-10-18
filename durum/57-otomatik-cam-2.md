# DURUM — SPEC 57 otomatik-cam-2

Dal: `claude/project-thread-ysr96h` · Oturum: bulut

## Sıradaki adım
İskelet (metin + arayüz + durum) commit'lendi; testler ayrı oturumda yazılacak, sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 0 | – | iskelet, testler henüz yok |

## Son oturum
**2026-10-18**
- SPEC metni onaylı (kullanıcı 16:06, "Dalga 7 taslakları 57, … onaylıyorum") `specs/57-otomatik-cam-2.md`'ye kopyalandı.
- `cam/plan2/` altında `NotImplementedError` gövdeli arayüz: `stok`, `erisim`, `ortu`, `sira`, `plan`.
- K9 bağlama gövdeleri SPEC 10 (#79) birleşince; o zamana kadar ilgili test xfail kalabilir (koordinatör notu).

## Arayüz netleştirmeleri (test yazarının soruları, 2026-10-18 16:35; SPEC metni değişmez)
1. **Yönelim:** `order_ops` yönelimi `PlannedOp.setup`'tan okur; `AutoPlan.plans[k]` bağlama `k`'nın `MillPlan`'ıdır ve
   içindeki `PlannedOp.setup`, `AutoPlan.frames[k]` içindeki yönelim indeksidir (K7d: iki yönelim = setup 0 ve 1).
   `N_rot` = ardışık iki işlemde `setup` farklı olan geçiş sayısı.
2. **İşlem türleri ve öncelik** (`precedence`): `kind` dizeleri SPEC 29'dakiler (`yuz_alma`, `acik_bolge`, `cep`,
   `cep_kalan`, `delik`, `lamba`) artı `punta`, `kilavuz`, `havsa`. Aynı `setup` içinde: `yuz_alma` → diğer her işlem;
   `{acik_bolge, cep, cep_kalan}` → `{punta, delik, kilavuz, havsa, lamba}`; aynı özellik adresinde `cep` → `cep_kalan`.
   Delik adresleri `holes[i,j,…]`; indeks kümeleri kesişen işlemler aynı delik sayılır: `punta` → `delik` →
   `{kilavuz, havsa, lamba}`. Farklı `setup`'lar arasında öncelik yoktur. Öncül sözlüğü: indeks → öncüllerin kümesi
   (öncülü olmayan indeks boş kümeyle bulunur).
3. **`min_cover` dönüşü:** yalnız `tuple[key, ...]` (imza esastır). Örtülemeyen elemanlar dönmez; çağıran
   `universe − ⋃ cover[k]` ile bulur. Anahtar sırası: boyut, sonra `cover` sözlüğündeki ekleme sırası (ilk örten alt küme).
   `cover` dışındaki eleman taşıyan küme (universe'te olmayan) görmezden gelinir.
4. **`select_stock` / `load_catalog`:** `bbox = (b_min, b_max)`, her biri 3 elemanlı dizi (2×3 dizi de kabul).
   Katalog JSON'u `StockSize` alanlarıyla nesne listesidir: `[{"kind": "blok", "a": 100, "b": 60, "c": 40, "name": "…"},
   {"kind": "cubuk", "a": 55, "max_len": 1000}]`; bilinmeyen anahtar, eksik `kind`/`a` ya da pozitif olmayan ölçü →
   `CamError`. Dönen 4×4 matris parçanın dünya koordinatından stok koordinatına dönüşümdür.
5. **Çene engeli:** `fixtures` = `Stock` kutuları dizisi, **bağlama yerel çerçevesinde**: `z = 0` parçanın o bağlamadaki
   en alt noktası (bağlanan yüz), `z` yukarı. Aynı fikstür her bağlamaya uygulanır. Çene üstü `z_c = max(f.zmax)`;
   `fixtures` boşsa çene engeli yoktur. Yan yönden (`d ⊥ z`) erişilen özellik, yerel tabanı (en düşük noktası)
   `z_c + clearance` altındaysa o bağlamada `cene_engeli` sayılır.

## Açık sorular
_(yok)_
