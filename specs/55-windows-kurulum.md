# SPEC 55 — Windows tek tık kurulum (uv betiği)

> Durum: **onaylı** (kullanıcı, 2026-10-18 14:52 duyurusu; 2 dakika itirazsız → otomatik kabul kuralı).
> Dalga 6, hat G8 (proje klasörü `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 3).
> Karar (kullanıcı, 2026-10-18): **"Önce uv betiği"**; yeni bağımlılık yok, kurulum paketi (MSI / PyInstaller)
> bu SPEC'te yok. Dayanır: SPEC 24 (Tezgah, `python -m tezgah`, 127.0.0.1:8724), `pyproject.toml` ekstraları
> `web` ve `cad`.

## Amaç
Atölyedeki bir Windows bilgisayarında, depo klasörü elde olduktan sonra **tek bir dosyaya çift tıklayarak** Tezgah'ı
kurmak ve masaüstündeki bir başlatıcıyla açmak. Bu adım bitince:
1. `kurulum\kur.bat` çift tıklanınca sanal ortam kurulur, paket ve ekstraları yüklenir, ön yüz hazır mı denetlenir,
   masaüstüne bir başlatıcı konur ve sonunda bir **hazırlık raporu** (ne tamam, ne eksik, ne yapılmalı) yazılır.
2. Masaüstündeki `Tezgah.bat` sunucuyu açar ve tarayıcıyı `http://127.0.0.1:8724/` adresinde başlatır.
3. `guncelle.bat` depoyu ve ortamı günceller; `kaldir.bat` yalnızca kurulumun kendi yarattıklarını siler, **projelere
   hiçbir zaman dokunmaz**.

## Neden
Bugün kurulum geliştirici adımlarıdır (`pip install -e ".[dev,cad]"`, `npm ci && npm run build`). Kullanıcının
makinesinde sistem Python'u yok, uv'nin getirdiği Python 3.14 kullanılıyor ve **PowerShell betik çalıştırma kapalı**
(`_kurulum/yerlestir.ps1` bu yüzden elle `-ExecutionPolicy Bypass` ister). Atölyede bir operatörün terminal açmadan
programı açabilmesi, SPEC 48'deki gerçek tezgâh doğrulamasının ön koşuludur.

## Teori (tasarım kararları)

### 1. Neden yalnızca cmd / .bat
- PowerShell betikleri kapalı; `-ExecutionPolicy Bypass` güvenlik ayarını dolanmak demektir, bu SPEC bunu **kullanmaz**.
  Betiklerin hiçbiri `powershell` / `pwsh` çağırmaz (K2).
- `.bat` çift tıklamayla çalışır, ek izin istemez, yönetici hakkı gerektirmez (her şey kullanıcı klasöründe).
- Karmaşık mantık (sürüm denetimi, içe aktarma denemesi, port denetimi) `.bat` içinde değil, kurulan ortamın
  Python'uyla çalışan `kurulum/kontrol.py` içindedir: `.bat` yalnızca sırayla komut çağırır ve `errorlevel` denetler.
  Böylece mantık Linux'ta pytest ile sınanabilir.

### 2. uv
- uv **önceden kurulu** varsayılır (`where uv`). Yoksa betik açık bir mesajla durur:
  `"kurulum: uv bulunamadı — https://docs.astral.sh/uv/ adresinden kurun ya da uv.exe'yi bu klasöre koyun, sonra kur.bat'ı yeniden çalıştırın"`
  ve 1 ile çıkar. `kurulum\uv.exe` varsa önce o kullanılır (çevrimdışı atölye için). Betik internetten uv
  **indirmez** (açık soru 1).
- Ortam: `uv venv .venv --python %TEZGAH_PYTHON%` (varsayılan `3.14`; ortam değişkeniyle değiştirilebilir), sonra
  `uv pip install --python .venv\Scripts\python.exe -e ".[web,cad]"`.
- `cad` (build123d / OCP) tekerleği bu Python sürümü için yoksa kurulum **durmaz**: `".[web]"` ile yeniden dener,
  raporda `"OCCT yok: STEP açma ve katı modelleme kapalı — uyarı"` yazar ve çıkış kodu 2 olur (0 = tam, 2 = eksikle
  çalışır, 1 = çalışmaz). Sessiz geçiş yok: eksik olan rapora ve `kurulum.log`'a yazılır.
- Yeni Python bağımlılığı yoktur; `pyproject.toml` değişmez.

### 3. Ön yüz (`tezgah/arayuz/dist/`)
`dist/` git'te yok. Sıra:
1. `tezgah\arayuz\dist\index.html` varsa: hazır, adım atlanır.
2. Yoksa ve `npm` bulunursa: `npm ci` + `npm run build` (`tezgah\arayuz` içinde); hata olursa durur (1).
3. Yoksa ve `npm` yoksa: durur (1), mesaj: `"Tezgah ön yüzü derlenmemiş — Node.js kurun ya da derlenmiş dist klasörünü
   tezgah\arayuz\dist içine kopyalayın"`.
Hazır derlenmiş `dist` içeren bir sürüm zip'i (GitHub Release) bu SPEC'te yok (açık soru 2: Actions dakikası).

### 4. Başlatıcı
- Masaüstü yolu OneDrive yönlendirmesi yüzünden `%USERPROFILE%\Desktop` varsayılmaz; `reg query
  "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop` ile okunur, `%...%`
  açılır; okunamazsa `%USERPROFILE%\Desktop`.
- Masaüstüne `Tezgah.bat` yazılır: `cd /d "<depo>"` ve `".venv\Scripts\python.exe" -m tezgah`. Sunucu penceresi açık
  kalır (kapatmak = sunucuyu durdurmak); pencere başlığı `Tezgah`. `.lnk` kısayolu yaratmak PowerShell / COM gerektirdiği
  için yok.
- Port 8724 doluysa (`kontrol.py --port`): başlatıcı sunucuyu ikinci kez açmaz, yalnızca tarayıcıyı o adrese açar
  (`start "" http://127.0.0.1:8724/`); port Tezgah olmayan bir programdaysa mesaj verip durur.

### 5. Betik kuralları
- `@echo off`, `setlocal EnableExtensions`, `chcp 65001 >nul` (Türkçe karakterler), tüm yollar tırnaklı, depo kökü
  `%~dp0..` ile bulunur (boşluklu ve Türkçe karakterli yollar, ör. `C:\Users\Ali Çelik\Masaüstü\3D-CORE`, çalışır).
- Dosyalar çalışma ağacında **CRLF** satır sonludur. Depodaki `.gitattributes` `* text=auto` içerdiğinden bu,
  `*.bat text eol=crlf` satırı olmadan sağlanamaz (Linux'ta çekilen kopya LF olur); satır bu SPEC'in PR'ında eklenir
  (karar 3). Test bunu denetler.
- Her adım sonrası `if errorlevel 1` denetimi; hata mesajı `kurulum: <adım>: <ne oldu> — <ne yapılabilir>` biçiminde
  (SPEC 54 §1 ile aynı biçim).
- **Tekrar çalıştırmak güvenli** (idempotent): var olan `.venv` silinmez, `uv pip install` yeniden eşitler; başlatıcı
  üzerine yazılır.
- Çıktı hem ekrana hem `kurulum\kurulum.log`'a (her çalıştırmada başa tarih satırı, eskisi `kurulum.log.1`).
- Çift tıklamada pencere sonunda `pause` ile açık kalır; `kur.bat /sessiz` ile `pause` yok (otomasyon ve test için).

### 6. Güncelle ve kaldır
- `guncelle.bat`: `git` varsa ve çalışma ağacı temizse `git pull --ff-only`; değilse uyarır ve çekmeden devam eder
  (yerel değişikliği asla ezmez, `reset` / `stash` yok). Sonra `kur.bat /sessiz` adımlarını yeniden çalıştırır.
- `kaldir.bat`: onay sorar (`E/H`), sonra yalnızca `.venv`, masaüstü `Tezgah.bat` ve `kurulum\kurulum.log*` silinir.
  `~\3D-CORE projeleri\`, `yerel_parcalar\`, depo dosyaları ve `.3dc` dosyaları **silinmez**; mesajda bu açıkça yazılır.

## Dosyalar
| Dosya | Ne |
|---|---|
| `kurulum/kur.bat` | ana kurulum (bölüm 2–5) |
| `kurulum/baslat.bat` | başlatıcı şablonu; `kur.bat` bunu masaüstüne yazarken depo yolunu doldurur |
| `kurulum/guncelle.bat` | bölüm 6 |
| `kurulum/kaldir.bat` | bölüm 6 |
| `kurulum/kontrol.py` | hazırlık denetimi (saf Python, stdlib) |
| `kurulum/BENIOKU.md` | operatör için kısa adımlar (resimsiz, Türkçe) |
| `tests/kurulum/test_kontrol.py`, `tests/kurulum/test_bat.py` | testler |
| `README.md` | "Kurulum (Windows, bir kez)" bölümünün başına `kurulum\kur.bat` satırı (yalnızca bu bölüm) |
| `BASLANGIC.md` | yalnızca kurulum satırlarına `kurulum\kur.bat` notu (koordinatör kararı: bu bölüm bu SPEC'in) |
| `.gitattributes` | `*.bat text eol=crlf` (karar 3) |

Dokunmaz: `pyproject.toml`, `_kurulum/yerlestir.ps1`, `scripts/bulut_kurulum.sh`, `.github/`, `tezgah/` kodu.

## Arayüz
`kurulum/kontrol.py` (yalnızca stdlib; kurulan ortamın Python'uyla çalışır):
```python
@dataclass(frozen=True)
class Madde:
    ad: str            # "python", "web", "occt", "on_yuz", "port"
    durum: str         # "tamam" | "uyari" | "eksik"
    mesaj: str         # SPEC 54 §1 biçimi

def python_denetle(surum: tuple[int, int, int] | None = None) -> Madde      # >= 3.11 değilse "eksik"
def ice_aktarma_denetle(modul: str, ad: str, zorunlu: bool) -> Madde       # importlib.util.find_spec
def on_yuz_denetle(kok: Path) -> Madde                                      # tezgah/arayuz/dist/index.html
def port_denetle(port: int = 8724, host: str = "127.0.0.1") -> Madde       # boş: tamam; Tezgah: uyari; başka: eksik
def rapor(maddeler: list[Madde]) -> tuple[str, int]                         # metin, çıkış kodu 0 / 2 / 1
def main(argv: list[str] | None = None) -> int   # --kok, --port, --yalniz-port
```
Çıkış kodu kuralı: herhangi bir `"eksik"` → 1; yoksa herhangi bir `"uyari"` → 2; değilse 0. `occt` zorunlu değildir
(yoksa `"uyari"`), `web` ve `on_yuz` zorunludur. "Port Tezgah'ta mı" denetimi (karar 4): SPEC 24'te sağlık ucu
yok; `GET http://127.0.0.1:<port>/api/openapi.json` yanıtı JSON ve `info.title == "Tezgah"` ise Tezgah sayılır
(ön yüz derlenmemiş olsa da çalışır). Bağlantı kurulamıyorsa port boştur; bağlanıyor ama bu denetim tutmuyorsa
başka bir programdır. İstek yalnızca verilen `host`'a gider, zaman aşımı 2 s; ağ dışına istek yoktur.

## Kabul kriterleri
- **K1** `kurulum/` altındaki dört `.bat` dosyası vardır, her biri `@echo off` ile başlar, `setlocal` ve
  `chcp 65001` içerir, CRLF satır sonludur (her satır `\r\n`). (`tests/kurulum/test_bat.py`)
- **K2** Hiçbir `.bat` dosyası (büyük/küçük harf duyarsız) `powershell`, `pwsh`, `ExecutionPolicy`, `Invoke-WebRequest`
  ya da `curl` içermez. (`test_bat.py`)
- **K3** `kur.bat` uv'yi önce `kurulum\uv.exe`, sonra `where uv` ile arar; Python sürümünü `TEZGAH_PYTHON` değişkeninden
  (varsayılan `3.14`) alır; `.venv` siler komutu (`rmdir`, `rd`, `del`) içermez. (`test_bat.py`, metin denetimi)
- **K4** `kaldir.bat`'taki her silme komutunun hedefi yalnızca `.venv`, masaüstü `Tezgah.bat` veya `kurulum.log`
  kalıbıdır; `projeleri`, `yerel_parcalar`, `*.3dc` geçmez. (`test_bat.py`)
- **K5** `guncelle.bat` `git pull --ff-only` kullanır; `reset`, `stash`, `checkout --`, `clean` içermez. (`test_bat.py`)
- **K6** `python_denetle((3, 10, 0))` → `"eksik"`; `(3, 11, 0)` ve `(3, 14, 7)` → `"tamam"`. (`test_kontrol.py`)
- **K7** `ice_aktarma_denetle("olmayan_modul_xyz", "occt", zorunlu=False)` → `"uyari"`; aynısı `zorunlu=True` ile →
  `"eksik"`; `"json"` → `"tamam"`. Mesajlar SPEC 54 §1 biçimindedir (` — ` içerir). (`test_kontrol.py`)
- **K8** `on_yuz_denetle(tmp_path)`: `tezgah/arayuz/dist/index.html` yoksa `"eksik"` ve mesajda `npm` ile `dist`
  geçer; dosya varsa `"tamam"`. (`test_kontrol.py`)
- **K9** `port_denetle`: boş bir portta `"tamam"`; testte açılan ve Tezgah olmayan bir yuva dinlerken `"eksik"`.
  Test yalnızca 127.0.0.1 kullanır. (`test_kontrol.py`)
- **K10** `rapor`: `[tamam, tamam]` → 0; `[tamam, uyari]` → 2; `[uyari, eksik]` → 1; metin her maddeyi bir satırda
  `[TAMAM]/[UYARI]/[EKSİK] ad: mesaj` biçiminde verir. (`test_kontrol.py`)
- **K11** `kontrol.py` yalnızca stdlib içe aktarır (test: modül kaynağındaki `import` satırları stdlib listesinde). (`test_kontrol.py`)
- **K12 (elle kabul, kullanıcının Windows makinesi)** Temiz bir kopyada (OneDrive'lı masaüstü, boşluklu yol):
  (a) `kur.bat` çift tıklama → rapor 0 ya da 2; (b) masaüstünde `Tezgah.bat` çıkar, çift tıklayınca tarayıcı
  `http://127.0.0.1:8724/` açar; (c) `kur.bat` ikinci kez çalışınca hata vermez; (d) Tezgah açıkken `Tezgah.bat`
  ikinci sunucu açmaz; (e) `kaldir.bat` sonrası `~\3D-CORE projeleri\` yerinde durur. Sonuç `durum/55-*.md`'ye
  kullanıcının gözlemiyle yazılır. Windows CI eklenmez (`.github/` değişmez).

## Bağımlılıklar
- SPEC 24 (Tezgah, `tezgah` giriş noktası, `dist` denetimi, `/api/openapi.json` başlığı `"Tezgah"`).
- SPEC 54 §1 (mesaj biçimi) yalnızca metin kuralı olarak; 54 birleşmeden de uygulanabilir.
- Dalga 6 içinde başka SPEC'i beklemez; 48'in (gerçek tezgâh doğrulaması) atölye bilgisayarı ön koşuludur.

## Kapsam dışı
MSI / Inno Setup / PyInstaller tek exe; uv'yi ya da Node'u otomatik indirme; derlenmiş `dist` içeren sürüm zip'i ve
onu üreten Actions işi; `.lnk` kısayolu ve Başlat menüsü kaydı; Windows hizmeti olarak çalıştırma; macOS / Linux
masaüstü betikleri; otomatik güncelleme denetimi; ağdaki başka makinelerden erişim (sunucu 127.0.0.1'de kalır).

## Kararlar (açık soruların önerilen cevapları, onaylı)
1. uv yoksa betik **indirmez** (ağ ve güvenlik politikası); `kurulum\uv.exe` koyma yolu yeter.
2. Node'u olmayan atölye bilgisayarları için derlenmiş `dist`'li sürüm zip'i **Dalga 6 sonrası ayrı küçük PR**
   (yalnızca etiket itildiğinde çalışan tek Actions işi). Bu SPEC'te yok.
3. `.gitattributes`'a `*.bat text eol=crlf` eklenir. Depoda `* text=auto` olduğu için satır olmadan CRLF
   korunamıyor (K1 Linux'ta hep düşerdi); `.gitattributes` CLAUDE.md'deki ortak dosya listesinde olmadığından
   satır bu SPEC'in PR'ında, mevcut `*.ps1 text eol=crlf` satırının yanına eklenir.
4. "Port Tezgah'ta mı": SPEC 24'te `/api/saglik` yok; `GET /api/openapi.json` → `info.title == "Tezgah"` kullanılır
   (bkz. Arayüz).
