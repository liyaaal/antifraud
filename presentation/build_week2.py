"""Презентация недели 2 (5–10 минут): паттерны, ошибки, v2, рабочая точка, приёмка.

python presentation/build_week2.py   ->  presentation/week2.pptx
Стиль — как у презентации недели 1 (build_deck.py). Все числа — из reports/week2/ (реальные запуски).
Текст для выступления — в заметках к слайдам.
"""
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
OUT = HERE / "week2.pptx"

DARK = RGBColor(0x14, 0x17, 0x1F)
DARK2 = RGBColor(0x1F, 0x24, 0x31)
INK = RGBColor(0x16, 0x1A, 0x22)
MUTED = RGBColor(0x5B, 0x64, 0x72)
CARD = RGBColor(0xF3, 0xF5, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xD6, 0x45, 0x2F)
RED_L = RGBColor(0xF2, 0x8B, 0x7D)
RED_SOFT = RGBColor(0xFB, 0xE4, 0xE0)
AMBER = RGBColor(0xE9, 0xA8, 0x3B)
AMBER_SOFT = RGBColor(0xFC, 0xF0, 0xDA)
TEAL = RGBColor(0x1F, 0x8A, 0x7A)
TEAL_L = RGBColor(0x5F, 0xD0, 0xBC)
TEAL_SOFT = RGBColor(0xDD, 0xF0, 0xEC)
GREY = RGBColor(0xB8, 0xBF, 0xCA)
GREY_D = RGBColor(0x8F, 0x97, 0xA3)
ON_DARK = RGBColor(0xAE, 0xB6, 0xC4)
HEAD, BODY = "Cambria", "Calibri"
NB = " "

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=16, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=None, name="txt"):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        for t, o in (para if isinstance(para, list) else [(para, {})]):
            r = p.add_run()
            r.text = t
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.color.rgb = o.get("color", color)
    tb.name = name
    return tb


def _fx3d(s, preset, fill):
    """Объём и тени как в презентации недели 1 (там их ставил fx.ps1 через PowerPoint; здесь — сразу в XML)."""
    from lxml import etree
    from pptx.oxml.ns import qn
    spPr = s._element.spPr
    for tag in ("a:effectLst", "a:scene3d", "a:sp3d"):
        for el in spPr.findall(qn(tag)):
            spPr.remove(el)
    def shadow(alpha, blur, dist):
        ef = etree.SubElement(spPr, qn("a:effectLst"))
        sh = etree.SubElement(ef, qn("a:outerShdw"), blurRad=str(int(blur * 12700)), dist=str(int(dist * 12700)),
                              dir="5400000", algn="t", rotWithShape="0")
        c = etree.SubElement(sh, qn("a:srgbClr"), val="000000")
        etree.SubElement(c, qn("a:alpha"), val=str(int(alpha * 1000)))
    dark = "{:02X}{:02X}{:02X}".format(*[int(v * 0.6) for v in (fill if fill is not None else RGBColor(0, 0, 0))])
    if preset == "tile":
        shadow(26, 16, 5)
    elif preset == "tile_dark":
        shadow(55, 18, 6)
    elif preset.startswith("card_"):
        shadow(55, 22, 10)
    elif preset == "sphere":
        shadow(35, 10, 4)
    sc = etree.SubElement(spPr, qn("a:scene3d"))
    if preset.startswith("card_"):
        rx, ry = {"card_a": (332, 12), "card_b": (336, 9), "card_c": (340, 6)}[preset]
        cam = etree.SubElement(sc, qn("a:camera"), prst="perspectiveFront", fov="2400000")
        etree.SubElement(cam, qn("a:rot"), lat=str(rx * 60000), lon=str(ry * 60000), rev="0")
    else:
        etree.SubElement(sc, qn("a:camera"), prst="orthographicFront")
    etree.SubElement(sc, qn("a:lightRig"), rig="threePt", dir="t")
    if preset == "sphere":
        w = int(s.width / 2)
        sp = etree.SubElement(spPr, qn("a:sp3d"), prstMaterial="plastic")
        etree.SubElement(sp, qn("a:bevelT"), w=str(w), h=str(w), prst="circle")
    elif preset.startswith("card_"):
        sp = etree.SubElement(spPr, qn("a:sp3d"), extrusionH=str(8 * 12700))
        etree.SubElement(sp, qn("a:bevelT"), w=str(5 * 12700), h=str(2 * 12700), prst="softRound")
        ec = etree.SubElement(sp, qn("a:extrusionClr"))
        etree.SubElement(ec, qn("a:srgbClr"), val=dark)
    else:
        sp = etree.SubElement(spPr, qn("a:sp3d"))
        inset = 5 if preset == "tile_dark" else 6
        etree.SubElement(sp, qn("a:bevelT"), w=str(inset * 12700), h=str(int(2.5 * 12700)), prst="softRound")


def shape(slide, kind, x, y, w, h, fill=CARD, line=None, lw=1.5, radius=None, name="shp", d3="auto"):
    s = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        s.fill.fore_color.rgb = fill
    if line:
        s.line.color.rgb = line
        s.line.width = Pt(lw)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if radius is not None and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if d3 == "auto":
        d3 = ("sphere" if kind == MSO_SHAPE.OVAL else
              ("tile_dark" if fill in (DARK, DARK2) else "tile") if kind == MSO_SHAPE.ROUNDED_RECTANGLE else None)
    if d3:
        _fx3d(s, d3, fill)
    s.name = name
    return s


def label_in(s, lines, size, color=WHITE, bold=True, font=HEAD, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE):
    tf = s.text_frame
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    tf.word_wrap = True
    lines = lines if isinstance(lines, list) else [(lines, {})]
    for i, (tx, o) in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = tx
        r.font.name = o.get("font", font)
        r.font.size = Pt(o.get("size", size))
        r.font.bold = o.get("bold", bold)
        r.font.color.rgb = o.get("color", color)
    return s


def title(slide, t, sub=None, dark=False):
    text(slide, 0.6, 0.4, 12.1, 0.7, t, size=28, font=HEAD, bold=True, color=WHITE if dark else INK, name="title")
    if sub:
        text(slide, 0.6, 1.1, 12.1, 0.45, sub, size=16, color=ON_DARK if dark else MUTED, name="sub")


LETTER = {"Назлы": "A", "Лия": "B", "Шырайлым": "C"}


def speaker(slide, who, dark=False):
    text(slide, 9.9, 7.02, 2.9, 0.3, f"говорит: {LETTER.get(who, who)}", size=11, color=GREY_D if dark else GREY,
         align=PP_ALIGN.RIGHT, name="who")


