"""Презентация v2: 10 слайдов, 3D-элементы, анимации, переходы «Морф». Все числа — из reports/ (реальные запуски).

Шаг 1 (этот скрипт): python-pptx раскладывает слайды -> presentation/_base.pptx.
    В имени фигуры — метки для шага 2: "имя|fx=порядок:эффект:запуск:задержка:длительность|3d=пресет|dir=left".
Шаг 2 (fx.ps1): PowerPoint через COM добавляет объём, тени, анимации, переходы -> presentation/antifraud.pptx.

python presentation/build_deck.py
powershell -ExecutionPolicy Bypass -File presentation/fx.ps1
"""
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
OUT = HERE / "_base.pptx"

DARK = RGBColor(0x14, 0x17, 0x1F)
DARK2 = RGBColor(0x1F, 0x24, 0x31)
INK = RGBColor(0x16, 0x1A, 0x22)
MUTED = RGBColor(0x5B, 0x64, 0x72)
CARD = RGBColor(0xF3, 0xF5, 0xF8)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
RED = RGBColor(0xD6, 0x45, 0x2F)
RED_L = RGBColor(0xF2, 0x8B, 0x7D)
AMBER = RGBColor(0xE9, 0xA8, 0x3B)
AMBER_SOFT = RGBColor(0xFC, 0xF0, 0xDA)
TEAL = RGBColor(0x1F, 0x8A, 0x7A)
TEAL_L = RGBColor(0x5F, 0xD0, 0xBC)
TEAL_SOFT = RGBColor(0xDD, 0xF0, 0xEC)
RED_SOFT = RGBColor(0xFB, 0xE4, 0xE0)
GREY = RGBColor(0xB8, 0xBF, 0xCA)
GREY_D = RGBColor(0x8F, 0x97, 0xA3)
ON_DARK = RGBColor(0xAE, 0xB6, 0xC4)
GOLD = RGBColor(0xD9, 0xA4, 0x3A)
HEAD, BODY = "Cambria", "Calibri"
NB = " "

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def tag(shp, name, fx=None, d3=None, direction=None):
    parts = [name]
    if fx:
        parts.append("fx=" + ":".join(str(v) for v in fx))
    if d3:
        parts.append("3d=" + d3)
    if direction:
        parts.append("dir=" + direction)
    shp.name = "|".join(parts)
    return shp


def bg(slide, color):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = color


def text(slide, x, y, w, h, runs, size=16, color=INK, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=None, name="txt", fx=None):
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
    return tag(tb, name, fx)


def shape(slide, kind, x, y, w, h, fill=CARD, line=None, lw=1.5, radius=None, name="shp", fx=None, d3=None,
          transparency=None, direction=None):
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
    if transparency is not None:
        clr = s.fill._xPr.find(qn("a:solidFill"))[0]
        clr.append(clr.makeelement(qn("a:alpha"), {"val": str(int((1 - transparency) * 100000))}))
    return tag(s, name, fx, d3, direction)


def label_in(s, lines, size, color=WHITE, bold=True, font=HEAD, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE):
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
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


def sphere(slide, x, y, d, color, letter="", size=20, name="sph", fx=None):
    s = shape(slide, MSO_SHAPE.OVAL, x, y, d, d, fill=color, name=name, fx=fx, d3="sphere")
    if letter:
        label_in(s, letter, size)
    return s


def title(slide, t, sub=None, dark=False):
    text(slide, 0.6, 0.42, 12.1, 0.8, t, size=34, font=HEAD, bold=True, color=WHITE if dark else INK, name="title",
         fx=(0, "fade", "with", 0, 0.6))
    if sub:
        text(slide, 0.6, 1.17, 12.1, 0.45, sub, size=16, color=ON_DARK if dark else MUTED, name="sub",
             fx=(0, "fade", "with", 0.1, 0.6))


def speaker(slide, who, dark=False):
    text(slide, 10.9, 7.02, 1.9, 0.3, f"говорит: {who}", size=10, color=GREY_D if dark else GREY,
         align=PP_ALIGN.RIGHT, name="who")


def bar_chart(slide, x, y, w, h, cats, vals, colors, font_size=12, max_v=None, name="chart", fx=None):
    cd = CategoryChartData()
    cd.categories = cats
    cd.add_series("у.е.", vals)
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.name = BODY
    plot = ch.plots[0]
    plot.gap_width = 40
    plot.has_data_labels = True
    dl = plot.data_labels
    dl.number_format = "# ##0"
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
    return tag(gf, name, fx, direction="left")


def notes(slide, t):
    slide.notes_slide.notes_text_frame.text = t


# =====================================================================
# 1. Титул
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
text(s, 0.8, 0.62, 7.5, 0.4, "ПРОЕКТ «АНТИФРОД» · КОМАНДА ИЗ ТРЁХ УЧАСТНИЦ", size=13, color=ON_DARK, bold=True,
     name="kicker", fx=(1, "fade", "after", 0, 0.5))
text(s, 0.8, 1.2, 7.3, 2.5, "Семь проверок в день, которые спасают больше всего денег", size=42, font=HEAD,
     bold=True, color=WHITE, name="headline", fx=(2, "ascend", "with", 0.1, 0.8))
text(s, 0.8, 3.75, 6.9, 0.9, "Система выбирает, какие операции по картам показать аналитикам, "
                             "и объясняет каждое решение тремя причинами.", size=17, color=ON_DARK,
     name="lead", fx=(3, "fade", "after", 0, 0.6))
stats = [("323" + NB + "389", "у.е. сэкономлено за 2 месяца", TEAL_L),
         ("98,7%", "от того, что вообще можно спасти", WHITE),
         ("30", "честных клиентов остановлено зря (у базовой модели — 72)", WHITE)]
