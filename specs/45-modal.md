# SPEC 45 — Modal analiz ve kesme kuvveti altında sehim (Dalga 5, H16)

> Onaylandı: kullanıcı, 2026-10-18 11:13 UTC, Dalga 5 toplu yazılı onayı ("önerilerle").

## Amaç
FEM modelinin doğal frekanslarını ve mod şekillerini (`K φ = ω² M φ`) hesaplamak ve bir kesme kuvvetinin
ağdaki bir parçada takım temas noktasında yarattığı sehimi (statik uyum) vermek: CAM ile FEM arasındaki
ilk gerçek köprü. Hesap `core/`'da saf numpy + scipy; parça → ağ → analiz zinciri yeni `analiz/` paketinde.

## Teori

### Birimler
N – mm – MPa sisteminde kütle birimi **ton** (t = 10³ kg) olur: `N = t · mm / s²`. `Material.rho` zaten
t/mm³'tür (çelik `7.85e-9`). Böylece `ω² = k / m` doğrudan 1/s², `f = ω / 2π` Hz çıkar; kodda birim
dönüşümü yoktur (altın kural 4). Kütle sonuçları ton cinsindendir.

### Eleman kütle matrisleri
Tutarlı (consistent) kütle, rijitlikle aynı şekil fonksiyonlarından: `me = ∫ ρ Nᵀ N dV`.