def source(slide, t, dark=False):
    text(slide, 0.6, 7.02, 9.0, 0.3, t, size=10, color=GREY_D if dark else GREY, name="src")


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


def table(slide, x, y, w, rows, col_w, size=13, head_fill=INK, zebra=CARD, row_h=0.42, bold_rows=(), name="tbl"):
    gt = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    gt.name = name
    tb = gt.table
    for j, cw in enumerate(col_w):
        tb.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tb.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            c = tb.cell(i, j)
            c.margin_left = c.margin_right = Inches(0.08)
            c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            c.fill.solid()
            c.fill.fore_color.rgb = head_fill if i == 0 else (zebra if i % 2 == 0 else WHITE)
            tf = c.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            if isinstance(val, tuple):
                val, col = val
            else:
                col = None
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            r = p.add_run()
            r.text = str(val)
            r.font.name = BODY
            r.font.size = Pt(size - (1 if i == 0 else 0))
            r.font.bold = i == 0 or i in bold_rows
            r.font.color.rgb = WHITE if i == 0 else (col or INK)
    return gt


def bar_chart(slide, x, y, w, h, cats, vals, colors, font_size=12, max_v=None, fmt="# ##0", name="chart"):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("знач.", vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    gf.name = name
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.name = BODY
    plot = ch.plots[0]
    plot.gap_width = 45
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = fmt
    dl.number_format_is_linked = False
    dl.position = XL_LABEL_POSITION.OUTSIDE_END
    dl.font.size = Pt(font_size + 1)
    dl.font.bold = True
    dl.font.color.rgb = INK
    va = ch.value_axis
    va.visible = False
    va.has_major_gridlines = False
    va.minimum_scale = 0
    if max_v:
        va.maximum_scale = max_v
    ca = ch.category_axis
    ca.reverse_order = True
    ca.tick_labels.font.size = Pt(font_size)
    ca.tick_labels.font.color.rgb = INK
    ca.format.line.fill.background()
    for i, pt in enumerate(plot.series[0].points):
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = colors[i]
    return gf


# =====================================================================
# 1. Титул
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
text(s, 0.8, 0.62, 7.3, 0.4, "ПРОЕКТ «АНТИФРОД» · НЕДЕЛЯ 2 · КОМАНДА ИЗ ТРЁХ УЧАСТНИЦ", size=13, color=ON_DARK, bold=True)
text(s, 0.8, 1.15, 7.2, 2.6, "Модель узнаёт мошенничество почти всегда. Деньги теряются в лимите проверок",
     size=32, font=HEAD, bold=True, color=WHITE)
text(s, 0.8, 3.75, 6.9, 1.0, "Мы разобрали мошенничество не по операциям, а по эпизодам, нашли, где и почему "
                             "решение ошибается, и сделали v2 — без переписывания.", size=16, color=ON_DARK)
stats = [("976", "эпизодов: один сценарий «захват карты на двое суток»", TEAL_L),
         ("98%", "упущенных денег модель узнала, но они не влезли в лимит 0,3%", WHITE),
         ("+3" + NB + "462", "у.е. у v2 на новом периоде; расхождение с оценкой 1,1 → 0,0 п.п.", WHITE)]
for i, (big, small, col) in enumerate(stats):
    x = 0.8 + i * 2.45
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 5.0, 2.25, 1.75, fill=DARK2, radius=0.08)
    text(s, x + 0.2, 5.12, 1.95, 0.7, big, size=30, font=HEAD, bold=True, color=col)
    text(s, x + 0.2, 5.85, 1.9, 0.85, small, size=11.5, color=ON_DARK)
for i, (l, role, quote, col, x, y, preset) in enumerate([
        ("A", "паттерны", "«как устроен эпизод»", RED, 8.35, 1.0, "card_a"),
        ("B", "ошибки", "«почему пропустили»", AMBER, 8.95, 2.3, "card_b"),
        ("C", "деньги", "«какую точку выбрать»", TEAL, 9.55, 3.6, "card_c")]):
    c = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 3.35, 2.1, fill=col, radius=0.09, d3=preset)
    label_in(c, [(l + "  ·  " + role, {"size": 19}), (quote, {"size": 13, "font": BODY, "bold": False}),
                 ("**** **** **** 48" + str(21 + i), {"size": 11, "font": BODY, "bold": False})],
             20, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    c.text_frame.margin_left = Inches(0.3)
    c.text_frame.margin_top = Inches(0.2)
speaker(s, "Назлы", dark=True)
notes(s, "Здравствуйте. Это вторая итерация нашего антифрода.\n\n"
         "На первой неделе мы построили систему, которая каждый день выбирает 0,3% операций для проверки аналитиками. "
         "На этой неделе задача была другая: не переписать, а понять, где и почему система ошибается, и доработать её.\n\n"
         "Три главных результата. Первое: в данных один устойчивый сценарий мошенничества — захват карты на двое "
         "суток, 976 таких эпизодов. Второе: модель его почти всегда узнаёт — 98% денег, которые мы упустили, модель "
         "узнала, но им не хватило места в лимите проверок. Третье: версия 2 на новом периоде, который никто не "
         "видел, дала плюс 3 462 у.е., и разница между нашей оценкой и реальным прогоном сократилась до нуля.\n\n"
         "Я расскажу про паттерны, Лия — про ошибки и новые признаки, Шырайлым — про деньги, выбор рабочей точки и ответы на ваши замечания.")

# =====================================================================
# 2. Паттерн: эпизод
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Мошенничество — это эпизод, а не операция", "Сценарий P1 «двухсуточный захват карты» — так его передали бы аналитику")
# Ось 48 часов
shape(s, MSO_SHAPE.RECTANGLE, 0.7, 3.35, 11.9, 0.05, fill=GREY)
blocks = [(0.7, "Ночь 1 · 00–03", "продукты в магазине ≈ 300 (2–4 раза)\n+ АЗС, продукты онлайн ≈ 10", AMBER, AMBER_SOFT),
          (3.75, "Вечер 1 · 22–23", "покупки онлайн ≈ 1 000, в магазине ≈ 880,\n«разное онлайн» ≈ 800, развлечения ≈ 500", RED, RED_SOFT),
          (6.8, "Ночь 2 · 00–03", "снова продукты ≈ 300\n+ мелочь ≈ 10–20", AMBER, AMBER_SOFT),
          (9.85, "Вечер 2 · 22–23", "снова крупные покупки ≈ 800–1 300\n→ конец эпизода", RED, RED_SOFT)]
for x, h, body, col, soft in blocks:
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.85, 2.75, 1.35, fill=soft, radius=0.08)
    text(s, x + 0.15, 1.95, 2.5, 0.4, h, size=15, bold=True, color=col)
    text(s, x + 0.15, 2.33, 2.5, 0.85, body, size=11.5, color=INK)
    shape(s, MSO_SHAPE.OVAL, x + 1.25, 3.24, 0.25, 0.25, fill=col)