for i, (big, small, col) in enumerate(stats):
    x = 0.8 + i * 2.45
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 5.0, 2.25, 1.65, fill=DARK2, radius=0.08, name=f"stat{i}",
          fx=(4, "rise", "after" if i == 0 else "with", 0.15 * i, 0.6), d3="tile_dark")
    text(s, x + 0.2, 5.12, 1.95, 0.7, big, size=30 if i == 0 else 32, font=HEAD, bold=True, color=col,
         name=f"statn{i}", fx=(4, "rise", "with", 0.15 * i, 0.6))
    text(s, x + 0.2, 5.85, 1.9, 0.7, small, size=12, color=ON_DARK, name=f"statt{i}",
         fx=(4, "rise", "with", 0.15 * i, 0.6))
cards = [("A", "профиль клиента", "«так хозяин не платит»", RED, 8.35, 1.0, "card_a"),
         ("B", "ритм операций", "«карту выкачивают»", AMBER, 8.95, 2.3, "card_b"),
         ("C", "деньги", "«что выгоднее проверить»", TEAL, 9.55, 3.6, "card_c")]
for i, (l, role, quote, col, x, y, preset) in enumerate(cards):
    c = shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 3.35, 2.1, fill=col, radius=0.09, name=f"card{l}",
              fx=(5 + i, "fly", "after", 0.05, 0.7), d3=preset)
    label_in(c, [(l + "  ·  " + role, {"size": 19}), (quote, {"size": 13, "font": BODY, "bold": False}),
                 ("**** **** **** 48" + str(21 + i), {"size": 11, "font": BODY, "bold": False})],
             20, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP)
    c.text_frame.margin_left = Inches(0.3)
    c.text_frame.margin_top = Inches(0.2)
speaker(s, "A", dark=True)
notes(s, "Слайд появляется сам: заголовок, три главных числа, три карты — это мы трое.\n\n"
         "Здравствуйте. Мы — команда из трёх человек. Задача: банк получает поток операций по картам, а аналитиков, "
         "которые могут проверить подозрительную операцию, мало. Нужно каждый день выбирать, какие операции им показать.\n\n"
         "Главный результат сразу: на двух месяцах, которые мы до конца не открывали, система сэкономила 323 389 "
         "условных единиц. Это 98,7% от того, что вообще можно было спасти при таком числе аналитиков. И она зря "
         "остановила всего 30 честных клиентов — у базовой модели было 72.\n\n"
         "У каждой из нас было своё решение: A смотрела на привычки клиента, B — на ритм операций, C — на деньги. "
         "Дальше расскажем, как мы их сравнили и собрали лучшее.")

# =====================================================================
# 2. Инсайт про лимит
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
title(s, "Мошенников больше, чем проверяющих", "Один средний день в данных", dark=True)
x0, d, step = 0.95, 0.66, 0.83
for i in range(14):
    sphere(s, x0 + i * step, 2.35, d, RED, name=f"f{i}", fx=(1, "zoom", "after", 0, 0.18))
text(s, 0.95, 3.32, 9, 0.5, [[("≈14", {"size": 26, "bold": True, "color": RED_L, "font": HEAD}),
                             ("  мошеннических операций в день — 0,58% потока", {"size": 17, "color": WHITE})]],
     name="lbl14", fx=(2, "fade", "after", 0, 0.5))
shape(s, MSO_SHAPE.RECTANGLE, x0 + 7 * step - 0.12, 2.2, 7 * step + 0.1, d + 0.3, fill=DARK, transparency=0.4,
      name="dim", fx=(3, "fade", "click", 0, 0.6))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x0 - 0.13, 2.2, 7 * step + 0.1, d + 0.3, fill=None, line=TEAL_L, lw=3,
      radius=0.2, name="frame7", fx=(3, "wipe", "with", 0, 0.7), direction="left")
text(s, 0.95, 3.95, 9, 0.5, [[("≈7", {"size": 26, "bold": True, "color": TEAL_L, "font": HEAD}),
                             ("  успевают проверить аналитики — лимит 0,3% операций", {"size": 17, "color": WHITE})]],
     name="lbl7", fx=(4, "fade", "after", 0, 0.5))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.95, 4.85, 11.45, 1.75, fill=DARK2, radius=0.08, name="callout",
      fx=(5, "rise", "click", 0, 0.6), d3="tile_dark")
text(s, 1.35, 5.07, 5.1, 1.4, [[("62%", {"size": 44, "bold": True, "color": TEAL_L, "font": HEAD})],
                               [("денег спасла бы даже идеальная модель, которая заранее знает правду",
                                 {"size": 14, "color": ON_DARK})]],
     name="c62", fx=(5, "rise", "with", 0.1, 0.6))
text(s, 6.5, 5.2, 5.6, 1.3, [[("Поэтому главный вопрос не «насколько вероятно мошенничество», а ", {"color": WHITE}),
                              ("«какие 7 операций проверить сегодня, чтобы спасти больше всего денег»",
                               {"bold": True, "color": TEAL_L})]],
     size=18, name="cq", fx=(5, "rise", "with", 0.2, 0.6))
speaker(s, "B", dark=True)
notes(s, "Шарики появляются сами — это мошеннические операции одного дня.\n\n"
         "Первое, что мы увидели в данных. В среднем за день проходит около 14 мошеннических операций. "
         "А аналитики, по условию, успевают проверить только 0,3% операций — это примерно 7 в день.\n\n"
         "[КЛИК] — рамка вокруг семи шариков, остальные гаснут.\n"
         "Вот эти семь аналитики успеют проверить. Остальные семь — нет, как бы хорошо мы ни искали.\n\n"
         "[КЛИК] — появляется вывод.\n"
         "Мы посчитали: даже идеальная модель, которая заранее знает правду, спасла бы только 62% денег. Это наш "
         "потолок. Поэтому вопрос не «насколько вероятно мошенничество», а «какие семь операций проверить сегодня, "
         "чтобы спасти больше всего денег». Это определило всю нашу работу.")

