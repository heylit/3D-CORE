# SPEC 20 — Torna takım yolu: alın, boy, kaba çevrim, ince profil, kanal, diş, burun yarıçapı telafisi

## Amaç
Dönel bir parçanın yarı kesit profilinden (XZ düzleminde doğru + yay zinciri) torna için doğrulanmış takım yolları
(`cam.model.Toolpath`, `G18`, `G95`) üretmek: alın tornalama, boy tornalama, boyuna kaba çevrim (Fanuc `G71` tip I mantığı),
burun yarıçapı telafili ince profil, dalarak kanal açma ve diş çekme (Fanuc `G76` paso derinlikleri). Telafi CAM
tarafında yapılır: yol, takımın **hayali uç noktasının** yoludur. Bu SPEC sadece hareket listesi üretir; G-code'a çevirmez (SPEC 21).

## Teori

### Koordinatlar ve profil
- İş mili ekseni Z, X radyal ve **yarıçaptır** (`cam/model.py`, SPEC 00 Ek 2). Ön uç büyük `z` (ayna `−Z` tarafında).
- Profil `cam.profile.Profile` ile verilir, koordinatlar **`(u, v) = (z, x)`**. Bu düzende saat yönü tersi yay
  (`ccw=True`) `G18`'de `G3`'tür (Z'den X'e dönüş); hareketin `center` alanı `(x, z)` sırasıyladır (model kuralı).
- Torna profili **açık** bir zincirdir ve **ön uçtan arkaya** gezilir: `orient` başlangıç `z`'si bitişinkinden küçükse
  profili ters çevirir. Profilin her noktasında `x ≥ −TOL`; kapalı profil veya eksenin altına inen profil → `CamError`.
- **Taraf** (`side`): `"dis"` dış çap işleme (malzeme profilin altında, `−X` tarafında), `"ic"` iç çap işleme
  (malzeme profilin üstünde, delik içinde). Dışta, profil ön→arka gezilirken malzeme yönün **solunda**, boşluk
  **sağında** kalır; birim teğet `t = (t_z, t_x)` için boş taraf normali `n = (t_x, −t_z)`.
- **İç işlemler dış işlemlerin aynasıdır**: girdi `x → −x` ile aynalanır (yaylar `ccw` değiştirir, uç numarası
  aşağıdaki tabloyla aynalanır, iç çap `d/2` yüzey yarıçapı `−d/2` olur), dış algoritma çalışır, sonuç geri aynalanır.
  Bu yüzden aşağıdaki kurallar dış taraf için yazılmıştır; iç tarafta `X_s = −d/2` ile aynalanmış olarak geçerlidir.

### Hayali uç ve burun yarıçapı telafisi
Burun dairesi merkezi `C`, burun yarıçapı `r`. Takım `X` ve `Z`'de burun dairesine teğet iki doğrunun kesiştiği
**hayali uç** `P` ile ölçülür (Fanuc uç numarası `T`):

`P = C + q_T`, `q_T = r · (s_z, s_x)` (bileşenler `(z, x)` sırasında)

| T | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 0, 9 |
|---|---|---|---|---|---|---|---|---|---|
| `(s_z, s_x)` | (+1, +1) | (−1, +1) | (−1, −1) | (+1, −1) | (+1, 0) | (0, +1) | (−1, 0) | (0, −1) | (0, 0) |

Kural: 1–4, `(z, x)` düzleminin I–IV. bölgeleri; 5 `+Z`, 6 `+X`, 7 `−Z`, 8 `−X`; 0 ve 9 burun merkezi.
Tipik: dış tornalama 3, iç tornalama 2. Aynalama (`x → −x`): 1↔4, 2↔3, 6↔8; 5, 7, 0, 9 değişmez.
Kaynak: Fanuc Series 0i-TF Operatör El Kitabı, "Imaginary tool nose direction"; Smid, *CNC Programming Handbook*, takım burun yarıçapı telafisi bölümü.