text(s, 0.7, 3.55, 11.9, 0.35, [[("Начало: ", {"bold": True}), ("в 77% эпизодов — ночью, покупкой продуктов ≈ 300 или АЗС.   ", {}),
                                ("Конец: ", {"bold": True}), ("в 93% — вечером вторых суток.   ", {}),
                                ("Длительность: ", {"bold": True}), ("медиана 45 ч, ≈ 10 операций", {})]],
     size=13, color=MUTED)
facts = [("99,9%", "эпизодов: ни одной операции самого держателя внутри — карта целиком у мошенника", TEAL),
         ("976 из 999", "карт прошли через такой эпизод ровно один раз за 2 года", INK),
         ("каждый квартал", "одинаковая форма: 10 операций, ≈ 5 200 у.е., обе волны в 89–96%", INK)]
for i, (big, small, col) in enumerate(facts):
    x = 0.7 + i * 4.05
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 4.2, 3.8, 1.45, fill=CARD, radius=0.08)
    text(s, x + 0.2, 4.3, 3.4, 0.55, big, size=24, font=HEAD, bold=True, color=col)
    text(s, x + 0.2, 4.85, 3.45, 0.8, small, size=12.5, color=MUTED)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.7, 5.85, 11.9, 0.95, fill=TEAL_SOFT, radius=0.1)
text(s, 0.95, 5.97, 11.5, 0.8, [[("Для аналитика: ", {"bold": True, "color": TEAL}),
                                ("подтвердили одну операцию эпизода — всё, что пройдёт по карте в ближайшие двое суток, "
                                 "тоже мошенничество. Карту нужно блокировать, а не ждать следующих операций.", {})]],
     size=15)
source(s, "reports/week2/2_pattern_map.md · эпизод = операции фрода одной карты с паузами < 48 ч (макс. пауза в данных 43 ч)")
speaker(s, "Назлы")
notes(s, "На первой неделе мы шли от гипотез к данным. Сейчас наоборот — от данных к паттерну. И главное, что мы "
         "поменяли: смотрим не на одну операцию, а на эпизод — все мошеннические операции одной карты подряд.\n\n"
         "Оказалось, что в данных один устойчивый сценарий. Мы назвали его «двухсуточный захват карты». Начинается "
         "ночью: две-четыре покупки продуктов в магазине примерно по 300 и мелочь на заправке. Вечером того же дня, "
         "в 22–23 часа, — дорогие покупки онлайн и в магазинах, по 800–1300. На вторые сутки всё повторяется. "
         "Заканчивается вечером вторых суток. Всего около 10 операций за 45 часов.\n\n"
         "Самая сильная примета: в 99,9% эпизодов внутри нет ни одной операции самого держателя — карта полностью у "
         "мошенника. После эпизода держатель возвращается к обычным покупкам.\n\n"
         "Паттерн устойчивый: одна и та же форма в каждом квартале и на новых данных, и почти каждая карта проходит "
         "через него один раз. Вывод для аналитика: подтвердили одну операцию — блокируйте карту.")

# =====================================================================
# 3. Карта паттернов
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Карта паттернов: что модель ловит, а что нет", "Детекция v1 на valid + holdout → на новом периоде (fraudTest)")
rows = [["Паттерн", "Операций", "Сумма, у.е.", "Модель узнаёт\n(p ≥ 0,5)", "Отправлено\nаналитику, деньги", "Итог"],
        ["P1·в  Вечерняя волна крупных покупок", "3 749", "2 960 802", "98% → 96%", "70% → 80%", ("ловится уверенно", TEAL)],
        ["P1·н  Ночная волна: продукты ≈ 300", "2 105", "1 000 441", "99% → 98%", "44% → 57%", ("узнаёт, но не влезает", RED)],
        ["P1·м  Мелкие сопутствующие < 100", "1 652", "26 846", "80% → 76%", "5% → 15%", ("не покрываем сознательно", GREY_D)],
        ["P2  Тот же захват на новой карте", "841", "499 421", "97% → 97%", "75% → 72%", ("ловится (артефакт)", AMBER)]]
table(s, 0.6, 1.75, 12.1, rows, [4.0, 1.2, 1.5, 1.65, 1.85, 1.9], size=13, row_h=0.55)
text(s, 0.6, 4.75, 5.9, 0.4, "Проверили и не подтвердили — 7 гипотез", size=16, bold=True, font=HEAD)
hyp = ["тестовое мелкое списание перед крупным", "волна атак на много карт сразу (дисперсия/среднее = 1,04)",
       "общий магазин до атаки (p = 0,85)", "фрод у отдельных магазинов (χ², p = 0,94)",
       "далеко от дома (78 км у обоих классов)", "повторная атака на ту же карту", "нарастание сумм внутри эпизода"]
text(s, 0.6, 5.2, 6.2, 1.8, [[("✕  " + h, {})] for h in hyp], size=12, color=MUTED)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.1, 4.75, 5.6, 2.1, fill=CARD, radius=0.08)
text(s, 7.35, 4.88, 5.2, 1.95, [[("Почему волны — фазы одного сценария, а не разные паттерны? ", {"bold": True})],
                                [("Обе волны есть в 93% эпизодов, мелкие операции — в 87%. Если бы это были разные "
                                  "сценарии, они жили бы в разных эпизодах. Отдельными строками они стоят только потому, "
                                  "что модель ловит их по-разному.", {"color": MUTED})]], size=13.5)
