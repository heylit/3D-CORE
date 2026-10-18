# SPEC 47 — Tezgah ekranları: otomatik CAM planı, çok eksen, analiz

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 11:13 UTC, proje sohbetinde yazılı toplu onay: "Dalga 5 SPEC … 47
> metinlerini önerilerle, … A3 arayüz metinlerini … onaylıyorum"). Açık sorular önerilen varsayılanlarla kapandı:
> üç alt PR (47a/b/c), düzlem tıklamayla / silindir elle, tri-dexel yalnız işlem sonları, eklem tablosu, %10 / %5
> uyarı eşikleri. Ekran kaydı A3 sürüm 3'e (`/mnt/project-files/yol-haritasi/a3-ekran-kaydi.md`) göre adlar:
> `Ekran.kimlik` → `ad`, `Ekran.ad` → `baslik`, `kayitli()` → `ekranlar()`, `EkranModulu.kimlik` → `ad`;
> kullanılamaz ekranın uçları 503. Davranış ve kabul kriterleri aynı.
> Dalga 5, hat H14 (`/mnt/project-files/yol-haritasi/dalga-5-onerisi.md`; kullanıcı 2026-10-18 10:51 UTC "Tam" kapsam).
> Tezgah kabuğu, köprü kuralları, `Is` şeması, ikili dizi biçimi, zaman şeridi, kanıt paneli ve ön yüz araç zinciri
> SPEC 24'ten, torna ve montaj ekranları SPEC 25'ten gelir; burada tekrar edilmez.
> Prototip yönü: https://claude.ai/artifact/2YA8RRJYuFSpRJyEFMEX8u (konsept; kabul ölçütü değildir).
> **Ek: K10 olay zamanı** (kullanıcı, 2026-10-18 12:08 UTC önerisi, 2 dakika kuralıyla onaylı): dosya sonunda.
> **Errata K8** (kullanıcı, 2026-10-18 16:27 UTC, proje sohbetinde yazılı onay): sınır dışı noktada eklem değerleri
> SPEC 44 kuralıyla; `G93` yalnız kesme hareketlerinde. Gerekçe: K10 dar profilde `eksen_siniri` olayı ister, SPEC 41
> `inverse` ise sınır dışında hata verir; eski K8 ile K8 ve K10 birlikte sağlanamıyordu.

## Amaç
Kütüphane olarak biten üç yeteneğe Tezgah'ta ekran vermek:
1. **Plan:** parçayı ve ham malzemeyi seçince SPEC 29'un kurduğu otomatik işlem planını özellik özellik gösterir,
   planlanamayanı gerekçesiyle söyler, "takımı çıkarsam / kalan malzemeyi kapatsam ne olur" sorusunu yeniden
   planlayarak cevaplar, planı simülasyonla doğrular ve tek tuşla freze (SPEC 24) ya da torna (SPEC 25) ekranında açar.
2. **Çok eksen:** 3+2 ve eş zamanlı 5 eksen işi tezgâhın kendi kinematiğiyle (SPEC 41–44) oynatır: döner eksen
   değerleri, eksen sınırları, tezgâh gövdesi çarpışmaları, doğrusallaştırma sapması ve tri-dexel talaş sonucu.
3. **Analiz:** parçayı tetrahedron ağına çevirir (SPEC 12), yüz seçerek mesnet ve yük verir, çözer (SPEC 11),
   von Mises ve deformeyi gösterir (SPEC 13), denge ve analitik çözümle kanıt sunar, CalculiX `.inp` dışa aktarır.

Bu adım bitince üç örnek iş tarayıcıda uçtan uca çalışır: `plan_blogu` planlanıp doğrulanır ve freze ekranında
açılır; `kubbe_5eksen` beşik tezgâhta oynatılır ve bir eksen sınırı olayı şeritte görünür; `delikli_plaka` çözülür
ve gerilme sondası Kirsch eğrisinin yanında çizilir.

## Temel ilke (SPEC 24'ten aynen)
**Ön yüz mühendislik sayısı hesaplamaz.** Plan, takım seçimi, gerekçe kodları, plan farkı (29), kinematik, eksen
değerleri, gövde pozları, çarpışma, sapma, ters zaman ilerlemesi, tri-dexel (41–44), ağ, seçim, yük, çözüm,
gerilme, sonda değerleri, güvenlik katsayısı (11–13) Python'dan gelir. Ön yüz gösterir, zaman içinde yalnız görsel
ara değer verir, sunucunun gönderdiği iki sayının farkını gösterebilir ve girdiyi sunucuya iletir. Arayüzde görülen
her sayı, repoda testi olan bir fonksiyonun çıktısıdır; kanıtlardaki "SPEC NN" etiketi o SPEC'in testine işaret eder.

## Bağımlılıklar
| SPEC | Bu SPEC'in ondan kullandığı yetenek | Gerektiği ekran |
|---|---|---|
| 24 Tezgah | kabuk, `Is`, `IsTanimi` / `Islem`, ikili `noktalar`, şerit, kanıtlar, komut çubuğu, `window.__tezgah` | hepsi |
| 25 Torna ve montaj | `TornaIsi` (planın torna işini torna ekranında açmak için) | Plan (torna) |
| A3 Ekran kaydı | aşağıdaki "Ekran kaydı (A3) beklentisi" | hepsi |
| 29 İşlem planı | `plan_mill`, `plan_mill_features`, `plan_turn`, `verify_mill`, `verify_turn`, `MillPlan`, `TurnPlan`, `PlanCheck`, `summary`, `gcode`, `tool_changes` | Plan |
| 27 Özellik tanıma | `recognize` sonucu `Features` (özellik adresleri ve geometrisi) | Plan |
| 28 Torna profili | `turn_profile(part)` (`.outer`, `.inner`) | Plan (torna) |
| 14 Kurulum | `ToolLibrary`, `Setup`, `Wcs` | Plan |
| 30 Tezgâh profili | `MachineProfile` (`x/y/z` sınırları, `kinematics`) | Çok eksen |
| 41 Kinematik, 3+2 | `forward`, `inverse`, `from_normal`, `local_stock`, `local_mesh`, `to_world`, `to_machine` | Çok eksen |
| 42 5 eksen yol | `finish5`, `Orientation`, `Avoid`, `linearize`, `joint_path`, `deviation`, `inverse_time` | Çok eksen |
| 43 Tri-dexel | `simulate5`, `SimResult5`, `TriDexel.intervals`, `volumes` | Çok eksen |
| 44 Tezgâh çarpışması | `MachineModel`, `poses`, `check`, `MachineEvent`, `examples/tezgah_ac_besik.json` | Çok eksen |
| 11 tet4 | `core.solver.solve`, `Result` (yer değiştirme, tepkiler) | Analiz |
| 12 gmsh | `tet_mesh`, `Refine`, `boundary_triangles`, `on_plane`, `on_cylinder`, `select_nodes`, `select_triangles`, `fix`, `add_traction`, `add_pressure` | Analiz |
| 13 Gerilme | `nodal_stress_tensors`, `von_mises`, `principal_stresses`, `fileio.calculix.to_inp` | Analiz |

Fonksiyon adları onaylı SPEC metinlerinden alınmıştır. Kod yazılırken bir yetenek ilgili SPEC'in birleşmiş kodunda
yoksa ya da imzası farklıysa `tezgah/` içinde yeniden yazılmaz: eksik, ilgili SPEC'e ek olarak kullanıcıya sorulur
(altın kural 3). Üç ekran birbirini beklemez (bkz. "Alt PR'lar").

## Kullanıcı deneyimi: alışılmışın dışında olanlar
Görsel tasarım kabul ölçütü değildir; aşağıdaki **davranışlar** ölçüttür (K numaraları parantezde).