# =====================================================================
# 3. Как система решает
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Как система выбирает, что проверить", "Пять шагов для каждой операции — от оплаты до карточки аналитика")
steps = [("Операция", ["сумма, категория, время, карта"], INK),
         ("Признаки", ["A — привычки клиента", "B — ритм операций", "C — сумма в категории"], INK),
         ("Вероятность", ["модель LightGBM: насколько похоже на мошенничество"], INK),
         ("Польза, у.е.", ["сколько денег в среднем спасёт проверка"], TEAL),
         ("Топ-7 за день", ["уходят аналитику с тремя причинами"], TEAL)]
w, gap = 2.3, 0.2
for i, (h, body, col) in enumerate(steps):
    x = 0.6 + i * (w + gap)
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.85, w, 1.9, fill=CARD if i < 3 else TEAL_SOFT, radius=0.08,
          name=f"step{i}", fx=(1 + i, "ascend", "after", 0, 0.45), d3="tile")
    sphere(s, x + 0.18, 2.02, 0.44, TEAL if i >= 3 else INK, str(i + 1), 13, name=f"stepn{i}",
           fx=(1 + i, "ascend", "with", 0, 0.45))
    text(s, x + 0.72, 2.1, w - 0.85, 0.4, h, size=15, bold=True, color=col, name=f"steph{i}",
         fx=(1 + i, "ascend", "with", 0, 0.45))
    text(s, x + 0.2, 2.65, w - 0.35, 1.05, body, size=12.5, color=MUTED, name=f"stepb{i}",
         fx=(1 + i, "ascend", "with", 0, 0.45))
    if i < 4:
        shape(s, MSO_SHAPE.CHEVRON, x + w + 0.03, 2.65, 0.14, 0.3, fill=GREY, name=f"arr{i}",
              fx=(1 + i, "fade", "with", 0, 0.3))
text(s, 0.6, 4.1, 5.6, 0.4, "Пример: какую из двух операций проверить?", size=16, bold=True, font=HEAD,
     name="exh", fx=(6, "fade", "click", 0, 0.4))
for i, (a, b, col, fill) in enumerate([("900 у.е., вероятность 30%", "проверка в среднем спасает ≈ 251 у.е.", TEAL, TEAL_SOFT),
                                       ("4 у.е., вероятность 90%", "проверка спасает ≈ 3 у.е.", MUTED, CARD)]):
    y = 4.6 + i * 1.1
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, y, 5.6, 0.95, fill=fill, radius=0.12, name=f"ex{i}",
          fx=(6, "rise", "with", 0.15 * (i + 1), 0.5), d3="tile")
    text(s, 0.85, y + 0.13, 5.2, 0.8, [[(a, {"bold": True, "size": 15})],
                                       [("→ " + b, {"bold": True, "color": col, "size": 14})]],
         name=f"ext{i}", fx=(6, "rise", "with", 0.15 * (i + 1), 0.5))
text(s, 6.9, 4.1, 5.9, 0.4, "Та же модель, другое правило выбора:", size=16, bold=True,
     font=HEAD, name="chh", fx=(7, "fade", "click", 0, 0.4))
bar_chart(s, 6.75, 4.5, 6.1, 1.7, ["Самые вероятные", "Самые выгодные"], [166067, 235437], [GREY, TEAL],
          font_size=13, max_v=300000, name="ch", fx=(7, "wipe", "with", 0.1, 0.9))
text(s, 6.9, 6.3, 5.9, 0.6, [[("+69 тыс. у.е. (+42%)", {"bold": True, "color": TEAL, "size": 22, "font": HEAD}),
                             ("  без нового признака", {"size": 15, "color": MUTED})]],
     name="plus", fx=(8, "zoom", "after", 0, 0.5))
speaker(s, "C")
notes(s, "Пять шагов появляются сами, по очереди.\n\n"
         "Вот как работает система. Приходит операция — сумма, категория, время, карта. По истории карты считаем "
         "признаки: это идеи A, B и C. Модель оценивает вероятность мошенничества. Дальше главный шаг: переводим "
         "вероятность в деньги — сколько в среднем спасёт проверка этой операции. И каждый день отдаём аналитикам семь "
         "самых выгодных, с тремя причинами обычными словами.\n\n"
         "[КЛИК] — пример.\n"
         "Покупка на 900 у.е. с вероятностью мошенничества 30% — проверка в среднем спасает около 251 у.е. Покупка на "
         "4 у.е. с вероятностью 90% — около 3. Проверяем первую, хотя она «менее подозрительная».\n\n"
         "[КЛИК] — график.\n"
         "Сначала мы отправляли самые вероятные операции. Когда перешли на самые выгодные, та же самая модель "
         "сэкономила на 69 тысяч больше — плюс 42%, без единого нового признака. Это самый большой эффект проекта.")