source(s, "reports/week2/2_pattern_map.md, tables/patterns.md, tables/comparison_tables.md")
speaker(s, "Назлы")
notes(s, "Это карта паттернов. Сценарий один, но его фазы модель ловит по-разному.\n\n"
         "Вечерняя волна крупных покупок — ловится уверенно: модель узнаёт 98% операций, до аналитика доходит 70% "
         "денег, на новом периоде — 80%.\n\n"
         "Ночная волна — продукты по 300. Модель узнаёт её почти всю, 99%, но до аналитика доходит меньше половины "
         "денег. Почему — сейчас расскажет Лия.\n\n"
         "Мелкие операции до 100 у.е. мы сознательно не покрываем: это 22% операций, но меньше 1% денег.\n\n"
         "P2 — тот же захват, но на новой карте без истории. Тут мы нашли артефакт данных: каждая новая карта в этих "
         "данных начинается с мошенничества. Об этом — в оценке решения.\n\n"
         "Слева — семь гипотез, которые мы проверили на данных и не подтвердили: например, волны атак — старты "
         "эпизодов случайны, как у независимых событий. Справа — как мы проверили, что волны — это фазы одного "
         "сценария: они встречаются в одних и тех же эпизодах.")

# =====================================================================
# 4. Куда уходят деньги
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
title(s, "Куда уходят деньги: не в ошибки модели, а в лимит", "Упущенный фрод v1 за 122 дня (valid + holdout): 342 819 у.е.", dark=True)
parts = [(0.982, "336 726 у.е. · 98,2%", "модель узнала (обычно p = 1,00), но в этот день не хватило места в лимите", TEAL_L),
         (0.017, "5 994 у.е. · 1,7%", "модель не узнала", AMBER), (0.001, "99 у.е.", "мелочь: проверять дороже", GREY)]
x = 0.7
for frac, big, small, col in parts:
    w = max(11.9 * frac, 0.12)
    shape(s, MSO_SHAPE.RECTANGLE, x, 1.85, w, 0.75, fill=col)
    x += w
text(s, 0.7, 2.75, 7.8, 0.9, [[("336 726 у.е. · 98,2%  ", {"bold": True, "color": TEAL_L, "size": 22, "font": HEAD})],
                              [("модель узнала (обычно p = 1,00), но в этот день не хватило места в лимите", {"color": WHITE})]],
     size=15)
text(s, 8.9, 2.75, 3.8, 0.9, [[("5 994 · 1,7%  ", {"bold": True, "color": AMBER, "size": 22, "font": HEAD})],
                              [("модель не узнала", {"color": WHITE})]], size=15)
rows = [["Нагрузка дня", "Деньги остановлены", "Упущено, у.е."],
        ["фрода ≤ лимита", ("99%", TEAL), "447"],
        ["фрода > лимита", "87%", "24 453"],
        ["фрода > 2× лимита", ("51%", RED), ("317 919  (93% потерь)", RED)]]
table(s, 0.7, 4.05, 6.6, rows, [2.4, 2.0, 2.2], size=14, row_h=0.5, zebra=CARD)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.7, 4.05, 4.9, 2.55, fill=DARK2, radius=0.08)
text(s, 7.95, 4.2, 4.5, 2.35, [[("Самая дорогая ошибка", {"bold": True, "color": WHITE, "size": 17, "font": HEAD})],
                               [("покупка онлайн 1 124 у.е., 11.03: p = 0,73, но в тот день 22 фрод-операции при "
                                 "лимите 4 — она была 10-й в очереди.", {"color": ON_DARK})],
                               [("Признали ограничением лимита, а не модели. Цена закрытия посчитана — на слайде 7.",
                                 {"color": TEAL_L, "bold": True})]], size=14, spacing=6)
source(s, "reports/week2/3_error_analysis.md · tables/errors_tables.md", dark=True)
speaker(s, "Лия", dark=True)
notes(s, "Мы разобрали каждую упущенную операцию по причине. Это главный вывод недели.\n\n"
         "Из 343 тысяч упущенных денег 98% — это операции, которые модель узнала, обычно с вероятностью 1. Им просто "
         "не хватило места: аналитики проверяют 0,3% операций, а мошенничества в день бывает в несколько раз больше. "
         "Модель не узнала только 1,7% денег.\n\n"
         "Средняя метрика это скрывала. Разрез по нагрузке дня показывает: в дни, когда мошенничества не больше лимита, "
         "мы останавливаем 99% денег. В дни, когда его больше чем в два раза, — только половину, и там 93% всех потерь. "
         "То есть решение отказывает не на «сложных» операциях, а в «тяжёлые» дни.\n\n"
         "Самая дорогая единичная ошибка — покупка на 1 124 у.е. Модель была уверена, но в тот день 22 мошеннические "
         "операции на 4 места. Мы признали это ограничением лимита, а не ошибкой модели.")

# =====================================================================
# 5. Построчный просмотр
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Что показал построчный просмотр", "24 пропуска с историей держателя и все 57 ложных срабатываний — то, чего не видно в агрегатах")
cards = [("Пропуск ≠ ошибка", "Покупка онлайн 1 067 у.е., p = 1,00. В тот день 31 фрод при лимите 5. Из её эпизода "
                              "уже проверены 2 операции. Так в 11 из 12 дорогих пропусков: эпизод уже у аналитика.", TEAL, TEAL_SOFT),
         ("Фрод, похожий на обычную покупку", "Товары для дома 220 у.е. днём: среди похожих операций фрода 0 из 1 402. "
                                              "Кафе 140 у.е.: 0 из 2 871. По одной строке не отличить — только по "
                                              "окружению в эпизоде.", AMBER, AMBER_SOFT),
         ("Ложные: устойчивый тип клиента", "Крупная покупка онлайн 600–1 500 у.е. ночью: 33 из 57. p ≈ 0,3 при сумме "
                                            "1 000 → проверка выгодна заранее (≈ 300 у.е.). Калибровка честная: "
                                            "предсказано 0,38, на деле 0,37.", RED, RED_SOFT),
         ("Артефакт данных", "У части пропусков нет истории. Проверили: каждая карта, появившаяся в середине периода, "
                             "начинается с мошенничества — 71 из 71. Модель могла этому выучиться.", INK, CARD)]
for i, (h, body, col, soft) in enumerate(cards):
    x, y = 0.6 + (i % 2) * 6.15, 1.8 + (i // 2) * 2.55
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 5.95, 2.35, fill=soft, radius=0.07)
    shape(s, MSO_SHAPE.RECTANGLE, x, y + 0.2, 0.09, 1.95, fill=col)
    text(s, x + 0.3, y + 0.18, 5.45, 0.45, h, size=17, bold=True, font=HEAD, color=col)
    text(s, x + 0.3, y + 0.7, 5.45, 1.6, body, size=13.5, color=INK)