**Plan**
1. **Özellik → işlem şeridi.** Sol sütunda parçanın her özelliği (SPEC 27 adresiyle), sağında o özelliği işleyen
   işlemler çip olarak durur; planlanamayan özellik kırmızı satırda düz Türkçe gerekçe ve kodla görünür
   ("Dişli delik: kılavuz çevrimi yok — `kilavuz_cevrimi_yok`, SPEC 29 §1"). Hiçbir özellik listeden düşmez;
   düşerse kanıt panelinde `sessiz_atlama` kontrolü `hata` olur (K3).
2. **"Ne olurdu?" kartı.** Kütüphanede bir takımı kapat, kalan malzemeyi kapat, `n_max` değiştir: sunucu yeniden
   planlar ve **fark** döner: eklenen / çıkan / takımı değişen işlemler, planlanamayana düşen özellikler, süre ve
   takım değişimi farkı. Kullanıcı bir takımın plandaki önemini planı bozmadan görür (K4).
3. **Özellik haritası.** Sahnede her özellik planlandığı işlemin rengiyle boyanır; planlanamayan taralı kırmızı;
   köşe artığı notu olan cebin köşelerinde artık hacmi etiketi (`kose_artigi` notunun değeri) (K2, K12).

**Çok eksen**
4. **Eklem şeridi.** Zaman şeridinin altında her döner eksen ayrı bir şerit: açı eğrisi, profilin sınır bantları,
   SPEC 44 `eksen_siniri` ve `tezgah_carpma` olayları işaretli. Bir olaya tıklayınca şerit o ana atlar, çarpışan
   iki gövde vurgulanır ve aradaki uzaklık yazılır (K7, K8).
5. **Göreli görünüm.** `V` tuşu: "Parça sabit" (WCS; takım eğilir) ↔ "Tezgâh sabit" (makine; masa ve beşik döner).
   İki görünüm de aynı sunucu pozlarından kurulur (K6).
6. **Sapma şeridi.** Doğrusallaştırılmış yolda her segmentin uç noktası konum sapması `e_p` ve eksen sapması `e_a`
   (SPEC 42 `deviation`, segment ortasında) tolerans çizgisiyle; `TCP kapalı` görünümünde takım ucunun gerçek
   (eklem uzayında ara değerli) yolu, programlanan yolun yanında çizilir (K9).

**Analiz**
7. **Tıkla, seç, yükle.** Sahnede bir sınır üçgenine tıklamak o üçgenin düzlemindeki sınır yüzünü seçer (SPEC 12
   `on_plane`); müfettişte "Mesnet" ya da "Yük" seçilir, yük vektörü ya da basınç yazılır. Seçilen düğüm sayısı,
   toplam alan ve toplam kuvvet sunucudan gelir (K14, K15).
8. **Gerilme sondası.** Parçanın üstünde iki nokta arasında çizgi çekilir; sunucu çizgi boyunca von Mises ve
   seçili gerilme bileşenini örnekler ve grafiğe döker; örnek işte Kirsch analitik eğrisi aynı grafikte durur (K17).
9. **Güven halkası.** "Yakınsama" düğmesi aynı problemi üç ağ boyunda (`h`, `h/1.5`, `h/2.25`) çözer; en büyük
   von Mises ve en büyük yer değiştirmenin ağ boyuyla değişimi küçük bir grafikte görünür. Kullanıcı sonuca ne kadar
   güveneceğini görür (K19).

## Ekran kaydı (A3) beklentisi
A3 arayüz PR'ı ("Tezgah uygulaması" thread'inin sahibi olduğu `tezgah/sunucu.py`, `tezgah/arayuz/src/`) ekran kaydını
tanımlar; bu SPEC onu **kullanır, değiştirmez**. A3 aşağıdakinden farklı ad seçerse yalnız adlar uyarlanır; davranış
(kabul kriterleri) değişmez. Bu SPEC'in ihtiyaç duyduğu davranışlar:

Python (`tezgah/ekranlar/__init__.py`, A3):
```python
@dataclass(frozen=True)
class Ekran:
    kimlik: str  # "plan", "cok_eksen", "analiz": adres #/<kimlik>, API /api/ekran/<kimlik>
    ad: str  # sekme adı
    sira: int  # sekme sırası
    tus: str | None  # kısayol ("4", "5", "6")
    router: APIRouter  # önek almadan yazılır; kabuk /api/ekran/<kimlik> altına bağlar
    # None → hazır; metin → neden (ör. "gmsh kurulu değil: pip install -e .[mesh]")
    hazir: Callable[[], str | None]
    sifirla: Callable[[], None] | None  # POST /api/sifirla bunu da çağırır


def kayitli() -> list[Ekran]: ...  # paket içindeki her modülün EKRAN'ı, sira'ya göre


# dinamik işi SPEC 24/25 iş deposuna ekler
def is_kaydet(ad: str, tanim: IsTanimi | TornaIsi) -> None: ...
```
- Bir modülün import'u (ör. gmsh yok) başarısız olursa kabuk çökmez; ekran `hazir` metniyle "kullanılamaz" görünür.
- Çekirdek hataları (`CamError`, `ModelError`, `AssyError`, `GeometryError`) ekran uçlarında da 422 + hata metni
  döner (SPEC 24 kuralı); kabuk bunu ortak bir istisna işleyicisiyle yapar.
- `is_kaydet` ile eklenen iş `GET /api/isler` listesinde ve `#/freze?is=<ad>` / `#/torna?is=<ad>` adresinde açılır.

Ön yüz (`tezgah/arayuz/src/ekranlar/<kimlik>.ts`, her ekranın `default` dışa aktarımı):
```ts
interface EkranModulu {
  kimlik: string; ad: string; tus?: string;
  ac(alan: HTMLElement, kabuk: Kabuk, secim?: URLSearchParams): Promise<void>;
  kapat(): void;
}
interface Kabuk {
  sahne: Sahne;            // SPEC 24 three.js sahnesi (katman ekle / temizle, kamera)
  serit: Serit;            // zaman şeridi (süre, klipler, olay işaretleri, alt şerit ekleme)
  kanitlar(k: Kontrol[]): void;
  mufettis(alan: HTMLElement): void;
  komut(ad: string, calistir: (arg: string) => void): void;   // komut çubuğuna komut kaydı
  git(adres: string): void;                                    // ör. "#/freze?is=plan_blogu-1"
  kanca: Record<string, unknown>;                              // window.__tezgah.<kimlik> test kancası
  api: { getJson, getIkili, postJson };                        // SPEC 24 api.ts, 422 → SunucuHatasi
}
```
A3 birleşmeden bu SPEC'in kodu birleşmez; iskelet A3 dalının üstüne kurulabilir.

## Ortak veri kuralları
- Her JSON yanıtında `"sema": 1`. Birimler N, mm, MPa, s, derece (açılar); dönüşüm yok (altın kural 4).
- İkili diziler little-endian, SPEC 24 biçiminde: başlık `uint32` sayılar, ardından bloklar. Her ikili uç `*_coz`
  eşi olan saf bir Python fonksiyonudur (testler bayt düzeyinde geri dönüşü denetler).
