# SPEC 58 — Süre, maliyet ve teklif

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 16:06 UTC, proje sohbetinde yazılı: "Dalga 7 taslakları 57, 58, 59, 61, 62,
> 63, 64 ve 72'yi önerileriyle onaylıyorum."). Açık sorular önerilen cevaplarla kapandı (dosya sonu "Kararlar").
> **Ek: 72 ve 59 uyumu** (kullanıcı, 2026-10-18 16:19 UTC, proje sohbetinde yazılı onay): dosya sonunda. K1 ve K5'in
> sayıları değişmez; yalnız kaynak, hangi SPEC'in `main`'de olduğuna göre seçilir.
> Önceki durum: taslak. Dalga 7, hat A2 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 4: "Atölyenin en çok sorduğu soru").
> Dayanır: SPEC 38 (iş föyü, `JobSheet.total_time`), SPEC 05 / 22 (süre kuralı `move_time`, `lathe_move_time`),
> SPEC 30 (`MachineProfile`), B2 + SPEC 66 (`Malzeme.rho`, `fiyat`, `malzeme_maliyeti_eur`), SPEC 59 (takım ömrü; isteğe bağlı).

## Amaç
Bir iş için **parça başı maliyeti** ve müşteriye verilecek **teklif sayfasını** üretmek. Girdi simülasyondan gelen
işleme süresi, bağlama ve hazırlık süreleri, malzeme, takım aşınması ve atölye ücretleridir. Çıktı iki parçadır:
- **Maliyet dökümü**: her kalemin formülü, girdisi ve sonucu ayrı satırdadır. Hiçbir sayı açıklamasız kalmaz.
- **Teklif sayfası**: tek dosya HTML, adet kademeli (ör. 1 / 10 / 50 / 200) birim fiyat tablosu. Yazdırılabilir.

Atölye ücretleri (saat ücreti, işçilik, genel gider, kâr payı, malzeme fiyatı) **gizli şirket verisidir**. Repoya
girmez, `yerel_parcalar/` altındaki kullanıcı dosyasında durur (SPEC 66 kararı D7). Repoda yalnız şema ve uydurma
örnek vardır.

## Neden
Bugün iş föyü süreyi veriyor ama "bu parça kaça çıkar, kaça teklif veririz" sorusu elle Excel'de cevaplanıyor.
Süre zaten simülasyondan geldiği için doğru maliyetin yarısı elimizde. Kalan yarısı (ücretler, fire, takım payı,
hazırlık süresinin adede bölünmesi) basit ama hataya açık hesaplardır: tek ve testli bir yerde olmalıdır.

## Teori

### 1. Süreler [s]
Bir iş `B` bağlamadan oluşur. Bağlama `b` için:
- `t_isleme(b)`: SPEC 38 `SetupSheet.time` (kesme + hızlı + takım değişimi; SPEC 05 kuralı). Torna bağlamasında SPEC 22
  `lathe_move_time` toplamı. Bu SPEC süreyi **yeniden hesaplamaz**, föyden okur.
- `t_yukle(b)`: parça bağlama / sökme süresi, her parçada bir kez (kullanıcı girer; varsayılan profil dosyasından).
- `t_hazirlik(b)`: iş başına bir kez: bağlama aparatı kurulumu, sıfır alma, takım ölçümü, ilk parça kontrolü.

`n` adetlik parti için parça başı süre:

    t_parca(n) = Σ_b [ t_isleme(b) + t_yukle(b) ] + Σ_b t_hazirlik(b) / n

Kodda süre saniyededir. Ücretler €/saat girildiği için çarpımda `/ 3600` yazılır ve fonksiyon adı birimi söyler
(`_eur`). Bu, SPEC 66'daki €/kg ile aynı türden bir gösterim sınırıdır.