source(s, "tables/missed_review.md · tables/fp_review.md")
speaker(s, "Лия")
notes(s, "ТЗ требовало посмотреть ошибки построчно, вместе с историей клиента. Вот четыре вещи, которых не было в "
         "средних цифрах.\n\n"
         "Первое. Самые дорогие пропуски — не ошибки. Модель уверена на 100%, просто мест нет. И почти всегда из того "
         "же эпизода уже проверена другая операция — то есть в реальном банке карту бы уже заблокировали.\n\n"
         "Второе. Есть операции эпизода, которые выглядят как обычная жизнь: товары для дома на 220 днём, кафе на "
         "140. Среди тысяч похожих операций фрода ноль. Отличить их можно только по окружению — что было до них на "
         "этой карте.\n\n"
         "Третье. Ложные срабатывания — это устойчивый тип честного клиента: крупная покупка онлайн ночью. Вероятность "
         "около 0,3, но сумма 1 000, поэтому проверять её выгодно. Это осознанная ставка, а не сбой.\n\n"
         "Четвёртое. Мы заметили пустые истории и нашли артефакт: в этих данных все новые карты начинаются с "
         "мошенничества.")

# =====================================================================
# 6. v2: блок E и регрессии
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "v2: признаки под паттерн и контроль регрессий", "Блок E «эпизод захвата карты» — окно 48 ч, по длине эпизода")
feat = [("e_h_since_big", "сколько часов назад по карте была крупная операция"),
        ("e_usual_ratio", "обычные покупки клиента за 48 ч / его привычный темп"),
        ("e_usual_48h", "сколько обычных покупок было за 48 ч")]
text(s, 0.6, 1.75, 5.6, 0.4, "Вошли в v2 (3 из 8, отбор по одному на valid)", size=15, bold=True)
for i, (f, d) in enumerate(feat):
    y = 2.2 + i * 0.78
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, y, 5.7, 0.68, fill=AMBER_SOFT, radius=0.12)
    text(s, 0.8, y + 0.07, 5.4, 0.6, [[(f, {"bold": True, "color": INK, "font": "Consolas", "size": 13})],
                                      [(d, {"color": MUTED, "size": 12.5})]])
text(s, 0.6, 4.6, 5.7, 1.2, [[("Почему 48 ч, а не сессии блока B: ", {"bold": True}),
                             ("между ночной и вечерней волной пауза до 20 ч — сессия «паузa > 3 ч» рвёт эпизод "
                              "пополам. Отклонены: ночные за 48 ч, сумма за 48 ч, крупные за 48 ч (вклад < 0).", {"color": MUTED})]],
     size=13)
rows = [["Набор", "Δ v2 − v1, у.е.", "90% интервал", "Ложных"],
        ["valid (выбирали)", "+784", "[−21; +1 739]", "27 → 29"],
        ["holdout (своя оценка)", ("−2 103", RED), "[−4 823; +242]", "30 → 37"],
        ["приёмка, fraudTest", ("+3 462", TEAL), "[+55; +7 287]", "167 → 174"]]
table(s, 6.75, 1.75, 6.0, rows, [2.1, 1.3, 1.5, 1.1], size=13, row_h=0.5, bold_rows=(3,))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 6.75, 4.0, 2.9, 2.75, fill=TEAL_SOFT, radius=0.07)
text(s, 6.95, 4.12, 2.55, 2.6, [[("Лучше", {"bold": True, "color": TEAL, "size": 16, "font": HEAD})],
                                [("вечерняя волна: упущено на 3 366 у.е. меньше; декабрь 96,9% → 98,1% потолка", {})]],
     size=13, spacing=4)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 9.85, 4.0, 2.9, 2.75, fill=RED_SOFT, radius=0.07)
text(s, 10.05, 4.12, 2.55, 2.6, [[("Хуже", {"bold": True, "color": RED, "size": 16, "font": HEAD})],
                                 [("честные клиенты с несколькими крупными покупками подряд: +7 задержанных за полгода "
                                   "(600–1 000 у.е.: 58 → 80)", {})]], size=13, spacing=4)
text(s, 0.6, 5.95, 5.7, 0.9, [[("Механизм проверен построчно: ", {"bold": True}),
                              ("v2 убрала 17 ложных — одиночные покупки (165 ч с прошлой крупной), добавила 26 — "
                               "покупки через часы после крупной (30 ч).", {"color": MUTED})]], size=12.5)
source(s, "reports/week2/3_error_analysis.md, разделы 7–8 · reports/experiments.csv")
speaker(s, "Лия")
notes(s, "Новые признаки мы делали только после разбора, и адресно — под паттерн. Блок E смотрит на окно 48 часов, "
         "ровно по длине эпизода. Окно сессий из моей первой недели тут не подходит: между ночной и вечерней волной "
         "пауза до 20 часов, и сессия рвёт эпизод пополам.\n\n"
         "Из восьми признаков, добавляя по одному на valid, оставили три: сколько часов назад была крупная операция, "
         "и пропали ли обычные покупки клиента. Остальные дали минус или ноль.\n\n"
         "Контроль регрессий — справа. На valid плюс 784, на holdout минус 2 103, на новом периоде плюс 3 462. Все "
         "интервалы около нуля — честно: это небольшое улучшение.\n\n"
         "Что стало лучше: вечерняя волна и декабрь. Что хуже: честные клиенты, которые делают несколько крупных "
         "покупок подряд, — их стали задерживать чуть чаще. Механизм мы проверили построчно: v2 перестала дёргать "
         "одиночные покупки и стала чаще дёргать покупки, сделанные через несколько часов после другой крупной.")

# =====================================================================
# 7. Чувствительность, специфичность, рабочая точка
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Чувствительность, специфичность и рабочая точка", "v2 на приёмке (fraudTest, 194 дня): что даёт каждый уровень лимита")
cd = CategoryChartData()
cd.categories = ["0,1%", "0,2%", "0,3%", "0,5%", "0,75%", "1%"]
cd.add_series("чувствительность, деньги", (0.31, 0.57, 0.74, 0.90, 0.97, 0.99))
cd.add_series("чувствительность, штуки", (0.17, 0.36, 0.51, 0.71, 0.83, 0.89))
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.5), Inches(1.6), Inches(6.2), Inches(3.4), cd)
ch = gf.chart
ch.font.name = BODY
ch.font.size = Pt(11)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.value_axis.maximum_scale = 1.0
ch.value_axis.minimum_scale = 0
ch.value_axis.tick_labels.number_format = "0%"
ch.value_axis.tick_labels.number_format_is_linked = False
ch.value_axis.major_gridlines.format.line.color.rgb = CARD
ch.category_axis.tick_labels.font.size = Pt(11)
for ser, col in zip(ch.plots[0].series, [TEAL, GREY_D]):
    ser.format.line.color.rgb = col
    ser.format.line.width = Pt(2.5)
    ser.marker.format.fill.solid()
    ser.marker.format.fill.fore_color.rgb = col
    ser.marker.format.line.color.rgb = col