# =====================================================================
# 4–6. Три решения (переход «Морф»: шары A/B/C)
# =====================================================================
SOL = [
    ("A", RED, RED_SOFT, "Решение A: «Так хозяин не платит»", "Профиль клиента · логистическая регрессия",
     "Картой пользуется чужой человек — у него другие привычки.",
     ["Сравниваем операцию с прошлым этой карты: редкая категория, непривычное время, сумма больше обычной.",
      "«Неожиданность» считаем в битах и складываем. У новой карты профиль — как у «среднего клиента».",
      "Простую модель взяли нарочно: проверить, хватит ли её при хороших признаках."],
     [("+18,7 тыс.", "крупная сумма в непривычное время"), ("+17,2 тыс.", "в последние дни тратит крупнее обычного"),
      ("+5,8 тыс.", "непривычное время суток")],
     [("Итог: 224" + NB + "148 у.е.", True), ("Лучше всех ловит первую операцию кражи.", False),
      ("Простой модели не хватило: те же признаки на деревьях — 245" + NB + "302.", False)],
     ("Та же модель без признаков A", 173562, "Решение A", 224148)),
    ("B", AMBER, AMBER_SOFT, "Решение B: «Карту выкачивают»", "Ритм операций · LightGBM с запретом",
     "После кражи идёт серия: ~10 операций за двое суток, пауза ≈ 1 час.",
     ["Плавная память вместо окна «за 24 часа»: давняя операция весит меньше свежей.",
      "Сравниваем с нормой клиента: «в 3 раза активнее обычного», а не «5 операций в день».",
      "Режем поток на «сессии атаки». Модели запрещено снижать риск при росте активности."],
     [("+10,9 тыс.", "сколько денег списано за последние сутки"), ("+4,3 тыс.", "пауза после прошлой операции"),
      ("+2,4 тыс.", "сумма растёт внутри серии")],
     [("Итог: 251" + NB + "417 у.е. — 98,4% потолка", True), ("Лучше всех ловит продолжение серии.", False),
      ("Запрет ничего не стоил по деньгам, а модель стала предсказуемее.", False)],
     ("Та же модель без признаков B", 235437, "Решение B", 251417)),
    ("C", TEAL, TEAL_SOFT, "Решение C: «Что выгоднее проверить»", "Деньги · LightGBM, который «учится деньгам»",
     "Решение принимается по деньгам — при жёстком лимите аналитиков.",
     ["Выбор по пользе проверки в у.е. (слайд 3) — самый большой эффект проекта.",
      "Модель «учится деньгам»: пропущенный дорогой фрод при обучении весит больше дешёвого.",
      "Риск категорий — только по меткам старше 30 дней: банк узнаёт о краже не сразу."],
     [("+69,4 тыс.", "выбор по деньгам, а не по вероятности"), ("+3,2 тыс.", "обучение с весами по деньгам"),
      ("≈" + NB + "0", "цена реализма: задержка меток 30 дней")],
     [("Итог: 239" + NB + "249 у.е.", True), ("Риск среды деревьям не нужен, простой модели дал +9,2 тыс.", False),
      ("Без меток (Isolation Forest) — 167 тыс.: необычное ≠ мошенническое.", False)],
     ("База, выбор по вероятности", 166067, "Решение C", 239249)),
]
NOTES_SOL = {
    "A": "Всё появляется само.\n\n"
         "Моё решение — про привычки. Если картой пользуется чужой человек, он покупает не то, не тогда и не на такие "
         "суммы, как хозяин. Я для каждой операции считала, насколько она неожиданна именно для этой карты: как редко "
         "клиент покупает в этой категории, в это время суток, на такую сумму.\n\n"
         "У новой карты истории нет. У меня её профиль равен профилю «среднего клиента» и постепенно становится своим, "
         "поэтому модель работает с первой же операции.\n\n"
         "Лучше всего сработали «крупная сумма в непривычное время» — плюс 18,7 тысячи — и «последние дни клиент тратит "
         "крупнее обычного» — плюс 17,2. Я специально взяла простую модель, чтобы проверить, хватит ли её. Не хватило: "
         "те же признаки на деревьях дают на 21 тысячу больше. Это честный отрицательный результат. Зато мои признаки "
         "лучше всех ловят самую первую операцию кражи.",
    "B": "Шарик B вырастает — моя очередь. Всё появляется само.\n\n"
         "Моё решение — про ритм. В данных мошенничество идёт сериями: около десяти операций за двое суток, пауза между "
         "ними — около часа. Я смотрела не на то, что покупают, а на то, как часто и сколько списывают.\n\n"
         "Обычно считают «сколько операций за 24 часа». Но тогда операция 23 часа назад считается, а 25 часов назад — "
         "уже нет. У меня память плавная: чем старше операция, тем меньше весит. И я сравниваю с нормой клиента: пять "
         "операций в день — норма для одного и тревога для другого.\n\n"
         "Самый сильный признак — сколько денег уже списано с карты за сутки: плюс 10,9 тысячи. Ещё я запретила модели "
         "снижать риск, когда активность растёт: по деньгам это ничего не стоило, а модель ведёт себя предсказуемо. "
         "98,4% от потолка, лучше всех ловит продолжение серии.",
    "C": "Шарик C вырастает. Всё появляется само.\n\n"
         "Моё решение — про деньги. Правило выбора по пользе проверки, которое вы видели на третьем слайде, — это моя "
         "часть, и это самый большой эффект: плюс 69 тысяч.\n\n"
         "Ещё я учила модель «думать деньгами»: при обучении пропущенный дорогой фрод весит больше, чем дешёвый. "
         "Небольшой, но стабильный плюс.\n\n"
         "Мои признаки — риск категорий по прошлым случаям мошенничества. В банке о краже узнают не сразу, а после "
         "жалобы клиента, поэтому я брала только метки старше 30 дней. Реализм ничего не стоил, а вариант «метки того "
         "же дня» наш тест поймал как подглядывание в будущее.\n\n"
         "Честно: деревьям эти признаки не помогли — модель и так видит категорию и час, зато простой модели дали "
         "плюс 9 тысяч. И мы проверили модель без меток: она сильно хуже — необычное не значит мошенническое.",
}
for letter, color, soft, ttl, sub, scen, idea, wins, result, cmp in SOL:
    s = prs.slides.add_slide(BLANK)
    bg(s, WHITE)
    # Шары A/B/C с одинаковыми именами на трёх слайдах: «Морф» плавно меняет их размер и цвет.
    for j, (L, col) in enumerate([("A", RED), ("B", AMBER), ("C", TEAL)]):
        active = L == letter
        dd = 1.0 if active else 0.5
        cx = 10.4 + j * 0.9
        sphere(s, cx - dd / 2, 0.92 - dd / 2, dd, col if active else GREY, L, 26 if active else 13, name=f"!!sph{L}")
    text(s, 0.6, 0.42, 9.3, 0.8, ttl, size=32, font=HEAD, bold=True, name="!!soltitle")
    text(s, 0.6, 1.14, 9.3, 0.45, sub, size=16, color=MUTED, name="!!solsub")
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 1.8, 6.85, 0.62, fill=soft, radius=0.3, name="scenbox",
          fx=(1, "fade", "after", 0.3, 0.5))
    text(s, 0.85, 1.8, 6.45, 0.62, [[("Сценарий. ", {"bold": True, "color": color}), (scen, {})]], size=15,
         anchor=MSO_ANCHOR.MIDDLE, name="scen", fx=(1, "fade", "with", 0, 0.5))
    for k, t in enumerate(idea):
        y = 2.7 + k * 0.78
        sphere(s, 0.6, y + 0.02, 0.36, color, str(k + 1), 11, name=f"in{k}", fx=(2 + k, "zoom", "after", 0, 0.35))
        text(s, 1.12, y, 6.3, 0.72, t, size=14.5, name=f"it{k}", fx=(2 + k, "fade", "with", 0.1, 0.4))
    text(s, 0.6, 5.2, 6.85, 0.3, "Экономия на двух месяцах проверки, у.е.", size=12, color=MUTED, bold=True,
         name="cmph", fx=(5, "fade", "after", 0, 0.3))
    bar_chart(s, 0.45, 5.45, 7.0, 1.35, [cmp[0], cmp[2]], [cmp[1], cmp[3]], [GREY, color], font_size=12,
              max_v=300000, name="cmp", fx=(5, "wipe", "with", 0.1, 0.8))
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.9, 1.8, 4.85, 2.85, fill=CARD, radius=0.06, name="wins",
          fx=(6, "rise", "after", 0, 0.5), d3="tile")
    text(s, 8.2, 1.98, 4.3, 0.4, "Что сработало (вклад в у.е.)", size=14, bold=True, color=MUTED, name="winsh",
         fx=(6, "rise", "with", 0, 0.5))
    for k, (num, lab) in enumerate(wins):
        text(s, 8.2, 2.45 + k * 0.7, 1.55, 0.55, num, size=21, font=HEAD, bold=True, color=TEAL, name=f"wn{k}",
             fx=(6, "rise", "with", 0.1 * (k + 1), 0.5))
        text(s, 9.8, 2.5 + k * 0.7, 2.8, 0.62, lab, size=13, name=f"wl{k}", fx=(6, "rise", "with", 0.1 * (k + 1), 0.5))
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 7.9, 4.85, 4.85, 1.95, fill=TEAL_SOFT, radius=0.06, name="res",
          fx=(7, "rise", "after", 0, 0.5), d3="tile")
    text(s, 8.2, 5.02, 4.3, 1.7, [[(t, {"bold": b, "size": 17 if b else 13, "color": TEAL if b else INK})]
                                  for t, b in result], spacing=5, name="rest", fx=(7, "rise", "with", 0, 0.5))
    speaker(s, letter)
    notes(s, NOTES_SOL[letter])

