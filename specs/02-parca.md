# SPEC 02 — Katı parça: kodla basit parça, kütle özellikleri, STEP/STL

## Amaç
CAM (05, 06) ve montajın (07, 09) ihtiyaç duyduğu en küçük katı altyapıyı kurmak: kodla blok / silindir
oluşturup delik, cep ve pah işlemek; hacim, alan, ağırlık merkezi, kütle ve atalet tensörünü analitik
değerle doğrulanmış şekilde vermek; STEP ve STL ile dışa / içe aktarmak; görüntüleme ve STL için üçgen ağı üretmek.

## Teori
Katı modelleme çekirdeği OCCT'dir (build123d üzerinden); B-rep ve boolean işlemleri bizim değil. Bizim işimiz
CAM'e uygun, sade bir parça API'si ve her sonucun **analitik değerle** doğrulanması.

Koordinat kuralı (CAM alışkanlığı): `block(a, b, c)` min köşesi orijinde, `x ∈ [0,a]`, `y ∈ [0,b]`, `z ∈ [0,c]`.
"Üst yüz" = parçanın `zmax` düzlemi; delik ve cep üstten −Z yönünde işlenir (takım ekseni +Z).

Hacim ve alan (el hesabı):
- Blok: `V = a·b·c`, `S = 2(ab + bc + ca)`
- Silindir (yarıçap r, boy h): `V = π r² h`, `S = 2π r² + 2π r h`
- Kör delik (çap d, derinlik t): kaldırılan `ΔV = π d² t / 4`; alan değişimi `ΔS = π d t` (yan) (taban dairesi üst yüzden çıkan daireyi yerine koyar)
- Boydan boya delik (blok yüksekliği c): `ΔV = π d² c / 4`, `ΔS = π d c − 2·π d²/4`
- Köşe yarıçaplı dikdörtgen cep (w × l, köşe r, derinlik t): taban alanı `A_c = w·l − (4 − π) r²`, `ΔV = A_c · t`;
  çevre `P = 2(w + l) − (8 − 2π) r`, `ΔS = P · t`
- Üst kenarlara eşit mesafeli pah d (blok a × b): her kenar `d²/2 · L` üçgen prizma kaldırır; iki pahın köşede
  kesiştiği bölge `∫₀^d (d − w)² dw = d³/3` iki kez sayılır. 4 köşe için
  `ΔV = (d²/2)·2(a + b) − 4·d³/3`  (el hesabı; OCCT ile ön deneme: a=100, b=60, d=3 → 1404.000 mm³)

Ağırlık merkezi: `x̄ = (Σ Vᵢ x̄ᵢ) / Σ Vᵢ` (kaldırılan hacimler eksi işaretle). Kütle `m = ρ V`.
Atalet tensörü, ağırlık merkezine göre, global eksenlerde: `I = ∫ ρ (|r|² 𝟙 − r rᵀ) dV`, `r = x − x̄`.
- Blok: `Ixx = m(b² + c²)/12`, `Iyy = m(a² + c²)/12`, `Izz = m(a² + b²)/12`, çarpım terimleri 0
- Silindir (eksen Z): `Izz = m r²/2`, `Ixx = Iyy = m(3r² + h²)/12`

Birimler N – mm – MPa ile tutarlı: ρ [t/mm³] (çelik 7.85e-9), m [t], I [t·mm²]. Dönüşüm yok.

Üçgen ağı hacmi (diverjans teoremi): `V = (1/6) Σ (p₁ · (p₂ × p₃))`, dışa bakan üçgenlerle.
Silindirde ağ içe çizilmiş çokgen olduğundan `V_ağ < π r² h`; `n` kenarlı çokgen için
`V_ağ = (n/2) r² sin(2π/n) h`. Tolerans küçüldükçe hata azalır.

Kaynaklar: build123d ve OCCT belgeleri (BRepGProp, BRepMesh); Beer & Johnston, *Vector Mechanics for
Engineers: Statics*, Ek B (atalet momentleri); Mortenson, *Geometric Modeling*, Bölüm 9 (kütle özellikleri).

## Dosyalar
- Yeni: `geometry/features.py` (blok, silindir, delik, cep, pah), `geometry/props.py` (kütle özellikleri),
  `geometry/mesh.py` (üçgen ağı, STL okuma), `tests/geometry/test_features.py`, `tests/geometry/test_props.py`,
  `tests/geometry/test_mesh_stl.py`, `tests/geometry/test_step.py`, `durum/02-parca.md`
- Değişecek: `geometry/__init__.py` (sadece docstring / dışa açılan adlar)
- Dokunulmayacak: `geometry/part.py` (arayüz sabit), `pyproject.toml`, diğer paketler. Yeni bağımlılık yok.

Tüm testler `@pytest.mark.occt` işaretli. Hiçbir işlem verilen `Part`'ı değiştirmez; her zaman yeni `Part` döner.
Geçersiz girdi ve OCCT başarısızlığı → `geometry.part.GeometryError` (sessiz hata yok).

## Arayüz