ch.plots[0].has_data_labels = False
text(s, 0.7, 5.05, 6.0, 0.3, "лимит аналитиков, % операций в сутки  ·  рабочая точка — 0,3%", size=11, color=MUTED,
     align=PP_ALIGN.CENTER)
rows = [["Лимит", "Проверок\nв сутки", "Честных задержано\nв месяц", "Фрод по\nденьгам", "Специфич-\nность", "Спасено\nв месяц"],
        [("0,3% (сейчас)", TEAL), "6,5", "27", "74%", "99,969%", "131 тыс."],
        ["0,5%", "9,2", "42", "90%", "99,951%", "159 тыс."],
        ["0,75%", "10,9", "53", "97%", "99,939%", "171 тыс."],
        ["1%", "11,7", "57", "99%", "99,935%", "174 тыс."]]
table(s, 7.0, 1.6, 5.8, rows, [1.3, 0.8, 1.1, 0.75, 0.95, 0.9], size=11.5, row_h=0.56, bold_rows=(1,))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.0, 4.6, 5.8, 1.15, fill=TEAL_SOFT, radius=0.08)
text(s, 7.2, 4.68, 5.45, 1.05, [[("Решает руководитель мониторинга ", {"bold": True, "color": TEAL}),
                                ("вместе с риск-менеджментом. Мы даём таблицу «аналитики → деньги → звонки честным». "
                                 "Рекомендация: 0,5–0,75%. Одна проверка стоит 3 у.е., а спасает 150–340.", {})]], size=12.5)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.5, 5.6, 6.2, 1.25, fill=AMBER_SOFT, radius=0.08)
text(s, 0.7, 5.68, 5.85, 1.15, [[("Специфичность 99,7% — это «пол», а не качество. ", {"bold": True, "color": INK}),
                                ("Честных 99,6%, проверяем ≤ 0,3% — даже если все проверки зря, она ≥ 99,7%. "
                                 "Информативно: 0,9 честного клиента в сутки и точность 86%.", {"color": MUTED})]], size=12.5)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.0, 5.9, 5.8, 0.95, fill=CARD, radius=0.08)
text(s, 7.2, 5.98, 5.45, 0.85, [[("Чувствительность в штуках упирается в лимит: ", {"bold": True}),
                                ("мест 1 574 на 2 145 фрод-операций → максимум 54%, у нас 51%. Смотрим деньги.", {"color": MUTED})]],
     size=12.5)
source(s, "reports/week2/5_sens_spec.md · tables/sens_spec_final_v2_test.md")
speaker(s, "Шырайлым")
notes(s, "Моя часть — деньги и выбор рабочей точки.\n\n"
         "Чувствительность — сколько мошенничества ловим. Специфичность — сколько честных не трогаем. Мы показываем их "
         "не одной точкой, а для каждого уровня лимита. Сейчас лимит 0,3%: 6–7 проверок в день, ловим 74% денег, "
         "около 27 честных клиентов в месяц получают звонок.\n\n"
         "Если поднять до 0,5% — ловим 90% денег, звонков 42 в месяц. При 0,75% — 97%. Одна проверка стоит банку 3 "
         "у.е., а дополнительная проверка спасает от 150 до 340. Значит, ограничение — люди, а не деньги. Наша "
         "рекомендация — 0,5–0,75%. Но решает не модель, а руководитель мониторинга вместе с риск-менеджментом, по "
         "этой таблице.\n\n"
         "Про специфичность 99,7%. Мошенничества меньше 1%, и мы проверяем не больше 0,3% операций. Поэтому даже если "
         "все проверки окажутся честными клиентами, специфичность всё равно не меньше 99,7%. Это пол, который даёт сам "
         "лимит, а не качество модели. Говорить заказчику надо штуки: 0,9 честного клиента в сутки и точность 86%.\n\n"
         "И чувствительность в штуках тоже упирается в лимит: больше 54% поймать нельзя физически, у нас 51%.")

# =====================================================================
# 8. Сравнение v1 / v2
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "v1 против v2 на новом периоде", "fraudTest: 21.06–31.12.2020, 555 719 операций, 0,39% фрода — не использовался ни в первой приёмке, ни в разработке")
rows = [["Показатель", "Было (v1)", "Стало (v2)", "За счёт чего"],
        ["Экономия, у.е.", "830 484", ("833 947", TEAL), "вечерняя волна: «крупная операция была недавно»"],
        ["Доля от лучшего возможного", "97,6%", ("98,0%", TEAL), "то же; декабрь 96,9% → 98,1%"],
        ["Точность", "86,7%", "86,2%", "+7 честных «серий крупных покупок»"],
        ["Чувствительность, деньги", "73,5%", "73,8%", "чаще выбираются дорогие операции эпизода"],
        ["Задержано честных в сутки", "0,86", "0,90", "то же, что точность"],
        ["Эпизодов с проверкой", "96,8%", "97,2%", "окно 48 ч видит эпизод целиком"],
        ["Деньги эпизодов до 1-й проверки", "118 417", ("111 683", TEAL), "эпизод попадает к аналитику раньше"]]
table(s, 0.6, 1.7, 12.1, rows, [3.3, 1.5, 1.5, 5.8], size=13, row_h=0.47)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 5.65, 6.2, 1.2, fill=TEAL_SOFT, radius=0.08)
text(s, 0.85, 5.73, 5.8, 1.1, [[("Расхождение «своя оценка ↔ приёмка»", {"bold": True, "color": TEAL})],
                               [("доля от лучшего: v1 −1,1 п.п. → v2 ", {}), ("0,0 п.п.", {"bold": True, "color": TEAL}),
                                ("  ·  точность: −5,9 → −4,8 п.п.", {})]], size=14)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.0, 5.65, 5.7, 1.2, fill=CARD, radius=0.08)
text(s, 7.2, 5.73, 5.35, 1.1, [[("Обе версии — тем же score.py, на тех же строках. ", {"bold": True}),
                               ("Интервал разницы по дням [+55; +7 287] — улучшение небольшое, но механизм объяснён.",
                                {"color": MUTED})]], size=13)