### 2. Maliyet kalemleri [€ / parça]
| Kalem | Formül | Girdi |
|---|---|---|
| Tezgâh | `Σ_b (t_isleme(b) + t_yukle(b)) · U_m(b) / 3600` | `U_m` tezgâh saat ücreti, `MachineProfile.name` anahtarlı |
| Hazırlık | `Σ_b t_hazirlik(b) · (U_m(b) + U_i) / 3600 / n` | `U_i` işçilik saat ücreti (hazırlıkta tezgâh da durur) |
| İşçilik (operatör) | `Σ_b (t_isleme(b) + t_yukle(b)) · U_i · k_op / 3600` | `k_op`: bir operatörün baktığı tezgâh oranı (1 = tek tezgâh, 0.5 = iki tezgâh) |
| Malzeme | `malzeme_maliyeti_eur(m, m_ham) · (1 + f_fire)` | `m_ham = ρ · V_ham`, `V_ham` stok hacmi + kesim payı (§3) |
| Takım | `Σ_takım c_kenar · t_kesme(takım) / T_omur(takım)` | `c_kenar` €/kesici kenar, `T_omur` dk (SPEC 59 ya da elle) |
| Dış işlem | `Σ c_dis` | Isıl işlem, kaplama: kullanıcı satır satır girer, adet bağımsız birim fiyat |

Ara toplam `M = Σ kalem`. Genel gider ve kâr payı ara toplama sırayla uygulanır:

    fiyat(n) = M(n) · (1 + g) · (1 + k)

`g` genel gider oranı, `k` kâr payı oranıdır. İkisi de `[0, 5]` aralığında olur, aksi `ModelError`.

### 3. Ham malzeme
- Prizmatik stok (`cam.model.Stock`): `V_ham = (Lx + 2·p) · (Ly + 2·p) · (Lz + 2·p)`. `p` her yüzde kesim / alın payıdır.
- Çubuk stok (`CylinderStock`): `V_ham = π·(D/2)²·(L + p_testere + p_alin)`. `p_testere` testere ağzı, `p_alin` alın payı.
- Kütle `m_ham = ρ · V_ham` [t]. Malzeme kimliği bileşenin `Component.material`'ından (B2) ya da işin malzeme alanından gelir.
- `fiyat` boşsa (yerleşik kayıtlarda boştur, D7) kullanıcının yerel fiyat dosyası okunur. Orada da yoksa `ModelError`:
  "Malzeme 1.0503 (C45) için fiyat yok: yerel_parcalar/atolye-ucretleri.json → malzeme_fiyati". Sessiz 0 yok.

### 4. Takım payı
`t_kesme(takım)` iş föyündeki `ToolRow.time`'dır (yalnız kesme hareketleri; SPEC 38 §4). `T_omur`:
- SPEC 59 `main`'deyse Taylor ömrüdür: `T = (C / Vc)^(1/n)` dk, `Vc` işin gerçek kesme hızı.
- Değilse ya da malzeme için Taylor katsayısı yoksa kullanıcı dosyasındaki `kenar_omru_dk` okunur.
- İkisi de yoksa `ModelError`. Takım payı **kesirlidir**: 3 dk kesen ve 30 dk ömürlü kenar parçaya `0.1 · c_kenar` yazar.

### 5. Yuvarlama ve kademeler
İç hesap `float`'tır. Yalnız gösterimde 2 ondalığa yuvarlanır (banker yuvarlaması değil, `ROUND_HALF_UP`, `decimal`).
Teklif tablosunun her satırı kendi `n`'i ile **baştan** hesaplanır; satırlar birbirinden türetilmez.

## Atölye ücret dosyası (yerel, repoya girmez)
Varsayılan yol `yerel_parcalar/atolye-ucretleri.json`. Şema (`sema: 1`, kanonik JSON, bilinmeyen alan `ModelError`):
```
{
  "sema": 1,
  "para_birimi": "EUR",                         # yalnız gösterim; döviz çevirisi yok
  "iscilik_saat": 0.0,                          # U_i €/saat
  "operator_orani": 1.0,                        # k_op, (0, 1]
  "genel_gider": 0.0, "kar_payi": 0.0,          # g, k
  "tezgah_saat": { "<MachineProfile.name>": 0.0 },
  "varsayilan_sureler": { "yukle_s": 0.0, "hazirlik_s": 0.0 },
  "malzeme_fiyati": { "<Malzeme.id>": 0.0 },    # €/kg; SPEC 66 fiyat'ından önce gelir
  "takim": { "<Tool.name>": { "kenar_eur": 0.0, "kenar_omru_dk": null } },
  "kesim_payi": { "prizma_mm": 0.0, "testere_mm": 0.0, "alin_mm": 0.0 }
}
```
Repoda yalnız `examples/58_atolye_ucretleri_ornek.json` bulunur; değerleri açıkça uydurmadır (ör. tezgâh 60 €/saat) ve
dosyanın ilk alanı `"aciklama": "UYDURMA ÖRNEK, gerçek ücret değildir"`dır.

