@echo off
rem SPEC 55 — Tezgah kurulumu: sanal ortam, paket, ön yüz, masaüstü başlatıcısı, hazırlık raporu.
rem Çift tıklayın. Tekrar çalıştırmak güvenlidir. "kur.bat /sessiz" sonda beklemez.
rem Çıkış kodu: 0 = tam, 2 = eksikle çalışır, 1 = çalışmaz.
setlocal EnableExtensions
chcp 65001 >nul
title Tezgah kurulumu
set "SESSIZ="
if /i "%~1"=="/sessiz" set "SESSIZ=1"
set "KOD=0"
pushd "%~dp0.."
set "KOK=%CD%"
set "LOG=%KOK%\kurulum\kurulum.log"
if exist "%LOG%" move /y "%LOG%" "%LOG%.1" >nul
echo ==== %DATE% %TIME% kur.bat ==== > "%LOG%"
call :yaz "Tezgah kurulumu: %KOK%"

rem ---- 1. uv: önce kurulum\uv.exe, sonra PATH
set "UV="
if exist "%KOK%\kurulum\uv.exe" set "UV=%KOK%\kurulum\uv.exe"
if not defined UV for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if not defined UV (
  call :yaz "kurulum: uv bulunamadı — https://docs.astral.sh/uv/ adresinden kurun ya da uv.exe'yi bu klasöre koyun, sonra kur.bat'ı yeniden çalıştırın"
  set "KOD=1"
  goto :son
)
call :yaz "uv: %UV%"

rem ---- 2. sanal ortam (varsa korunur)
if not defined TEZGAH_PYTHON set "TEZGAH_PYTHON=3.14"
set "PY=%KOK%\.venv\Scripts\python.exe"
if exist "%PY%" (
  call :yaz "sanal ortam: .venv var, korunuyor"
) else (
  call :yaz "sanal ortam: .venv kuruluyor (Python %TEZGAH_PYTHON%)"
  "%UV%" venv "%KOK%\.venv" --python %TEZGAH_PYTHON% >> "%LOG%" 2>&1
  if errorlevel 1 (
    call :yaz "kurulum: sanal ortam: uv venv başarısız — kurulum\kurulum.log'a bakın; TEZGAH_PYTHON ile başka bir sürüm deneyin"
    set "KOD=1"
    goto :son
  )
)

rem ---- 3. paket: önce web+cad, cad yoksa yalnız web
call :yaz "paket: .[web,cad] yükleniyor"
"%UV%" pip install --python "%PY%" -e ".[web,cad]" >> "%LOG%" 2>&1
if errorlevel 1 (
  call :yaz "paket: .[web,cad] yüklenemedi, .[web] deneniyor — OCCT olmadan devam"
  "%UV%" pip install --python "%PY%" -e ".[web]" >> "%LOG%" 2>&1
  if errorlevel 1 (
    call :yaz "kurulum: paket: .[web] de yüklenemedi — kurulum\kurulum.log'a bakın, internet bağlantısını denetleyin"
    set "KOD=1"
    goto :son
  )
)

rem ---- 4. ön yüz (tezgah\arayuz\dist)
if exist "%KOK%\tezgah\arayuz\dist\index.html" (
  call :yaz "ön yüz: derlenmiş, adım atlandı"
  goto :baslatici
)
where npm >nul 2>&1
if errorlevel 1 (
  call :yaz "kurulum: ön yüz: Tezgah ön yüzü derlenmemiş — Node.js kurun ya da derlenmiş dist klasörünü tezgah\arayuz\dist içine kopyalayın"
  set "KOD=1"
  goto :son
)
call :yaz "ön yüz: npm ci + npm run build"
pushd "%KOK%\tezgah\arayuz"
call npm ci >> "%LOG%" 2>&1
if errorlevel 1 goto :npm_hata
call npm run build >> "%LOG%" 2>&1
if errorlevel 1 goto :npm_hata
popd
goto :baslatici
:npm_hata
popd
call :yaz "kurulum: ön yüz: npm derlemesi başarısız — kurulum\kurulum.log'a bakın"
set "KOD=1"
goto :son

rem ---- 5. masaüstü başlatıcısı (OneDrive yönlendirmesi için kayıt defterinden)
:baslatici
set "MASAUSTU="
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul ^| find /i "REG_"') do set "MASAUSTU=%%b"
if defined MASAUSTU call set "MASAUSTU=%MASAUSTU%"
if not defined MASAUSTU set "MASAUSTU=%USERPROFILE%\Desktop"
if not exist "%MASAUSTU%\" set "MASAUSTU=%USERPROFILE%\Desktop"
set "BASLATICI=%MASAUSTU%\Tezgah.bat"
> "%BASLATICI%" echo @echo off
>> "%BASLATICI%" echo rem Tezgah başlatıcısı (kurulum\kur.bat yazdı; yeniden kurulumda üzerine yazılır)
>> "%BASLATICI%" echo call "%KOK%\kurulum\baslat.bat"
if errorlevel 1 (
  call :yaz "kurulum: başlatıcı: %BASLATICI% yazılamadı — kurulum\baslat.bat'ı elle çalıştırabilirsiniz"
  set "KOD=2"
) else (
  call :yaz "başlatıcı: %BASLATICI%"
)

rem ---- 6. hazırlık raporu
call :yaz ""
call :yaz "Hazırlık raporu:"
"%PY%" "%KOK%\kurulum\kontrol.py" --kok "%KOK%"
set "RKOD=%ERRORLEVEL%"
"%PY%" "%KOK%\kurulum\kontrol.py" --kok "%KOK%" >> "%LOG%" 2>&1
if %RKOD% GTR %KOD% set "KOD=%RKOD%"
if %RKOD%==1 set "KOD=1"

:son
call :yaz ""
if "%KOD%"=="0" call :yaz "Kurulum tamam. Masaüstündeki Tezgah.bat ile açın."
if "%KOD%"=="2" call :yaz "Kurulum eksikle tamam (yukarıdaki [UYARI] satırları). Masaüstündeki Tezgah.bat ile açın."
if "%KOD%"=="1" call :yaz "Kurulum tamamlanamadı. Yukarıdaki mesajı ve kurulum\kurulum.log'u okuyun."
popd
if not defined SESSIZ pause
exit /b %KOD%

:yaz
echo(%~1
>> "%LOG%" echo(%~1
exit /b 0
