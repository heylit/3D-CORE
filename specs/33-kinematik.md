# SPEC 33 — Montaj kinematiği: eklemler, serbestlik, sürme, sürükleme ve hareket boyunca çarpışma (Dalga 5)

## Amaç
`assy.model.Assembly`'ye eklenen eklemlerle (`Joint`: sabit, döner, kayar, silindirik, küresel) montajı bir
**mekanizma** olarak ele alan saf numpy modül: eklem artıkları ve Jacobian'ları, Grübler–Kutzbach ve rank ile
serbestlik sayımı, eklem koordinatını değere sürme (`drive`), bir noktayı kısıtları bozmadan sürükleme (`drag`),
bir eklemi bir değer dizisi boyunca süpürme (`sweep`) ve bu hareket boyunca parçaların çarpışmasını (SPEC 09)
bulma, ilk temas değerini ikiye bölerek daraltma.

## Teori

### Bilinmeyenler ve referanslar
SPEC 08 ile aynı: sabit olmayan her bileşenin 6 bilinmeyeni `x = [Δt, ω]`, dönme dünya ekseninde sol çarpım
(`R' = exp([ω]×) R`). Yerel `p0`, `d0` için `p = R p0 + t`, `d = R d0`,
`δp = Δt − [R p0]× ω`, `δd = −[d]× ω` (SPEC 08 Teori). Mate artıkları ve Jacobian'ları **SPEC 08'den aynen**
alınır (`assy.mates.residual`, `assy.mates.jacobian`); bu SPEC yalnızca eklemleri ekler.

