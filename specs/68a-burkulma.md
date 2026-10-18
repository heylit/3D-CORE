# SPEC 68a — Doğrusal burkulma (geometrik rijitlik + özdeğer) (Dalga 7, A10)

> Durum: **onaylı** (kullanıcı, 2026-10-18 16:19, önerilen cevaplarla; mesaj cmsg_01DTo5iWYb5RBUWgjk6xu1sGJGTUdh2rjZ3topbRjRQuit). Kullanıcı kararı (2026-10-18 11:07): ek analizlerin hepsi yapılacak. Bu dosya A10'un ilk
> parçasıdır; geçici ısıl 68b, harmonik 68c, yorulma 68d'dedir.
> Bağımlılık: SPEC 11 (tet4), 45 (özdeğer altyapısı, `analiz/` deseni), 67a (tet10), 67b (yüz yükü).

## Amaç
İnce ve narin parçalar (uzun pim, ince cidarlı boru, uzun matkap ya da bara, ince et) akma gerilmesine ulaşmadan
burkulabilir. Doğrusal statik analiz bunu göremez. Bu SPEC şunları ekler:
- verilen bir yük durumu için **kritik yük çarpanı** `λ_cr`: yük `λ_cr` katına çıkınca yapı burkulur
- burkulma mod şekli

Yöntem klasik doğrusallaştırılmış (Euler) burkulmadır: önce statik çözüm, sonra geometrik rijitlik, sonra özdeğer. Kendi
çözücümüzle numpy + scipy kullanılarak yapılır.

## Teori
1. Referans yük `F` altında statik çözüm `K u0 = F`, eleman gerilmeleri `σ0`.
2. Eleman geometrik rijitliği (başlangıç gerilmesi matrisi):
   ```
   Kg_e = ∫ Gᵀ Ŝ G dV
   ```
   - `G (9 × 3n)`: yer değiştirme gradyanı `∂u_i/∂x_j`'yi düğüm DOF'larından veren matris.
   - `Ŝ = diag(S, S, S)`: `S` 3×3 Cauchy gerilme tensörü `σ0`.
   - tet4'te `G` ve `σ0` sabittir, `Kg_e = V Gᵀ Ŝ G`.
   - tet10'da 4 noktalı Gauss kuralı kullanılır (`σ0` doğrusal, `G` doğrusal; çarpım 4. derecedir, kural tam değildir ama
     CalculiX C3D10 ile aynıdır).
3. Özdeğer problemi:
   ```
   (K + λ Kg) φ = 0
   ```
   Fiziksel kök en küçük **pozitif** `λ`'dır. `Kg` belirsiz işaretlidir. Çözüm yolu: tutulu DOF'lar ayrılır,
   `scipy.sparse.linalg.eigsh(Kg, k, M=K, sigma=…)` yerine kararlı biçim `K φ = μ (−Kg) φ` kullanılır, `μ = λ` olur.
   Shift-invert ile `σ = 0` civarında, `K` pozitif tanımlı olduğu için `eigsh(-Kg, M=K, which="LA")` ile `1/λ`'nin en
   büyük değerleri bulunur, sonra `λ = 1/ν` çevrilir. Seçim kodda belgelenir ve SPEC 45'in çözüm yolu deseni izlenir.
4. Negatif `λ`, yük yönü tersine çevrilince burkulma demektir; ayrı raporlanır, atılmaz.

Kapalı formüller (Euler, kare kesit `b × b`, `I = b⁴/12`):
- **Ankastre–serbest** (konsol), uçta eksenel basma: `P_cr = π² E I / (4 L²)`
- Daha yüksek modlar `P_n = (2n − 1)² P_1`
- Kare kesitte her mod iki kez görünür (x ve y yönünde eşit `λ`)

Sayısal örnek (`b = 10`, `L = 200`, `E = 210000`): `P_cr = 10 794.88` N. Etkin boy `2L = 400`, narinlik
`λ_s = 2L/i = 138.6`. Bu yüzden kayma etkisi ‰2 altındadır ve Euler 3B katıyla karşılaştırılabilir.

Kaynak: Timoshenko–Gere, *Theory of Elastic Stability*, bölüm 2; Cook, Malkus, Plesha, Witt, *Concepts and Applications
of FEA*, 4. baskı, bölüm 18.

## Dosyalar
- **Yeni:**
  - `core/burkulma.py`
  - `analiz/burkulma.py`
  - `tests/unit/test_kg.py`, `tests/benchmarks/test_burkulma.py`, `tests/analiz/test_burkulma_parca.py`
  - `tests/reference/test_ccx_buckle.py`
  - `specs/68a-burkulma.md`, `durum/68a-burkulma.md`
- **Değişecek:**
  - `core/elements/tet4.py` ve `tet10.py`: isteğe bağlı `kg(element, model, sigma0)`
  - `core/elements/__init__.py` (sözleşme)
  - `core/assembly.py`: yeni `assemble_Kg(model, sigma0)`
  - `analiz/__init__.py`
  - `fileio/calculix.py`: `*BUCKLE` adımı
- **Dokunulmayacak:** `core/model.py`, `core/solver.py`, `core/modal.py`.