# =====================================================================
# 7. Турнир — тепловая таблица
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Турнир: работу делают признаки, а не модель",
      "Поменяли модели местами. Экономия за 2 месяца проверки, тыс. у.е. Чем зеленее — тем больше денег")
rows = [("Сырые поля", [173.6, 235.4, 235.4, 238.6]), ("+ A профиль", [224.1, 245.3, 245.3, 247.5]),
        ("+ B ритм", [202.7, 249.6, 251.4, 252.0]), ("+ C среда", [182.8, 234.4, 234.4, 239.2]),
        ("+ A + B", [227.1, 249.0, 250.2, 252.3]), ("+ A + B + сумма из C", [226.1, 250.7, 250.5, 252.5])]
heads = ["Признаки \\ модель", "LogReg", "LightGBM", "LightGBM с запретом", "LightGBM «учит деньгам»"]
gf = s.shapes.add_table(len(rows) + 1, 5, Inches(0.6), Inches(1.95), Inches(7.6), Inches(3.9))
tag(gf, "table", fx=(1, "fade", "after", 0.1, 0.7))
tbl = gf.table
for j, wdt in enumerate([2.2, 1.1, 1.25, 1.45, 1.6]):
    tbl.columns[j].width = Inches(wdt)
lo, hi = 170.0, 253.0


def heat(v):
    t = max(0.0, min(1.0, (v - lo) / (hi - lo))) ** 1.6
    a, b = (0xF3, 0xF5, 0xF8), (0x1F, 0x8A, 0x7A)
    return RGBColor(*[round(a[k] + (b[k] - a[k]) * t) for k in range(3)]), t


for i in range(len(rows) + 1):
    for j in range(5):
        c = tbl.cell(i, j)
        c.margin_left = c.margin_right = Inches(0.08)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        c.text_frame.word_wrap = True
        p = c.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
        r = p.add_run()
        r.font.name = BODY
        c.fill.solid()
        if i == 0:
            r.text = heads[j]
            r.font.bold, r.font.size, r.font.color.rgb = True, Pt(12), WHITE
            c.fill.fore_color.rgb = DARK
        elif j == 0:
            r.text = rows[i - 1][0]
            r.font.bold, r.font.size, r.font.color.rgb = True, Pt(14), INK
            c.fill.fore_color.rgb = WHITE
        else:
            v = rows[i - 1][1][j - 1]
            col, t = heat(v)
            r.text = f"{v:.1f}".replace(".", ",")
            r.font.size = Pt(15)
            r.font.bold = t > 0.75
            r.font.color.rgb = WHITE if t > 0.55 else INK
            c.fill.fore_color.rgb = col
