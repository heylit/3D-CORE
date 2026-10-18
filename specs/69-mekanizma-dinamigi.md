# SPEC 69 — Mekanizma dinamiği: ters dinamik, eklem kuvvetleri ve motor torku (Dalga 7, A11)

> Durum: **onaylı** (kullanıcı, 2026-10-18 16:19, önerilen cevaplarla; mesaj cmsg_01DTo5iWYb5RBUWgjk6xu1sGJGTUdh2rjZ3topbRjRQuit). Bağımlılık:
> - SPEC 33 (montaj kinematiği, `assy/kinematik.py`: `Joint`, `drive`, `sweep`)
> - SPEC 02/07 (`geometry/props.mass_props`)
> - B2/66 (`Component.material` → `rho`)

## Amaç
SPEC 33 bir mekanizmanın nasıl hareket ettiğini bulur. Atölye ve tasarım soruları ise kuvvetle ilgilidir:
- Bu hareketi yapmak için motor ya da silindir ne kadar tork veya kuvvet vermeli?
- Pim ve yatak hangi kuvveti taşıyor?
- En kötü an hangisi?

Bu SPEC **ters dinamik** hesaplar. Sürücü eklemin hareketi zamanın fonksiyonu olarak verilir; sonuç olarak her anda
sürücü torku veya kuvveti ve bütün eklem tepki kuvvetleri ve momentleri bulunur. Yöntem katı cisim Newton–Euler
denklemleri ve Lagrange çarpanlarıdır (numpy). Eklem kuvvetleri ileride 67b'ye pim yükü olarak verilebilir (açık soru 2).

## Teori

### Birimler
- kütle t, uzunluk mm, zaman s
- kuvvet N (t·mm/s²), moment N·mm
- atalet t·mm²
- `g` vektörü kullanıcı verir; Dünya için `|g| = 9810` mm/s²

### Kütle özellikleri
Her bileşen için `geometry.props.mass_props(part, rho)` kütle `m`, kütle merkezi `c` ve atalet tensörü `J_c`
verir. `rho`, 66 köprüsünden gelir (`Component.material`). Bileşen için açık bir `MassProps` geçersiz kılması
verilebilir; gövde dışı motor ya da yük gibi parçalar için kullanılır. Sabit (`fixed`) bileşenlerin kütlesi kullanılmaz.

### Kinematik (33'ten)
- Konum: `drive` ile `q(t)` her zaman adımında çözülür.
- Hız: kısıt denklemi `Φ(q, t) = 0`, sürücü kısıtı dahil. Doğrusal sistem `Φ_q q̇ = −Φ_t` çözülür.
- İvme: `Φ_q q̈ = γ`. `γ = −(Φ_q q̇)_q q̇ − 2Φ_qt q̇ − Φ_tt` analitik yerine, hız çözümünün `t` etrafında merkezi farkıyla
  bulunur (`h = 1e-4·T_periyot`, hata `O(h²)` ≈ 1e-8 göreli). Bu basitleştirme kodda ve teoride belgelenir.
- Her cisim için dünya çerçevesinde kütle merkezi hızı ve ivmesi `v_c, a_c` ile açısal hız ve ivme `ω, ω̇` elde edilir.

