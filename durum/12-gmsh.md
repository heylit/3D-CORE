# DURUM — SPEC 12 Parçadan tetrahedron ağı (gmsh) ve sınır yükleri

Dal: `claude/project-thread-eioc8y` · Oturum: bulut thread "FEM ağ ve gerilme analizi (12–13)"

## Sıradaki adım
Ayrı oturumda testler (bu dalın üstünde), sonra burada cherry-pick ve kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18 — onay ve iskelet**
- SPEC 12 ve 13 metinleri kullanıcı onaylı (10:38 UTC, proje sohbetinde yazılı).
- `mesh/gmsh_ag.py`, `mesh/secim.py`, `mesh/yukler.py`: `NotImplementedError` iskeletleri; `mesh/__init__.py` dışa açılan adlar.

**2026-10-18 — SPEC taslağı**
- `specs/12-gmsh.md` yazıldı: Part → STEP → gmsh OCC → tet4 `Model`; geometrik seçim (`on_plane`, `on_cylinder`),
  `fix`, `add_traction`, `add_pressure`; K1–K12. Yeni veri modeli yok, çıktı `core.model.Model`.
- Eşikler karalama hesabıyla (gmsh 4.15.2, repoya girmedi) ayarlandı: silindir hacim hatası %1.35 / %0.72 / %0.19
  (`h = 5, 2.5, 1.25`); düzensiz ağda çekme tam (σ hatası 4e-12); Lamé iç yüzey `u_r` hatası %6.1 / %1.9 / %0.64
  (`h = 4, 2, 1`), eleman `σ_θ` RMS hatası %9.6 → %5.3; `Refine` küresinde ortalama kenar 1.33 h_yerel; iki çağrı aynı ağı verdi.
- Delikli plaka Kt (yol haritasında 12'deydi) SPEC 13'e taşındı: düğüm gerilmesi olmadan eleman gerilmesinin
  en büyüğü gürültülü (3.15–3.23); düğüm ortalamasıyla 3.03.
- gmsh pip tekerleği Linux'ta `libglu1-mesa libxcursor1 libxinerama1 libxft2` ister; CI ve bulut kurulumu için ayrı PR gerekli.

## Açık sorular
_(yok)_ — CI'da gmsh kurulumu PR #57 ile `main`'de.