- `Kontrol = {kimlik, baslik, deger, birim, durum: "tamam"|"uyari"|"hata", aciklama, spec}` (SPEC 24).
- Hesap pahalı uçlar (doğrulama, simülasyon, çözüm, yakınsama) sonucu, girdinin parmak izine (girdi JSON'unun
  SHA-256'sı) göre bellekte saklar; aynı girdi ikinci kez hesaplanmaz. Önbellek davranışı sonucu değiştirmez (K21).
- Sunucu tek kullanıcı ve `127.0.0.1`'dedir. Durum bellektedir; `POST /api/sifirla` ekranları başlangıca döndürür.

## Ekran 1: Plan

### Veri modeli
```
Plan = {
  sema: 1, ad, tur: "freze" | "torna", malzeme,
  baglamalar: [{i, wcs, stok, fiksturler: [stok]}],                  # MillPlan.setups / TurnPlan.setup
  ozellikler: [Ozellik],                                              # SPEC 27 sırası (adres sırası)
  islemler: [summary() satırı + {sure}],                              # MillPlan.summary() / TurnPlan.summary()
  planlanamayan: [{adres, kod, detay, metin}],                        # Unplanned; metin = gerekçe tablosunun Türkçesi
  notlar: [{adres, kod, deger, detay, metin}],                        # PlanNote
  takim_degisimi: int,                                                # tool_changes() (torna: ardışık farklı takım)
  takimlar: [{id, ad, tur, D, acik}],                                 # kütüphane; acik = "Ne olurdu?" durumu
  secenekler: {...},                                                  # MillOptions / TurnOptions alanları
  dogrulama: PlanCheck sözlüğü | null,                                # yalnız /dogrula çağrılınca dolar
  gcode: [[satır]],                                                   # bağlama başına program (plan.gcode)
  kontroller: [Kontrol]
}
Ozellik = {adres, tur, durum: "planlandi" | "planlanamadi", islemler: [name], kod?, geometri}
geometri = freze: {z_ust, z_alt, dis: [[x, y]], adalar: [[[x, y]]]} | delik: {merkez, eksen, D, derinlik}
           torna: {profil: [[x, z]]}                                   # özellik kaydının kendi geometrisi
Fark = {eklenen: [name], cikan: [name], takimi_degisen: [{adres, once, sonra}],
        yeni_planlanamayan: [{adres, kod}], kurtulan: [adres], sure_farki, takim_degisimi_farki}
```
- **Özellik → işlem eşlemesi:** işlemin `feature` alanı tek adres ya da delik grubunda `"holes[i,j,...]"`'dir
  (SPEC 29 §1). Grup adresi her `holes[i]`'ye açılır. Bir özellik `planlandi` ise en az bir işlem onu taşır;
  `planlanamadi` ise `planlanamayan` listesinde tam bir kaydı vardır. İkisi birden ya da hiçbiri olamaz.
- **Süre:** işlem başına süre SPEC 05 süre tahmininden (`verify_*` çağrılmadan da; tek işlemin `Toolpath`'ı
  üstünde). Torna işleminde SPEC 22 süre fonksiyonu (SPEC 25 K5 ile aynı kaynak).
- **Fark:** `plan_farki(eski, yeni) -> Fark` saf fonksiyon. İşlemler `(feature, kind)` çiftiyle eşlenir (ad, sıra
  numarası içerdiği için kayabilir); `takimi_degisen` aynı çiftte farklı `tool_id`. `sure_farki = Σyeni − Σeski`.
- **Takımı kapatmak:** kütüphaneden o takım çıkarılmış kopya ile yeniden planlamak demektir (`ToolLibrary`
  değiştirilmez; yeni nesne kurulur). Kütüphanedeki son freze takımı da kapatılabilir; sonuç planlanamayanlarla dolar.
- **Freze ekranında aç:** bağlama `i`'nin işlemleri sırasıyla `Islem(anahtar = kind, ad = name, op, parametreler =
  {"D", "F", "rpm", "a_p", "stepover"})`, `IsTanimi(ad = f"{plan}-{i+1}", kurulum = setups[i], malzeme)` olarak
  `is_kaydet` ile eklenir; hedef parça ağı `parca_ag` olarak geçer (SPEC 24 çakma kontrolü çalışsın diye).
  Torna planı `TornaIsi` olarak torna ekranına gider.

### Örnek işler (uydurma geometri)
- **`plan_blogu` (freze, OCCT):** SPEC 29 K12 parçası: 100×60×20 blok, 40×30 cep (`r = 5`, `[12, 20]`), iç cep
  16×12 × 4, iki adet Ø8 boydan; stok `[−2, 102]×[−2, 62]×[−3, 22]`; kütüphane SPEC 29 Ek A `LIB`; malzeme `"al"`.
  Beklenen: iki bağlama (alt yüz `ikinci_baglama` notu), planlanamayan yok.
- **`plan_engelli` (freze, OCCT'siz):** elle kurulmuş `Features` (SPEC 29 K6 delik kümesi: kayıtlı Ø8, Ø4 kör,
  lambalı Ø6.6/Ø11, havşalı, M8 dişli, eğimli, Ø5) + K3 keskin köşeli cep; `plan_mill_features` ile planlanır.
  Gerekçe kodlarının ekranda görünmesi için vardır: `havsa_takimi_yok`, `kilavuz_cevrimi_yok`, `ustten_erisilemez`,
  `takim_yok`, not `kose_artigi`. Sahnede parça ağı yoktur; özellik geometrisi çizilir.
- **`plan_mili` (torna, OCCT):** SPEC 27 K10 profilinden döndürülmüş parça, `CylinderStock(D = 32, zmin = −10,
  zmax = 62)`, SPEC 29 Ek A torna kütüphanesi, `rpm_max = 3000`; profil `turn_profile(part)` ile (SPEC 28).

### Uçlar (`/api/ekran/plan` altında)
| Uç | Yanıt |
|---|---|
| `GET /ornekler` | örnek listesi `[{ad, tur, aciklama}]` |
| `GET /{ad}` | `Plan` |
| `GET /{ad}/ag` | ikili parça ağı (SPEC 25 biçimi: `float32[nv·3]`, `uint32[nt·3]`); parça yoksa 404 |
| `POST /{ad}/ne_olurdu` | `{takim_kapat?: [id], takim_ac?: [id], secenek?: {anahtar: deger}}` → `{plan: Plan, fark: Fark}`; durum kalıcı olur |
| `POST /{ad}/dogrula` | `Plan` (`dogrulama` dolu, kontroller güncel) |
| `POST /{ad}/ac` | `{bag: i}` → `{adres: "#/freze?is=..."}` (torna: `#/torna?is=...`) |

