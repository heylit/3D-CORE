# SPEC TK — Gerçek takım kütüphanesi (atölye envanteri, montajlar, katalog içe aktarma)

> **Durum:** TASLAK (onaysız). Kullanıcı onayı olmadan `specs/` altına girmez.
> **Bağlam:** "Gerçek takımlar freze torna kullanacak mıyız, kütüphane" sorusu (2026-10-18).
> **Bölünme:** Bir SPEC = bir dal = bir PR kuralı gereği aşağıdaki iş 5 SPEC'e bölünür: **TK0** (arayüz PR'ı),
> **TK1** (envanter + montaj), **TK2** (ISO 13399 / GTC içe aktarma), **TK3** (malzemeye göre kesme verisi),
> **TK4** (tezgâh takım tablosu + post entegrasyonu).

## 1. Bugün `main`'de ne var

| Konu | Var | Dosya |
|---|---|---|
| Freze takımı geometrisi | `Tool`: `FLAT, BALL, DRILL, CONE, SPOT, CHAMFER, TAP`; `D`, `flute_length`, `corner_r` (torus), `flutes`, `shank_d`, `stickout`, `tip_angle`, `pitch` | `cam/model.py` |
| Freze tutucu | `ToolHolder(name, gauge_length, profile)` dönel (z, r) profili; çarpışma ve takım boyu ofseti bundan | `cam/model.py`, `cam/tool_length.py` |
| Torna takımı | `LatheTool`: `TURN, BORE, GROOVE, THREAD`; `nose_r`, `tip` (uç yönü), `kappa_r`, `eps_r`, `width`, `edge_len` | `cam/model.py` (SPEC 20/40) |
| Torna tutucu | `LatheHolder(name, polygon, half_width)`; simde `tutucu_carpma` | `cam/model.py`, `cam/sim/lathe.py` |
| Kesme verisi | `CuttingData(Vc, fz/fn, ap, ae)`, takım başına **malzeme adı → veri** sözlüğü | `cam/model.py` |
| Kütüphane | `ToolLibrary` JSON yükle/kaydet, ara, `check_tools` | `cam/library.py`, `examples/takim_kutuphanesi.json` |
| Kesme kuvveti | Kienzle `kc1.1`, `mc` malzeme kaydından | `cam/kuvvet.py`, `malzeme/model.py` |
| Takım ömrü | Taylor (SPEC 59 taslak; takım malzemesi alanı eksik, Açık soru 1) | taslak |
| Post | `T<id> M6` (ISO/Sinumerik), `TOOL CALL <id> Z S..` (TNC), tornada `T<id><id>` | `cam/post/`, `cam/gcode/lathe.py` |

Sonuç: geometri, tutucu ve kesme verisi **modellenebiliyor**; takımlar elle girilen JSON'dan geliyor ve
gerçek dünyayla bağı yok.

## 2. Eksikler

1. **Kimlik:** üretici, sipariş kodu, ISO uç kodu (`CNMG 120408-PM`), tutucu kodu (`PCLNR 2525M12`), kalite/kaplama,
   **takım malzemesi** (HSS / karbür / sermet / CBN / PCD; SPEC 59 bunu bekliyor).
2. **Montaj:** tutucu + uzatma + pens/sap + kesici zinciri yok. Tek `ToolHolder` var; `stickout` elle giriliyor.
   HSK-A63 / SK40 / BT40 / Capto C6 arayüzleri ve torna taret istasyonu (VDI / BMT) tanımlı değil.
3. **Envanter:** atölyede kaç adet var, hangi tezgâhın magazininde / taret istasyonunda, kenar sayısı, kalan ömür yok.
4. **Katalog içe aktarma:** Sandvik, Iscar, Kennametal, Walter, Seco vb. **ISO 13399** verisi (GTC paketi, `.p21`
   özellik dosyası + STEP 3B model) okunamıyor.
5. **Kesme verisi kaynağı:** `CuttingData` kaynaksız; B2/66 malzeme kütüphanesindeki ISO P/M/K/N/S/H grubuna bağlı değil.
6. **Tezgâh tarafı:** takım numarası = kütüphane `id`. Sinumerik takım yönetimi (`T="ad"`, kardeş takım `DUPLO`),
   `D` kesici numarası, TNC `TOOL.T` tablosu, MAPPS ofset tablosu dışa aktarılamıyor. Takım yarıçap düzeltmesi (`D`)
   ve aşınma ofseti alanları yok.

