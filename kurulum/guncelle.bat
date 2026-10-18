@echo off
rem SPEC 55 — depoyu ve ortamı günceller. Yerel değişikliklere asla dokunmaz.
setlocal EnableExtensions
chcp 65001 >nul
title Tezgah güncelleme
pushd "%~dp0.."
where git >nul 2>&1
if errorlevel 1 (
  echo kurulum: güncelleme: git bulunamadı — depo çekilmeden ortam yeniden eşitleniyor
  goto :kur
)
set "KIRLI="
for /f "delims=" %%i in ('git status --porcelain --untracked-files=no 2^>nul') do set "KIRLI=1"
if defined KIRLI (
  echo kurulum: güncelleme: yerel değişiklik var, git pull atlandı — değişiklikleri kaydedin ya da bırakın, sonra yeniden deneyin
  goto :kur
)
git pull --ff-only
if errorlevel 1 echo kurulum: güncelleme: git pull --ff-only başarısız — dal ileri sarılamıyor; depo olduğu gibi bırakıldı
:kur
popd
call "%~dp0kur.bat" /sessiz
set "KOD=%ERRORLEVEL%"
if /i not "%~1"=="/sessiz" pause
exit /b %KOD%