### Kontroller (Plan)
| kimlik | Kaynak | `hata` / `uyari` koşulu |
|---|---|---|
| `sessiz_atlama` | `Features` ↔ `ozellikler` | bir adres ne planlandı ne planlanamadı (SPEC 29'a aykırılık) → `hata` |
| `planlanamayan` | `unplanned` | sayısı > 0 → `uyari` (değer = sayı) |
| `dogrulama_carpma` | `PlanCheck.collisions` | > 0 → `hata` |
| `dogrulama_cakma` | `PlanCheck.gouge_volume` | > 0 → `hata` |
| `kalan_malzeme` | `rest_volume − expected_rest` | SPEC 29 K12 sınırının (`P·Δ·H`) dışında → `uyari` |
| `takim_degisimi` | `tool_changes()` | bilgi (`tamam`) |
Doğrulama yapılmadıysa `dogrulama_*` ve `kalan_malzeme` kontrolleri listede yoktur (sahte "tamam" yok).

## Ekran 2: Çok eksen

### Veri modeli
```
CokEksen = {
  sema: 1, ad, tur: "3arti2" | "5eksen",
  tezgah: {ad, eksenler: [{ad, tur: "dogrusal" | "doner", min, max}], govdeler: [{ad, halka, sekil}]},
  wcs, L,                                           # takım boyu (pivot – uç)
  islemler: [{i, ad, takim, t0, t1, k0, k1, cerceve: Frame sözlüğü | null, yonelim: Orientation | null}],
  olaylar: [MachineEvent sözlüğü + zaman],          # SPEC 44 check(), (kind, k, a, b) başına ilk t; zaman [s]: Ek K10
  sim: {removed_volume, rest_volume | null, gouge_volume | null, total_time, collisions: [Collision]} | null,
  sapma: {tol_p, tol_a, e_p_max, e_a_max},          # SPEC 42
  kontroller: [Kontrol]
}
```
İkili diziler:
- **`noktalar`:** SPEC 24 biçimi (WCS'de takım ucu, kümülatif süre, işlem, hızlı bayrağı) + `float32[n·3]` takım
  ekseni `a` (birim, WCS) + `float64[n·(3+k)]` eklem değerleri `q` (`joint_path` / `to_machine`; X Y Z mm, döner
  eksenler derece, sarma çözülmüş) + `float32[n]` `G93` değeri (`inverse_time`; hızlı harekette 0).
- **`pozlar`:** her nokta `k` ve her gövde `b` için `poses(model, q_k, setup, tool)` dönüşümü: `float32[n·m·12]`
  (`R` satır öncelikli 9 + `t` 3). Ön yüz iki nokta arasında yalnız görsel ara değer verir (öteleme doğrusal,
  dönme SLERP); `k` tam sayıda poz sunucudan gelenle birebirdir.
- **`sapma`:** doğrusallaştırılmış yolun her segmenti için `float32[s·2]` (`e_p`, `e_a`), segmentin `t = 0.5`'teki
  `deviation` değeri; ve `TCP kapalı` uç yolu: her segment için 8 ara noktada eklem uzayında doğrusal `q`'nun ileri
  kinematiği (`forward`) `float32[s·8·3]`.
- **`dexel`:** her işlem sonu için (zincirleme `simulate5(ops[j], initial = önceki)`) tri-dexel aralık uçları:
  her eksen için `uint32` ışın sayısı, ışın başına `uint16` aralık sayısı ve `float32` uç çiftleri (ışın
  parametresinde). Ön yüz bunları nokta / kısa çizgi bulutu olarak çizer ("ışın görünümü"); **yüzey ağı kurulmaz**
  (dexel → ağ dönüşümü bu SPEC'te yok).

### Örnek işler (uydurma geometri)
Tezgâh: `examples/tezgah_ac_besik.json` (SPEC 44, uydurma AC beşik tezgâh). Hepsinde malzeme ve stok uydurma.
- **`egik_yuz_3arti2`:** 80×60×40 blok, bir kenarı boyunca 30° pahlı (eğik) yüz; eğik yüzde 30×20 × 3 cep.
  `Frame = from_normal(o, n, x_hint)` (eğik yüzün normali), SPEC 03 cebi `local_stock` / yerel çerçevede, `to_world`
  ile WCS'ye; Ø6 düz freze. Beklenen: tek sabit açı çifti (`A`, `C`), işlem boyunca döner eksen değişmez.
- **`kubbe_5eksen`:** 60×60 tabanlı, yarıçapı 40 olan küre kapağı (tepe `z = 20`); SPEC 06 `Raster` + SPEC 42
  `finish5`, `Orientation("normal", lead = 0, tilt = 10)`, Ø6 küresel uç, `linearize(tol_p = 1e-3, tol_a = 0.05)`.
  Beklenen: `A` ekseni kubbe eteğinde sınıra yaklaşır; örnek, `A` sınırı bilerek dar seçilmiş bir profil
  varyantıyla (`ac_besik_dar`, `examples/` değil, ekranın kendi örnek dosyasında) en az bir `eksen_siniri` olayı üretir.
- **`kubbe_carpisma`:** `kubbe_5eksen` + fikstür gövdesi (kutu) takım tutucusunun geçtiği yerde: en az bir
  `tezgah_carpma` olayı.

### Uçlar (`/api/ekran/cok_eksen` altında)
| Uç | Yanıt |
|---|---|
| `GET /ornekler` | örnek listesi |
| `GET /{ad}` | `CokEksen` |
| `GET /{ad}/noktalar`, `/pozlar`, `/sapma`, `/dexel` | ikili diziler |
| `GET /{ad}/govde/{gövde}` | ikili gövde ağı (kutu / kapsül üçgenlemesi, halka çerçevesinde) |
| `POST /{ad}/parametre` | `{anahtar, deger}`: `lead`, `tilt`, `tol_p`, `tol_a`, `L`, `clearance` → yeni `CokEksen` + `sure_farki` |
| `POST /{ad}/simule` | `CokEksen` (`sim` dolu); tri-dexel pahalı olduğu için ayrı uç |

### Kontroller (Çok eksen)
| kimlik | Kaynak | koşul |
|---|---|---|
| `tezgah_carpma` | SPEC 44 `check` | olay sayısı > 0 → `hata` |
| `eksen_siniri` | SPEC 44 `check` | olay sayısı > 0 → `hata` |
| `dogrusallastirma` | SPEC 42 | `e_p_max > tol_p` ya da `e_a_max > tol_a` → `hata` |
| `govde_carpma` | SPEC 43 `collisions` | > 0 → `hata` |
| `cakma` | SPEC 43 `gouge_volume` | > `gouge_tol` → `hata` |
| `sure` | SPEC 43 `total_time` | bilgi |
Simülasyon çalışmadıysa SPEC 43 kontrolleri listede yoktur.

### G-code
Bu ekranda G-code paneli yerine **eklem tablosu** vardır: satır başına `X Y Z A C` (ya da profilin eksen adları),
`G93` değeri ve işlem. 5 eksen G-code yazımı (`G43.4`, `TRAORI`, `M128`) postprosesör SPEC'idir (42 "Kapsam dışı");
burada "postprosesör yok" etiketiyle açıkça söylenir.

## Ekran 3: Analiz

### Veri modeli
```
Analiz = {
  sema: 1, ad, parca: {ad, hacim}, malzeme: {ad, E, nu, Re},     # Re [MPa]: kullanıcı girdisi, yalnız katsayı için
  ag: {h, dugum, eleman, hacim},                                 # tet_mesh sonucu; hacim = Σ eleman hacmi
  secimler: [{kimlik, tur: "duzlem" | "silindir", tanim, dugumler, ucgenler, alan}],
  kosullar: [{kimlik, secim, tur: "mesnet" | "cekme" | "basinc", deger}],   # mesnet: dof listesi; cekme: [tx,ty,tz]; basinc: p
  cozum: {u_max, u_max_dugum, vm_max, vm_max_dugum, tepki: [Rx, Ry, Rz], yuk: [Fx, Fy, Fz],
          denge: [ex, ey, ez], guvenlik: Re / vm_max | null, olcek} | null,
  analitik: [{ad, formul, deger, birim, fem, fark}],             # örnek işe özgü kapalı formlar
  yakinsama: [{h, dugum, u_max, vm_max}] | null,
  kontroller: [Kontrol]
}
```
İkili diziler:
- **`ag`:** düğüm `float32[nd·3]`, sınır üçgeni `uint32[m·3]` (`boundary_triangles`, düğüm indeksi 0 tabanlı),
  düğüm kimliği `int32[nd]`.
- **`alan`:** çözüm sonrası düğüm başına `float32[nd·3]` yer değiştirme `u`, `float32[nd]` von Mises,
  `float32[nd·3]` asal gerilmeler, `float32[nd·6]` düğüm gerilme tensörü (`nodal_stress_tensors`). Katıya ait
  olmayan düğüm yoktur (tet4 ağı); olsaydı `NaN` yerine ayrı bayrak dizisi gerekirdi (altın kural 5).
- **`sonda`:** `{p0, p1, n, bilesen}` → `float64[n]` yay uzunluğu `s`, `float64[n]` değer, `uint8[n]` içeride bayrağı.

### Hesaplar (Python, saf)
- **Seçim:** tıklanan sınır üçgeni `j` → düzlem `(nokta = üçgenin ağırlık merkezi, normal = triangle_normals[j])`,
  `on_plane(..., tol)`; `tol = 1e-6·L_kutu` (parçanın sınır kutusu köşegeni). Seçim = `select_triangles` ve
  `select_nodes`; aynı düzlemdeki **bütün** sınır yüzleri seçilir (SPEC 12 kuralı, bağlı bileşen ayrımı yok).
  Silindir seçimi müfettişten eksen noktası, yönü ve yarıçapla (`on_cylinder`). Alan = `Σ triangle_areas`.
- **Koşullar:** `mesnet` → `fix(model, dugumler, dofs)`; `cekme` → `add_traction(model, ucgenler, t)`;
  `basinc` → `add_pressure(model, ucgenler, p)`. Model her çözümde ağın temiz kopyasından, koşullar listedeki
  sırayla yeniden kurulur (geri al = listeden çıkar).
- **Çözüm:** `core.solver.solve(model)`; `u_max = max_i |u_i|`; `vm = von_mises(nodal_stress_tensors(...))`;
  `tepki` = mesnet düğümlerinin tepki toplamı; `yuk` = `Load`'ların toplamı; `denge = tepki + yuk`.
  `guvenlik = Re / vm_max` (`Re` verilmemişse `null`; `vm_max = 0` → `ModelError`, sıfıra bölme yok).
  Deforme ölçeği `olcek = 0.1·L_kutu / u_max` (görsel; ön yüz `x + olcek·u` çizer, kaydırıcı bunu 0–2 katla çarpar).
- **Sonda:** `[p0, p1]` üzerinde `n` eşit aralıklı nokta; her nokta için onu içeren tet (barisentrik koordinatlar
  `λ ≥ −1e-9`), değer = düğüm değerlerinin barisentrik ağırlıklı toplamı. Nokta hiçbir tette değilse bayrak 0 ve
  değer 0 (grafikte boşluk; değer gösterilmez). `n ≤ 2000`, `p0 ≠ p1`, aksi `ModelError`.
- **Yakınsama:** aynı parça, koşullar ve malzeme ile `h`, `h/1.5`, `h/2.25` (`max_nodes` sınırı aşılırsa o ağ
  çözülmez ve satırda neden yazılır; sahte sayı yok).

### Örnek işler (uydurma geometri)
- **`delikli_plaka`:** 200×100×5 plaka, merkezde Ø10 delik (`d/W = 0.1`), çelik `E = 210000`, `ν = 0.3`,
  `Re = 235`; plaka `[0, 200]×[0, 100]×[0, 5]`, delik merkezi `(100, 50)`. Sol yüz (`x = 0`) `ux` tutulu; rijit cisim
  kilidi olarak sol yüzün `y = 50` çizgisindeki düğümler ek olarak `uy`, `(0, 50, 0)` düğümü ek olarak `uz` (bu iki
  kilit örnek modülünde `select_nodes` ile iki düzlem tahmininin kesişimiyle kurulur ve ekranda "örnek koşulu"
  olarak kilitli görünür); sağ yüz (`x = 200`) `t = (100, 0, 0)` MPa çekme. Delik çevresinde `Refine` küresi.
  Analitik satırlar: Heywood `Kt_g = (2 + (1 − d/W)³) / (1 − d/W)` = 3.032 (SPEC 13) ve sonda için Kirsch
  `σ_xx(y) = σ/2·(2 + r²/y² + 3r⁴/y⁴)` (sonsuz plaka; `y` delik merkezinden, `θ = 90°` doğrultusu).
- **`konsol_kiris`:** 200×20×20 çubuk, `x = 0` yüzü tam mesnetli, `x = 200` yüzüne toplam `P = 1000 N` aşağı
  (`t = (0, 0, −2.5)` MPa); analitik `δ = P·L³ / (3·E·I)`, `I = b·h³/12`, ve kesme düzeltmeli Timoshenko
  `δ_T = δ + P·L / (κ·G·A)`, `κ = 5/6`, `G = E / (2(1 + ν))`.

`fark` alanı = `fem / analitik − 1` (Python'da). Bu satırlar **bilgi** amaçlıdır; FEM doğruluğunun kanıtı SPEC 11–13
benchmark'larıdır. Kontrol `analitik_sapma`: `|fark| > 0.10` → `uyari` (ağ kaba olabilir), aksi `tamam`.

### Uçlar (`/api/ekran/analiz` altında)
| Uç | Yanıt |
|---|---|
| `GET /ornekler` | örnek listesi |
| `GET /{ad}` | `Analiz` |
| `GET /{ad}/ag`, `/alan` | ikili diziler (`alan` çözüm yoksa 404) |
| `POST /{ad}/sec` | `{ucgen: j}` ya da `{silindir: {nokta, eksen, r}}` → `Analiz` (yeni seçim eklenmiş) |
| `POST /{ad}/kosul` | `{secim, tur, deger}` → `Analiz`; `DELETE /{ad}/kosul/{kimlik}` |
| `POST /{ad}/ag` | `{h}` → yeniden ağ (seçimler tanımlarından yeniden uygulanır) |
| `POST /{ad}/coz` | `Analiz` (`cozum` dolu) |
| `POST /{ad}/sonda` | `{p0, p1, n, bilesen: "vm" \| "sxx" \| ... \| "s1"}` → ikili `sonda` |
| `POST /{ad}/yakinsama` | `Analiz` (`yakinsama` dolu) |
| `GET /{ad}/inp` | `to_inp(model)` metni, `text/plain`, dosya adı `<ad>.inp` |

Mesnet yoksa ya da yetersizse çözücü tekil matriste `ModelError` fırlatır → 422 "Mesnet eksik: …" (çekirdeğin metni).

### Kontroller (Analiz)
| kimlik | Kaynak | koşul |
|---|---|---|
| `denge` | `tepki + yuk` | `max|e| > 1e-6·max(|yuk|, 1)` → `hata` |
| `ag_hacmi` | `Σ eleman hacmi` ↔ `Part.volume` | bağıl fark > 1e-2 → `uyari` |
| `akma` | `guvenlik` | `< 1` → `hata`, `< 1.5` → `uyari`, `Re` yoksa listede yok |
| `analitik_sapma` | örnek analitik satırları | yukarıdaki kural |
| `yakinsama` | son iki ağın `vm_max` bağıl farkı | `> 0.05` → `uyari`; yakınsama çalışmadıysa listede yok |

## Mimari ve dosyalar
```
tezgah/ekranlar/                 (paket ve __init__.py A3'ündür; bu SPEC yalnız aşağıdaki modülleri ekler)
  plan.py                        EKRAN + APIRouter (ince: kopru fonksiyonlarını çağırır, 422 eşler)
  plan_kopru.py                  saf: plan_json, ozellik_eslemesi, plan_farki, plan_isleri, kontroller. FastAPI'siz.
  plan_ornekler.py               plan_blogu, plan_engelli, plan_mili
  cok_eksen.py                   EKRAN + APIRouter
  cok_eksen_kopru.py             saf: cok_json, noktalar/pozlar/sapma/dexel ikili + *_coz, kontroller
  cok_eksen_ornekler.py          egik_yuz_3arti2, kubbe_5eksen, kubbe_carpisma; ac_besik_dar profili
  analiz.py                      EKRAN + APIRouter
  analiz_kopru.py                saf: analiz_json, secim, kosullar, coz, sonda, yakinsama, ikili + *_coz, kontroller
  analiz_ornekler.py             delikli_plaka, konsol_kiris
tezgah/arayuz/src/ekranlar/
  plan.ts, cok_eksen.ts, analiz.ts            EkranModulu (A3 sözleşmesi)
  plan_yardim.ts                 saf: fark rozetleri, özellik satırı sıralaması, gerekçe metni eşlemesi
  cok_eksen_yardim.ts            saf: poz ara değeri (öteleme doğrusal + SLERP), eklem şeridi örnekleme, olay → t
  analiz_yardim.ts               saf: renk ölçeği (değer → renk), deforme konumu x + s·u, sonda grafiği ölçeği
tests/tezgah/ekranlar/           test_plan.py, test_cok_eksen.py, test_analiz.py, test_ekran_uclari.py,
                                 test_bagimlilik_47.py
tezgah/arayuz/tests/ekranlar/    plan.test.ts, cok_eksen.test.ts, analiz.test.ts, e2e_47.spec.ts
durum/47-tezgah-ekranlari.md
```
- Dokunulmayacak: `tezgah/sunucu.py`, `tezgah/kopru.py`, `tezgah/arayuz/src/` altındaki mevcut dosyalar,
  `tezgah/ekranlar/__init__.py` (A3), tüm `*/model.py`, `cam/`, `core/`, `mesh/`, `fileio/`, `examples/`,
  `pyproject.toml`, `DURUM.md`, `docs/yol-haritasi.md`. Yeni bağımlılık yok (gmsh `[mesh]`'te, OCCT `[cad]`'de,
  FastAPI `[web]`'de zaten var).
- Bağımlılık yönü SPEC 24 K9 kuralı: `tezgah` → `cam`, `assy`, `geometry`, `mesh`, `core`, `fileio` herkese açık
  adları; bu SPEC'le `mesh`, `core.solver`, `core.post`, `fileio.calculix` de izinli listeye girer. Hiçbir paket
  `tezgah`'ı import etmez. Ekran modülleri birbirini import etmez (ortak ihtiyaç A3 kabuğundan gelir).

## Kabul kriterleri
Konum toleransı `1e-9` mm, açı `1e-9`°, bağıl `1e-12` (aksi yazmadıkça). Python testleri `[web]` yoksa atlanır;
OCCT gerektirenler `@pytest.mark.occt`, gmsh gerektirenler `pytest.importorskip("gmsh")`.

**Ortak**
- [ ] **K1 Kayıt:** üç modülün her biri A3 `Ekran` kaydını verir (`kimlik` `plan` / `cok_eksen` / `analiz`, `tus`
  `4` / `5` / `6`); gmsh yokken `analiz` `hazir()` metni "gmsh" içerir ve kabuk açılır; OCCT yokken `plan_engelli`
  çalışır, `plan_blogu` ve `plan_mili` `hazir` değildir (listede nedenle). (`test_ekran_uclari.py::test_kayit`)

**Plan**
- [ ] **K2 Plan köprüsü:** `plan_json(plan)`'ın `islemler` satırları `plan.summary()` ile aynı sırada ve değerde;
  `planlanamayan` ve `notlar` `unplanned` / `notes` ile birebir; `takim_degisimi == tool_changes()`; `gcode` her
  bağlama için `plan.gcode(LIB, GRBL, program_no = i+1)` ile satır satır aynı; torna planında
  `gcode(spindle = "M3", tool_change = (50, 80))`. (`test_plan.py::test_plan_json`)
- [ ] **K3 Sessiz atlama yok:** her örnekte SPEC 27 sonucundaki her adres `ozellikler`'de tam bir kez; `planlandi`
  olanın `islemler`'i boş değil ve her ad gerçekten o adresi (ya da onu içeren delik grubunu) taşıyan işlemin adı;
  `planlanamadi` olanın kodu `unplanned`'daki kod. `ozellikler`'den bir adres elle silinmiş bir plan sözlüğünde
  `sessiz_atlama` `hata`, örneklerde `tamam`. `plan_engelli`'de kodlar tam olarak `{havsa_takimi_yok,
  kilavuz_cevrimi_yok, ustten_erisilemez, takim_yok}` ve not `kose_artigi` değeri SPEC 29 K3 değeri.
  (`test_plan.py::test_sessiz_atlama*`)
- [ ] **K4 Ne olurdu:** `plan_blogu`'da T1 (Ø16) kapatılınca `fark`: `takimi_degisen` T1'in işlediği her
  `(feature, kind)` çifti için `once = 1`; `sure_farki` iki planın ayrı ayrı hesaplanan süre toplamlarının farkı
  (rel 1e-12); `takim_degisimi_farki` iki `tool_changes()` farkı. Bütün freze takımları kapatılınca her alan özelliği
  `kurtulan` değil `yeni_planlanamayan`'da (`takim_yok` ya da `kesme_verisi_yok`). Aynı takım yeniden açılınca plan
  ilk planla `summary()` düzeyinde aynı ve `fark` boş. `secenek: {rest: false}` → `cep_kalan` işlemleri `cikan`'da.
  Girdi `ToolLibrary` nesnesi değişmez. (`test_plan.py::test_ne_olurdu*`)
- [ ] **K5 Doğrulama:** `POST /dogrula` sonrası `dogrulama` alanları `verify_mill(plan, part, cell = 0.5)` (torna:
  `verify_turn(plan, cell = 0.25)`) ile birebir; `plan_blogu`'da `ok`, `dogrulama_cakma` ve `dogrulama_carpma`
  `tamam`; doğrulama yokken bu kontroller listede yok. İkinci çağrı önbellekten gelir ve sonuç aynı (K21).
  `@occt`, `@slow`. (`test_plan.py::test_dogrulama`)
- [ ] **K6 Freze / tornada aç:** `POST /ac {bag: 0}` sonrası `GET /api/isler` yeni işi listeler; o işin
  `hareketler`'i `plan.ops_for(0)`'ın (delik çevrimi kanonik açılımıyla) hareketleriyle birebir; kurulum
  `setups[0]`; `parca_ag` var ve SPEC 24 `cakma` kontrolü `tamam`. `plan_mili` için torna işi `TornaIsi` olarak açılır
  ve hareketleri plan işlemleriyle birebir. Bilinmeyen bağlama → 422. (`test_ekran_uclari.py::test_plan_ac`)
- [ ] **K7 Plan hataları:** geçersiz seçenek (`n_max ≤ 0`, `plunge_ratio = 0`), bilinmeyen takım kimliği,
  `strict = true` ve planlanamayan varken → 422 ve çekirdeğin (`CamError`) metni; bilinmeyen örnek → 404.
  (`test_ekran_uclari.py::test_plan_hatalar`)

**Çok eksen**
- [ ] **K8 Eklem değerleri:** `noktalar` ikilisinden çözülen `q` dizisi `kubbe_5eksen`'de `joint_path(tp, kin, wcs, L)`
  (SPEC 42), `egik_yuz_3arti2`'de `to_machine(tp, kin, wcs, L)` (SPEC 41) ile birebir (`float64`); sınır dışı
  noktada SPEC 44 kuralı (`inverse(kin)`, olmazsa döner eksen sınırları kaldırılmış `inverse`, önceki noktadan
  süreklilikle); ikincide döner eksen sütunları işlem boyunca sabit; `G93` dizisi `inverse_time(tp, q)` ile `float32`
  olarak birebir, yalnız kesme hareketlerinde hesaplanır, hızlı harekette 0; takım ekseni `a` her noktada birim (1e-6, `float32`). (`test_cok_eksen.py::test_eklemler`)
- [ ] **K9 Pozlar:** her `k` ve gövde için `pozlar` ikilisindeki `(R, t)` `poses(model, q_k, setup, tool)` ile
  `float32` olarak birebir; "Parça sabit" görünümü için `pozlar`'dan türetilen takım ucunun WCS konumu `noktalar`
  konumuyla 1e-4 mm (`float32`) içinde (göreli görünüm tutarlılığı). (`test_cok_eksen.py::test_pozlar`)
- [ ] **K10 Olaylar:** `olaylar` `check(model, setup, ops, L, tcp = True, clearance)` çıktısıyla aynı sırada ve
  değerde; `kubbe_5eksen` + `ac_besik_dar`'da en az bir `eksen_siniri` olayı ve `eksen_siniri` kontrolü `hata`;
  `kubbe_carpisma`'da en az bir `tezgah_carpma` (olaydaki `a`, `b` gövde adları örnekteki gövdeler) ve kontrol
  `hata`; `kubbe_5eksen` + `ac_besik`'te ikisi de `tamam`. Her olayın `zaman`'ı `noktalar` süre dizisinde
  `zaman[k-1] ≤ e["zaman"] ≤ zaman[k]` (Ek: K10 olay zamanı). (`test_cok_eksen.py::test_olaylar`)
- [ ] **K11 Sapma:** `sapma` ikilisindeki her segment değeri `deviation(kin, wcs, L, q0, q1, p0, p1, a0, a1, 0.5)`
  ile `float32` birebir; `linearize` sonrası `e_p_max ≤ tol_p` ve `e_a_max ≤ tol_a`, kontrol `tamam`;
  `linearize` atlanmış (ham `finish5`) yolda aynı ölçü `tol_p`'yi aşar ve kontrol `hata`. `TCP kapalı` noktaları
  `forward(kin, q(s), L, wcs)` ile `float32` birebir (`q(s)` segment uçlarının doğrusal ara değeri).
  (`test_cok_eksen.py::test_sapma`)
- [ ] **K12 Tri-dexel:** `POST /simule` sonrası `sim` alanları zincirleme `simulate5` sonucuyla birebir; `dexel`
  ikilisinden çözülen her ışının aralıkları son `TriDexel.intervals(axis, i, j)` ile `float32` birebir; ışın sayıları
  `nx·ny`, `ny·nz`, `nx·nz`; `removed_volume = V_stok − son TriDexel.volume()` (rel 1e-9). `@slow`.
  (`test_cok_eksen.py::test_tridexel`)
- [ ] **K13 Çok eksen parametre ve hatalar:** `tilt` değişince yeni iş ve `sure_farki` iki işin ayrı hesaplanan
  sürelerinin farkı; `tol_p ≤ 0`, `L ≤ 0`, küresel olmayan takımla `finish5` → 422 ve çekirdeğin metni.
  (`test_ekran_uclari.py::test_cok_eksen_*`)

**Analiz**
- [ ] **K14 Ağ:** `ag` ikilisinin düğümleri ve sınır üçgenleri `tet_mesh(part, h, material)` modelinin düğümleri
  ve `boundary_triangles(model)` ile birebir (indeks eşlemesi düğüm kimliği dizisiyle); `ag.hacim` eleman
  hacimleri toplamı; `ag_hacmi` kontrolü `delikli_plaka`'da `tamam`. (`test_analiz.py::test_ag`)
- [ ] **K15 Seçim:** `delikli_plaka`'da `x = 200` yüzündeki bir üçgene tıklanınca seçimin düğümleri
  `select_nodes(model, on_plane(c, n, tol))` ile aynı, üçgenleri `select_triangles` ile aynı, alan `100·5` (rel 1e-9,
  düzlem yüzde üçgen alanı toplamı kesin); delik yüzeyi silindir seçimiyle (`r = 5`) seçilir ve alan `π·10·5`
  (rel 1e-2, ağ yaklaşımı). Sınır dışı üçgen indeksi, sıfır eksen → 422. (`test_analiz.py::test_secim`)
- [ ] **K16 Çözüm ve denge:** `POST /coz` sonrası `alan` ikilisindeki `u`, von Mises, asal gerilme ve tensörler
  `solve(model)` + `nodal_stress_tensors` + `von_mises` + `principal_stresses` ile `float32` birebir; `yuk` toplamı
  `delikli_plaka`'da `(100·500, 0, 0)` N (rel 1e-9), `denge` kontrolü `tamam`; `u_max`, `vm_max` ve düğümleri
  ikiliden bulunanla aynı; `guvenlik = Re / vm_max` (rel 1e-12); mesnetsiz modelde 422 ve `ModelError` metni.
  `@occt`, gmsh. (`test_analiz.py::test_coz*`)
- [ ] **K17 Sonda:** sabit (doğrusal) bir alanla kurulmuş uydurma tet4 modelinde (`gmsh`'siz, elle 6 tet küp) sonda
  değeri analitik doğrusal alanla 1e-9; `delikli_plaka`'da `θ = 90°` doğrultusundaki sondanın değerleri, içeren
  tetin barisentrik ağırlıklarıyla elle hesaplanan değerle birebir; parça dışı noktalar bayrak 0; `n > 2000`,
  `p0 = p1` → 422. Kirsch eğrisi satırı formülle rel 1e-12 (bu bir gösterim değeridir, FEM ile kıyas ölçütü değil).
  (`test_analiz.py::test_sonda*`)
- [ ] **K18 Analitik satırlar:** `konsol_kiris`'te `δ` ve `δ_T` formüllerle rel 1e-12; `fark = fem/analitik − 1`;
  `delikli_plaka`'da `Kt_g = 3.032` (4 hane). `analitik_sapma` kuralı (`|fark| > 0.10` → `uyari`) iki yönlü test
  edilir (uydurma `fem` değerleriyle, köprü fonksiyonu doğrudan). (`test_analiz.py::test_analitik`)
- [ ] **K19 Yakınsama:** üç satırın her biri o `h` ile ayrı ayrı kurulup çözülen modelin `dugum`, `u_max`, `vm_max`
  değerleriyle birebir; `max_nodes` aşılan satırda sayı yok, neden metni var. `@slow`. (`test_analiz.py::test_yakinsama`)
- [ ] **K20 Dışa aktarım:** `GET /inp` gövdesi `fileio.calculix.to_inp(model)` ile birebir (koşullar uygulanmış
  model); başlıkta `Content-Disposition` dosya adı `delikli_plaka.inp`. (`test_ekran_uclari.py::test_inp`)

**Sunucu ve kural**
- [ ] **K21 Önbellek ve sıfırlama:** aynı girdiyle ikinci `dogrula` / `simule` / `coz` çağrısı çekirdek fonksiyonu
  tekrar çağırmaz (sayaçlı sahte fonksiyonla, `monkeypatch`) ve aynı yanıtı verir; girdi değişince yeniden hesaplar;
  `POST /api/sifirla` sonrası üç ekranın örnekleri başlangıç değerinde (ör. kapatılan takım açık, koşullar örnek
  dosyasındaki gibi). (`test_ekran_uclari.py::test_onbellek_sifirla`)
- [ ] **K22 Bağımlılık kuralı:** SPEC 24 K9 AST taraması yeni modülleri kapsar: hiçbir paket `tezgah`'ı import etmez;
  ekran modülleri yalnız izinli paketlerin herkese açık adlarını ve A3 kabuğunu import eder; ekran modülleri
  birbirini import etmez; bu SPEC'in PR'ında `tezgah/ekranlar/` ve `tests/tezgah/ekranlar/` ile
  `tezgah/arayuz/src/ekranlar/`, `tezgah/arayuz/tests/ekranlar/`, `durum/47-*.md` dışında dosya değişmez.
  (`test_bagimlilik_47.py`)

**Ön yüz**
- [ ] **K23 Saf fonksiyonlar (vitest):** `cok_eksen_yardim.ts`'de `k` tam sayıda poz sunucu pozuyla birebir, arada
  dönme SLERP'i birim dördey ve `R` ortonormal (1e-6), öteleme iki uç arasındaki doğruda; olay → şerit zamanı
  eşlemesi; `analiz_yardim.ts`'de renk ölçeğinin uçları (min → ilk renk, max → son renk, `min = max` durumunda tek
  renk, `NaN` yok); deforme konumu `x + s·u`; `plan_yardim.ts`'de gerekçe kodu → metin eşlemesinin SPEC 29 §1'deki
  10 kodun hepsini kapsaması ve fark rozeti işaretleri. (`tezgah/arayuz/tests/ekranlar/*.test.ts`)
- [ ] **K24 Uçtan uca (Playwright, `@slow`):** `4` ile Plan açılır, konsolda hata yok; `plan_engelli`'de dört
  planlanamayan satırı ve kodları görünür; "Ne olurdu?"da T1 kapatılınca fark rozetleri sunucu `fark`'ıyla aynı;
  `plan_blogu` "Freze ekranında aç" freze ekranını o işle açar ve G-code satır sayısı sunucuyla aynı. `5` ile çok
  eksen açılır; şerit sonunda `window.__tezgah.cok_eksen` ile okunan eklem değerleri son `q` ile (ε içinde) aynı;
  bir `eksen_siniri` olayına tıklanınca saat olayın `zaman`'ına (`e.zaman`, saniye) gider; `V` görünümü değiştirir ve takım ucunun ekrandaki
  dünya konumu iki görünümde K9 ε'u içinde aynı. `6` ile analiz açılır; `x = 200` yüzüne tıklanıp çekme yazılınca
  ve "Çöz" denince kanıt panelinde `denge` `tamam`, renk ölçeği uçları sunucunun min/max'ı; sonda çizilince grafik
  noktaları sunucu ikilisiyle aynı. 400 px ve 1440 px'te ekran görüntüsü, yatay kaydırma yok.
  (`tezgah/arayuz/tests/ekranlar/e2e_47.spec.ts`)
- [ ] **K25 Klavye ve erişilebilirlik:** `4`/`5`/`6` sekmeler, `V` göreli görünüm, `P` sonda modu, `Enter` seçimi
  onayla, `Del` seçili koşulu sil, SPEC 24 tuşları; her etkileşimli öğede görünür odak; renk taşıyan her şeyin metin
  karşılığı (planlanamayan satırının kodu, olay işaretinin etiketi, renk ölçeğinin sayıları). (K24 içinde)
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz.

## Test tablosu
| Test dosyası | K | İşaret | Gerektirir |
|---|---|---|---|
| `tests/tezgah/ekranlar/test_plan.py` | K2–K5 | `occt` (plan_blogu, plan_mili), `slow` (K5) | `[web]`, SPEC 27, 28, 29 |
| `tests/tezgah/ekranlar/test_cok_eksen.py` | K8–K12 | `slow` (K12) | `[web]`, SPEC 41–44, `examples/tezgah_ac_besik.json` |
| `tests/tezgah/ekranlar/test_analiz.py` | K14–K19 | `occt`, gmsh, `slow` (K19) | `[web]`, `[mesh]`, SPEC 11–13 |
| `tests/tezgah/ekranlar/test_ekran_uclari.py` | K1, K6, K7, K13, K20, K21 | ilgili ekranın işaretleri | `[web]`, A3 |
| `tests/tezgah/ekranlar/test_bagimlilik_47.py` | K22 | — | — |
| `tezgah/arayuz/tests/ekranlar/*.test.ts` | K23 | yalnız yerel (pre-push) | Node |
| `tezgah/arayuz/tests/ekranlar/e2e_47.spec.ts` | K24, K25 | `@slow`, yalnız yerel | Node, Chromium |

Analitik değerler testte formülden hesaplanır; köprü çıktısından kopyalanmaz. Uydurma örnek geometrileri test dosyası
kendi kurar ya da `*_ornekler.py`'nin herkese açık kurucularını çağırır (iç dosya değil, ekranın örnek modülü).

## Alt PR'lar
Üç ekran ayrı dosyalarda olduğundan kod üç alt PR'da paralel yürür; her biri kendi iskeleti, test commit'i ve kod
commit'iyle (CLAUDE.md "Test bağımsızlığı"):
| Alt PR | K | Kod başlar |
|---|---|---|
| 47a Plan | K1 (plan), K2–K7, K21 (plan), K22–K25 (plan kısmı) | A3 + 29 (27, 28, 14 ile) dallarının üstünde |
| 47b Çok eksen | K1 (çok eksen), K8–K13, K21, K22–K25 | A3 + 41–44 (+ 30 profili) |
| 47c Analiz | K1 (analiz), K14–K21, K22–K25 | A3 + 12, 13 (11 `main`'de) |
Ortak kriterler (K1, K21, K22, K24) her alt PR'da o ekranın kısmıyla kapanır; üçüncü birleşmede tamamı.

## Yol haritası yeri
- **Numara:** 47 (`47-tezgah-ekranlari`), Dalga 5 hat H14.
- **Bağımlılık:** 47 → 24, 25, A3, 29 (27, 28, 14), 41–44 (30), 11–13.
- `docs/yol-haritasi.md` ve `DURUM.md` bu PR'da değişmez; sahip thread'ler ekler.

## Kapsam dışı
- 3B yüzey işleme planı (SPEC 29 kapsam dışı); yan / alt yüz özelliklerinin 3+2 ile otomatik planı.
- 5 eksen G-code / postprosesör (`G43.4`, `TRAORI`, `M128`, `CYCLE800`, `PLANE SPATIAL`): eklem tablosu yeterli.
- Tri-dexel'den yüzey ağı (dual contouring vb.) ve tri-dexel'in zaman içinde (her `k`'da) gösterimi: yalnız işlem
  sonu anlık görüntüleri.
- Analizde temas, doğrusal olmayan malzeme, modal analiz (SPEC 45), ısıl yük, kesme kuvvetinden sehim (SPEC 45/H4).
- Yüz seçiminde bağlı bileşen ayrımı ve tıklamayla silindir tanıma (OCCT yüz kimliği ağa taşınmıyor); silindir elle.
- CalculiX'i Tezgah'tan çalıştırmak: yalnız `.inp` dışa aktarımı (karşılaştırma SPEC 13'ün test aracıdır).
- SPEC 26 modelleme ekranından ya da kullanıcı STEP dosyasından analize / plana parça göndermek (dosya seçici yok);
  örnek işler dışında parça girişi sonraki ek.
- Gerçek şirket parçaları (gizlilik kuralı): bütün örnekler uydurmadır.

## Açık sorular (2026-10-18 11:13'te önerilerle kapandı)
1. **Alt PR bölünmesi:** üç ekran üç alt PR (47a/b/c) olarak ayrı dallarda mı (öneri), yoksa tek PR mı?
2. **Analizde yüz seçimi:** düzlem tıklamayla, silindir müfettişte eksen + yarıçap yazarak mı (öneri), yoksa
   OCCT yüz kimliğinin ağa taşınması için SPEC 12'ye ek mi?
3. **Tri-dexel gösterimi:** işlem sonu anlık görüntüleri ve "ışın görünümü" nokta bulutu mu (öneri), yoksa
   her `k`'da canlı tri-dexel (olay listesi, SPEC 24 `sim` gibi; çok daha büyük veri) mi?
4. **Çok eksende G-code:** postprosesör yokken eklem tablosu mu (öneri), yoksa ekran postprosesör SPEC'ini mi bekler?
5. **Analitik sapma eşiği:** `%10` `uyari` eşiği ve yakınsama `%5` eşiği uygun mu (öneri: evet; ikisi de yalnız
   uyarı, ölçüt değil)?

## Ek: K10 olay zamanı (2026-10-18)
> Onay: koordinatörün 12:08 UTC önerisi ("SPEC 47b, çok eksen ekranı (K10)"), kullanıcının 11:14 UTC kuralıyla
> ("beni bekleyen bir şey varsa 2dkdan fazla geçerse öneriyi kabul et") kabul edildi.

**Sorun:** K10 olayların SPEC 44 `check()` çıktısıyla birebir aynı olmasını, K24 ise olayın zamanının saniye
cinsinden şeride düşmesini istiyor. SPEC 44 `MachineEvent.t` saniye değil, hareketin içindeki orandır (0–1).

**Karar:**
- `olaylar`'daki her olaya ek bir alan girer: `zaman` [s] `= zaman[k-1] + t·(zaman[k] − zaman[k-1])`.
  - `k`: SPEC 05 genel adım indisi; adım `k`, nokta `k-1`'den nokta `k`'ye giden harekettir (`1 ≤ k ≤ n-1`).
  - `t`: SPEC 44 `MachineEvent`'in hareket içindeki parametresi (0–1).
  - `zaman[]`: `noktalar` ikilisindeki kümülatif süre dizisi.
- SPEC 44 alanları değişmez; `zaman` dışındaki alanlar `check()` çıktısıyla birebir aynıdır (K10'un "aynı sırada ve
  değerde" koşulu bu alanlar için geçerlidir).
- K10 zaman koşulu: `zaman[k-1] ≤ e["zaman"] ≤ zaman[k]`.
- K24'te olaya tıklanınca şerit `e.zaman`'a gider; K23'teki "olay → şerit zamanı eşlemesi" bu alanı kullanır.