## 3. Kararlar (öneri; kullanıcı onayı gerekir)

- **K-A:** Yeni paket `takim/` (atölye envanteri, montaj, katalog içe aktarma). Arayüzü `takim/model.py`.
  CAM bugünkü `cam.model.Tool` / `LatheTool`'u kullanmaya devam eder; `takim` montajdan bunları **üretir**
  (`Montaj.cam_takimi() -> Tool | LatheTool`). Böylece mevcut CAM, sim, post ve föy kodu değişmeden gerçek takımla çalışır.
- **K-B:** `cam/model.py`'ye yalnız **ekleyici, varsayılanlı** alanlar (TK0 arayüz PR'ı, A0 thread'i sahibi):
  `Tool` / `LatheTool` üzerine `material: str | None` (takım malzemesi), `ref: str | None` (envanter kimliği),
  `d_no: int = 1` (kesici numarası), `edges: int | None` (değiştirilebilir uçta kenar sayısı). Eski JSON aynen okunur.
- **K-C:** Bağımlılık eklenmez. ISO 13399 `.p21` okuyucu saf Python yazılır (yalnız gerekli özellik kodları);
  3B model STEP'i `geometry` üzerinden (build123d, `@pytest.mark.occt`) okunur ve sadece çarpışma gövdesi için kullanılır.
- **K-D:** Gizlilik: atölyenin gerçek envanteri `yerel_parcalar/` (gitignore) altında durur. Repoda ve testlerde
  yalnız uydurma takımlar ve uydurma `.p21` örnekleri. Üretici katalog dosyaları repoya girmez (lisans).
- **K-E:** Uydurma kesme verisi yasak (B2 kuralı): her `CuttingData` bir `kaynak` taşır (katalog, atölye deneyimi,
  hesap). Kaynaksız veri CAM'e verilirken uyarı değil `CamError`.

## 4. TK0 — Arayüz PR'ı (`cam/model.py` + `takim/model.py` iskeleti)

`takim/model.py` (saf Python + numpy):

```python
class Arayuz(StrEnum): HSK_A63, HSK_A100, SK40, BT40, CAPTO_C6, VDI40, BMT65, SAP  # "SAP" = silindirik sap
class Rol(StrEnum): TUTUCU, UZATMA, PENS, KESICI, UC   # UC = değiştirilebilir kesici uç (insert)

@dataclass(frozen=True)
class Bilesen:
    kod: str                 # sipariş kodu (uydurma testte)
    uretici: str
    rol: Rol
    makine_tarafi: Arayuz | None    # tezgâha / öncekine bağlanan uç
    is_tarafi: Arayuz | None        # sonrakine bağlanan uç
    boy: float               # mm, makine tarafı ölçü hattından iş tarafı ölçü hattına (ISO 13399 LF / LB)
    profil: tuple[tuple[float, float], ...]  # dönel (z, r) veya torna için çokgen; çarpışma gövdesi
    ozellik: Mapping[str, float | str]       # ISO 13399 özellik kodu → değer (DC, APMX, RE, KAPR, IC, S ...)
    malzeme: str | None = None              # takım malzemesi: "karbur", "hss", "sermet", "cbn", "pcd"
    kalite: str | None = None               # üretici kalite / kaplama kodu
    step: str | None = None                 # 3B model dosya yolu (isteğe bağlı)

@dataclass
class Montaj:
    ref: str                       # atölye kimliği, ör. "F-0123"
    zincir: tuple[Bilesen, ...]    # tezgâh tarafından kesiciye; arayüzler eşleşmeli
    def boy(self) -> float          # ölçü hattından takım ucuna toplam (gauge length)
    def stickout(self) -> float     # son tutucu ağzından uca
    def cam_takimi(self, id: int) -> Tool | LatheTool   # CAM'in bugünkü veri modeline dönüşüm

@dataclass
class Envanter:
    montajlar: dict[str, Montaj]
    stok: dict[str, int]                         # bileşen kodu → adet
    yerlesim: dict[tuple[str, int], str]         # (tezgâh adı, cep / istasyon no) → montaj ref
    def kutuphane(self, tezgah: str) -> ToolLibrary     # o tezgâhın yüklü takımları, id = cep no
```

