# Bağımsız çapraz kontrol (inceleme bulgusu Y1)

Buradaki testler kodu **kendi kendisiyle değil, bağımsız bir referansla** karşılaştırır.
Gidiş-dönüş (`read(write(x)) == x`) gibi iç tutarlılık testleri, iki tarafın paylaştığı bir
yorum hatasını göremez; bu klasör o boşluğu kapatır.

| Dosya | Neyi neyle karşılaştırır | Harici araç |
|---|---|---|
| `gcode_ref.py` | Bağımsız G-code yorumlayıcısı (LinuxCNC / RS274NGC anlamı). `cam.gcode`'dan hiçbir şey import etmez. | — |
| `gcode_check.py` | Modelden beklenen hareketler, karşılaştırma, tezgâh güvenliği denetimleri | — |
| `test_gcode_crosscheck.py` | `cam.gcode.write` çıktısı → `gcode_ref` → hareketler = CAM modeli; GRBL ↔ Fanuc aynı yol; GRBL çevrim açılımı ↔ LinuxCNC G81/G83; güvenlik (K1–K3) | `rs274` varsa onunla da |
| `calculix.py`, `test_calculix.py` | Kendi FEM çözücümüz ↔ CalculiX (aynı model, `.inp` üzerinden): yer değiştirme, tepki, gerilme | `ccx` (yoksa atlanır) |
| `test_assy_closed_form.py` | Montaj çözücüsü ↔ kapalı form: dört çubuk mekanizması (çember kesişimi), eğik eksende kovan | — |

## Bilinen kusurlar: `xfail(strict=True)`

İnceleme raporundaki K1, K2, K3 burada strict `xfail` olarak duruyor (`@known(...)`). Kusur
düzelince test XPASS olur ve strict olduğu için **kırmızıya döner**: bu bilinçli bir uyarıdır.
G-code güvenlik düzeltmesini birleştiren kişi ilgili `@known` işaretini kaldırır; test o andan
sonra düzeltmeyi korur. `raises=AssertionError` sayesinde başka bir hata (ör. yazıcının çökmesi)
xfail'e saklanamaz.

Güvenlik denetimleri genel kurallardır, düzeltmenin nasıl yapıldığına bağlı değildir:
XY hızlı hareket ham malzeme üstünde (Z ≥ 0) olmalı, takım değişimi kesme derinliğinde olmamalı,
GRBL'de iş mili durmadan takım değişmemeli, Fanuc'ta kesme sırasında `G43 H<takım>` ve `G54`
etkin olmalı. Karşılaştırma, güvenlik için eklenen fazladan hızlı hareketlere (geri çekme) izin verir.

## Harici araçlar

- **CalculiX**: Ubuntu/Debian `sudo apt install calculix-ccx`; Windows'ta `ccx` PATH'te olmalı.
  Tanım farkı: CalculiX `RF = K u`, bizde `R = K u − F` (SPEC 01). Mesnetli düğüme doğrudan yük
  verilince ikisi o yük kadar ayrışır; test ccx tanımına çevirip karşılaştırır.
- **LinuxCNC `rs274`**: varsa G-code testleri onunla da çalışır. Bu bağdaştırıcı geliştirme
  ortamında `rs274` olmadığı için denenmedi; ilk çalıştırmada çıktı biçimi kontrol edilmeli.
  CAMotics için bağdaştırıcı yok.

Harici araç yoksa ilgili testler atlanır (`skipif`); diğerleri her ortamda çalışır.
