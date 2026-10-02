# Восстановление 47 документов, испорченных 29.09.2026 в 18:39–18:42, из теневой копии Windows № 9.
# 1) копирует нынешние (испорченные) версии в Documents\antifraud\_backup_испорченные_29-09;
# 2) заменяет ровно эти файлы в корне Documents версиями из теневой копии; 3) сверяет SHA-256.
# Без -Apply только показывает список.
param([switch]$Apply)
$ErrorActionPreference = "Stop"
$docs = "C:\Users\DT-KazNu-PC\Documents"
$shadow = "\\?\GLOBALROOT\Device\HarddiskVolumeShadowCopy9\Users\DT-KazNu-PC\Documents"
$backup = "C:\Users\DT-KazNu-PC\Documents\antifraud\_backup_испорченные_29-09"
$from = [datetime]"2026-09-29 18:39:00"; $to = [datetime]"2026-09-29 18:42:00"
$list = @(Get-ChildItem -LiteralPath $docs -Filter *.docx -File | Where-Object { $_.LastWriteTime -ge $from -and $_.LastWriteTime -le $to } | Sort-Object Name)
if ($list.Count -ne 47) { throw "Ожидалось 47 файлов, найдено $($list.Count) — остановка." }
foreach ($f in $list) {
    if ($f.DirectoryName -ne $docs) { throw "Файл не в корне Documents: $($f.FullName)" }
    if (-not (Test-Path -LiteralPath ("$shadow\" + $f.Name))) { throw "В теневой копии нет: $($f.Name)" }
}
"Будут восстановлены ($($list.Count)):"; $list | ForEach-Object { "  {0}   (копия от {1:dd.MM.yyyy HH:mm})" -f $_.Name, (Get-Item -LiteralPath ("$shadow\" + $_.Name)).LastWriteTime }
"Резервная копия нынешних версий: $backup"
if (-not $Apply) { "Пробный режим: ничего не записано."; return }
New-Item -ItemType Directory -Force -Path $backup | Out-Null
foreach ($f in $list) { Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $backup $f.Name) }
"Резервных копий сделано: " + @(Get-ChildItem -LiteralPath $backup -File).Count
$ok = 0; $bad = @()
foreach ($f in $list) {
    $src = "$shadow\" + $f.Name
    Copy-Item -LiteralPath $src -Destination $f.FullName -Force
    $h1 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash; $h2 = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    if ($h1 -eq $h2) { $ok++ } else { $bad += $f.Name }
}
"Восстановлено и совпадает с копией: $ok из $($list.Count)"
if ($bad) { "НЕ совпали: " + ($bad -join ", ") }
