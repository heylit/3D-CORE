<#
  3D-CORE yerel CI - GitHub Actions'taki kontrolün aynısı, ücretsiz.

  Kullanım (proje kökünde, .venv aktif olsun ya da olmasın):
      .\ci.ps1            # lint + tüm testler + rapor + log
      .\ci.ps1 -Ac        # sonunda HTML raporu tarayıcıda açar
      .\ci.ps1 -Gecmis    # son 15 çalıştırmayı gösterir

  Çıktılar (git'e girmez):
      reports\rapor.html   test raporu
      reports\junit.xml    makine okunur sonuç
      reports\ci-log.csv   her çalıştırmanın tarihi, commit'i, sonucu
#>
param([switch]$Ac, [switch]$Gecmis)

Set-Location $PSScriptRoot
$log = "reports/ci-log.csv"

if ($Gecmis) {
    if (Test-Path $log) { Import-Csv $log -Delimiter ";" | Select-Object -Last 15 | Format-Table -AutoSize | Out-String -Width 200 | Write-Host }
    else { Write-Host "Henüz kayıt yok." }
    exit 0
}

$py = "python"
foreach ($aday in @(".venv/Scripts/python.exe", ".venv/bin/python")) {
    if (Test-Path $aday) { $py = $aday; break }
}

New-Item -ItemType Directory -Force reports | Out-Null
$baslangic = Get-Date
$commit = (git rev-parse --short HEAD 2>$null)
if (-not $commit) { $commit = "-" }
$kirli = (git status --porcelain 2>$null)
if ($kirli) { $commit = "$commit*" }   # * = commit edilmemiş değişiklik var

Write-Host "`n== 1/2 Lint (ruff) ==" -ForegroundColor Cyan
& $py -m ruff check .
$ruffKod = $LASTEXITCODE

Write-Host "`n== 2/2 Testler (pytest, slow dahil) ==" -ForegroundColor Cyan
& $py -m pytest -o addopts="" -q --junitxml=reports/junit.xml --html=reports/rapor.html --self-contained-html
$testKod = $LASTEXITCODE

$toplam = 0; $hata = 0; $atlanan = 0  # atlanan = occt yok + uygulanmamış (NotImplementedError)
if (Test-Path reports/junit.xml) {
    [xml]$j = Get-Content reports/junit.xml
    foreach ($s in $j.SelectNodes("//testsuite")) {
        $toplam  += [int]$s.tests
        $hata    += [int]$s.failures + [int]$s.errors
        $atlanan += [int]$s.skipped
    }
}
$gecen = $toplam - $hata - $atlanan
$sure = [math]::Round(((Get-Date) - $baslangic).TotalSeconds, 1)
$durum = if ($ruffKod -eq 0 -and $testKod -eq 0) { "GECTI" } else { "KALDI" }

if (-not (Test-Path $log)) { "tarih;commit;durum;gecen;kalan;atlanan;lint;sure_sn" | Out-File $log -Encoding utf8 }
$lint = if ($ruffKod -eq 0) { "ok" } else { "hata" }
"$($baslangic.ToString('yyyy-MM-dd HH:mm'));$commit;$durum;$gecen;$hata;$atlanan;$lint;$sure" | Add-Content $log -Encoding utf8

Write-Host ""
if ($durum -eq "GECTI") {
    Write-Host "  CI GECTI  |  $gecen test geçti  |  lint ok  |  $sure sn  |  $commit" -ForegroundColor Green
} else {
    Write-Host "  CI KALDI  |  $gecen geçti, $hata kaldı  |  lint $lint  |  $sure sn  |  $commit" -ForegroundColor Red
}
Write-Host "  Rapor: reports/rapor.html   Geçmiş: .\ci.ps1 -Gecmis`n"

if ($Ac) { Start-Process reports/rapor.html }
if ($durum -eq "GECTI") { exit 0 } else { exit 1 }