row_h = 3.9 / 7
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6 + 2.2 + 1.1 + 1.25 + 1.45 - 0.05, 1.95 + 6 * row_h - 0.05, 1.7, row_h + 0.1,
      fill=None, line=AMBER, lw=4, radius=0.15, name="finalring", fx=(6, "zoom", "click", 0, 0.5))
text(s, 0.6, 6.0, 7.6, 0.9, "Потолок (идеальная модель) — 255,5. Финал — 252,5 = 98,8% потолка. "
                            "Между вариантами LightGBM на одних признаках — до 3,3 тыс., это шум.",
     size=12, color=MUTED, name="tnote", fx=(2, "fade", "after", 0, 0.4))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 8.55, 1.95, 4.2, 4.9, fill=CARD, radius=0.05, name="panel",
      fx=(3, "fade", "after", 0, 0.4), d3="tile")
text(s, 8.85, 2.12, 3.7, 0.4, "Что видно", size=20, font=HEAD, bold=True, name="ph", fx=(3, "fade", "with", 0, 0.4))
text(s, 8.85, 2.65, 3.7, 2.2, [
    [("По строкам: ", {"bold": True}), ("признаки A+B дают +13,6…14,8 тыс. на любом дереве.", {})],
    [("По столбцам: ", {"bold": True}), ("деревья между собой — в пределах шума.", {})],
    [("Простая модель ", {"bold": True}), ("отстаёт на 17–62 тыс.: не видит, что фрод дорогой в одних категориях "
                                           "и дешёвый в других.", {})]], size=13.5, spacing=8,
     name="pts", fx=(4, "fade", "click", 0, 0.5))
text(s, 8.85, 5.0, 3.7, 1.75, [[("Финал — A и B вместе: ", {"bold": True, "color": TEAL}),
                               ("A лучше ловит первую кражу, B — продолжение серии. Вместе — оба сценария и меньше всего "
                                "честных остановок: 27 против 76 у базы.", {})]], size=13.5,
     name="why", fx=(5, "fade", "click", 0, 0.5))
speaker(s, "B")
notes(s, "Таблица появляется сама.\n\n"
         "Как мы выбирали лучшее из трёх решений. Мы не просто сравнили три итоговых числа, а поменяли модели местами: "
         "каждый набор признаков прогнали на простой модели и на трёх вариантах деревьев. Чем зеленее клетка, тем больше "
         "денег.\n\n"
         "[КЛИК] — выводы по строкам и столбцам.\n"
         "По строкам: добавили признаки A и B — плюс примерно 14 тысяч на любой модели-дереве. По столбцам: деревья "
         "между собой отличаются максимум на 3 тысячи — это случайный разброс. Значит, результат делают признаки и "
         "правило выбора, а не конкретная модель. Простая модель отстаёт везде.\n\n"
         "[КЛИК] — почему финал.\n"
         "Лучшие варианты отличаются на сотни у.е. — это шум, поэтому мы разобрали, кто что ловит. A лучше ловит первую "
         "операцию кражи, B — продолжение серии. Вместе ловят оба сценария и реже всех останавливают честных клиентов: "
         "27 за два месяца против 76 у базовой модели.\n\n"
         "[КЛИК] — рамка вокруг финала.\n"
         "Это и есть наш финал: 252,5 тысячи, 98,8% от потолка.")

# =====================================================================
# 8. Экономика — стопки монет
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, WHITE)
title(s, "Экономика: 323 тысячи за два месяца",
      "Отложенные 2 месяца (22.04–21.06.2020) — их не трогали до конца. Одна монета = 20 тыс. у.е.")
stacks = [("Правило «самые дорогие»", 76358, "grey"), ("База, по вероятности", 220219, "grey"),
          ("База, по деньгам", 304083, "grey"), ("Наша система", 323389, "gold"), ("Потолок", 327812, "ghost")]
coin_w, coin_step, base_y = 1.0, 0.15, 5.05
for i, (lab, val, kind) in enumerate(stacks):
    x = 0.75 + i * 1.42
    n = max(1, round(val / 20000))
    grp = s.shapes.add_group_shape()
    for k in range(n):
        c = grp.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(base_y - k * coin_step), Inches(coin_w),
                                 Inches(coin_w))
        c.fill.solid()
        c.fill.fore_color.rgb = GOLD if kind == "gold" else (RGBColor(0x8C, 0x96, 0xA5) if kind == "grey" else RGBColor(0xEC, 0xDF, 0xC0))
        c.line.fill.background()
        c.shadow.inherit = False
        tag(c, f"coin{i}_{k}", d3="coin_" + kind)
    tag(grp, f"stack{i}", fx=(1 + i, "wipe", "after", 0.05, 0.7))
    top = base_y - (n - 1) * coin_step
    text(s, x - 0.2, top - 0.2, coin_w + 0.4, 0.4, f"{val:,}".replace(",", NB), size=15, bold=True,
         color=TEAL if kind == "gold" else INK, align=PP_ALIGN.CENTER, name=f"sv{i}",
         fx=(1 + i, "fade", "after", 0, 0.3))
    text(s, x - 0.22, base_y + coin_w - 0.15, coin_w + 0.44, 0.6, lab, size=12, bold=kind == "gold",
         color=TEAL if kind == "gold" else MUTED, align=PP_ALIGN.CENTER, name=f"sl{i}",
         fx=(1 + i, "fade", "with", 0, 0.3))
text(s, 0.6, 6.55, 7.3, 0.6, [[("Честных клиентов остановлено зря: ", {"bold": True}),
                               ("правило 347 · база 48 и 72 · ", {}), ("наша система 30", {"bold": True, "color": TEAL})]],
     size=14, name="honest", fx=(6, "fade", "after", 0, 0.4))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 8.25, 1.9, 4.5, 4.95, fill=RED_SOFT, radius=0.05, name="stress",
      fx=(7, "rise", "click", 0, 0.5), d3="tile")