source(s, "reports/week2/6_comparison.md · experiments/w2_compare.py")
speaker(s, "Шырайлым")
notes(s, "Теперь сравнение. Обе версии мы прогнали одним и тем же score.py на новом периоде — с конца июня по "
         "декабрь 2020. Его не видели ни в первой приёмке, ни при разработке v2.\n\n"
         "Версия 2 спасла 833 947 у.е. против 830 484 у версии 1, это плюс 3 462. Доля от лучшего возможного выросла "
         "с 97,6 до 98%. За счёт чего: признак «крупная операция была недавно» помогает выбирать продолжение эпизода "
         "в вечерней волне.\n\n"
         "Что стало хуже: точность чуть упала — на 7 честных клиентов за полгода. Мы показали выше, почему.\n\n"
         "Отдельный показатель из ТЗ — расхождение между нашей оценкой и реальным прогоном. У v1 на новом периоде доля "
         "от лучшего была на 1,1 пункта ниже, чем мы обещали. У v2 — ровно столько, сколько обещали. Разница "
         "сократилась до нуля.")

# =====================================================================
# 8б. Ответы на замечания преподавателя
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Ответы на замечания преподавателя", "Группы риска теперь печатает сама программа — пример: score.py на fraudTest (v2)")
box = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 1.7, 6.3, 3.35, fill=DARK, radius=0.04)
con = ["Группы риска (по вероятности мошенничества):",
       "  ВЫСОКИЙ (p ≥ 0,90) «точно мошенник»    1 912",
       "  СРЕДНИЙ (0,10–0,90) «подозрительно»      668",
       "  НИЗКИЙ  (p < 0,10) «не мошенник»     553 139",
       "  Рисковых: 13,3 в день · отправлено: 6,5 в день",
       "",
       "Сверка с ответами: мошеннических 2 145",
       "  в группе «высокий»   1 889  (88,1%)",
       "  в группе «средний»     197   (9,2%)",
       "  в группе «низкий»       59   (2,8%)",
       "  Отправлено 1 264, из них мошенников 1 090 (86%)"]
text(s, 0.85, 1.85, 5.9, 3.1, [[(l, {"color": TEAL_L if i in (0, 6) else WHITE})] for i, l in enumerate(con)],
     size=12, font="Consolas")
rows = [["Замечание", "Ответ"],
        ["Группы: точно / средне / не мошенник", "src/risk.py, сводка при каждом запуске"],
        ["Из скольких рисковых помечаем", "13,3 рисковых в день → 6,5 проверок"],
        ["Сколько рисковых среди плохих", "97% фрода — рисковые, отправлено 51%"],
        ["Метрика PR", "PR-AUC 0,972 (у случайной — 0,004)"],
        ["Баланс плохих и хороших", "0,39% фрода, 1 на 259; веса вместо SMOTE"],
        ["«Точно 7 аналитиков?»", "7 проверок в день (0,3% от ≈ 2 500), не 7 человек"],
        ["Откуда 328", "потолок: провидец при том же лимите; мы 323 389 = 98,65%"],
        ["Почему не LogReg", "не видит «ночь И продукты И 300»: −26 тыс., PR-AUC 0,87"]]
table(s, 7.15, 1.7, 5.6, rows, [2.45, 3.15], size=11, row_h=0.47)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 5.3, 6.3, 1.55, fill=TEAL_SOFT, radius=0.08)
text(s, 0.85, 5.4, 5.85, 1.4, [[("Формула выбора: ", {"bold": True, "color": TEAL}),
                               ("EV = p · (сумма + 5) − 3 − (1 − p) · 25", {"bold": True, "font": "Consolas"})],
                              [("Группа — подпись для людей. К аналитику идут операции с наибольшей EV: покупка на 1 000 "
                                "из средней группы важнее покупки на 20 из высокой.", {"color": MUTED})]], size=13, spacing=4)
source(s, "reports/week2/1_remarks.md · tables/remarks_tables.md · tables/remarks_pr_curve.png")
speaker(s, "Шырайлым")
notes(s, "На прошлой защите вы дали нам замечания. Я расскажу, что мы с ними сделали.\n\n"
         "Первое — вы просили делить операции на «точно мошенник», «среднее» и «не мошенник» и чтобы программа сама "
         "показывала, сколько мошенников куда попало. Теперь так и есть. Слева — то, что программа печатает после "
         "запуска на новых данных. Высокий риск — вероятность от 0,9, там 99% действительно мошенники. Средний — от 0,1 "
         "до 0,9. Низкий — меньше 0,1. Из 2 145 мошенников 88% попали в высокий риск, 9% — в средний и только 3% — в "
         "низкий.\n\n"
         "Второе — из скольких рисковых мы помечаем. Рисковых около 13 в день, а проверить можно шесть-семь. Модель "
         "помечает рисковыми 97% мошенников, но к аналитику доходит только половина — мест не хватает. Поэтому внутри "
         "рисковых мы выбираем по деньгам.\n\n"
         "Третье — про «7 аналитиков». Это была наша неточная формулировка. Правильно — 7 проверок в день, а не 7 "
         "человек. По заданию проверять можно 0,3% операций, а в день их около 2 500.\n\n"
         "Четвёртое — откуда 328 тысяч. Это потолок: столько спас бы провидец, который заранее знает всех "
         "мошенников, при том же лимите. Мы спасли 323 тысячи — это 98,65% от потолка. Внизу формула, по которой мы "
         "выбираем операцию: вероятность умножить на сумму плюс 5, минус 3 за проверку, минус 25 за риск задержать "
         "честного.\n\n"
         "Пятое — метрика PR и баланс. Мошенничества меньше полпроцента, поэтому точность в целом ничего не говорит. "
         "PR-AUC у нас 0,97, у случайной модели — 0,004.\n\n"
         "И последнее — почему не логистическая регрессия. Она складывает признаки по одному и не видит сочетаний "
         "вроде «ночью И продукты И около 300». На тех же признаках она хуже на 26 тысяч.\n\n"
         "Одно уточнение: группа — это подпись для людей. Отправку решают деньги: покупка на 1 000 из средней группы "
         "важнее покупки на 20 из высокой.")

# =====================================================================
# 9. Где решение откажет первым
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Где решение откажет первым", "Стресс-тесты v2 на fraudTest: доля от лучшего возможного при лимите 0,3%")
bar_chart(s, 0.5, 1.6, 6.6, 4.6,
          ["как есть", "нет истории карт", "суммы × 1,5", "нет поля category", "время сдвинуто на +3 ч"],
          [0.980, 0.972, 0.951, 0.866, 0.851], [TEAL, GREY, AMBER, RED, RED], font_size=13, max_v=1.08, fmt="0.0%")
