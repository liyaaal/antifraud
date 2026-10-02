# Экспорт PDF четырёх документов проекта. Файлы открываются ТОЛЬКО НА ЧТЕНИЕ, docx не меняются.
# PDF пишутся в Documents\antifraud\docs\pdf. Любой путь вне разрешённой папки -> остановка.
param([Parameter(Mandatory = $true)][string]$Root, [switch]$Apply)
$ErrorActionPreference = "Stop"
$allowed = "C:\Users\DT-KazNu-PC\Documents\antifraud\docs\"
$docsDir = [IO.Path]::GetFullPath((Join-Path $Root "docs")) + "\"
if ($docsDir -ne $allowed) { throw "Папка $docsDir не разрешена — остановка." }
$names = @("Разбор_решений", "Текст_речи", "Отчёт", "Шпаргалка_к_защите")
$pdfDir = $allowed + "pdf\"
"Читаются: "; $names | ForEach-Object { "  $allowed$_.docx" }
"Пишутся:  "; $names | ForEach-Object { "  $pdfDir$_.pdf" }
if (-not $Apply) { "Пробный режим: ничего не записано."; return }
New-Item -ItemType Directory -Force -Path $pdfDir | Out-Null
$word = New-Object -ComObject Word.Application; $word.Visible = $false; $word.DisplayAlerts = 0
try {
    foreach ($n in $names) {
        $src = $allowed + $n + ".docx"; $pdf = $pdfDir + $n + ".pdf"
        if (-not $pdf.StartsWith($allowed)) { throw "Путь вне разрешённой папки: $pdf" }
        $doc = $word.Documents.Open($src, $false, $true, $false)
        $doc.ExportAsFixedFormat($pdf, 17, $false, 0, 0, 1, 1, 0, $true, $true, 0, $true, $true, $false)
        "{0}.pdf: страниц {1}" -f $n, $doc.ComputeStatistics(2)
        $doc.Close(0)
    }
} finally { $word.Quit() }
