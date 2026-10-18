@echo off
rem SPEC 55 — Tezgah başlatıcısı. Masaüstündeki Tezgah.bat bunu çağırır.
rem Pencere açık kaldıkça sunucu çalışır; kapatmak sunucuyu durdurur.
setlocal EnableExtensions
chcp 65001 >nul
title Tezgah
cd /d "%~dp0.."
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo kurulum: başlatma: sanal ortam yok — önce kurulum\kur.bat'ı çalıştırın
  pause
  exit /b 1
)
"%PY%" "%CD%\kurulum\kontrol.py" --yalniz-port >nul 2>&1
if errorlevel 2 goto :acik
if errorlevel 1 (
  echo kurulum: başlatma: 127.0.0.1:8724 başka bir program tarafından kullanılıyor — o programı kapatıp yeniden deneyin
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m tezgah
if errorlevel 1 pause
exit /b %ERRORLEVEL%

:acik
echo Tezgah zaten açık; tarayıcı açılıyor.
start "" http://127.0.0.1:8724/
exit /b 0
