# Шаг 2 сборки презентации: PowerPoint (COM) добавляет 3D, тени, анимации и переходы.
# Метки берутся из имён фигур, которые расставил build_deck.py:
#   "имя|fx=порядок:эффект:запуск:задержка:длительность|3d=пресет|dir=left"
# powershell -ExecutionPolicy Bypass -File presentation/fx.ps1 [-Render]
param([switch]$Render)

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $here "_base.pptx"
$dst = Join-Path $here "antifraud.pptx"

# Эффекты (MsoAnimEffect): fade, zoom (современное «Масштабирование»), rise («Подъём»), ascend («Выцветание вверх»),
# fly («Вылет» снизу), wipe («Появление» стиранием), appear.
$EFF = @{ fade = 10; zoom = 48; rise = 34; ascend = 39; fly = 2; wipe = 22; appear = 1 }
$TRIG = @{ click = 1; with = 2; after = 3 }

function Darken([int]$bgr, [double]$k) {
    $r = [int](($bgr -band 0xFF) * $k); $g = [int]((($bgr -shr 8) -band 0xFF) * $k); $b = [int]((($bgr -shr 16) -band 0xFF) * $k)
    return $r + ($g -shl 8) + ($b -shl 16)
}

function Parse([string]$name) {
    $parts = $name.Split("|")
    $t = @{ base = $parts[0] }
    foreach ($p in $parts[1..($parts.Length)]) { if ($p -and $p.Contains("=")) { $kv = $p.Split("=", 2); $t[$kv[0]] = $kv[1] } }
    return $t
}

function Softshadow($sh, [double]$transp, [int]$blur, [int]$dy) {
    $sh.Shadow.Visible = -1
    $sh.Shadow.ForeColor.RGB = 0
    $sh.Shadow.Transparency = $transp
    $sh.Shadow.Blur = $blur
    $sh.Shadow.OffsetX = 0
    $sh.Shadow.OffsetY = $dy
}

function Apply3D($sh, [string]$preset) {
    $td = $sh.ThreeD
    $fill = $sh.Fill.ForeColor.RGB
    switch -Wildcard ($preset) {
        "sphere" {
            $td.BevelTopType = 3; $td.BevelTopInset = $sh.Width / 2; $td.BevelTopDepth = $sh.Width / 2
            $td.PresetMaterial = 6; $td.PresetLighting = 15
        }
        "coin_*" {
            $td.RotationY = 65; $td.Depth = 6; $td.ExtrusionColor.RGB = (Darken $fill 0.72)
            $td.BevelTopType = 3; $td.BevelTopInset = 4; $td.BevelTopDepth = 2; $td.PresetMaterial = 6
            if ($preset -eq "coin_ghost") { $sh.Fill.Transparency = 0.35 }
        }
        "card_*" {
            $rx = @{ card_a = 332; card_b = 336; card_c = 340 }[$preset]
            $ry = @{ card_a = 12; card_b = 9; card_c = 6 }[$preset]
            $td.RotationX = $rx; $td.RotationY = $ry; $td.Perspective = -1; $td.FieldOfView = 40
            $td.Depth = 8; $td.ExtrusionColor.RGB = (Darken $fill 0.6)
            $td.BevelTopType = 7; $td.BevelTopInset = 5; $td.BevelTopDepth = 2
            Softshadow $sh 0.45 22 10
        }
        "tile" { $td.BevelTopType = 7; $td.BevelTopInset = 6; $td.BevelTopDepth = 2.5; Softshadow $sh 0.74 16 5 }
        "tile_dark" { $td.BevelTopType = 7; $td.BevelTopInset = 5; $td.BevelTopDepth = 2; Softshadow $sh 0.45 18 6 }
    }
}

$app = New-Object -ComObject PowerPoint.Application
$pres = $app.Presentations.Open($src, $false, $false, $false)
$slideNo = 0
$report = @()
foreach ($slide in $pres.Slides) {
    $slideNo++
    $todo = @()
    $z = 0
    foreach ($sh in @($slide.Shapes)) {
        $z++
        $t = Parse $sh.Name
        if ($sh.Type -eq 6) {  # группа: объём задаём каждой фигуре внутри
            foreach ($it in @($sh.GroupItems)) { $ti = Parse $it.Name; if ($ti["3d"]) { Apply3D $it $ti["3d"] }; $it.Name = $ti.base }
        }
        if ($t["3d"]) { Apply3D $sh $t["3d"] }
        if ($t["fx"]) {
            $f = $t["fx"].Split(":")
            $todo += [pscustomobject]@{ ord = [double]$f[0]; z = $z; eff = $f[1]; trig = $f[2]; delay = [double]$f[3]; dur = [double]$f[4]; dir = $t["dir"]; sh = $sh }
        }
        $sh.Name = $t.base
    }
    $seq = $slide.TimeLine.MainSequence
    foreach ($a in ($todo | Sort-Object ord, z)) {
        $e = $seq.AddEffect($a.sh, $EFF[$a.eff], 0, $TRIG[$a.trig])
        if ($a.dur -gt 0) { $e.Timing.Duration = $a.dur }
        if ($a.delay -gt 0) { $e.Timing.TriggerDelayTime = $a.delay }
        if ($a.eff -eq "wipe" -and $a.dir -eq "left") { $e.EffectParameters.Direction = 4 }
    }
    $tr = $slide.SlideShowTransition
    if ($slideNo -ge 4 -and $slideNo -le 6) { $tr.EntryEffect = 3954; $tr.Duration = 1.25 }   # «Морф»
    else { $tr.EntryEffect = 3849; $tr.Duration = 0.7 }                                        # плавное затухание
    $report += "слайд ${slideNo}: анимаций $($seq.Count), щелчков $(@($todo | Where-Object { $_.trig -eq 'click' } | Select-Object -ExpandProperty ord -Unique).Count)"
}
$pres.SaveAs($dst)
if ($Render) {
    $out = Join-Path $here "render"; New-Item -ItemType Directory -Force $out | Out-Null
    Get-ChildItem $out -Filter *.png | Remove-Item -Force -Confirm:$false
    $i = 1; foreach ($s in $pres.Slides) { $s.Export((Join-Path $out "slide-$i.png"), "PNG", 1600, 900); $i++ }
}
$pres.Close(); $app.Quit()
$report
"Сохранено: $dst"