## Dosyalar
- **Yeni:** `atolye/maliyet.py`, `atolye/teklif.py` (HTML), `examples/58_atolye_ucretleri_ornek.json`,
  `tests/atolye/test_maliyet.py`, `tests/atolye/test_teklif.py`, `durum/58-sure-maliyet-teklif.md`.
- **Tezgah (ayrı küçük iş, A3 ekran kaydıyla):** `tezgah/ekranlar/maliyet.py` (`GET /api/ekran/maliyet/{is}`,
  `GET /api/ekran/maliyet/{is}/teklif.html`). Bu SPEC'in kabulü kitaplık + HTML'dir; ekran K10'dadır.
- **Dokunulmayacak:** `cam/model.py`, `malzeme/model.py`, `atolye/is_foyu.py` (yalnız `JobSheet` okunur),
  `pyproject.toml`. Yeni bağımlılık yok (`decimal`, `json`, `html` stdlib).

## Arayüz
```python
# atolye/maliyet.py
@dataclass(frozen=True)
class Ucretler: ...                               # dosya şemasının alanları; from_dict / to_dict
def ucretleri_oku(yol: str | Path = "yerel_parcalar/atolye-ucretleri.json") -> Ucretler
    # dosya yoksa ModelError: "Atölye ücret dosyası yok: <yol>. Örnek: examples/58_atolye_ucretleri_ornek.json"

@dataclass(frozen=True)
class Kalem:
    ad: str                  # "tezgah" | "hazirlik" | "iscilik" | "malzeme" | "takim" | "dis_islem"
    aciklama: str            # formül + girdiler, okunur metin
    tutar_eur: float

@dataclass(frozen=True)
class Maliyet:
    n: int
    t_parca_s: float
    kalemler: tuple[Kalem, ...]
    ara_toplam_eur: float
    fiyat_eur: float         # parça başı, genel gider ve kâr dahil
    uyarilar: tuple[str, ...]

def ham_hacim(stok: Stock | CylinderStock, u: Ucretler) -> float                     # mm³
def maliyet(job: JobSheet, profiller: Sequence[MachineProfile], stok: Stock | CylinderStock,
            malzeme: Malzeme, u: Ucretler, n: int,
            sureler: Sequence[tuple[float, float]] | None = None,                    # bağlama başına (yukle_s, hazirlik_s)
            dis_islem: Sequence[tuple[str, float]] = ()) -> Maliyet
def kademeler(..., adetler: Sequence[int] = (1, 10, 50, 200)) -> list[Maliyet]

# atolye/teklif.py
def teklif_html(baslik: str, musteri: str, tarih: str, kademeler: Sequence[Maliyet],
                gecerlilik_gun: int = 30, dokum: bool = False) -> str
    # tek dosya, dış kaynaksız (SPEC 38 §8 kuralları); dokum=False → yalnız adet / birim / toplam tablosu
```

## Kabul kriterleri
Uydurma iş: SPEC 38 Ek A prizmatik iş (iki bağlama), uydurma ücret dosyası, SPEC 66 yerleşik C45 + yerel fiyat.
- [ ] **K1 Süre:** `t_parca(n)` §1 formülüyle; iki bağlamalı işte `n = 1` ve `n = 10` için elle hesaplanan değerle
  göreli 1e-12. `t_isleme` `JobSheet.setups[b].time` ile birebir (yeniden hesap yok). (`test_maliyet.py::test_sure`)
- [ ] **K2 Kalemler:** her kalem §2 formülüyle elle hesaplananla göreli 1e-12; `aciklama` formülün girdilerini
  sayıyla içerir. `kalemler` sırası tablodaki sıradır. (`::test_kalemler`)