## Arayüz
```python
# core/burkulma.py
@dataclass(frozen=True)
class BucklingResult:
    lam: np.ndarray        # (k,) yük çarpanları, |λ| artan; negatifler dahil
    modes: np.ndarray      # (n_dof, k), max |φ| = 1, tutulu DOF'ta 0
    u0: np.ndarray         # referans statik çözüm
def buckling(model: Model, n_modes: int = 4) -> BucklingResult: ...
    # model.loads referans yüktür; yük yoksa, serbest DOF yoksa ya da n_modes geçersizse → ModelError
    # bulunan bütün λ sonsuz ya da tanımsızsa (gerilmesiz model) → ModelError

# analiz/burkulma.py
def parca_burkulmasi(part, h, malzeme, *, order=2, sabit, basinc=(), kuvvet=(), n_modes=4)
    -> tuple[PartMesh, BucklingResult]: ...      # 67b parca_dayanimi ile aynı yük ve mesnet dili
```

### Ayrıntı (kodlayıcı, iskelet aşaması)
- `sigma0`: eleman id → gerilme sözlüğü `dict[int, np.ndarray]`. tet4'te değer `(6,)` Voigt
  `[xx, yy, zz, xy, xz, yz]` [MPa] (`tet4.stress` ile aynı düzen; kayma bileşenleri tensör bileşenidir, `γ` değil).
  tet10'da (67a sonrası) Gauss noktası başına `(4, 6)`.
- `tet4.kg(element, model, sigma0_e) -> np.ndarray (12 × 12)`: `sigma0_e` o elemanın `(6,)` gerilmesi; DOF sırası `ke` ile aynı.
- `assemble_Kg(model, sigma0) -> scipy.sparse.csr_matrix (n_dof × n_dof)`: `kg` sağlamayan eleman tipi ya da
  `sigma0`'da bulunmayan eleman → `ModelError`.
- `buckling` referans gerilmeyi `core.solver.solve` sonucundan değil, `u0` ve `tet4.stress`'ten kurar (solver dokunulmaz).

## Kabul kriterleri
- [ ] **K1** `kg`:
  - simetrik
  - `σ0` ile doğrusal
  - rijit öteleme vektörleri `Kg`'nin çekirdeğindedir (`Kg · t = 0`, abs 1e-12·‖Kg‖)
  - düzgün hidrostatik `σ0 = p I` için `Kg_e = p V Gᵀ G` olur (göreli 1e-12)
- [ ] **K2** Çubuk elemanla çapraz kontrol: tek tet4 yerine, bilinen tek elemanlı bir sonuç kullanılır. Çekmede çubuk
  için enine `Kg` bileşeni `P/L` ile tutarlıdır. Bunun için `2×2×20` Kuhn ağında enine yer değiştirme alanına göre
  Rayleigh oranı `φᵀ Kg φ / (P/L ∫ (w')² dx)` → 1 (göreli %1).
- [ ] **K3** Konsol burkulması (`10 × 10 × 200`, alt yüz tam tutulu, üst yüze toplam `P = 1000` N düzgün basma):
  - tet10, `k = 2` Kuhn ağı: `λ_1 · P` `10 794.88`'e %1 içinde.
  - `λ_1` ve `λ_2` arasında göreli fark 1e-3'ten küçük (kare kesit, ağ simetrik Kuhn bölümü).
  - `λ_3 / λ_1` 9'a %3 içinde (ikinci mod çifti).
  - tet4'te `λ_1` ağ inceldikçe **yukarıdan** azalarak yaklaşır (`k = 2, 4, 8`).
- [ ] **K4** Mod şekli: K3'te birinci modun eksen boyunca enine yer değiştirmesi `1 − cos(π z / 2L)` şekline benzer.
  Normlanmış farkın RMS'i 0.02'den küçüktür.
- [ ] **K5** İşaret: K3'te yük çekmeye çevrilince bütün `λ` negatif olur. `λ_1`, `−10 794.88/P`'ye %1 içinde eşittir
  (simetri); sonuç atılmaz, raporlanır.
- [ ] **K6** Hatalar (`ModelError`):
  - yük yok
  - `n_modes = 0`
  - mesnet yok (tekil `K`)
  - `kg` sağlamayan eleman tipi (`bar1d`)
- [ ] **K7** CalculiX (`*BUCKLE`, C3D10, aynı ağ; `ccx` yoksa atlanır): ilk 4 `λ` göreli 1e-4 içinde eşit.
- [ ] **K8** Parça köprüsü (OCCT): 67b dilinde `FaceRef` ile alt yüz sabit, üst yüze basınç verilir; K3 ile aynı `λ_1`
  çıkar (gmsh ağı, %2).
- [ ] **K9** `core/burkulma.py` numpy, scipy ve `core` dışında import etmez. `ruff` temiz; `slow` işaretleri doğru.

## Bağımlılık
- SPEC 11, 13, 45 (birleşti).
- 67a: tet10 ve K3 için; tet4 kısımları 67a'yı beklemez.
- 67b: K8 için.

## Kararlar (kullanıcı onayı 2026-10-18 16:19; önerilen cevaplar kabul edildi)
1. **Yük çarpanına ek olarak "burkulma emniyeti" `n_b = λ_cr` 67b'nin `Dayanim` raporuna eklensin mi?** Karar: evet;
   ayrı alan olarak, statik emniyetle karıştırılmadan.
2. **Kusurlu (imperfection) doğrusal olmayan burkulma?** Karar: hayır: büyük şekil değişimi gerektirir, 70 (CalculiX
   köprüsü) kapsamıdır.

## Kapsam dışı
- Doğrusal olmayan ve ardıl burkulma, kusur hassasiyeti: 70.
- Kabuk elemanlar (ince levha burkulması katı tet10 ile yapılır; kalınlık boyunca en az 2 eleman önerilir, belgelenir).
- Yorulma ve dinamik kararlılık.