text(s, 8.55, 2.08, 4.0, 0.8, "Если мошенничества станет втрое больше", size=18, font=HEAD, bold=True,
     name="sh", fx=(7, "rise", "with", 0, 0.5))
text(s, 8.55, 2.9, 4.0, 0.35, "Пропущено мошенничества за 2 месяца, у.е.:", size=12.5, color=MUTED, name="ssub",
     fx=(7, "rise", "with", 0, 0.5))
for k, (cap, per_day, miss) in enumerate([("лимит 0,3%", "≈7 проверок в день", "558" + NB + "875"),
                                          ("лимит 0,5%", "≈10 в день", "232" + NB + "918"),
                                          ("лимит 1%", "≈15 в день", "25" + NB + "712")]):
    y = 3.35 + k * 0.82
    text(s, 8.55, y, 2.0, 0.65, [[(cap, {"bold": True})], [(per_day, {"size": 12, "color": MUTED})]], size=15,
         name=f"sc{k}", fx=(8 + k, "fade", "after", 0, 0.35))
    text(s, 10.4, y, 2.1, 0.6, miss, size=24, font=HEAD, bold=True, color=RED, align=PP_ALIGN.RIGHT, name=f"sm{k}",
         fx=(8 + k, "zoom", "with", 0, 0.35))
text(s, 8.55, 5.9, 4.0, 0.9, "Больше 15–16 проверок в день почти ничего не добавляют — "
                             "это ответ на вопрос, сколько аналитиков нужно.", size=13, name="snote",
     fx=(11, "fade", "after", 0, 0.4))
speaker(s, "C")
notes(s, "Стопки монет вырастают сами, слева направо. Одна монета — 20 тысяч.\n\n"
         "Теперь деньги — на двух месяцах, которые мы открыли один раз, в самом конце. Без системы банк потерял бы 513 "
         "тысяч. Простое правило «проверять самые дорогие операции» спасает 76 тысяч. Базовая модель — 220, а если "
         "выбирать по деньгам — 304. Наша система — 323 тысячи, почти потолок в 328. Посмотрите, насколько последние две "
         "стопки одинаковые.\n\n"
         "И всего 30 честных клиентов остановлено за два месяца; у простого правила — 347.\n\n"
         "[КЛИК] — стресс-тест.\n"
         "Что будет, если мошенничества станет втрое больше? При нынешнем штате банк будет пропускать 559 тысяч за два "
         "месяца. Если аналитиков хватит на 10 проверок в день — 233 тысячи. На 15 — всего 26 тысяч, дальше почти ничего "
         "не меняется. Так заказчик может посчитать, сколько людей нанимать.")

# =====================================================================
# 9. Карточка аналитика
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, CARD)
title(s, "Что видит аналитик: три причины словами", "Настоящие операции с отложенных двух месяцев — выход score.py")
cards = [
    ("Мошенничество · поймано", "08.06.2020, 23:49 · покупки в магазине", "1" + NB + "215,89 у.е. · вероятность 100%",
     ["За последние сутки по карте уже списано около 4" + NB + "870 у.е.",
      "Сумма дороже 99% покупок в категории «покупки в магазине»", "Серия из 5 операций ночью"], TEAL, TEAL_SOFT),
    ("Мошенничество · новая карта", "07.06.2020, 22:10 · покупки в магазине", "1" + NB + "324,80 у.е. · вероятность 75%",
     ["Сумма дороже 99% покупок в категории «покупки в магазине»", "Новая карта: это её первая операция",
      "Категория «покупки в магазине» — частая цель мошенников"], TEAL, TEAL_SOFT),
    ("Честная покупка · ложная тревога", "27.04.2020, 23:13 · покупки онлайн", "3" + NB + "918,79 у.е. · вероятность 1,9%",
     ["Сумма дороже 99% покупок в категории «покупки онлайн»", "Категория «покупки онлайн» — частая цель мошенников",
      "Сумма в 453 раза больше обычной для клиента (обычно ≈ 9 у.е.)"], RED, RED_SOFT),
]
for i, (tg, head, amt, rs, col, soft) in enumerate(cards):
    x = 0.6 + i * 4.1
    o = 1 + i
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, 1.9, 3.85, 4.1, fill=WHITE, radius=0.05, name=f"cd{i}",
          fx=(o, "rise", "after", 0.1, 0.6), d3="tile")
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x + 0.25, 2.1, 3.35, 0.42, fill=soft, radius=0.3, name=f"cdt{i}",
          fx=(o, "rise", "with", 0, 0.6))
    text(s, x + 0.25, 2.1, 3.35, 0.42, tg, size=13, bold=True, color=col, align=PP_ALIGN.CENTER,
         anchor=MSO_ANCHOR.MIDDLE, name=f"cdtt{i}", fx=(o, "rise", "with", 0, 0.6))
    text(s, x + 0.25, 2.7, 3.4, 0.35, head, size=13, color=MUTED, name=f"cdh{i}", fx=(o, "rise", "with", 0, 0.6))
    text(s, x + 0.25, 3.05, 3.4, 0.45, amt, size=16, bold=True, name=f"cda{i}", fx=(o, "rise", "with", 0, 0.6))
    for k, r in enumerate(rs):
        sphere(s, x + 0.25, 3.72 + k * 0.72, 0.36, DARK, str(k + 1), 11, name=f"rn{i}{k}",
               fx=(o, "rise", "with", 0.05 * (k + 1), 0.6))
        text(s, x + 0.75, 3.7 + k * 0.72, 2.95, 0.7, r, size=12.5, name=f"rt{i}{k}",
             fx=(o, "rise", "with", 0.05 * (k + 1), 0.6))