Hatalar (`ModelError`): arayüz uyuşmazlığı (`HSK_A63` → `SK40`), boy ≤ 0, kesici olmayan zincir, yinelenen
ref, var olmayan montaja yerleşim, stokta 0 adet bileşenle montaj (uyarı değil hata, `strict=True` iken).

Kabul (TK0): JSON gidiş-dönüş birebir; `cam_takimi()` sonucu `Tool.validate` / `LatheTool` kontrollerinden geçer;
eski `examples/takim_kutuphanesi.json` değişmeden okunur.

## 5. TK1 — Envanter ve montaj (`takim/envanter.py`, `takim/montaj.py`)

- Montaj kurma: `kur(bilesenler, ref) -> Montaj` arayüzleri zincirler, boyları toplar.
- `stickout` ve gauge length hesaptan gelir, elle girilmez; `cam/tool_length.py` aynı sayıyı verir.
- Çarpışma gövdesi: tüm zincir profillerinin birleşimi `ToolHolder.profile` olarak (SPEC 44 / 05 / 39 değişmez).
- Torna: tutucu çokgeni + uç (`IC`, `S`, `RE`, `KAPR`) → `LatheTool` + `LatheHolder`; taret istasyonu yerleşimden.
- Atölye dosyası: `yerel_parcalar/takimlar/envanter.json`; Tezgah'ta "Takımlar" ekranı (47 kalıbı, `tezgah/ekranlar/takim.py`)
  ayrı küçük SPEC olabilir (TK5, isteğe bağlı).

Kabul: uydurma 3 bileşenli freze montajı (HSK-A63 pens tutucu + ER32 pens + Ø10 karbür parmak freze) için boy =
analitik toplam (1e-9); 2 bileşenli torna montajı (`PCLNR 2525` benzeri uydurma tutucu + `CNMG 1204` benzeri uydurma uç)
için `LatheTool.kappa_r = 95°`, `eps_r = 80°`, `nose_r = RE`; arayüz uyuşmazlığı `ModelError`.

## 6. TK2 — ISO 13399 / GTC içe aktarma (`takim/iso13399.py`)

- GTC paketi (zip): `package_assortment.xml` + takım başına `.p21` (ISO 10303-21 kodlu ISO 13399 özellikleri) + `.stp`.
- Okunan özellik kodları (ilk sürüm): freze `DC, DCX, APMX, LF, LU, DMM, RE, ZEFP, KAPR, CCMS`; uç `IC, S, RE, L, KAPR, AN`;
  tutucu `LF, WF, HF, B, H, KAPR, PSIR, ADINTMS, ADINTWS` (arayüz tipi).
- Okunamayan / eksik zorunlu kod → `ModelError` (ad ve kod ile). Sessiz varsayılan yok.
- GTC sınıfı (ör. "solid end mill") → `ToolKind` / `LatheToolKind` eşleme tablosu SPEC içinde sabit; eşlenmeyen sınıf hata.
- 3B STEP isteğe bağlı: varsa `geometry` ile okunur, dönel profil kesitten çıkarılır, ISO özellik profiliyle
  karşılaştırılır (fark > 0,1 mm → uyarı listesi).

Kabul: repo içinde **uydurma** `.p21` örnekleri (`tests/takim/veri/`) — özellik değerleri elle yazılmış; içe aktarılan
`Bilesen` alanları bire bir; bozuk dosya, bilinmeyen sınıf, eksik `DC` hata. Gerçek üretici dosyasıyla deneme
kullanıcının yerelinde `yerel_parcalar/` altında yapılır (repoya girmez).

## 7. TK3 — Malzemeye göre kesme verisi (`takim/kesme.py`)

