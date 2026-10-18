# SPEC 01 — 1D çubuk elemanı ve doğrusal statik çözücü

## Amaç
Eksenel yüklü 1D çubuk sistemlerini çözen ilk uçtan uca zincir:
`Model (JSON) -> eleman matrisleri -> global K, F -> K u = F -> yer değiştirme, tepki, gerilme`.
Sonraki tüm elemanlar (kafes, üçgen, tetrahedron) bu iskeleti kullanacak.

## Teori
2 düğümlü çubuk, düğüm başına 1 DOF (ux). Boy `L = |x2 - x1|`.

Eleman rijitlik matrisi:
```
ke = (E A / L) * [[ 1, -1],
                  [-1,  1]]
```
Eksenel kuvvet (pozitif = çekme):  `N = (E A / L) * (u2 - u1)`
Gerilme: `sigma = N / A`

Global sistem: `K u = F`. DOF'lar serbest (f) ve tutulu (c) diye ayrılır:
```
K_ff u_f = F_f - K_fc u_c
R = K u - F            (tepkiler, sadece tutulu DOF'larda anlamlı)
```
Kaynak: Logan, *A First Course in the Finite Element Method*, Bölüm 2–3.

## Dosyalar
- Uygulanacak: `core/elements/bar1d.py`, `core/assembly.py`, `core/solver.py`, `core/post.py`
- Dokunulmayacak: `core/model.py` (arayüz sabit), `tests/**`

## Arayüz
- `bar1d.length(element, model) -> float` — L <= 1e-12 ise `ModelError`
- `bar1d.ke(element, model) -> np.ndarray (2x2)`
- `bar1d.dofs(element, model) -> list[int]` — `model.dof_index(node, "ux")` ile, element.nodes sırasında
- `bar1d.axial_force(element, model, u) -> float`
  - Düğüm sırası tersse (x2 < x1) işaret yine "çekme = pozitif" kalmalı: uzama = (u_sağ - u_sol)
- `assembly.assemble_K(model) -> scipy.sparse.csr_matrix` — eleman tipi `core.elements.get(e.type)` ile seçilir
- `assembly.assemble_F(model) -> np.ndarray` — aynı DOF'a gelen yükler TOPLANIR
- `solver.solve(model) -> Result`
  - Önce `model.validate()`
  - Tekil / kötü koşullu K_ff (ör. mesnet yok) -> `ModelError`. Kontrol: `scipy.sparse.linalg.spsolve` sonucu sonlu değilse veya `MatrixRankWarning` / `RuntimeError` oluşursa; ya da K_ff boyutu küçükken (yoğun) `np.linalg.cond` > 1e12.
  - `Result.reactions`: boyut n_dof, serbest DOF'larda 0
- `post.element_forces(model, u)`, `post.element_stresses(model, u)` -> `{eleman_id: değer}`

## Kabul kriterleri
- [ ] K1 Eleman matrisi tam değer, simetrik, rijit mod sıfır enerji, özdeğerler {0, 2EA/L} — `tests/unit/test_bar_element.py`
- [ ] K2 Uç yüklü çubuk δ = FL/EA, 1–50 eleman için — `test_B1_*`
- [ ] K3 Kademeli çubuk (iki malzeme, iki kesit) — `test_B2_stepped_bar`
- [ ] K4 İki ucu ankastre hiperstatik çubuk, tepkiler — `test_B3_*`
- [ ] K5 Yayılı yük (tutarlı düğüm yükleri) u(x) = q(Lx − x²/2)/EA — `test_B4_*`
- [ ] K6 Zorlanmış yer değiştirme — `test_B5_*`
- [ ] K7 Global denge, K özellikleri, F toplama, düğüm sırası bağımsızlığı — genel testler
- [ ] K8 Mekanizma -> ModelError — `test_mechanism_raises`
- [ ] K9 `examples/01_cubuk.json` çözülüyor — `test_example_json`
- [ ] Tüm testler yeşil: `pytest` -> 0 failed

## Kapsam dışı
- 2D/3D, açılı çubuk (SPEC 02: kafes)
- Sıcaklık yükü, yayılı yükün otomatik dönüşümü
- Görselleştirme (isteğe bağlı küçük bir `viz/plot_bar.py` SPEC 01b olarak ayrı yapılabilir)