rows = [["Условие", "Что происходит"],
        ["Сдвиг времени +3 ч", ("−13 п.п., ложных ×3,2 — отказ №1", RED)],
        ["Фрода ×3", "лимит 0,3%: остаётся 27% убытка; 1%: 2%"],
        ["Суммы ×1,5 (рынок)", "−3 п.п., ложных ×3,3"],
        ["Нет истории карт", "−0,8 п.п., ложных +56%"],
        ["Новые честные карты", "к аналитику в 2,4 раза чаще"],
        ["Декабрь (сезон)", "ложных 1,77 в сутки вместо 0,5–0,9"]]
table(s, 7.4, 1.6, 5.4, rows, [2.1, 3.3], size=12.5, row_h=0.5)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.4, 5.3, 5.4, 1.55, fill=CARD, radius=0.08)
text(s, 7.6, 5.4, 5.05, 1.4, [[("Если автора нет месяц: ", {"bold": True}),
                              ("история карт не пополняется, калибровка стареет при сдвиге доли фрода, лимит в потоке "
                               "требует суточного счётчика. Что мониторить каждый день — в оценке решения.", {"color": MUTED})]],
     size=12.5)
source(s, "reports/week2/4_solution_evaluation.md · tables/stress_v2.md")
speaker(s, "Назлы")
notes(s, "Для инженера, который будет сопровождать решение, мы написали отдельный документ. Каждое ограничение "
         "в нём измерено, а не предположено.\n\n"
         "Мы ломали входные данные и смотрели, что будет. Первым решение откажет при сдвиге времени: если в выгрузке "
         "другой часовой пояс на 3 часа, теряем 13 пунктов и ложных тревог втрое больше — потому что весь паттерн "
         "держится на ночи и позднем вечере. Второе — если пропадёт поле категории. Смена масштаба сумм и отсутствие "
         "истории карт бьют слабее.\n\n"
         "Если мошенничества станет втрое больше, модель менять не надо — нужен лимит около 1%. Новых честных клиентов "
         "модель не считает мошенниками автоматически, но отправляет к аналитику в 2,4 раза чаще.\n\n"
         "И что сломается, если автора нет месяц: история карт перестанет пополняться, калибровка устареет, а в "
         "декабре вырастут ложные тревоги.")

# =====================================================================
# 10. Итог
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
title(s, "Итог и что мы предлагаем банку", dark=True)
items = [("1", "Структура", "Один устойчивый сценарий — двухсуточный захват карты. Вечерняя волна ловится уверенно, ночная "
                            "узнаётся, но не влезает в лимит, мелочь не покрываем сознательно. 7 гипотез отвергнуто.", TEAL_L),
         ("2", "Ошибки", "98% упущенных денег — лимит, а не модель. Решение отказывает в «тяжёлые» дни (93% потерь) "
                         "и при сдвиге времени.", AMBER),
         ("3", "v2", "+3 462 у.е. на новом периоде, расхождение с оценкой 1,1 → 0,0 п.п. Цена: +7 задержанных "
                     "честных за полгода.", WHITE)]
for i, (n, h, body, col) in enumerate(items):
    y = 1.35 + i * 1.2
    shape(s, MSO_SHAPE.OVAL, 0.7, y + 0.05, 0.55, 0.55, fill=DARK2)
    text(s, 0.7, y + 0.12, 0.55, 0.45, n, size=18, bold=True, color=col, align=PP_ALIGN.CENTER, font=HEAD)
    text(s, 1.5, y, 6.4, 1.15, [[(h + ". ", {"bold": True, "color": col}), (body, {"color": WHITE})]], size=15)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 8.3, 1.35, 4.4, 3.5, fill=DARK2, radius=0.06)
text(s, 8.55, 1.5, 4.0, 3.3, [[("Банку — два рычага без новой модели", {"bold": True, "color": TEAL_L, "size": 16, "font": HEAD})],
                              [("Блокировать карту после первой подтверждённой операции: ", {"bold": True, "color": WHITE}),
                               ("та же модель спасла бы 1,07 млн вместо 830 тыс. у.е. на новом периоде.", {"color": ON_DARK})],
                              [("Поднять лимит до 0,5–0,75%: ", {"bold": True, "color": WHITE}),
                               ("+28–40 тыс. у.е. в месяц, +15–26 звонков честным.", {"color": ON_DARK})]],
     size=13.5, spacing=8)
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.7, 5.15, 12.0, 1.6, fill=DARK2, radius=0.06)
text(s, 0.95, 5.27, 11.5, 1.4, [[("Замечания: ", {"bold": True, "color": WHITE}),
                                ("9 замечаний преподавателя — все разобраны: группы риска встроены в программу, «7 аналитиков» исправлено на "
                                 "«7 проверок в день», 328 и формула расписаны. Отклонили: группу как правило отправки (решают деньги) и SMOTE.",
                                 {"color": ON_DARK})],
                               [("С чего начали бы сейчас: ", {"bold": True, "color": WHITE}),
                                ("с эпизодов и потолка при разных лимитах, потом — с метрики «по картам» вместе с заказчиком, "
                                 "и только потом — признаки.", {"color": ON_DARK})]], size=14, spacing=6)
source(s, "reports/week2/1_remarks.md · 3_error_analysis.md · 4_solution_evaluation.md", dark=True)
speaker(s, "Шырайлым", dark=True)
notes(s, "Подводим итог.\n\n"
         "Первое — структура мошенничества: один устойчивый сценарий, двухсуточный захват карты. Мы знаем, какая его "
         "часть ловится, какая нет и почему.\n\n"
         "Второе — ошибки: почти все потери — это лимит проверок, а не модель. Решение отказывает в тяжёлые дни и "
         "при сдвиге времени.\n\n"
         "Третье — v2: небольшое, но объяснённое улучшение и сократившееся до нуля расхождение с нашей оценкой.\n\n"
         "Банку мы предлагаем два рычага, для которых не нужна новая модель. Блокировать карту после первой "
         "подтверждённой операции — та же модель тогда спасла бы 1,07 миллиона вместо 830 тысяч. И поднять лимит до "
         "0,5–0,75%.\n\n"
         "По замечаниям: все девять разобраны. Группы риска теперь печатает сама программа. Не согласились в одном: группа — это подпись, а решение об отправке по-прежнему принимается по деньгам.\n\n"
         "Если бы начинали заново — начали бы с эпизодов и потолка, а не с признаков. Спасибо, готовы к вопросам.")

prs.save(OUT)
print(f"OK -> {OUT}")