- Anahtar: (kesici kalite / takım malzemesi, ISO malzeme grubu P/M/K/N/S/H **veya** B2/66 malzeme kaydı adı).
- Değer: `CuttingData` + `kaynak` + geçerli aralık (`Vc_min..Vc_max`, `fz` aralığı, `ap`/`ae` sınırı).
- Çözüm sırası: atölye deneyimi > katalog > hesap (Kienzle güç sınırı + SPEC 59 Taylor ömrü). Hiçbiri yoksa `CamError`.
- `cam_takimi(id, malzeme=...)` doğru `cutting` sözlüğünü doldurur; CAM ve SPEC 32 / 59 / 58 aynı veriyi görür.
- Bağımlılık: SPEC 66 (#127) malzeme kütüphanesi `main`'e girdikten sonra başlar.

Kabul: uydurma tabloda P grubu çelik için atölye kaydı varsa o, yoksa katalog seçilir; aralık dışı `Vc` hata;
Taylor ile ömür hedefi verildiğinde `Vc = C / T^n` (SPEC 59 formülü) 1e-12.

## 8. TK4 — Tezgâh takım tablosu ve post (`cam/post/` sahibi post thread'i)

- Program takım çağrısı tezgâh profiline göre: Sinumerik `T<cep> M6` + `D1` (T numarası; karar 2);
  TNC `TOOL CALL "F-0123" Z S..` veya numara; MAPPS / Fanuc tornada `T<istasyon><ofset>`.
- Dışa aktarma: Sinumerik takım listesi (`.ini`/`.tma` biçiminde `$TC_DP` blokları), Heidenhain `TOOL.T`, MAPPS ofset
  tablosu (CSV). İçerik: ad, boy (`$TC_DP3` / `L`), yarıçap (`$TC_DP6` / `R`), köşe radyüsü (`R2`), kardeş no.
- Ön kontrol: programdaki takım, o tezgâhın envanter yerleşiminde yoksa post `CamError` (SPEC 48 doğrulama akışına bağlanır).
- İş föyü (SPEC 38): takım satırına sipariş kodu, montaj boyu, stickout, cep / istasyon no eklenir (föy kodu `Tool.ref` okur).

Kabul: uydurma iki takımlı programda üç denetleyicinin çıktısı beklenen satırları içerir; boy ve yarıçap değerleri
`Montaj.boy()` ile aynı; yerleşimde olmayan takım hata. Gerçek tezgâh denemesi SPEC 48 adımlarıyla kullanıcıda.

## 9. Kim nasıl kullanır

| Kullanıcı | Neyi alır |
|---|---|
| CAM (03–06, 19, 20, 29 plan) | `Envanter.kutuphane(tezgah)` → mevcut `ToolLibrary`; plan yalnız o tezgâhta yüklü takımlardan seçer |
| Sim / çarpışma (05, 22, 39, 44) | Montaj zincirinin birleşik profili (`ToolHolder` / `LatheHolder`) |
| Kuvvet / ömür / maliyet (32, 59, 58, Ek 2) | `material`, `edges`, kesme verisi kaynağı, uç fiyatı (isteğe bağlı alan) |
| Post (31, 21) | Takım adı / cep / `D` no, tezgâh tablosu dışa aktarma |
| İş föyü (38) | Sipariş kodu, montaj boyu, stickout, yerleşim |
| Tezgah (47/62) | Takım ekranı (TK5, isteğe bağlı) |

## 10. Kapsam dışı
- Üretici çevrim içi API'leri (CoroPlus, ToolsUnited vb.) ve ağ erişimi.
- Takım ön ayar cihazından ölçü okuma (Zoller vb.) — ileride ayrı SPEC.
- MES'e takım yazma (MES'e Tezgah yazmaz kuralı).

## 11. Verilen kararlar (2026-10-18, otomatik kabul kuralıyla öneriler)
1. İlk aşama: atölye envanteri elle / CSV ile girilir (TK0 + TK1). Katalog içe aktarma (TK2) sonra.
2. Sinumerik: isimli takım yok, **T numarası** (`T<cep> M6` + `D1`). İsimli takım (`T="..."`) kapsam dışı.
3. Ana tedarikçi **Sandvik**: TK2'de ilk denenen GTC paketi Sandvik biçimi; Iscar / Kennametal sonra.

## 12. Sıra
TK0 (arayüz PR'ı) → TK1 → TK4 → TK3 (SPEC 66 #127 main'e girince) → TK2.

## 13. Nerede kaldı (2026-10-18 19:13, kullanıcının durdurma isteği)
- Taslak tutarlı ve tam; kod, dal veya PR yok.
- Onay bekleyen: taslak metninin (TK0–TK4) kullanıcı onayı ve §11'deki üç kararın kullanıcının kendi yazısıyla teyidi
  (otomatik kabulle seçildiler).
- Devam edildiğinde ilk iş: TK0 arayüz PR'ı (`cam/model.py` sahibi A0 thread'i ile).