- [ ] **K3 Ham malzeme:** 100×60×30 prizma, `p = 2` → `V_ham = 104·64·34`; Ø40×120 çubuk, testere 3, alın 1 →
  `π·20²·124`; C45 `ρ = 7.85e-9`, yerel fiyat 1.5 €/kg → beklenen € göreli 1e-12. (`::test_ham`)
- [ ] **K4 Eksik veri:** fiyat yok, tezgâh ücreti yok, takım ömrü yok, ücret dosyası yok → her biri `ModelError`,
  mesajda eksik anahtar ve dosya yolu. Hiçbir durumda `0` ya da `nan` dönmez. (`::test_eksik`)
- [ ] **K5 Takım payı:** 3 dk kesme, 30 dk ömür, kenar 12 € → `1.2 €`; SPEC 59 yoksa `kenar_omru_dk`, varsa Taylor
  (59 yoksa bu alt durum `skip`). (`::test_takim`)
- [ ] **K6 Kademe:** `n = 1, 10, 50, 200` için birim fiyat azalan (hazırlık > 0 iken kesin azalan); her satır tek
  başına `maliyet(n)` ile birebir aynı. (`::test_kademe`)
- [ ] **K7 Oran sınırları:** `g`, `k` ∉ `[0, 5]`, `k_op ∉ (0, 1]`, `n < 1`, `n` tamsayı değil → `ModelError`. (`::test_sinir`)
- [ ] **K8 Teklif HTML:** `html.parser` ile ayrışır; `http` / `<script>` yok; `table#kademe` satır sayısı kademe sayısı;
  `dokum=False` iken `kalem` adları sayfada **geçmez** (iç maliyet müşteriye gitmez); aynı girdi → bayt bayt aynı;
  tutarlar 2 ondalık `ROUND_HALF_UP` (`2.675 → 2.68`). (`test_teklif.py`)
- [ ] **K9 Gizlilik:** depoda `yerel_parcalar/` altında dosya yok; `examples/58_atolye_ucretleri_ornek.json`'ın
  `aciklama` alanı "UYDURMA" içerir; `.gitignore` `yerel_parcalar/`'ı kapsıyor. (`::test_gizlilik`)
- [ ] **K10 Tezgah ekranı (isteğe bağlı, ayrı PR olabilir):** `GET /api/ekran/maliyet/{is}?n=10` → `Maliyet` JSON;
  ücret dosyası yoksa 422 ve mesaj. (`tests/tezgah/test_maliyet_ekrani.py`)