### Newton–Euler ve Lagrange çarpanları
Her hareketli cisim `i` için:
```
m_i a_c,i = F_dış,i + m_i g + Σ_eklem F_eklem
J_i ω̇_i + ω_i × J_i ω_i = M_dış,i + Σ_eklem (r × F_eklem + M_eklem)
```
Eklem tepkileri `Φ_qᵀ λ` ile ifade edilir; sürücü kısıtının çarpanı sürücü torkudur (ya da kuvveti):
```
Φ_qᵀ λ = Q_dış + Q_g − M q̈ − Q_v       (Q_v: ω × Jω terimleri)
```
Kısıt rankı tam ise sistem `λ` için tek çözümlüdür. Fazla kısıtlı mekanizmada (33'ün `mobility` raporu) en küçük kareler
çözümü verilir ve rapor "statik belirsiz, tepkiler tek değil" uyarısını taşır. Tork yine tektir, çünkü güç dengesinden
gelir.

Her eklem için tepki, eklemin `a` çerçevesinde kuvvet ve moment bileşenleri olarak raporlanır.

### Kapalı formüllü referanslar
1. **Güç dengesi** (her mekanizmada, her anda):
   ```
   Σ_sürücü τ · q̇_sürücü = dE_k/dt + dV_g/dt − P_dış
   ```
   Bu, kinematik ve dinamiğin birlikte doğruluğunu sınayan genel bir testtir.
2. **Sürülen sarkaç:** kütle `m`, boy `L`, düzgün çubuk, pim ucundan döner. `θ` aşağı düşeyden ölçülür.
   - `τ = (m L²/3) θ̈ + m g (L/2) sin θ`
   - `θ̇ = ω` sabitken pim tepkisinin radyal bileşeni `m ω² L/2 + m g cos θ` olur.
3. **Krank–biyel:** krank `r`, biyel `l`. Krank ve biyel kütlesiz, piston kütlesi `m`, sabit `ω`, yerçekimi ve sürtünme
   yok.
   - `x = r cos θ + √(l² − r² sin² θ)`
   - `ẋ` ve `ẍ` kapalı türevlerdir
   - `τ = m ẍ · dx/dθ` (güç dengesinden)
   - Örnek: `r = 50`, `l = 200`, `m = 0.002` t (2 kg), `ω = 100` rad/s. `θ = 90°`'de `τ` testte formülden hesaplanır.

Kaynak: Shabana, *Computational Dynamics*, 3. baskı, bölüm 6–7; Nikravesh, *Computer-Aided Analysis of Mechanical
Systems*, bölüm 11; Hibbeler, *Dynamics*, krank–biyel örnekleri.

## Dosyalar
- **Yeni:**
  - `assy/dinamik.py`
  - `tests/assy/test_dinamik.py`, `tests/assy/test_dinamik_parca.py` (OCCT)
  - `examples/69_krank_biyel.json`
  - `specs/69-mekanizma-dinamigi.md`, `durum/69-mekanizma-dinamigi.md`
- **Değişecek:** `assy/__init__.py` (yeni adlar).
- **Dokunulmayacak:**
  - `assy/model.py`: arayüz değişmez; kütle özellikleri dışarıdan sözlükle gelir.
  - `assy/kinematik.py`: SPEC 33'ün dosyasıdır; `drive`, `joint_jacobian`, `joint_value` ve `mobility` kamu adlarıyla
    kullanılır. İç `_Sistem`'e erişim gerekirse 33 sahibine küçük bir kamu işlev eki istenir; içeri import yapılmaz.
  - `geometry/props.py`, `malzeme/`.

Bağımlılık yönü: `assy/dinamik.py` → `assy.model`, `assy.kinematik` (kamu adları), numpy. `geometry` ve `malzeme`
yalnız `dinamik_parca` köprüsünde, geç import ile kullanılır.

## Arayüz
```python
@dataclass(frozen=True)
class Kutle:
    m: float  # t
    c: np.ndarray  # (3,) mm, bileşenin yerel çerçevesinde
    J: np.ndarray  # (3, 3) t·mm², c etrafında, yerel çerçevede


@dataclass(frozen=True)
class Surucu:
    joint: str
    q: Callable[[float], float]  # derece (döner) ya da mm (kayar), zamanın fonksiyonu
    # yardımcı kurucular: Surucu.sabit_hiz(joint, q0, hiz), Surucu.tablo(joint, t, q) (kübik spline, scipy)


@dataclass(frozen=True)
class DinamikSonuc:
    t: np.ndarray  # (s,)
    q: Mapping[str, np.ndarray]  # eklem → (s,)
    tork: Mapping[str, np.ndarray]  # sürücü → (s,) N·mm ya da N
    eklem_kuvveti: Mapping[str, np.ndarray]  # eklem → (s, 3) N, eklemin a çerçevesinde
    eklem_momenti: Mapping[str, np.ndarray]  # eklem → (s, 3) N·mm
    guc: np.ndarray  # (s,) W değil mW (N·mm/s)
    belirsiz: bool  # fazla kısıtlı → tepkiler en küçük kareler

    def en_kotu(self, ad: str) -> tuple[float, float]: ...  # (t, |değer| maks)


def ters_dinamik(
    assembly: Assembly,
    kutleler: Mapping[str, Kutle],
    suruculer: Sequence[Surucu],
    t: Sequence[float],
    *,
    g=(0.0, 0.0, -9810.0),
    dis_kuvvetler: Mapping[str, Callable[[float], tuple[np.ndarray, np.ndarray]]] | None = None,
) -> DinamikSonuc: ...
def kutleler_parcadan(assembly, parts: Mapping[str, Part], kutuphane) -> dict[str, Kutle]: ...  # 66 köprüsü
```
Hatalar (`ModelError` ya da 33'ün `AssyError`'ı aynen):
- hareketli bileşenin kütlesi yok
- `m ≤ 0` ya da `J` pozitif tanımlı değil
- sürücü sayısı mobiliteye eşit değil (eksik sürücü → hareket belirsiz; fazla → çelişki)
- herhangi bir zamanda `drive` yakınsamıyor (zaman ve eklem mesajda)
- eklem sınırı aşıldı
- `t` artan değil

## Kabul kriterleri
- [ ] **K1** Kinematik türevler: krank–biyel (Kutle elle verilir, OCCT'siz) `θ ∈ [0, 360)` boyunca 72 noktada `ẋ` göreli
  1e-8, `ẍ` göreli 1e-6 içinde kapalı formla eşleşir.
- [ ] **K2** Krank–biyel torku: K1'de kütlesiz biyel ve krank için (`m = 1e-12`, `J ≈ 0`), `τ(θ) = m ẍ dx/dθ` 72 noktada
  göreli 1e-6 içinde (ya da `τ ≈ 0` noktalarında abs 1e-6·`m r ω²·r`).
- [ ] **K3** Sarkaç:
  - Sabit `ω = 2` rad/s, `m = 0.001`, `L = 300`.
  - `τ = m g L/2 sin θ` (`θ̈ = 0`) ve pim tepkisinin radyal bileşeni formüle göreli 1e-6 içinde.
  - Sinüs sürüşte (`θ = 30° sin(2πt)`) `τ` `I θ̈` terimini de içerir, göreli 1e-6.
- [ ] **K4** Güç dengesi: K1–K3 ve 33'ün bir uzaysal örneğinde (küresel eklemli 4 çubuk) her zamanda güç dengesi göreli
  1e-6 içinde tutar (`dE_k/dt` merkezi farkla).
- [ ] **K5** Belirsizlik: aynı eksende iki döner eklemle fazla kısıtlı bir menteşe kurulur.
  - `belirsiz = True` olur.
  - Tork K3 ile aynıdır.
  - İki eklemin eksen yönü dışındaki tepkilerinin toplamı tek eklemli çözüme eşittir (göreli 1e-9).
- [ ] **K6** Sürücü sayısı: mobilite 1 olan mekanizmaya 0 ya da 2 sürücü verilirse `ModelError` verir; mesajda mobilite
  değeri geçer.
- [ ] **K7** Parça köprüsü (OCCT): krank–biyel üç gerçek parça ile kurulur (uydurma geometri, 66'dan `1.0503` ve
  `EN-AW-6061-T6`).
  - `kutleler_parcadan` kütleleri `mass_props` ile aynıdır.
  - Güç dengesi K4 toleransıyla tutar.
- [ ] **K8** Hatalar: malzemesiz hareketli bileşen, `J` negatif özdeğerli, `t` azalan, eklem sınırı aşımı (33'ün hatası
  korunur).
- [ ] **K9** `assy/dinamik.py` OCCT import etmez (`sys.modules` denetimi). `ruff` temiz.

## Bağımlılık
- 33 (birleşti).
- 02/07 `mass_props` (birleşti).
- B2/66: yalnız K7 köprüsü için.
- Kullananlar: 67b (açık soru 2), 47 (Tezgah'ta tork grafiği), 36 (montaj sırası; ilgisiz).

## Kararlar (kullanıcı onayı 2026-10-18 16:19; önerilen cevaplar kabul edildi)
1. **İleri dinamik (kuvvet verilir, hareket bulunur; zaman entegrasyonu)?** Karar: ayrı bir ek. Ters dinamik atölye
   sorusuna (motor seçimi) yeter, ileri dinamik DAE entegratörü gerektirir.
2. **En kötü andaki eklem kuvveti 67b'ye otomatik pim yükü olarak aktarılsın mı?** Karar: evet; ama 67b birleştikten
   sonra küçük bir köprü olarak (`analiz/` içinde), bu SPEC'in K'larına girmeden.
3. **Sürtünme (Coulomb, eklemde)?** Karar: hayır. Doğrusal olmayan ve belirsiz; ilk sürüm sürtünmesizdir, rapor bunu
   yazar.

## Kapsam dışı
- İleri dinamik, temas ve çarpma, esnek gövdeler.
- Eklem sürtünmesi, yay ve sönümleyici elemanları (kuvvet fonksiyonu olarak `dis_kuvvetler` ile verilebilir).
- Motor ve redüktör seçimi kataloğu.