### Eklem çerçevesi
Her eklemin her iki ucunda bir yerel çerçeve vardır: başlangıç noktası `o`, eksen `z` (`Ref.direction`),
sıfır yönü `x` (`z`'ye dik birim vektör; `Joint.zero_a` / `zero_b`, verilmezse aşağıdaki kuralla seçilir).
Dünyada: `p_a, z_a, x_a` (bileşen `a.component`) ve `p_b, z_b, x_b` (bileşen `b.component`), `y = z × x`.

Sıfır yönü verilmezse (arayüz kuralı, `assy/model.py`): `e` = dünya taban vektörlerinden `|z·e|` en küçük
olanı (eşitlikte x, y, z sırası), `x = birim(e − (e·z) z)`. Deterministiktir; testler bu kurala güvenebilir.

### Eklem koordinatları
| Eklem | Koordinat `q` | Tanım | Birim |
|---|---|---|---|
| REVOLUTE | `θ` | `atan2((x_a × x_b)·z_a, x_a·x_b)`, aralık `(−180, 180]` | derece |
| PRISMATIC | `s` | `(p_b − p_a)·z_a` | mm |
| CYLINDRICAL | `(θ, s)` | yukarıdaki iki tanım birlikte | (derece, mm) |
| SPHERICAL, FIXED | yok | koordinatı sorulursa `AssyError` | — |

İşaret: `θ`, `z_a` etrafında sağ el kuralıyla `x_a`'dan `x_b`'ye pozitif; `s`, `b`'nin çerçevesi `z_a` yönünde
ilerlerken pozitif.

### Eklem artıkları
Eklemler **yönlüdür**: eş eksen kısıtının (SPEC 08) aksine `z_b = +z_a` istenir, `−z_a` kabul edilmez
(koordinat işareti buna bağlı). `L` = SPEC 08'deki karakteristik uzunluk; yön satırları `L` ile çarpılır
(SPEC 08 "ölçekli artık" kuralı, `assy.mates.angular_rows` ile aynı sınıflandırma).

| Eklem | Ref türleri | Artık r | Kaldırdığı serbestlik `c` | Kalan `f = 6 − c` |
|---|---|---|---|---|
| FIXED | AXIS–AXIS | `p_b − p_a` (3) ; `L(z_b − z_a)` (3) ; `L(x_b − x_a)` (3) | 6 | 0 |
| REVOLUTE | AXIS–AXIS | `p_b − p_a` (3) ; `L(z_b − z_a)` (3) | 5 | 1 |
| PRISMATIC | AXIS–AXIS | `(p_b − p_a) × z_a` (3) ; `L(z_b − z_a)` (3) ; `L(x_b − x_a)` (3) | 5 | 1 |
| CYLINDRICAL | AXIS–AXIS | `(p_b − p_a) × z_a` (3) ; `L(z_b − z_a)` (3) | 4 | 2 |
| SPHERICAL | POINT–POINT | `p_b − p_a` (3) | 3 | 3 |

Satır sayısı `c`'den fazladır (ör. `z_b − z_a` 3 satır, rank 2); serbestlik sayımı bu yüzden **rank** ile yapılır
(SPEC 08 ile aynı gerekçe). `z_b − z_a` artığı `z_b = −z_a`'da sıfır olmayan, türevi sıfır olmayan bir değer
verir; yanlış dal durağan noktası oluşmaz.

### Sürme kısıtı (koordinatı bir değere kilitlemek)
`drive`, `sweep` ve sınıra takılan eklem için koordinat ek bir artıkla kilitlenir:
- Dönme, değer `v`: `L(x_b − (cos v · x_a + sin v · y_a))` (3 satır, diğer eklem satırlarıyla birlikte rank 1 ekler).
  `atan2` yerine bu biçim kullanılır: `±180`'de süreksizlik yoktur, `v` herhangi bir gerçel sayı olabilir
  (`v` ve `v + 360` aynı konumdur).
- Öteleme, değer `v`: `(p_b − p_a)·z_a − v` (1 satır).

### Serbestlik sayımı
**Grübler–Kutzbach (uzaysal):** tüm sabit bileşenler tek gövde (zemin) sayılır; `n` = sabit olmayan bileşen
sayısı + 1 (zemin).
```
M = 6 (n − 1) − Σ_eklemler c_i − Σ_mate'ler c_j
```
Mate'lerin `c_j` değeri SPEC 08 tablosundaki "kaldırdığı serbestlik" sütunudur. İki ucu da sabit bileşende olan
eklem/mate toplamdan çıkarılır (zemin üzerinde döngü; sadece tutarlılığı kontrol edilir).
Kaynak: Uicker–Pennock–Shigley, *Theory of Machines and Mechanisms*, Bölüm 1.6 (Kutzbach ölçütü).

**Gerçek serbestlik (rank):** `dof = 6·n_serbest − rank(J)`, `J` mate + eklem satırları, SPEC 08'deki eşik
(`σ_i > 1e-8 σ_max`), mevcut konumda.

**Fazla tanım:** `redundant = dof − M` (tutarlı bir mekanizmada `≥ 0`). Düzlemsel dört çubuk uzaysal olarak
`M = 6·3 − 4·5 = −2` verir ama gerçekte `dof = 1`'dir: `redundant = 3`. Bu, eksenlerin paralel olmasından gelen
geometrik özelliktir (düzlemsel Grübler `3·3 − 4·2 = 1`); rank bunu doğru sayar.

### Sürme (drive)
Seçilen eklemlerin koordinatları sürme kısıtıyla kilitlenir, tüm sistem SPEC 08'deki Gauss–Newton'la
(en küçük normlu adım, geri izleme, `tol`) mevcut konumdan çözülür. En küçük normlu adım sayesinde çözüm mevcut
konuma en yakın daldır (dört çubukta açık/çapraz montaj değişmez). Yakınsamazsa → `AssyError`
("ulaşılamaz konum": ör. Grashof dışı kolu kilit konumunun ötesine sürmek).

### Sınırlar
`Joint.limits` (REVOLUTE: derece, PRISMATIC: mm, CYLINDRICAL: dönme ve öteleme ayrı) kapalı aralıktır.
- `drive` hedefi sınırın dışındaysa → `AssyError` (sessizce kırpmak yok).
- Çözümde başka (sürülmeyen) bir eklemin koordinatı sınırı `1e-9` aşarsa → `AssyError`, mesaj eklemin adını yazar.
- `drag` sınırda **durur** (aktif küme): sürükleme sonucu bir eklem sınırı aşarsa, en çok aşan eklem o sınıra
  sürme kısıtıyla kilitlenir ve sürükleme başlangıç konumundan yeniden çözülür; aşan eklem kalmayana dek
  (en fazla sınırlı eklem sayısı kadar).
- Sınırlı REVOLUTE için sınırlar `[−180, 180]` içindedir (arayüz kuralı); koordinat `(−180, 180]`'de okunur.

### Sürükleme (drag)
Bileşen `c` üzerindeki yerel nokta `p0`'ı dünya hedefi `h`'ye sürükler (SPEC 17 sürükleme mantığının 3B hâli).
Çözülmüş `x`'ten her adımda, `J` tüm kısıtların Jacobian'ı, `N` sıfır uzayının ortonormal tabanı
(`J`'nin SVD'sinde eşik altı tekil değerlere karşılık gelen sağ tekil vektörler), `S_p = ∂p/∂x` (`c`'nin
sütunlarında `[I, −[R p0]×]`, diğer sütunlar sıfır):
```
δx = N (S_p N)⁺ (h − p)            kısıtları birinci mertebede bozmayan, noktayı hedefe en çok yaklaştıran adım
x ← x + δx, ardından Gauss–Newton ile r(x) = 0'a geri dönüş
```
`|S_p δx| ≤ 1e-12 · L` veya `max_iter` ile durur. Sonuç noktası hedefe **yerel olarak en yakın** erişilebilir
konumdur. Sabit bileşen sürüklenirse → `AssyError`. Hareketsiz mekanizmada (`dof = 0`) nokta yerinde kalır.

### Süpürme (sweep)
Bir eklemin koordinatı bir değer dizisi `v_0, v_1, ...` boyunca sürülür; her adım bir önceki adımın çözümünden
başlar (devamlılık: dal değişmez, adım küçük tutulduğu sürece). Her adımda tüm montajın `T`'leri ve tüm
eklem koordinatları kaydedilir. Bir adım çözülemezse (ulaşılamaz veya başka eklemin sınırı aşıldı):
`partial=False` → `AssyError` (adım indisi ve değeri mesajda); `partial=True` → o ana kadarki hareket döner,
`Motion.stopped` sebebi yazar.

### Hareket boyunca çarpışma
Her adımda montaj, bileşen başına bir yaprak olan düz bir SPEC 07 ağacına çevrilir (kök `"montaj"`, yaprak adı =
bileşen adı, `T` = bileşenin `T`'si) ve SPEC 09 `assy.girisim.check` çağrılır. Raporlanan `Clash` yolları bileşen
adlarına çevrilir. Bir eklemle doğrudan bağlı bileşen çiftleri varsayılan olarak atlanır (`ignore_joined=True`):
pim–delik gibi eklem yüzeyleri tasarım gereği temas eder.

**İlk temas:** `first_contact` eklemi `start`'tan `end`'e `steps` eşit adımla süpürür; çarpışmanın (`GIRISIM`
veya `TEMAS`, ya da `clearance > 0` ise `DAR`) ilk görüldüğü adım ile önceki serbest adım arasında **ikiye
bölme** yapar, aralık `tol`'den küçük olunca serbest taraftaki değeri döndürür. Ayrık örneklemedir: iki örnek
arasında girip çıkan çarpışma kaçabilir (bkz. Kapsam dışı); `steps` bunu kullanıcı tarafından sınırlar.

### Analitik doğrulama değerleri
- **Sarkaç** (REVOLUTE, eksen z, merkez orijin, kol ucu yerelde `(L, 0, 0)`): `θ` sürülünce uç
  `(L cos θ, L sin θ, 0)`. Uç `h = (hx, hy, hz)`'ye sürüklenince `L·(hx, hy, 0)/|(hx, hy)|`.
- **Krank–biyel** (krank `r`, biyel `l`, piston eksen x üzerinde, krank açısı `θ`):
  piston konumu `x = r cos θ + √(l² − r² sin² θ)`. Kaynak: Uicker–Pennock–Shigley, Bölüm 3.
- **Dört çubuk** (zemin `d`, krank `a`, biyel `b`, sarkaç kol `c`; krank `A0 = (0,0)`, kol `B0 = (d,0)`, düzlem
  z = 0): krank açısı `θ2` için `A = a(cos θ2, sin θ2)`, `B` = `A` merkezli `b` ve `B0` merkezli `c` yarıçaplı
  çemberlerin başlangıçtaki (açık) daldaki kesişimi; kol açısı `θ4 = atan2(B_y, B_x − d)`.
  Freudenstein denklemi ile çapraz kontrol: `K1 cos θ4 − K2 cos θ2 + K3 = cos(θ2 − θ4)`,
  `K1 = d/a`, `K2 = d/c`, `K3 = (a² − b² + c² + d²)/(2ac)`. Grashof kilidi (kol için
  ulaşılamayan krank açısı): `|A − B0| > b + c` olduğu `θ2`.
- **Kayan blok çarpışması** (10 mm küp PRISMATIC ile x ekseninde kayıyor, `s = 0`'da sabit duvara uzaklık `g`):
  ilk temas `s = g`.
- **Dönen kol çarpışması** (kol kutusu `[0, Lk] × [−e, e] × [0, h]`, z ekseni etrafında döner; sabit engel
  `y ≥ w` yarı uzayını kaplayan kutu, `x ∈ [0, Lk + 10]`): ilk temas
  `θ* = asin(w / √(Lk² + e²)) − atan2(e, Lk)` (kolun dış köşesi `(Lk, e)`'nin yörüngesi `y = w`'ye değer).

## Dosyalar
- Yeni: `assy/kinematik.py`, `tests/assy/test_kinematik.py`, `tests/assy/test_kinematik_carpisma.py`
  (OCCT, `@pytest.mark.occt`), `durum/33-kinematik.md`
- Ön koşul (ayrı arayüz PR'ı, A1, `assy/model.py` sahibi "Dalga 2 arayüz ekleri"): `JointKind`, `Joint`,
  `Assembly.joints` (aşağıda). SPEC 33 PR'ı `assy/model.py`'yi değiştirmez.
- Ön koşul (kod): SPEC 08 (`main`'de), SPEC 09 `assy/girisim.py` (`check`), SPEC 07 `Node`.
- Dokunulmayacak: `assy/model.py`, `assy/mates.py`, `assy/solver.py` (yalnızca genel adlarıyla kullanılır),
  diğer paketler, ortak dosyalar.

`assy/kinematik.py` OCCT import etmez; parçalara yalnızca `assy.girisim.check` üzerinden (o da `Part`
arayüzüyle) dokunur. Çarpışma dışındaki her şey OCCT olmadan test edilir.

## Arayüz

### Ön koşul: `assy/model.py` eki (A1, arayüz PR'ı)
```python
class JointKind(StrEnum):
    FIXED = "sabit"
    REVOLUTE = "doner"
    PRISMATIC = "kayar"
    CYLINDRICAL = "silindirik"
    SPHERICAL = "kuresel"


@dataclass
class Joint:
    """İki bileşen arasında yönlü eklem. a: ebeveyn (genelde zemine yakın), b: çocuk.

    a, b: SPHERICAL için POINT, diğerleri için AXIS referansı (yerel origin + eksen).
    zero_a, zero_b: yerel sıfır yönü (dönme açısı 0 ve FIXED/PRISMATIC'te dönme kilidi); eksene dik bileşeni
        alınıp birim yapılır. None → dünya taban vektörlerinden eksene en dik olanının izdüşümü
        (|z·e| en küçük; eşitlikte x, y, z sırası).
    limits: koordinat aralığı (alt, üst), kapalı. REVOLUTE: derece, [−180, 180] içinde; PRISMATIC: mm;
        CYLINDRICAL: ((θ_alt, θ_üst), (s_alt, s_üst)), her biri None olabilir. None → sınırsız.
    """

    name: str
    kind: JointKind
    a: Ref
    b: Ref
    zero_a: tuple[float, float, float] | None = None
    zero_b: tuple[float, float, float] | None = None
    limits: tuple | None = None

    def axis_frame(self, side: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """side 'a' veya 'b': YEREL (origin, z, x); x Teori'deki kuralla tamamlanmış birim vektör."""
```
`__post_init__` doğrulaması (`AssyError`): `name` boş; `kind` bilinmeyen; ref türü eklemle uyumsuz (SPHERICAL dışında
AXIS, SPHERICAL'da POINT); `zero_*` sonlu değil veya eksene paralel (`|birim(zero) × z| < 1e-9`); SPHERICAL ve
FIXED'de `limits` dolu; sınırda alt > üst, sonlu olmayan değer veya REVOLUTE için `[−180, 180]` dışı; CYLINDRICAL'da
`limits` iki elemanlı değil.

`Assembly` eki: `joints: list[Joint] = field(default_factory=list)`; `validate` ayrıca eklem adlarının tekilliğini,
eklem bileşenlerinin varlığını ve iki ucun farklı bileşende olmasını kontrol eder; `to_dict` / `from_dict` eklemleri
taşır (`"joints"` anahtarı yoksa boş liste: eski JSON'lar okunur).

### `assy/kinematik.py`
```python
JointValue = float | tuple[float | None, float | None]  # CYLINDRICAL: (θ, s), None = serbest


@dataclass(frozen=True)
class Mobility:
    gruebler: int  # Kutzbach M
    dof: int  # rank ile gerçek serbestlik
    redundant: int  # dof − gruebler


@dataclass
class Motion:
    joint: str
    values: list[float]  # başarıyla çözülen adımların sürme değerleri
    poses: list[dict[str, np.ndarray]]  # adım başına bileşen adı → 4x4 T (sabitler dahil)
    joint_values: list[dict[str, JointValue]]  # adım başına koordinatı olan her eklemin değeri
    stopped: str | None = None  # partial=True ile durduysa sebep

    def apply(self, assembly: Assembly, step: int) -> None:
        """step. adımın T'lerini bileşenlere yazar."""


@dataclass(frozen=True)
class MotionClash:
    step: int
    value: float  # o adımın sürme değeri
    clash: Clash  # SPEC 09 Clash; a, b bileşen adları
```
- `joint_residual(assembly, joint) -> np.ndarray` — Teori tablosundaki ölçekli artık
- `joint_jacobian(assembly, joint, unknowns: list[str]) -> np.ndarray` — sütun düzeni SPEC 08 `jacobian` ile aynı
- `joint_value(assembly, joint: str | Joint) -> JointValue` — Teori'deki koordinat (CYLINDRICAL'da `None` yok);
  SPHERICAL / FIXED → `AssyError`
- `mobility(assembly) -> Mobility` — mevcut konumda; sabit bileşen yoksa `AssyError`
- `drive(assembly, values: Mapping[str, JointValue], tol=1e-10, max_iter=50) -> SolveResult` — SPEC 08
  `SolveResult` (`dof` = sürme kısıtlarıyla kalan serbestlik); girdiyi değiştirmez
- `drag(assembly, component: str, point: Sequence[float], target: Sequence[float], tol=1e-10, max_iter=100)
  -> SolveResult` — `point` bileşenin yerelinde, `target` dünyada; girdiyi değiştirmez
- `sweep(assembly, joint: str, values: Sequence[float], tol=1e-10, max_iter=50, partial=False) -> Motion` —
  CYLINDRICAL'da sürülen koordinat dönmedir, öteleme serbest kalır (öteleme için `drive` + kendi döngüsü)
- `sweep_clashes(assembly, parts: Mapping[str, Part], motion: Motion, clearance=0.0, ignore_joined=True,
  ignore: Iterable[tuple[str, str]] = ()) -> list[MotionClash]` — adım sırasıyla, adım içinde SPEC 09 sırasıyla;
  `parts` anahtarı `Component.part`
- `first_contact(assembly, parts, joint: str, start: float, end: float, steps=50, tol=1e-3, clearance=0.0,
  ignore_joined=True, ignore=()) -> float | None` — Teori'deki ikiye bölme; hiç çarpışma yoksa `None`;
  `start`'ta zaten çarpışma varsa `start` döner

Hatalar (`AssyError`), her biri ayrı test edilir: `validate` hataları; sabit bileşen yok; bilinmeyen eklem adı;
`drive`'da SPHERICAL / FIXED eklem veya CYLINDRICAL'a tek sayı; sürme değeri sınır dışı; sürülmeyen eklem sınırı
aştı; yakınsamama (ulaşılamaz); sabit bileşeni sürükleme; `sweep`'te boş `values`; `first_contact`'ta `steps < 1`,
`tol ≤ 0` veya `start == end`; `clearance` negatif; `parts`'ta olmayan parça kimliği (SPEC 09'dan).

## Kabul kriterleri
Konum toleransı `1e-9` mm, açı `1e-9` derece, aksi yazmadıkça. Çarpışma testleri `@pytest.mark.occt`.
- [ ] K1 Eklem artıkları: her eklem türü için elle kurulmuş sağlanan konumda `r = 0` (1e-12); bilinen bozulmada
  bilinen değer (REVOLUTE'ta b 3 mm kaçık → `|p_b − p_a| = 3`; PRISMATIC'te b ekseni 2 mm yana → `|r_konum| = 2`);
  `z_b = −z_a` sağlanmış sayılmaz — `tests/assy/test_kinematik.py::test_joint_residual_*`
- [ ] K2 Analitik Jacobian = merkezi fark (h = 1e-6, mutlak 1e-6), her eklem türü ve iki sürme kısıtı için,
  rastgele konumlarda — `test_joint_jacobian_matches_fd`
- [ ] K3 `joint_value`: REVOLUTE `θ` b'yi `z_a` etrafında `rot(α)` ile döndürünce `α` (`α ∈ (−180, 180]`, 180 dahil);
  PRISMATIC `s`, b `z_a` boyunca `s` ötelenince `s` (negatif dahil); CYLINDRICAL ikisi birlikte; sıfır yönü
  verilmeyince Teori'deki otomatik kural (z = (0,0,1) → x = (1,0,0); z = (1,0,0) → x = (0,1,0)); SPHERICAL / FIXED → `AssyError`
- [ ] K4 Serbestlik (`mobility`): tek gövde + REVOLUTE → (M, dof, redundant) = (1, 1, 0); PRISMATIC (1,1,0);
  CYLINDRICAL (2,2,0); SPHERICAL (3,3,0); FIXED (0,0,0); iki gövdeli seri kol (2 REVOLUTE) (2,2,0);
  düzlemsel dört çubuk (−2, 1, 3); krank–biyel (−2, 1, 3); aynı eklem iki kez yazılınca dof değişmez, M 5 azalır;
  eklem + mate karışık (REVOLUTE + iki eksene dik AXIS arasında ANGLE 60° mate → (0, 0, 0)); iki ucu sabit eklem M'ye girmez
- [ ] K5 `drive`, sarkaç: `θ = 30, 90, 180, −135` → uç kapalı formda; `θ = 400` ile `θ = 40` aynı konum;
  `joint_value` sonrası sürülen değer (mod 360); girdi değişmez; zaten o değerdeyse 0 iterasyon
- [ ] K6 `drive`, krank–biyel (`r = 20`, `l = 70`): `θ = 0, 45, 90, 135, 180, 270` için piston `x` kapalı formda
  (1e-9 mm); biyel–piston eklemi PRISMATIC `s` değeri piston konumuyla tutarlı
- [ ] K7 `sweep`, dört çubuk (`a = 20`, `b = 60`, `c = 50`, `d = 70`, krank `θ2 = 0..360` 5° adım, Grashof
  krank–sarkaç): her adımda `θ4` kapalı formla ve Freudenstein denklemiyle (1e-9) tutuyor; dal değişmiyor;
  `Motion.poses` uzunluğu = değer sayısı; `Motion.apply` T'leri yazıyor
- [ ] K8 Ulaşılamaz konum: Grashof dışı dört çubuk (`a = 40`, `b = 30`, `c = 30`, `d = 60`) kilitlenen açının
  ötesine `drive` → `AssyError`; aynı süpürme `partial=True` ile kilitten önceki son adımda duruyor, `stopped` dolu,
  son çözülen `θ2` kapalı formdaki kilit açısından küçük ve en fazla bir adım uzakta
- [ ] K9 Sınırlar: REVOLUTE `limits = (−45, 45)` sarkaçta `drive(60)` → `AssyError`; dört çubukta kol eklemine
  sınır verilip krank sürülünce sınırı aşan adımda `AssyError`, mesajda eklem adı
- [ ] K10 `drag`: sarkaç ucu `(30, 40, 7)`'ye sürüklenince (`L = 10`) uç `(6, 8, 0)`; kayar blok noktası eksen
  dışı hedefe sürüklenince hedefin eksene izdüşümüne; `limits = (−45, 45)` sarkaç 90°'lik hedefe sürüklenince
  `θ = 45` (aktif küme); FIXED eklemli bileşen sürüklenince yerinde kalıyor; sabit bileşen → `AssyError`;
  her durumda `max|r| ≤ 1e-10`, girdi değişmez
- [ ] K11 Krank–biyel `drag`: piston pimi x eksenindeki `X` hedefine sürüklenince (`l − r < X < l + r`) piston
  `X`'te, krank açısı kapalı formun başlangıç dalındaki çözümü (başlangıç `θ = 45` → pozitif kök) (`cos θ = (X² + r² − l²)/(2 r X)`)
- [ ] K12 Değişmezlik: tüm montaj keyfi rijit `G` ile taşınınca `drive` ve `sweep` sonuçları `G·T`, eklem
  koordinatları aynen (1e-9)
- [ ] K13 Hatalar: Arayüz'deki her `AssyError` durumu ayrı ayrı
- [ ] K14 (OCCT) `first_contact`, kayan blok `g = 5`: `5 − tol ≤ sonuç ≤ 5`; `g = 5` ama `end = 4` → `None` —
  `tests/assy/test_kinematik_carpisma.py`
- [ ] K15 (OCCT) `first_contact`, dönen kol (`Lk = 50`, `e = 3`, `h = 5`, `w = 20`): sonuç kapalı formdaki `θ*`'a
  `tol = 1e-3` derece içinde ve `θ*`'dan küçük ya da eşit
- [ ] K16 (OCCT) `sweep_clashes`: kayan blok 0..10 mm 11 adım, `g = 5`: `s < 5` adımlarında rapor yok, `s = 5`
  adımında TEMAS, `s > 5` adımlarında GIRISIM ve hacim `10·10·(s − 5)` (1e-6 bağıl); pimli iki bileşen
  `ignore_joined=True` ile raporlanmıyor, `False` ile raporlanıyor; `clearance = 2` ile `3 < s < 5` adımları DAR
- [ ] Tüm testler yeşil: `pytest` → 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` temiz

## Kapsam dışı
- Hız, ivme, kuvvet analizi ve dinamik (Jacobian'dan hız oranı dahil); zamana bağlı hareket profili
- Sürekli çarpışma (iki örnek arasındaki çarpışmayı kaçırmayan süpürülmüş hacim / konservatif ilerleme);
  burada ayrık örnekleme + ikiye bölme var
- Dişli, kam, kayış, vida (helisel) eklemi, düzlemsel eklem, evrensel (kardan) eklem; küresel eklemde koni sınırı
- Otomatik adım inceltme (dal sıçramasını kendiliğinden önleme) ve tekil (kilit) konumdan geçiş
- Ters kinematik hedefleri için çerçeve (konum + yönelim) sürükleme; burada tek nokta sürüklenir
- Alt montajlı (SPEC 07 ağacı) mekanizma: eklemler düz `Assembly` üzerindedir
- Tezgah ekranı / görselleştirme (ayrı SPEC); STEP'ten eklem okuma
