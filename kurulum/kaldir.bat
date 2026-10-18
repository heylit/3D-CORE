@echo off
rem SPEC 55 — yalnızca kurulumun yarattıklarını siler: .venv, masaüstü Tezgah.bat, kurulum\kurulum.log*.
rem Projeler (~\3D-CORE projeleri\), yerel_parcalar\, .3dc dosyaları ve depo dosyaları SİLİNMEZ.
setlocal EnableExtensions
chcp 65001 >nul
title Tezgah kaldırma
pushd "%~dp0.."
set "KOK=%CD%"
set "MASAUSTU="
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul ^| find /i "REG_"') do set "MASAUSTU=%%b"
if defined MASAUSTU call set "MASAUSTU=%MASAUSTU%"
if not defined MASAUSTU set "MASAUSTU=%USERPROFILE%\Desktop"
echo Silinecekler: "%KOK%\.venv", "%MASAUSTU%\Tezgah.bat", "%KOK%\kurulum\kurulum.log*"
echo Projeleriniz, parça dosyalarınız ve depo dosyaları silinmez.
set "YANIT="
set /p "YANIT=Devam edilsin mi? (E/H) "
if /i not "%YANIT%"=="E" (
  echo Vazgeçildi, hiçbir şey silinmedi.
  goto :son
)
if exist "%KOK%\.venv\" rmdir /s /q "%KOK%\.venv"
if exist "%MASAUSTU%\Tezgah.bat" del /q "%MASAUSTU%\Tezgah.bat"
if exist "%KOK%\kurulum\kurulum.log*" del /q "%KOK%\kurulum\kurulum.log*"
echo Kaldırıldı. Projeleriniz yerinde duruyor.
:son
popd
pause
exit /b 0
