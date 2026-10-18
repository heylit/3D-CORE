# Tezgah'ı Windows'a kurmak

Yönetici hakkı ve PowerShell gerekmez. Her şey bu klasörde ve kullanıcı klasörünüzde kalır.

## Bir kez
1. **uv** kurulu olmalı (<https://docs.astral.sh/uv/>). İnternet yoksa `uv.exe`'yi bu `kurulum` klasörüne koyun.
2. Ön yüz için **Node.js** gerekir; yoksa derlenmiş `dist` klasörünü `tezgah\arayuz\dist` içine kopyalayın.
3. `kurulum\kur.bat` dosyasına çift tıklayın. Sonda bir hazırlık raporu çıkar:
   - `[TAMAM]` hazır, `[UYARI]` o özellik kapalı ama program çalışır, `[EKSİK]` program çalışmaz (yanında ne
     yapılacağı yazar).
4. Masaüstünde **Tezgah.bat** belirir.

## Her gün
- Masaüstündeki **Tezgah.bat**'a çift tıklayın; tarayıcı `http://127.0.0.1:8724/` adresinde açılır.
- Açılan siyah pencere sunucudur: kapatırsanız Tezgah durur. Tezgah zaten açıksa ikinci kez açılmaz, yalnızca
  tarayıcı açılır.

## Güncellemek
`kurulum\guncelle.bat`: depoyu çeker (yerel değişiklik varsa çekmez, uyarır) ve ortamı yeniden eşitler.

## Kaldırmak
`kurulum\kaldir.bat`: yalnızca `.venv`, masaüstündeki `Tezgah.bat` ve `kurulum\kurulum.log` dosyalarını siler.
Projeleriniz (`3D-CORE projeleri`), parça dosyalarınız ve depo dosyaları silinmez.

## Sorun olursa
`kurulum\kurulum.log` dosyasında her adımın çıktısı vardır. Python sürümünü değiştirmek için `kur.bat`'tan önce
`set TEZGAH_PYTHON=3.12` verin (varsayılan 3.14).