- [ ] **K11 Bağımlılık:** `atolye/maliyet.py` ve `teklif.py` yalnız stdlib, `cam.model`, `malzeme.model`,
  `malzeme.kutuphane`, `atolye.is_foyu` dışa açılanlarını içe aktarır. (`test_bagimlilik.py`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
- SPEC 38 (`main`'de), B2 + SPEC 66 (Dalga 6, birleşmeleri gerekir). SPEC 59 isteğe bağlıdır (K5'in Taylor dalı).
- Arayüz değişikliği yok. `MachineProfile`'a ücret alanı **eklenmez**: ücret gizli veridir, profil dosyası repodadır.

## Kapsam dışı
- Döviz çevirisi, KDV, iskonto, ödeme koşulu metinleri (teklif şablonu sabit ve sade).
- Fiyatın tedarikçi / tarih geçmişi: MES (SPEC 64) tarafının işi.
- Enerji tüketimi, amortisman hesabı: tezgâh saat ücretinin içinde kabul edilir.
- Sim olmadan "tahmini" süre (öznitelikten hızlı tahmin): teklif aşamasında CAM yoksa ayrı SPEC (açık soru 3).

## Kararlar (açık sorular; önerilen cevaplarla kapandı, kullanıcı 2026-10-18 16:06 UTC)
Her maddedeki **Öneri** artık karardır.
1. Para birimi tek mi (EUR) olsun, yoksa dosyada seçilebilsin mi? **Öneri:** dosyada `para_birimi` metni, yalnız
   gösterim; çeviri yok. TL ile çalışılıyorsa tüm ücretler TL girilir ve formül aynı kalır.
2. Genel gider ile kâr payı çarpımsal mı (`(1+g)(1+k)`), toplamsal mı (`1+g+k`)? **Öneri:** çarpımsal; kâr, gider dahil
   maliyete eklenir (yaygın atölye uygulaması). Kullanıcı farklı çalışıyorsa tek satır değişir.
3. CAM'i henüz yapılmamış bir parça için hızlı teklif gerekir mi? **Öneri:** bu SPEC'te hayır; süre her zaman
   simülasyondan gelir. Gerekirse SPEC 57 (otomatik CAM 2) planından süre alınarak aynı `maliyet()` kullanılır.
4. Teklif sayfasında firma logosu / başlığı? **Öneri:** `yerel_parcalar/teklif-baslik.html` varsa sayfanın başına
   gömülür (dış kaynak değil, satır içi); yoksa yalnız metin başlık. Repoya şirket adı girmez.

## Ek: 72 ve 59 uyumu (2026-10-18)
Onay: kullanıcı, 2026-10-18 16:19 UTC ("… ve 58 uyum ekini önerileriyle onaylıyorum"). SPEC 72 "58'in okuduğu tek
sözleşme `CycleTime`'dır" der; SPEC 59 parça başı aşınmayı `ToolWear.D` (Palmgren–Miner) olarak verir. Bu ek 58'i ikisine
bağlar; ikisi de yokken davranış ve sayılar bu ekten öncekiyle aynıdır.

1. **Süre kaynağı (§1).** SPEC 72 `main`'deyse ve bağlamanın tezgâhı için bir `TimeProfile` (`machine ==
   MachineProfile.name`) verilmişse, bağlama `b` için
   `ct_b = cycle_time(ops_b, prof_b, setup_time = t_yukle(b))` ve `t_isleme(b) + t_yukle(b) = ct_b.total` alınır
   (72'nin `k` kalibrasyonu, palet ve program sabiti dahil; çift sayım yok). `t_hazirlik(b)` 58'de kalır (72'de karşılığı
   yoktur). 72 yoksa ya da o tezgâh için `TimeProfile` verilmemişse §1 aynen geçerlidir (`JobSheet.setups[b].time`) ve
   `Maliyet.uyarilar`'a "Süre SPEC 05 modelinden (72 zaman profili yok: <tezgâh>)" yazılır.
2. **Takım payı (§4).** SPEC 59 `main`'deyse takım payı `c_kenar · D` olur; `D` o takımın parça başı `ToolWear.D`'sidir
   (`mill_wear` / `turn_wear`). 59 yoksa ya da çağıran aşınma listesi vermemişse §4'ün `t_kesme / T_omur` kuralı
   (`kenar_omru_dk`) geçerlidir. Sabit `Vc`'de iki kural aynı sayıyı verir (`D = t / T`).
3. **Döküm.** `tezgah` ve `takim` kalemlerinin `aciklama`'sı kaynağı söyler: "süre: SPEC 72 CycleTime" ya da
   "süre: SPEC 05 (iş föyü)"; "takım: SPEC 59 Miner D" ya da "takım: kenar ömrü (yerel dosya)".
4. **Arayüz eki.** `maliyet(...)` ve `kademeler(...)` iki isteğe bağlı parametre alır:
   `zaman_profilleri: Mapping[str, TimeProfile] | None = None` (tezgâh adı → profil) ve
   `asinma: Sequence[ToolWear] | None = None`. Varsayılanlarla davranış ekten öncekidir.
5. **Ek kabul kriterleri** (72 / 59 `main`'de değilse `skip`):
   - [ ] **K1b** 72 varken iki bağlamalı işte `Σ_b (t_isleme(b) + t_yukle(b))` = `Σ_b ct_b.total` (göreli 1e-12);
     `TimeProfile` verilmeyen tezgâhta §1 değeri ve uyarı metni birebir. (`test_maliyet.py::test_sure_72`)
   - [ ] **K5b** 59 varken sabit `Vc` ile 3 dk kesme, `T = 30` dk, kenar 12 € → `1.2 €` (K5 ile aynı); iki hızlı
     örnek (SPEC 59: `D = 0.75`) kenar 12 € → `9.0 €`. (`::test_takim_59`)

