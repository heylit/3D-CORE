# Korumalı klasörlere giden dosyaları yerine taşır (tekrar çalıştırmak güvenli).
#   powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1
$kok = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force -Path "$kok\.claude\agents"    | Out-Null
New-Item -ItemType Directory -Force -Path "$kok\.github\workflows" | Out-Null
$tasimalar = @{
    "yazici.md"      = "$kok\.claude\agents\yazici.md"
    "dogrulayici.md" = "$kok\.claude\agents\dogrulayici.md"
    "test.yml"       = "$kok\.github\workflows\test.yml"
}
foreach ($ad in $tasimalar.Keys) {
    $kaynak = Join-Path $PSScriptRoot $ad
    if (Test-Path $kaynak) {
        Move-Item -Force $kaynak $tasimalar[$ad]
        Write-Host "tasindi: $ad"
    }
}
# Git hook'larini etkinlestir (repo varsa)
if (Test-Path "$kok\.git") {
    git -C $kok config core.hooksPath .githooks
    Write-Host "git hook'lari etkin (.githooks)"
}
Write-Host "Tamam. _kurulum klasorunu silebilirsin."