Burun merkezi yolu, profilin boş tarafa `ρ` kadar ofsetidir (`ρ = r + δ`, `δ` ince talaş payı, ince profilde `δ = 0`):
- **Doğru**: `n` yönünde `ρ` kaydırılmış doğru. Hayali uç yolu bu doğrunun `q_T` kaydırılmışı, yani profil doğrusuna paralel
  ve `δ_P = ρ·n + q_T` kadar kaydırılmış doğrudur. Eğimi `m = dx/dz` olan doğruda sabit `z`'de `X` kayması
  `ΔX = δ_P,x − m·δ_P,z`, sabit `x`'te `Z` kayması `ΔZ = δ_P,z − δ_P,x / m`.
  - Silindir (`t = (−1, 0)`) ve alın (`t = (0, +1)`), `T = 3`: kayma doğrunun kendi üzerinde; `P` yolu profil doğrusunun **kendisi**.
  - Koni, `T = 3`, `δ = 0`, `x` arkaya doğru artan, yarım açısı `α` (doğru ile Z ekseni arası, `0 < α < 90°`):
    `ΔX = −r · (1 − tan(45° − α/2))`, `ΔZ = −r · (1 − tan(α/2))` (Smid'deki çap formülleri `2·ΔX`).
- **Yay** (merkez `c`, yarıçap `R`): burun merkezi yolu merkezi `c` olan yay; `ccw` (dışbükey, boş taraf dışarıda)
  `R + ρ`, `cw` (içbükey) `R − ρ`. Hayali uç yolu merkezi `c + q_T`, aynı yarıçaplı yay.
- **Köşeler** (gelen teğet `t₁`, giden `t₂`, `k = t₁ × t₂ = t₁,z·t₂,x − t₁,x·t₂,z`): `k > TOL` (sola dönüş, dışbükey köşe) →
  burun köşenin etrafında döner: köşe noktası `V` merkezli `ρ` yarıçaplı `ccw` yay eklenir. `k < −TOL` (içbükey köşe) →
  komşu ofset parçaları kesiştirilir ve kesişimden budanır (keskin köşe). Teğet köşede ek yok.
- **Budama** (SPEC 03'teki ham ofset + budama yönteminin açık zincir hâli): ofset yarıçapı `R − ρ ≤ TOL` olan içbükey yay
  düşer; tüm ham parçaların ikili kesişimleri bulunup parçalar bölünür; orta noktası profile `ρ − TOL`'den yakın olan alt parça
  atılır; kalanlar baştan sona bağlanır. Burun merkezi yolu, profil başlangıç noktasının `ρ·n₀` ötesinden başlar ve bitiş
  noktasının `ρ·n_son` ötesinde biter.
  Bölme, profilin başlangıç ve bitiş noktası merkezli `ρ` yarıçaplı daireler (**uç kapakları**) ile de yapılır; bu daireler
  yola eklenmez, yalnız içlerine giren alt parçaların atılmasını sağlar. Bir uç parçanın ofseti budamada tamamen silinirse
  burun merkezi yolu, kalan son parçanın uç kapağına değdiği noktada başlar/biter (kaba çevrimde hata değildir; sıkı modda
  "Erişilemeyen profil" kuralı uygulanır).
- **Erişilemeyen profil** (sıkı mod, ince profil): ofset yarıçapı `R − r ≤ TOL` olan içbükey yay **veya** budamada ofseti
  tamamen silinen bir profil parçası (örn. genişliği `2r`'den dar kanal tabanı) → `CamError`. Sessizce malzeme bırakılmaz.
  Kaba çevrimde (`ρ = r + δ`) bu durumlar hata değildir; o bölgede fazla malzeme kalır ve ince paso sıkı modda kontrol eder.
- Keskin içbükey köşede burun profile köşeden `r / tan(θ/2)` uzaklıkta teğet olur (`θ` köşenin malzeme dışından görülen iç açısı);
  bu komşuluk ve yarıçapı `r` olan köşe dolgusu kaçınılmazdır.

### Takımın erişimi (yaklaşma ve uç açısı)
Profil ön→arka gezilirken teğetin açısı `φ = atan2(t_x, −t_z)` (`−Z` yönünden `+X`'e doğru, derece). Ana kesici kenar
ilerleme yönüyle `κr`, arka kenar `κr' = 180° − κr − εr` açı yapar. Takım profili sadece
`−κr' ≤ φ ≤ κr` ise kenarlarıyla çakmadan izler (örn. `κr = 93°` ile 90° omuz işlenir; `κr' = 7°` en fazla 7° inen geri
çekme). Yaylarda bütün süpürme aralığındaki teğetler kontrol edilir. Aksi `CamError`. Kaynak: Sandvik Coromant, *Turning*,
yaklaşma açısı ve uç açısı; arka kenar boşluğu.
Profil **monoton** (Fanuc `G71` tip I): her noktada `t_z ≤ TOL` ve `t_x ≥ −TOL`, yani `0° ≤ φ ≤ 90°`.

### Güvenli noktalar
`X_s` ham malzeme yüzey yarıçapı (dış: `D/2`; iç: aynada `−d/2`), `z_max` ham malzemenin ön yüzü, `cl` yaklaşma payı.
Burun dairesinin tamamı ham malzeme kutusunun dışında kalsın diye:
- Başlangıç / bitiş noktası `A`: burun merkezi `C_A = (z_max + cl + r, X_s + cl + r)`; yol `P_A = C_A + q_T`'de başlar ve biter.
- Ön düzlem: `C_z = z_max + cl + r`; güvenli yarıçap: `C_x = X_s + cl + r`.

### Alın tornalama
`H = z_max − z_face`, `n = ⌈H / a_p⌉` (SPEC 03 `depths` kuralı, `1e-9` toleransla), temas düzlemleri
`z_i = z_max − i·H/n`, `i = 1..n`, son `z_n = z_face` tam. Her pasoda burun dairesinin `−Z` ucu `z_i`'de: `C_z = z_i + r`.
Paso: `G0` güvenli yarıçapa → `G1` `−X` yönünde `C_x = x_son`'a (`x_son = 0` dolu çubukta; borude `max(0, d/2 − cl)`) →
`G0` `+Z`'de `cl` geri → `G0` güvenli yarıçapa. Dolu çubukta `T = 3` ile hayali uç `x = −r`'ye kadar gider
(burun merkezi eksende, alın merkeze kadar temiz).

### Kaba çevrim (boyuna, `G71` tip I)
Sınır: profilin `ρ = r + δ` burun merkezi yolu (budamalı), son noktasından `+X` yönünde uzatılmış.
`x_low` = `δ` ofsetli profilin başlangıç noktasının `x`'i (monoton profilde en küçük temas `x`'i),
`H = X_s − x_low` (`H ≤ TOL` → `CamError`), `n = ⌈H / a_p⌉`, temas seviyeleri `x_k = X_s − k·H/n`.
- `k = 1..n−1` **boyuna pasolar**: burun merkezi `C_x = x_k + r`'de, ön düzlemden `−Z` yönünde, sınırla ilk kesiştiği
  noktaya (ön→arka gezide sınırın `C_x`'e ilk ulaştığı nokta; yatay örtüşmede en öndeki nokta) kadar `G1`. Sonra `G1`
  ile `45°`'de geri çekilme `(+e, +e)` (`e = retract`), `G0` ön düzleme, `G0` sonraki seviyeye. Boyu `≤ TOL` olan paso atlanır.
- `k = n` **kontur pasosu**: sınırın kendisi (basamakları kaldırır; her yerde `δ` talaş payı kalır). Giriş: `G0` ön
  düzlemde `F = (max(z_max + cl + r, C0_z), C0_x)` → `G1` `C0`'a → sınır boyunca `G1`/`G2`/`G3` → son noktadan `+X`
  yönünde `G1` güvenli yarıçapa → `G0` `A`'ya.
- Basamak kalınlığı X'te `H/n ≤ a_p`. `n = 1` ise sadece kontur pasosu.
- Ön koşullar (aksi `CamError`): profil monoton, erişim koşulu, profil başlangıcı `z ≥ z_max − TOL` (ön alın önceden
  alınmış), profil sonu `x ≥ X_s − TOL` (profil ham malzeme yüzeyine çıkar). Ön alın profile dahilse alın hizasındaki
  seviyelerde kısa (≤ `cl`) havada pasolar oluşur; önerilen sıra önce `face`, sonra alından sonra başlayan profille `rough`.
- Kaynak: Fanuc 0i-TF, `G71` boyuna kaba çevrim (tip I); Smid, kaba çevrimler.

### Boy tornalama
`turn(X_f, z_end)`: profil `(z_max, X_f) → (z_end, X_f) → (z_end, X_s)` için `δ = 0` kaba çevrim.
`n = ⌈(X_s − X_f) / a_p⌉` paso; `n − 1` boyuna paso ve omuzda biten bir kontur pasosu. `T = 3`'te boyuna paso
uçları `P_z = z_end` (burun merkezi `z_end + r`, hayali uç omuz düzleminde).

### İnce profil
Sıkı modda `ρ = r` burun merkezi yolu; hayali uç yolu `P = C + q_T`. Giriş ve çıkış kaba çevrimin kontur pasosuyla aynı.
Ön koşul: erişim koşulu (monotonluk gerekmez; geri çekmeler erişim koşuluyla sınırlı).

### Kanal (dalarak, radyal, dış çap)
Kanal genişliği `W = z_right − z_left`, takım genişliği `w`, her iki köşede burun yarıçapı `r`. Sol köşe burun merkezi `C_L`,
sağ `C_R = C_L + (w − 2r, 0)`. Hayali uç: `T = 3` → `P = C_L + (−r, −r)` (takımın sol kenarı, tabanda); `T = 4` →
`P = C_R + (+r, −r)` (sağ kenar). Takımın sol kenarının `z_L` olduğu bir dalış tabanı düz `w − 2r` genişlikte keser.
- `W = w` → tek dalış. `W > w` → `m = ⌈(W − w) / (w − 2r)⌉ + 1` dalış, sol kenarlar `z_L,j = z_left + j·(W − w)/(m − 1)`,
  `j = 0..m−1`, `z_left`'ten `z_right`'a. Komşu dalışların düz tabanları örtüştüğü için taban `x_bottom`'da düz, duvarlar
  `z_left` ve `z_right`'ta düz; köşelerde `r` dolgu.
- Dalış: `G0` (`C_x = x_top + cl + r`) → `G1` `C_x = x_bottom + r`'ye → `G0` `x_top + cl + r`'ye. İlk dalıştan önce `A`'dan
  güvenli yarıçapta dalış `z`'sine, son dalıştan sonra güvenli yarıçap üzerinden `A`'ya `G0`.
- `W < w`, `x_bottom ≥ x_top` (dışta), `x_bottom < 0`, `W > w` iken `w − 2r ≤ TOL` (tam yarıçaplı uç) → `CamError`.

### Diş çekme
- ISO metrik (ISO 68-1) temel üçgen yüksekliği `H = (√3/2)·P`. Diş derinliği (yarıçapta): dış `h = 17/24·H = 0,613435·P`,
  iç `h = 5/8·H = 0,541266·P`.
- Paso derinlikleri (Fanuc `G76`): kümülatif derinlik `h_i = Δd·√i`; artış `h_i − h_{i−1} < Δd_min` ise
  `h_i = h_{i−1} + Δd_min`; `h_i ≥ h` olan ilk paso `h`'ye kırpılır ve son pasodur. Kırpma yoksa paso sayısı
  `n = ⌈(h/Δd)²⌉`. Ardından `k` boş paso (yay geri esnemesi için) aynı `h` derinliğinde. Kaynak: Fanuc 0i-TF, `G76` çok pasolu diş çevrimi.
- Takım derinliği: burunun en derin noktası temas yarıçapında: dışta `C_x = x0 − h_i + r` (`x0` = büyük çap/2).
  `T = 8` ile `P_x = x0 − h_i`. İç dişte `x0` = küçük çap/2 (delik) ve derinlik dışa doğru: `P_x = x0 + h_i` (`T = 6`).
- Dalma yönü: `"radyal"` her paso aynı `z`'den başlar. `"yanak"` (tek kenarla kesme): her paso arka yanak doğrusu boyunca
  derinleşir; geçiş kesme yönünde `Δz_i = s · h_i · tan(εr/2)` (`s = sign(z_end − z_start)`), paso başı ve sonu birlikte kayar.
  Böylece arka yanak bir önceki pasonun yanağı üzerinde kalır, sadece ön kenar keser.
- Paso: `G0` (`z_start + Δz_i`, geri çekilme yarıçapı `C_x = x0 + cl + r`) → `G0` derinliğe → `G1` ilerleme = **hatve** `P`
  (mm/dev) ile `z_end + Δz_i`'ye → `G0` geri çekilme yarıçapına → sonraki pasonun başına. Senkronlu diş `G32` / `G76`
  yazımı SPEC 21'in işidir; burada `G1` ve `feed = P`.
- Diş sabit devirle çekilir: `css` verilirse `CamError`.

## Dosyalar
- Yeni: `cam/lathe.py`, `cam/lathe_ops.py`, `tests/cam/test_lathe.py`, `tests/cam/test_lathe_ops.py`,
  `tests/cam/test_lathe_thread.py`, `durum/20-torna-yol.md`
- Kullanılır (değişmez): `cam/model.py`, `cam/profile.py`, `cam/geom2d.py` (`intersect`, `closest`, `TOL`), `cam/ops2d.py` (`depths`).
- Dokunulmayacak: `cam/model.py` (arayüz sabit), `cam/gcode/` (torna yazıcı koruması SPEC 21'e kadar kalır), diğer tüm paketler ve ortak dosyalar.

## Arayüz

### `cam/lathe.py`
- `TIP_DIR: dict[int, tuple[int, int]]` — yukarıdaki tablo, `(s_z, s_x)`.
- `tip_offset(tip: int, r: float) -> np.ndarray` — `q_T`, `(z, x)` sırasında. `tip ∉ 0..9` veya `r < 0` → `CamError`.
- `mirror_tip(tip: int) -> int` — `x → −x` aynası.
- `orient(profile: Profile) -> Profile` — ön→arka yön; kapalı profil, `x < −TOL` → `CamError`.
- `mirror(profile: Profile) -> Profile` — `(z, x) → (z, −x)`, yaylar `ccw` değiştirir.
- `angles(profile: Profile, side: str = "dis") -> tuple[float, float]` — teğet açısı `φ`'nin en küçük ve en büyük değeri [derece]
  (profil önce `orient` edilir; `"ic"` için aynada ölçülür).
- `is_monotone(profile: Profile, side: str = "dis") -> bool` — `0 ≤ φ ≤ 90°` (± `1e-9` derece) her yerde.
- `check_reach(profile: Profile, tool: LatheTool, side: str = "dis") -> None` — `−κr' ≤ φ ≤ κr` değilse `CamError`.
- `nose_path(profile: Profile, rho: float, side: str = "dis", strict: bool = True) -> list[Segment]` — burun merkezi yolu
  (ön→arka), `ρ ≥ 0` (`ρ = 0` → profilin kendisi). `strict=True` erişilemeyen profilde `CamError`.
- `tip_path(profile: Profile, tool: LatheTool, side: str = "dis", allowance: float = 0.0, strict: bool = True) -> list[Segment]`
  — `nose_path(profile, tool.nose_r + allowance, ...)` parçalarının `q_T` kadar kaydırılmışı (hayali uç yolu).
- `side` `"dis"` veya `"ic"` değilse `CamError`.

### `cam/lathe_ops.py`
- `@dataclass TurnCut(feed: float, rpm: float, css: float | None = None, a_p: float | None = None, clearance: float = 1.0, retract: float = 0.5)`
  - `feed` mm/dev (`G95`), `rpm` dev/dk (`css` verilirse devir sınırı, `G50`), `css` m/dk (`G96`), `a_p` radyal (alında eksenel) paso derinliği.
  - `feed > 0`, `rpm > 0`, `css` `None` veya `> 0`, `a_p` `None` veya `> 0`, `clearance > 0`, `retract > 0`; `nan` / `inf` → `CamError`.
  - `face`, `turn`, `rough` için `a_p` zorunlu (`None` → `CamError`).
- Her işlem `Toolpath(plane=Plane.ZX, feed_mode=FeedMode.PER_REV, css=cut.css, rpm=cut.rpm, tool=tool)` döndürür;
  `start = P_A`, son hareket `P_A`'da biter; noktalar `(x, 0, z)`; yay merkezleri `(x, z)`; kesme hareketleri
  `feed = cut.feed` (diş: `pitch`), `G0`'da `feed = None`; dönen yol `validate()`'ten geçer; sıfır boylu hareket yazılmaz.
- `face(stock: CylinderStock, tool: LatheTool, cut: TurnCut, z_face: float, name: str = "alin") -> Toolpath`
  — `stock.zmin < z_face < stock.zmax`; takım `TURN`, `tip ∈ {3, 0, 9}`.
- `turn(stock, tool, cut, x_final: float, z_end: float, side: str = "dis", name: str = "boy") -> Toolpath`
  — dışta `0 ≤ x_final < D/2`, içte `d/2 < x_final < D/2`; `stock.zmin ≤ z_end < stock.zmax`.
- `rough(profile: Profile, stock, tool, cut, allowance: float = 0.0, side: str = "dis", name: str = "kaba") -> Toolpath`
  — `allowance = δ ≥ 0`.
- `finish(profile: Profile, stock, tool, cut, side: str = "dis", name: str = "ince") -> Toolpath`
- `groove(stock, tool, cut, z_left: float, z_right: float, x_top: float, x_bottom: float, side: str = "dis", name: str = "kanal") -> Toolpath`
  — takım `GROOVE`; dışta `tip ∈ {3, 4}`, içte `tip ∈ {2, 1}` (`x_bottom > x_top`).
- `iso_thread_depth(pitch: float, external: bool = True) -> float`
- `thread_depths(h: float, first: float, minimum: float = 0.0, spring: int = 0) -> list[float]` — kümülatif derinlikler,
  boş pasolar dahil. `h > 0`, `first > 0`, `minimum ≥ 0`, `spring ≥ 0` tam sayı; aksi `CamError`. `first ≥ h` → `[h]` (+ boş pasolar).
- `thread(stock, tool, cut, z_start: float, z_end: float, x0: float, pitch: float, depth: float, first: float, minimum: float = 0.0, spring: int = 1, infeed: str = "radyal", side: str = "dis", name: str = "dis") -> Toolpath`
  — takım `THREAD`; dışta `tip ∈ {8, 0, 9}`, içte `tip ∈ {6, 0, 9}`; `pitch > 0`, `z_start ≠ z_end`, dışta `x0 − depth > 0`;
  `infeed ∈ {"radyal", "yanak"}`; `cut.css is not None` → `CamError`.
- Takım türü / uç numarası işleme uymuyorsa, `side = "ic"` iken `stock.d = 0` ise → `CamError`.
- `"dis"` işlemlerde takım `TURN`, `"ic"` işlemlerde `BORE` (kaba, ince, boy), `tip ∈ {3, 0, 9}` / `{2, 0, 9}`.

## Kabul kriterleri
Geometrik değerlerde tolerans aksi yazılmadıkça mutlak `1e-9 mm`. Test profilleri uydurma geometridir.
- [ ] K1 Uç tablosu: `tip_offset` 0..9 tablo değerleri, aynalama 1↔4, 2↔3, 6↔8; hatalı uç numarası / negatif `r` → `CamError` — `tests/cam/test_lathe.py`
- [ ] K2 `orient` arkadan öne verilen profili çeviriyor; kapalı profil ve `x < 0` → `CamError`; `mirror` iki kez uygulanınca aynı profil, yay yönü değişiyor — `tests/cam/test_lathe.py`
- [ ] K3 Açılar ve erişim: silindir `φ = 0`, alın / omuz `φ = 90°`, 30° koni `φ = 30°`, geri çekme `φ < 0`; `is_monotone`; `κr = 93°` omzu işler, `κr = 60°` → `CamError`; `κr' `'den dik iniş → `CamError` — `tests/cam/test_lathe.py`
- [ ] K4 Telafi, doğru: silindir ve alında `T = 3` hayali uç yolu profilin kendisi; koni (`α = 30°`, `45°`) için `ΔX = −r(1 − tan(45° − α/2))` ve `ΔZ = −r(1 − tan(α/2))`; `T = 0` hayali uç = burun merkezi (`ρ·n` kayması) — `tests/cam/test_lathe.py`
- [ ] K5 Telafi, yay: dışbükey yay → merkez `c + q_T`, yarıçap `R + r`; içbükey yay → `R − r`; `R ≤ r` içbükey yay → sıkı modda `CamError`, `strict=False`'ta yay düşüyor — `tests/cam/test_lathe.py`
- [ ] K6 Köşeler: omuzda (içbükey 90°) burun merkezi köşesi `(z_s + ρ, x_f + ρ)` keskin; pah üstünde (dışbükey) `V` merkezli `ρ` yarıçaplı yay; `2r`'den dar kanal → sıkı modda `CamError`; budama sonrası burun merkezi yolundaki örnek noktaların profile uzaklığı `ρ` (± 1e-9); örnek noktaların profile (uç noktaları dahil) uzaklığı ≥ `ρ − 1e-9` — `tests/cam/test_lathe.py`
- [ ] K7 `TurnCut` doğrulamaları ve `a_p` zorunluluğu → `CamError` — `tests/cam/test_lathe_ops.py`
- [ ] K8 `face`: paso sayısı `⌈H/a_p⌉`, temas düzlemleri `z_i`, son paso tam `z_face`; `T = 3` dolu çubukta uç `x = −r`'ye iniyor, boruda `max(0, d/2 − cl)`; hatalı `z_face` → `CamError` — `tests/cam/test_lathe_ops.py`
- [ ] K9 `turn`: paso sayısı `⌈(X_s − X_f)/a_p⌉`, seviyeler `x_k = X_s − k·H/n`, boyuna paso uçları `P_z = z_end`, kontur pasosu `X_f`'de ve omuzda; iç tarafta (boru) aynı formüller aynada — `tests/cam/test_lathe_ops.py`
- [ ] K10 `rough`: koni ve omuzlu milde boyuna paso uçları kapalı formla (sınırın seviyeyle kesişimi, `δ` dahil); kontur pasosu `tip_path(..., allowance=δ)` ile birebir; dışbükey yayda kontur pasosu yarıçapı `R + δ + r`; ön koşullar (monoton değil, başlangıç `z < z_max`, son `x < X_s`, `H ≤ 0`) → `CamError` — `tests/cam/test_lathe_ops.py`
- [ ] K11 `finish`: pah + silindir + dolgu + omuz + koni profilinde hayali uç yolu `tip_path` ile birebir; giriş `F → C0` ve çıkış `+X`; içbükey dolgu `R < r` ve dar kanal → `CamError` — `tests/cam/test_lathe_ops.py`
- [ ] K12 Çakma yok ve kalan malzeme yok (`rough`, `finish`, dış ve iç): bütün hareketler (G0 dahil) üzerindeki örnek noktalarda burun merkezi `C = P − q_T` için `dist(C, profil) ≥ r + δ − 1e-9`; `finish`'te profilin her örnek noktası (keskin içbükey köşelerin `r / tan(θ/2)` komşuluğu hariç) burun merkezi yoluna `≤ r + 1e-9` uzaklıkta — `tests/cam/test_lathe_ops.py`
- [ ] K13 `groove`: dalış sayısı `m` ve konumları, `T = 3` uç `P = (z_L,j, x_bottom)`, `T = 4` uç `P = (z_L,j + w, x_bottom)`; tabanın her örnek noktası bir dalışın düz tabanının altında; takım `[z_left, z_right]` dışına taşmıyor; hatalı girdiler → `CamError` — `tests/cam/test_lathe_ops.py`
- [ ] K14 `iso_thread_depth` (`P = 1,5` → `0,920152…`, iç `0,811899…`, rel 1e-12); `thread_depths` Fanuc kuralı (`√i` dizisi, `Δd_min` kırpması, son paso tam `h`, boş pasolar, `first ≥ h`) ve hatalı girdiler — `tests/cam/test_lathe_thread.py`
- [ ] K15 `thread`: her pasoda `G1` `feed = pitch`, sabit `x = x0 − h_i` (`T = 8`), paso uçları `z_start`/`z_end`; `"yanak"`ta kayma `s·h_i·tan(εr/2)` kesme yönünde; iç diş aynada; `css` verilmişse, `x0 − h ≤ 0`, yanlış takım → `CamError` — `tests/cam/test_lathe_thread.py`
- [ ] K16 Genel yol kuralları (bütün işlemler): `plane = ZX`, `feed_mode = PER_REV`, `css`/`rpm` aktarılmış, `y = 0`, `start = P_A` ve bitiş `P_A`, `validate()` geçiyor, yaylar `G18` yön kuralına uygun (`ccw` → `G3`, merkez `(x, z)`), kesme hareketlerinde `feed`, `G0`'da `None` — `tests/cam/test_lathe_ops.py`
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz

## Kapsam dışı
- G-code yazımı ve okuması (çap programlama, `G96`/`G50`, `G71`/`G70`/`G76`/`G32`, `G41`/`G42` makine tarafı telafi): SPEC 21.
- Talaş simülasyonu, ayna / punta / gövde çarpışması, kalan malzeme hesabı: SPEC 22. `G0` hareketlerinin kalan ham malzemeye
  girmediği burada sadece kurallarla sağlanır, simülasyonla doğrulanmaz.
- `G71` tip II (monoton olmayan cep kaba çevrimi), `G72` alında kaba çevrim, `G73` profil tekrarlı çevrim, tutucu / takım gövdesi
  çarpışması (sadece `κr`, `εr` kenar açıları kontrol edilir).
- Alın kanalı, kanal tornalama (yanal), talaş kırma (gagalama), bekleme; kanal ve diş girişinde / çıkışında pah.
- Çok ağızlı, konik, değişken hatveli diş; değişen yanak dalması; diş çıkış pahı (`G76` pah). Dişte senkron hız sınırları.
- Profil çıkarma (katı parçadan dönel kesit): SPEC 22. Profil sadece doğru + yay.
- Kesme verisinden devir / ilerleme hesabı (`n = 1000·Vc/(πD)`): SPEC 14; burada `rpm`, `css`, `feed` doğrudan verilir.
- Arka (ayna tarafına doğru `+Z`'de kesen) takımlar, C/Y eksenli işlemler.