**bar1d** (`A` kesit, `L` boy; 1B, düğüm başına 1 DOF):
```
tutarlı:   me = ρ A L / 6 · ┌ 2 1 ┐         toplanmış:  me = ρ A L / 2 · I₂
                            └ 1 2 ┘
```
**tet4** (`V` hacim; DOF sırası `ke` ile aynı `[u1, v1, w1, ..., w4]`):
```
tutarlı:   me = ρ V / 20 · (1 + δ_ab) ⊗ I₃       (4x4 düğüm bloğu: köşegen 2, dışı 1)
toplanmış: me = ρ V / 4 · I₁₂
```
İki biçimde de her yönde toplam kütle `Σ_ab me_ab = ρ V` (ρAL) tutar. Tutarlı `me` simetrik pozitif tanımlıdır;
toplanmış `me` köşegendir. `ρ ≤ 0` olan elemanla kütle matrisi kurulamaz → `ModelError`
(`Material.rho` varsayılanı 0.0'dır; modal analiz açıkça `rho` ister).

### Özdeğer problemi
Serbest DOF'lar `f`, tutulu DOF'lar `c` (statik çözücüdeki gibi `model.bcs`'ten). Tutulu DOF'lar mod şeklinde
**sıfırdır**; BC `value` değeri doğrusal sistemin modlarını etkilemediği için okunmaz. `model.loads` okunmaz
(ön gerilme yok).
```
K_ff φ = ω² M_ff φ          φᵢᵀ M_ff φⱼ = δᵢⱼ      φᵢᵀ K_ff φⱼ = ωᵢ² δᵢⱼ
```
`K_ff` pozitif yarı tanımlı (mesnetsiz modelde rijit cisim modları `ω = 0`), `M_ff` pozitif tanımlıdır; bu yüzden
tüm `ω² ≥ 0`'dır. Rayleigh–Ritz özelliği: uyumlu eleman + **tutarlı** kütle ile her `ωᵢ` gerçek değerin
**üstündedir** ve iç içe ağlarda inceltmeyle **monoton azalır**. Toplanmış kütle bu sınırı garanti etmez
(çubukta ve tet4 konsolda gerçek değerin altında / tutarlının altında kalır).

**Çözüm yolu:**
- `n_f ≤ 300` serbest DOF ya da `n_modes > n_f − 2` → yoğun `scipy.linalg.eigh(K_ff, M_ff)`.
- Aksi → `scipy.sparse.linalg.eigsh` kaydır-ters çevir Lanczos (`sigma < 0`, `which="LM"`): `K_ff − σ M_ff` her zaman
  pozitif tanımlı olduğu için mesnetsiz modelde de çarpanlara ayrılır ve en küçük `n_modes` özdeğer bulunur.
  `σ`'nın seçimi uygulamanındır (testler buna bağlı değildir).
- Yuvarlamadan gelen küçük negatif özdeğer `|λ| ≤ 1e-9 · λ_ölçek` sıfıra çekilir (`λ_ölçek` = `diag(K_ff)/diag(M_ff)`
  oranlarının en büyüğü); daha negatif özdeğer → `ModelError` (sessiz hata yok).
- Mod şekilleri kütleye göre birimlenir (`φᵀ M φ = 1`) ve işaret kuralı: mutlak değeri en büyük bileşen pozitiftir
  (eşitlikte en küçük indeks). Katlı özdeğerlerde (simetri) özuzay içindeki taban serbesttir; testler tabandan bağımsız
  ölçüler kullanır (frekans, izdüşüm matrisi `Φ Φᵀ M`).

### Etkin kütle
Taban ivmesi yönü `d` için etki vektörü `r_d` (serbest DOF'larda o yöndeki öteleme = 1, diğerleri 0):
```
Γᵢ_d = φᵢᵀ M_ff r_d            m_eff,i,d = Γᵢ_d²          Σ_i (tüm modlar) m_eff,i,d = r_dᵀ M_ff r_d  (serbest kütle)
```
Kaynak tanım yalnız serbest bölümü kullanır; tüm modlar toplanınca tam olarak serbest kütleyi verir. Konsol
Euler–Bernoulli kirişinde ilk eğilme modunun etkin kütlesi toplam kütlenin `0.6131`'idir.

### Kapalı formüllü referanslar
- **Çubuk, eşit `N` eleman, `h = L/N`, `c² = E/ρ`** (tam ayrık çözüm, sinüs modları):
  - tutarlı: `ωₙ² = 6c²/h² · (1 − cos θₙ) / (2 + cos θₙ)`; toplanmış: `ωₙ² = 4c²/h² · sin²(θₙ/2)`
  - iki ucu tutulu: `θₙ = nπ/N`, `n = 1..N−1`; bir ucu tutulu bir ucu serbest: `θₙ = (2n−1)π/(2N)`, `n = 1..N`
  - sürekli çubuk: `fₙ = (2n−1) c / (4L)` (ankastre–serbest); `θ → 0`'da tutarlı üstten, toplanmış alttan yaklaşır.
  - Tek eleman ankastre–serbest: tutarlı `ω² = 3E/(ρL²)`, toplanmış `ω² = 2E/(ρL²)`.
- **Konsol kiriş** (`L = 100, b = h = 10` mm, çelik `E = 210000`, `ν = 0.3`, `ρ = 7.85e-9`):
  Euler–Bernoulli `fᵢ = (βᵢL)² / (2πL²) · √(EI/(ρA))`, `β₁L = 1.875104`, `β₂L = 4.694091` →
  `f₁ = 835.52 Hz`, `f₂ = 5236.1 Hz`. Eksenel `f_ax = √(E/ρ)/(4L) = 12930 Hz`.
  Kesmeli: `δ_T = PL³/(3EI) + PL/(κGA)`, `κ = 5/6` (SPEC 11 K10 ile aynı).
- **Ön hesap** (repoya girmeyen karalama; SPEC 11 Kuhn ağı `10k × k × k`, ankastre uç tam tutulu, tutarlı kütle):

  | k | f₁ [Hz] | f₁ / f₁,EB | f₂ [Hz] | eksenel mod [Hz] | m_eff,y (mod 1+2) / ρV |
  |---|---|---|---|---|---|
  | 1 | 1565.2 | 1.873 | 2050.1 | 13168 | — |
  | 2 | 1079.6 | 1.292 | 1282.3 | 13034 | 0.614 |
  | 4 | 904.5 | 1.083 | 970.0 | 12993 | 0.612 |
  | 8 | 852.1 | 1.020 | 870.0 | 12977 | 0.612 |

  Kuhn bölümü `(1,1,1)` köşegenini öne çıkardığı için iki eğilme modu `y ± z` köşegen yönlerinde ayrışır
  (`f₁ ≠ f₂`; kare kesitte bile katlı değildir). Bu bir hata değil ağın özelliğidir; testler iki modu birlikte ele alır.
  Toplanmış kütle her `k`'da tutarlının biraz altında (k = 8: 852.05 Hz). tet4 eğilmede kilitlendiği için
  (SPEC 11) frekanslar kaba ağda yüksektir.

### Kesme kuvveti altında sehim (`analiz/`)
Takım temas noktası `p` ve kesme kuvveti `F` (3, N) verilir. `p`'ye uzaklığı `≤ r` olan **sınır düğümleri** `S`
(`mesh.boundary_triangles` köşeleri) seçilir ve kuvvet eşit bölünür: her düğüme `F / |S|`. Bileşke `F`'dir
(moment `p`'ye göre sıfır değildir; `r` eleman boyuna yakın tutulursa ihmal edilir). Statik çözüm `u`'dan:
```
u_p = (1/|S|) Σ_{i∈S} u_i        δ = F̂ · u_p        k = |F| / δ   [N/mm]
```
`δ`, kuvvetin yaptığı işle eşleniktir: `Fᵀ u = |F| δ`; `K` pozitif tanımlı olduğu için `δ > 0`'dır. Uyumlu elemanla
`δ` gerçek değerin **altında** kalır ve iç içe ağlarda artar (SPEC 11). Kuvvetin kendisi (SPEC 32, Kienzle) bu
SPEC'in girdisidir; burada `F` çağıranın verdiği bir vektördür.

Kaynaklar: Bathe, *Finite Element Procedures*, Bölüm 9.3 ve 10–11 (kütle matrisleri, alt uzay / Lanczos, Rayleigh–Ritz
sınırı); Cook–Malkus–Plesha, *Concepts and Applications of FEA*, Bölüm 11 (tutarlı ve toplanmış kütle, ayrık çubuk
dispersiyonu); Blevins, *Formulas for Natural Frequency and Mode Shape*, Tablo 8-1 (konsol, `βL`) ve Tablo 8-16
(etkin kütle); Timoshenko, *Vibration Problems in Engineering*.

## Dosyalar
- Yeni: `core/modal.py`, `analiz/__init__.py`, `analiz/sehim.py`, `analiz/parca.py`,
  `tests/unit/test_kutle.py`, `tests/benchmarks/test_modal.py`, `tests/analiz/__init__.py`, `tests/analiz/test_sehim.py`,
  `tests/analiz/test_parca.py`, `examples/45_modal_cubuk.json`, `durum/45-modal.md`
- Değişecek: `core/elements/bar1d.py` ve `core/elements/tet4.py` (yeni `me`), `core/elements/__init__.py`
  (sözleşme metni), `core/assembly.py` (yeni `assemble_M`; `assemble_K` / `assemble_F` değişmez)
- Dokunulmayacak: `core/model.py` (`Material.rho` zaten var), `core/solver.py`, `core/post.py` (SPEC 13),
  `mesh/` (SPEC 12; yalnız `mesh/__init__.py` adları kullanılır), `pyproject.toml` ve diğer ortak dosyalar.
  `analiz*` paketinin `[tool.setuptools.packages.find]` listesine eklenmesi ortak dosya işidir; ayrı PR'da sahibi
  thread ekler (testler `pythonpath = ["."]` ile o PR olmadan da çalışır).

Bağımlılık yönü: `analiz` → `core`, `mesh`, `geometry` (yalnız `model.py` / `__init__` adları). `core` hiçbir yeni pakete
bağımlı olmaz; `core/modal.py` numpy + scipy dışında bir şey import etmez.

## Arayüz

### Eleman sözleşmesi (`core/elements/`)
- `me(element, model, lumped: bool = False) -> np.ndarray` — `ke` ile aynı boyut ve DOF sırası. bar1d `(2, 2)`,
  tet4 `(12, 12)`. Hatalar `ke` ile aynı, ek olarak `rho ≤ 0` → `ModelError`.
- `me` isteğe bağlıdır (`axial_force` / `stress` gibi); sağlamayan eleman tipi modal analizde `ModelError` verir.

### `core/assembly.py`
- `assemble_M(model, lumped: bool = False) -> sp.csr_matrix` — `(n_dof, n_dof)`, `assemble_K` ile aynı COO birleştirmesi.

### `core/modal.py`
- `ModalResult` (dondurulmuş dataclass; `core/model.py`'ye eklenmez):
  - `omega2: np.ndarray (k,)` [1/s²], artan; `omega: np.ndarray (k,)` [rad/s]; `f: np.ndarray (k,)` [Hz]
  - `modes: np.ndarray (n_dof, k)` — global DOF sırasında, tutulu DOF'larda 0, `φᵀ M φ = 1`
  - `lumped: bool`
  - `mode(model, i, node_id, dof="ux") -> float` — `i`. modun o düğüm/DOF bileşeni
- `model_mass(model) -> float` [t] — `Σ ρ V` (bar1d: `ρ A L`). `rho ≤ 0` → `ModelError`.
- `modal(model, n_modes: int, *, lumped: bool = False) -> ModalResult`
  1. `model.validate()`; 2. `K`, `M` birleştir; 3. serbest / tutulu ayrımı (çelişen BC → `ModelError`, solver ile aynı);
  4. Teori'deki çözüm yolu; 5. birimleme ve işaret kuralı.
- `effective_mass(model, result) -> np.ndarray (k, model.dim)` [t] — `Γ²`, sütunlar `ux, uy, uz` sırasında.
- Hatalar (`ModelError`): `n_modes` tamsayı değil, `< 1` veya `> n_f`; serbest DOF yok; `rho ≤ 0`; `me` sağlamayan eleman;
  Teori'deki negatif özdeğer; sonlu olmayan sonuç.

### `analiz/` (köprü paketi; dışarıya yalnız `analiz/__init__.py` adları)
- `analiz/sehim.py` (gmsh ve OCCT gerektirmez; her `dim = 3` tet4 `Model` ile):
  - `nokta_kuvveti(model, nokta, F, yaricap) -> list[int]` — Teori'deki `S`'yi seçer, her düğüme `F/|S|` için `Load`
    ekler (düğüm id'si artan, `ux, uy, uz` sırası, tam sıfır bileşen eklenmez; `mesh.add_traction` gibi modeli yerinde
    değiştirir) ve `S`'yi artan sırada döndürür.
  - `Sehim` (dondurulmuş dataclass): `dugumler: list[int]`, `u_nokta: np.ndarray (3,)` [mm], `delta: float` [mm],
    `k: float` [N/mm], `u: np.ndarray (n_dof,)`, `u_maks: float` [mm] (en büyük düğüm yer değiştirmesi büyüklüğü).
  - `kesme_sehimi(model, nokta, F, yaricap) -> Sehim` — modelin kopyasına `nokta_kuvveti` uygular, `core.solver.solve`
    ile çözer; verilen `model` değişmez.
  - Hatalar (`ModelError`): `dim ≠ 3`; `nokta` / `F` (3,) ve sonlu değil; `|F| = 0`; `yaricap ≤ 0`; yarıçapta sınır düğümü
    yok; `kesme_sehimi`'de `model.loads` boş değil (karışık yük sessizce toplanmaz); çözücü hataları aynen (mekanizma).
- `analiz/parca.py` (gmsh + OCCT):
  - `parca_modal(part, h, material, sabit, n_modes, *, lumped=False) -> tuple[Model, ModalResult]`
  - `parca_sehimi(part, h, material, sabit, nokta, F, yaricap) -> tuple[Model, Sehim]`
  - `sabit`: `mesh` tahmin fonksiyonları dizisi (ör. `[mesh.on_plane((0, 0, 0), (1, 0, 0))]`); seçilen her düğümün üç DOF'u
    `mesh.fix` ile tutulur. Ağ `mesh.tet_mesh(part, h, material)`. Hiç düğüm seçilmezse → `ModelError`
    (mesnetsiz parçanın modları istenirse `core.modal.modal` doğrudan kullanılır).

Kullanım:
```python
m, r = analiz.parca_modal(
    parca, 2.5, Material("St", 210000.0, 0.3, 7.85e-9), [mesh.on_plane((0, 0, 0), (1, 0, 0))], n_modes=6
)
m, s = analiz.parca_sehimi(
    parca,
    2.5,
    celik,
    [mesh.on_plane((0, 0, 0), (1, 0, 0))],
    nokta=(100, 5, 10),
    F=(0, 0, -400.0),
    yaricap=3.0,
)
print(r.f[0], s.delta, s.k)
```

## Kabul kriterleri
- [ ] **K1** Kütle matrisleri: bar1d ve birim köşe tet4'ünde tutarlı ve toplanmış `me` el hesabıyla tam (rel 1e-12);
  simetrik; tutarlı `me` pozitif tanımlı; her yönde `rᵀ me r = ρV` (ρAL); `rho = 0` ve `rho < 0` → `ModelError` —
  `tests/unit/test_kutle.py`
- [ ] **K2** `assemble_M` + `model_mass`: SPEC 11 kutu ağında (iç düğümleri kaydırılmış) her yön için `r_dᵀ M r_d = ρ L b h`
  ve `model_mass = ρ L b h` (rel 1e-12), tutarlı ve toplanmışta; `M` simetrik — unit
- [ ] **K3** Tek eleman ankastre–serbest çubuk: tutarlı `ω² = 3E/(ρL²)`, toplanmış `ω² = 2E/(ρL²)` (rel 1e-12) —
  `tests/benchmarks/test_modal.py::test_cubuk_*`
- [ ] **K4** Ayrık çubuk tam çözümü (Teori formülleri), `N = 10` eşit eleman: iki ucu tutulu ve ankastre–serbest,
  tutarlı ve toplanmış, **tüm** modlar (rel 1e-10) — benchmark
- [ ] **K5** Sürekli çubuğa yakınsama, ankastre–serbest `N = 100`: ilk 3 mod için tutarlı `fₙ ≥ fₙ,tam`, toplanmış `fₙ ≤ fₙ,tam`,
  ikisi de `|fₙ/fₙ,tam − 1| ≤ 1e-3` — benchmark
- [ ] **K6** Diklik ve artık: her testte `Φᵀ M_ff Φ = I` (abs 1e-9), `Φᵀ K_ff Φ = diag(ω²)` (rel 1e-8 · ω²_maks),
  `‖K φ − ω² M φ‖ ≤ 1e-8 ‖K φ‖`; tutulu DOF'larda `φ = 0`; işaret kuralı tutar — benchmark
- [ ] **K7** Yoğun ve Lanczos yolları aynı sonucu verir: `n_f > 300` bir tet4 modelinde `modal` ile testin kendi
  `scipy.linalg.eigh(K_ff, M_ff)` referansı ilk 6 frekansta rel 1e-8; aynı ağın mod uzayı izdüşümleri eşleşir — benchmark
- [ ] **K8** Mesnetsiz tet4 kutu (`n_f > 300`, Lanczos yolu): ilk 6 `ω² ≤ 1e-8 · ω₇²`, 7. mod pozitif; ilk 6 modun
  uzayı rijit cisim uzayıyla (3 öteleme + 3 dönme) aynı (izdüşüm farkı ≤ 1e-6) — benchmark
- [ ] **K9** Konsol kiriş (Teori tablosu, tutarlı kütle, `k = 2, 4, 8`):
  - `f₁` ve `f₂` her inceltmede **azalır** ve her `k`'da `f₁ ≥ 0.99 · f₁,EB`
  - `e_k = f₁/f₁,EB − 1`: `e_2 / e_4 ≥ 2.5` ve `e_4 / e_8 ≥ 2.5`
  - `k = 8`: `f₁ / f₁,EB ≤ 1.04` ve `f₂ / f₁,EB ≤ 1.06`
  - İlk 8 mod içinde x yönü etkin kütlesi en büyük mod (eksenel mod), `k = 4`: `|f/f_ax − 1| ≤ 0.01`
  - İlk iki modun y yönü etkin kütleleri toplamı / `ρV`, `k = 4`: `|… − 0.6131| ≤ 0.005`
  - Toplanmış kütle her `k`'da `f₁,toplanmış ≤ f₁,tutarlı`
  - `k = 8` alt testleri `@pytest.mark.slow` — `test_konsol_*`
- [ ] **K10** Değişmezlikler (küçük tet4 kutu): `ρ → 4ρ` iken `f → f/2`; geometri `s` katına büyütülünce `f → f/s`;
  model rastgele bir `R` ile döndürülünce frekanslar aynı (rel 1e-9) — benchmark
- [ ] **K11** `effective_mass`: tüm modlar istenince (`n_modes = n_f`) her yönde toplam `= r_dᵀ M_ff r_d` (rel 1e-9);
  değerler `≥ 0`; boyut `(k, dim)` (bar1d'de `(k, 1)`) — benchmark
- [ ] **K12** Hatalar `ModelError`: `n_modes = 0`, `n_modes > n_f`, tamsayı olmayan `n_modes`, serbest DOF'u olmayan model,
  `rho = 0` malzeme, `me` sağlamayan (test içinde kaydı yapılan sahte) eleman tipi, çelişen BC — unit
- [ ] **K13** `analiz.kesme_sehimi`, SPEC 11 konsolunda (`k = 2, 4, 8`), `nokta = (L, b/2, h/2)`, `F = (0, 0, −1000)`:
  - `yaricap` küçük (yalnız merkez düğüm) ve büyük (uç yüzün tamamı): `δ` her inceltmede **artar**, `δ < δ_T`
  - `k = 8`, uç yüzün tamamı: `δ / δ_T ≥ 0.90` (ön hesap 0.930; `slow`)
  - `δ` ve `u`, aynı düğüm yükleri elle eklenip `solve` ile çözülen modelle aynı (rel 1e-12); `Fᵀu = |F| δ`;
    `k = |F|/δ`; verilen model değişmemiş (yükler boş) — `tests/analiz/test_sehim.py`
- [ ] **K14** `analiz.nokta_kuvveti`: bileşke `F` (abs 1e-12 · |F|); yalnız sınır düğümleri seçilir (iç düğüm yarıçap içinde
  olsa bile); Teori'deki tüm `ModelError` durumları (yarıçapta düğüm yok, `|F| = 0`, `yaricap ≤ 0`, `dim ≠ 3`, sonlu olmayan
  girdi, `kesme_sehimi`'de dolu `model.loads`) — analiz
- [ ] **K15** `analiz/parca.py` (`@pytest.mark.occt`, gmsh yoksa atlanır): `geometry` ile `100 × 10 × 10` kutu `Part`, `h = 2.5`,
  `x = 0` yüzü sabit: `parca_modal` `0.99 ≤ f₁ / f₁,EB ≤ 1.35`; `parca_sehimi` uç yüz merkezinde `0.6 ≤ δ / δ_T < 1.0`;
  `sabit` hiçbir düğüm seçmiyorsa `ModelError` — `tests/analiz/test_parca.py`
- [ ] **K16** `examples/45_modal_cubuk.json` (10 elemanlı ankastre–serbest çelik çubuk, `rho` dolu) `Model.from_json` +
  `modal(m, 3)` ile K4 değerlerini veriyor — benchmark
- [ ] Tüm testler yeşil: `pytest --uygulanmamis-hata` → 0 failed, `ruff check .` ve `ruff format --check .` temiz

## Kapsam dışı
- Kesme kuvvetinin hesabı (SPEC 32, Kienzle). 32 birleşince `cam` hareket listesinden `F(t)` alıp burada çağıran ek
  (45b) ayrıca yazılır.
- Zorlanmış titreşim, frekans tepki fonksiyonu (FRF), sönüm, tırlama (chatter) kararlılık diyagramı (Dalga 6)
- Ön gerilmeli / dönen (gyroscopic) modal, burkulma, doğrusal olmayan analiz
- Fikstür ve parça temasının modellenmesi (sabit yüz = tam ankastre)
- Kesme kuvveti momentinin düğümlere dağıtımı (eşit bölme yeterli; `r` küçük tutulur)
- CalculiX `*FREQUENCY` çapraz kontrolü (SPEC 13 `fileio/calculix.py` birleşince küçük ek)
- Tezgah ekranı (analiz ekranı yol haritasında ayrı satır)
- Performans: eleman döngüsü Python'da kalabilir; yalnız `k = 8` testleri `slow`