text(s, 0.6, 6.25, 12.1, 0.8, [[("Все 406 отправленных операций получили по три причины. ", {"bold": True}),
                                ("Третью карточку система отправила сознательно: вероятность мала, но проверка стоит "
                                 "3 у.е., а пропуск такой суммы — почти 3" + NB + "924.", {})]], size=14,
     name="cnote", fx=(4, "fade", "click", 0, 0.5))
speaker(s, "A")
notes(s, "Карточки появляются сами, по одной.\n\n"
         "Заказчик хотел, чтобы решение можно было объяснить. Вот что видит аналитик — это настоящие операции, их выдал "
         "наш скрипт.\n\n"
         "Первая: за сутки с карты уже списали почти 5 тысяч, сумма дороже 99% покупок в этой категории, пятая операция "
         "подряд ночью. Аналитику сразу понятно, что происходит.\n\n"
         "Вторая — новая карта, это её первая операция. Истории нет, но модель её поймала: сумма необычная для "
         "категории в целом.\n\n"
         "Третья — честный клиент, ложная тревога. Вероятность мошенничества всего 2%, но сумма почти 4 тысячи.\n\n"
         "[КЛИК] — пояснение.\n"
         "Проверка стоит 3 у.е., пропуск — почти 4 тысячи, поэтому проверить выгодно. Это осознанное решение, а не "
         "ошибка. Причины мы пишем обычными словами и показываем только верные для этой операции: «ночная» — только если "
         "она правда ночью.")

# =====================================================================
# 10. Отвергнутые идеи и итог
# =====================================================================
s = prs.slides.add_slide(BLANK)
bg(s, DARK)
title(s, "Что не сработало — и почему это тоже результат", dark=True)
rej = [("Расстояние до продавца", "Самый популярный признак на Kaggle. У мошенничества и честных медиана одна: 78,2 км"),
       ("«Проверка мелкой суммой»", "Первая мошенническая операция серии в медиане — 311 у.е. Мелкой проверки нет"),
       ("Первая покупка у продавца", "У честных клиентов это 37% всех операций — сигнала нет"),
       ("Окно «операций за 24 часа»", "Поверх плавной памяти ничего не добавило"),
       ("Риск категории и продавца", "Деревьям не нужен: модель и так видит категорию и час"),
       ("Обучение без меток", "167 тыс. против 235: необычное ≠ мошенническое")]
for i, (h, dsc) in enumerate(rej):
    col, row = i % 2, i // 2
    x, y = 0.6 + col * 6.2, 1.5 + row * 1.2
    shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 5.95, 1.02, fill=DARK2, radius=0.1, name=f"rj{i}",
          fx=(1 + i, "fade", "after", 0.05, 0.35), d3="tile_dark")
    sphere(s, x + 0.22, y + 0.28, 0.46, RED, "✕", 14, name=f"rx{i}", fx=(1 + i, "zoom", "with", 0, 0.35))
    text(s, x + 0.9, y + 0.12, 4.9, 0.35, h, size=16, bold=True, color=RED_L, name=f"rh{i}",
         fx=(1 + i, "fade", "with", 0, 0.35))
    text(s, x + 0.9, y + 0.48, 4.9, 0.55, dsc, size=12.5, color=ON_DARK, name=f"rd{i}", fx=(1 + i, "fade", "with", 0, 0.35))
text(s, 0.6, 5.2, 12.1, 0.4, "Как понимали, что дело в идее, а не в проверке: одна линейка для всех, интервалы по дням, "
                             "тест на подглядывание в будущее ловит заведомые утечки.", size=13.5, color=ON_DARK,
     name="how", fx=(7, "fade", "after", 0, 0.4))
shape(s, MSO_SHAPE.ROUNDED_RECTANGLE, 0.6, 5.8, 12.15, 1.05, fill=TEAL, radius=0.15, name="final",
      fx=(8, "zoom", "click", 0, 0.6), d3="tile_dark")
text(s, 0.95, 5.8, 11.5, 1.05, [[("Итог:  ", {"bold": True, "size": 20}),
                                 ("выбор по деньгам + привычки клиента (A) + ритм операций (B) = 98,7% от возможного, "
                                  "30 зря остановленных клиентов, 550 тысяч операций за 32 секунды.", {"size": 17})]],
     color=WHITE, anchor=MSO_ANCHOR.MIDDLE, name="finalt", fx=(8, "zoom", "with", 0, 0.6))
speaker(s, "B", dark=True)
notes(s, "Карточки появляются сами.\n\n"
         "Напоследок — что не сработало. Это важная часть работы.\n\n"
         "Самый популярный признак в таких задачах — расстояние от дома до магазина. У нас он бесполезен: у мошенничества "
         "и у честных покупок медиана одна и та же, 78 километров. Похоже, генератор данных ставит магазин просто рядом "
         "с домом. Мы ожидали, что мошенники сначала проверяют карту мелкой суммой — не подтвердилось: первая "
         "мошенническая операция в среднем стоит 311 у.е. «Первая покупка у продавца» — у честных клиентов это каждая "
         "третья операция. Модель без меток сильно хуже — необычное не значит мошенническое.\n\n"
         "Откуда мы знаем, что проблема в идее, а не в проверке: у всех признаков одна и та же линейка, интервалы по "
         "дням и тест на подглядывание в будущее, который мы сами проверили на заведомых утечках.\n\n"
         "[КЛИК] — итог.\n"
         "Итог: выбор по деньгам плюс привычки клиента плюс ритм операций — 98,7% от возможного, 30 зря остановленных "
         "клиентов, и система обрабатывает 550 тысяч операций за полминуты. Спасибо, готовы ответить на вопросы.")

prs.save(OUT)
print(f"Сохранено: {OUT}")