### `geometry/features.py`
- `block(a, b, c, name="blok") -> Part` — min köşe orijinde. `a, b, c > 0` değilse `GeometryError`.
- `cylinder(r, h, name="silindir") -> Part` — taban merkezi orijinde, eksen +Z. `r, h > 0`.
- `hole(part, x, y, d, depth=None) -> Part` — üst yüzden (`zmax`) −Z yönünde silindirik delik, eksen (x, y).
  `depth=None` → boydan boya. `d <= 0`, `depth <= 0`, `depth > yükseklik` veya delik parçadan malzeme
  kaldırmıyorsa (ΔV ≤ 1e-9) → `GeometryError`.
- `pocket(part, x, y, w, l, depth, r=0.0) -> Part` — üstten dikdörtgen cep, merkez (x, y), X boyu w, Y boyu l,
  köşe yarıçapı r (`0 <= r <= min(w, l)/2`). `depth >= yükseklik` (cep deler) veya `depth <= 0` → `GeometryError`.
- `chamfer_top(part, d) -> Part` — üst yüzün (`zmax`) tüm kenarlarına eşit mesafeli pah.
  `d <= 0` veya OCCT pahı oluşturamazsa (ör. d kenar boyundan büyük) → `GeometryError`.

### `geometry/props.py`
- `@dataclass(frozen=True) MassProps(V: float, m: float, com: np.ndarray, I: np.ndarray)` — `I` (3,3) simetrik, ağırlık merkezine göre
- `mass_props(part, rho) -> MassProps` — `rho <= 0` → `GeometryError`
- `principal_moments(mp) -> tuple[np.ndarray, np.ndarray]` — artan sıralı asal momentler (3,) ve sütunları asal eksen olan (3,3) matris

### `geometry/mesh.py`
- `tessellate(part, tol=0.01) -> tuple[np.ndarray, np.ndarray]` — köşeler `V (n,3)` float, üçgenler `T (m,3)` int,
  dışa bakan sırada; ağ kapalı (her kenar tam iki üçgende). `tol <= 0` → `GeometryError`.
- `mesh_volume(V, T) -> float` — diverjans teoremi formülü (OCCT'siz, saf numpy)
- `read_stl(path, name=None) -> Part` — STL üçgenlerini dikip kapalı katıya çevirir. Dosya yok, ağ kapalı değil
  veya hacim ≤ 0 → `GeometryError`.

STEP için `Part.to_step` / `Part.from_step` (SPEC 00) kullanılır; bu SPEC onları işlenmiş parçalarla doğrular.

## Kabul kriterleri
- [x] K1 `block`, `cylinder`: V, S, ağırlık merkezi, sınır kutusu analitikle rel 1e-6; geçersiz boyut hata — `tests/geometry/test_features.py`
- [x] K2 `hole`: kör ve boydan boya delikte ΔV ve ΔS formülle rel 1e-6; ağırlık merkezi kaydırması formülle 1e-6 mm; parça dışı / geçersiz delik hata — `test_features.py`
- [x] K3 `pocket`: r = 0 ve r > 0 için ΔV = A_c·t ve ΔS = P·t rel 1e-6; delen cep ve büyük r hata — `test_features.py`
- [x] K4 `chamfer_top`: blokta ΔV = (d²/2)·2(a+b) − 4d³/3 rel 1e-6; aşırı büyük pah hata — `test_features.py`
- [x] K5 İşlemler girdiyi değiştirmiyor (girdi hacmi aynı kalıyor); zincir (blok → delik → cep → pah) hacmi tek tek ΔV toplamıyla tutuyor — `test_features.py`
- [x] K6 `mass_props`: blok ve silindirde m, ağırlık merkezi, I tensörü rel 1e-6; delikli blokta paralel eksen teoremiyle el hesabı; `principal_moments` döndürülmüş blokta değişmez — `tests/geometry/test_props.py`
- [x] K7 `tessellate`: blok ağında `mesh_volume = abc` rel 1e-9, ağ kapalı ve dışa bakan; silindirde tol küçüldükçe hata azalıyor ve `V_ağ ≤ π r² h` — `tests/geometry/test_mesh_stl.py`
- [x] K8 STL: delikli blok `to_stl` → `read_stl`; düz yüzlü blokta hacim rel 1e-6, silindirik delikte üçgen ağı hacmiyle rel 1e-6; açık ağ ve eksik dosya hata — `test_mesh_stl.py`
- [x] K9 STEP: işlenmiş parça (delik + cep + pah) STEP gidiş-dönüşünde V, S, ağırlık merkezi, sınır kutusu rel 1e-6 — `tests/geometry/test_step.py`
- [x] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` temiz

## Kapsam dışı
- `geometry/part.py` arayüz değişikliği (gerekirse ayrı arayüz PR'ı)
- Genel boolean API (`cut / fuse / common`) ve girişim hacmi — SPEC 09
- Yuvarlatma (fillet), eğimli / açılı delik, yan yüzden işleme, dişli delik, havşa
- Özellik ağacı, eskiz ve eskiz kısıt çözücü (yol haritası: "İhtiyaç olursa")
- Parçadan işleme özelliği tanıma (düz yüz, cep, delik) — SPEC 05
- Montaj STEP'i, çok parçalı STEP — SPEC 07
- Ekrana çizim: `viz/` bu SPEC'te yazılmaz; `tessellate` ileride `viz/`'in kullanacağı veriyi verir
- gmsh ile hacim ağı — SPEC 12
