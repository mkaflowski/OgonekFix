# -*- coding: utf-8 -*-
"""
Sprawdza pliki czcionek (TTF/OTF) w podanym folderze pod kątem polskich znaków
i tworzy kopię <nazwa>_PL.<ext> w podfolderze "fixed" z uzupełnionymi znakami.

Strategia uzupełniania (od najlepszej):
1. 🎨 złożenie nowego glifu: litera bazowa + znak diakrytyczny wycięty z fontu
   - kreska (ć ń ó ś ź): z istniejącego ó/é/á lub samodzielnego ´
   - kropka (ż):         z istniejącego ż/ė lub ˙, albo kropka znad "i"
   - ogonek (ą ę):       z istniejącego ą/ę/į lub samodzielnego ˛
2. 🧪 synteza geometryczna, gdy w foncie nie ma dawcy:
   - przekreślenie ł/Ł: ukośna belka
   - ogonek ą/ę/Ą/Ę:    haczyk rysowany krzywą Béziera, zaczepiony w spodzie
                        litery, o grubości dobranej do grubości jej laski
   - kreska ć/ń/ó/ś/ź:  ukośna belka nad literą (proporcje jak w prawdziwych
                        fontach), grubość dobrana do laski litery
   - kropka ż/Ż:        koło nad literą, średnica dobrana do laski litery
3. ⚠️ fallback: mapowanie na literę bez ogonka (ą -> glif "a")
"""

import io
import math
import os
import sys
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import DecomposingRecordingPen, RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.cu2quPen import Cu2QuPen

# Scalanie konturów (suma logiczna) litery z dorobionym znakiem. Bez niego glif
# zostaje DWOMA nachodzącymi na siebie konturami: przy regule nonzero wygląda
# dobrze, ale rasteryzer wypełniający even-odd (tak renderuje część silników
# i podglądów) wycina część wspólną - belka ł przecina wtedy laskę białą
# szparą, a ogonek wygryza róg litery. Po scaleniu glif ma jeden zarys bez
# nakładek i wygląda tak samo w obu regułach.
try:
    import pathops
except ImportError:      # bez skia-pathops zostaje stare zachowanie (nakładki)
    pathops = None

# emoji na konsoli Windows (cp1250)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# polski znak -> (litera bazowa, rodzaj znaku diakrytycznego)
ACCENTS = {
    "ą": ("a", "ogonek"), "ć": ("c", "acute"), "ę": ("e", "ogonek"),
    "ł": ("l", "stroke"), "ń": ("n", "acute"), "ó": ("o", "acute"),
    "ś": ("s", "acute"), "ź": ("z", "acute"), "ż": ("z", "dot"),
    "Ą": ("A", "ogonek"), "Ć": ("C", "acute"), "Ę": ("E", "ogonek"),
    "Ł": ("L", "stroke"), "Ń": ("N", "acute"), "Ó": ("O", "acute"),
    "Ś": ("S", "acute"), "Ź": ("Z", "acute"), "Ż": ("Z", "dot"),
}
POLISH_CHARS = list(ACCENTS.keys())

# źródła znaków diakrytycznych: pary (znak złożony, litera bazowa) do wycięcia
# różnicy oraz samodzielne znaki diakrytyczne
MARK_PAIRS = {
    "acute": [("ó", "o"), ("é", "e"), ("á", "a"), ("ú", "u"), ("ý", "y"),
              ("Ó", "O"), ("É", "E"), ("Á", "A")],
    "dot": [("ż", "z"), ("ė", "e"), ("ċ", "c")],
    "ogonek": [("ą", "a"), ("ę", "e"), ("į", "i"), ("ų", "u")],
}
# najpierw znaki SKŁADAJĄCE (U+03xx) - są projektowane do nakładania na litery,
# więc mają właściwy rozmiar i wysokość; odstępowe (´ ˙ ˛) bywają rysowane
# w środku kratki, zwłaszcza w fontach CJK
MARK_STANDALONE = {
    "acute": ["́", "´", "ˊ"],    # combining acute, ´, ˊ
    "dot": ["̇", "˙"],                # combining dot above, ˙
    "ogonek": ["̨", "˛"],             # combining ogonek, ˛
}


# ---------------------------------------------------------------- pomocnicze

def replay(ops, pen):
    for op, args in ops:
        getattr(pen, op)(*args)


def record_glyph(glyph_set, name):
    """Zwraca zdekomponowany (bez komponentów) zapis konturów glifu."""
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.value


def _ascii_outlines(glyph_set, cmap):
    """Kontury glifów zwykłych znaków ASCII (U+0021-U+007E) danego fontu."""
    outlines = []
    for code in range(0x21, 0x7F):
        plain = cmap.get(code)
        if plain in glyph_set:
            ops = record_glyph(glyph_set, plain)
            if ops:
                outlines.append(ops)
    return outlines


def _is_ascii_clone(glyph_set, name, ascii_outlines):
    """Czy glif `name` jest kopią któregoś zwykłego znaku ASCII (przesunięta cmap)."""
    ops = record_glyph(glyph_set, name)
    return bool(ops) and ops in ascii_outlines


def missing_characters(font, chars):
    """Brak kodu albo glif zastępczy, także kopia .notdef pod inną nazwą.

    Electronic Highway Sign ma ó/Ó w cmap, ale oba są prostokątem .notdef.
    Sama obecność kodu nie jest w tym przypadku pokryciem znaku.
    """
    cmap = font.getBestCmap() or {}
    glyph_set = font.getGlyphSet()
    notdef = record_glyph(glyph_set, '.notdef') if '.notdef' in glyph_set else None
    ascii_outlines = None
    missing = []
    for ch in chars:
        name = cmap.get(ord(ch))
        if not name or name == '.notdef' or name not in glyph_set:
            missing.append(ch)
        elif notdef is not None and record_glyph(glyph_set, name) == notdef:
            missing.append(ch)
        elif ord(ch) > 0x7F:
            # Przesunięta cmap: kod literą z akcentem wskazuje na zwykły glif
            # ASCII (courier_bold z Playable Archive: Ó->"s.1", ó->"three.1" -
            # cały zakres 0xC0-0xFF jest przesunięty). TMP nie sięgnie wtedy po
            # fallback, bo font "ma" ten znak, a na ekranie jest inna litera.
            if ascii_outlines is None:
                ascii_outlines = _ascii_outlines(glyph_set, cmap)
            if _is_ascii_clone(glyph_set, name, ascii_outlines):
                missing.append(ch)
    return missing


def split_contours(ops):
    contours, cur = [], []
    for op, args in ops:
        if op == "moveTo" and cur:
            contours.append(cur)
            cur = []
        cur.append((op, args))
    if cur:
        contours.append(cur)
    return contours


def bbox(ops):
    pen = ControlBoundsPen(None)
    replay(ops, pen)
    return pen.bounds  # (xMin, yMin, xMax, yMax) albo None


def contour_sig(contour):
    out = []
    for op, args in contour:
        coords = tuple(round(c) for pt in args for c in pt)
        out.append((op, coords))
    return tuple(out)


def translate_ops(ops, dx, dy):
    rec = RecordingPen()
    replay(ops, TransformPen(rec, (1, 0, 0, 1, dx, dy)))
    return rec.value


# -------------------------------------------- wyszukiwanie znaku diakrytycznego

def detached_top_mark(ops, upm):
    """Oddzielny akcent nad rzeczywistym korpusem litery dawcy.

    W krojach display korpus ó bywa niższy od o, żeby zmieścić kreskę pod
    linią wersalików. Różnica względem góry o wybiera wtedy szum konturu
    zamiast akcentu. Przerwa między pasmami konturów rozdziela oba kształty
    bez tego założenia; zapobiega też uznaniu szumu wewnątrz I za kropkę i.
    """
    contours = [(c, bbox(c)) for c in split_contours(ops)]
    contours = [(c, b) for c, b in contours if b and b[2] > b[0] and b[3] > b[1]]
    if not contours:
        return None
    bands = []
    for lo, hi in sorted((b[1], b[3]) for _, b in contours):
        if bands and lo <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], hi)
        else:
            bands.append([lo, hi])
    if len(bands) < 2:
        return None
    mark_bottom, mark_top = bands[-1]
    body_top = bands[-2][1]
    if body_top - bands[0][0] < (mark_top - bands[0][0]) * 0.5:
        return None
    mark = [op for contour, b in contours if b[1] >= mark_bottom for op in contour]
    b = bbox(mark)
    if (b[2] - b[0] > 0.45 * upm or b[3] - b[1] > 0.45 * upm
            or b[3] - b[1] < 0.02 * upm):
        return None
    return mark, body_top


def extract_mark_from_pair(glyph_set, cmap, pre_ch, base_ch, kind, upm):
    """Wycina kontury akcentu jako różnicę: znak złożony minus litera bazowa."""
    pre_ops = record_glyph(glyph_set, cmap[ord(pre_ch)])
    base_ops = record_glyph(glyph_set, cmap[ord(base_ch)])
    base_bb = bbox(base_ops)
    if not base_bb or not pre_ops:
        return None
    if kind in ("acute", "dot"):
        detached = detached_top_mark(pre_ops, upm)
        if detached is not None:
            return detached

    base_sigs = {contour_sig(c) for c in split_contours(base_ops)}
    candidates = [c for c in split_contours(pre_ops) if contour_sig(c) not in base_sigs]

    def position_ok(c):
        cb = bbox(c)
        if not cb:
            return False
        if kind in ("acute", "dot"):
            return cb[1] > base_bb[3] - 0.05 * upm   # w całości nad literą
        return cb[1] < base_bb[1] - 0.03 * upm        # ogonek: schodzi poniżej

    candidates = [c for c in candidates if position_ok(c)]
    if not candidates:  # znak złożony narysowany ręcznie - filtr czysto pozycyjny
        candidates = [c for c in split_contours(pre_ops) if position_ok(c)]
    if not candidates:
        return None

    ops = [op for c in candidates for op in c]
    mark_bb = bbox(ops)
    if kind == "ogonek" and (mark_bb[2] - mark_bb[0] > 0.45 * upm
                              or mark_bb[3] - mark_bb[1] > 0.45 * upm):
        # W ozdobnych fontach (np. ChiaWonk Rough) ogonek bywa częścią jednego
        # konturu z literą. Różnica konturów zwraca wtedy całą literę, więc
        # odcinamy jej dolny fragment z niewielkim zapasem na połączenie.
        ops = clip_merged_ogonek(candidates, base_bb[1] + 0.06 * upm, base_bb[1])
        if not ops:
            return None
    # Dla ogonka odniesieniem jest spód dawcy; dla akcentów górnych jego góra.
    return ops, base_bb[1] if kind == "ogonek" else base_bb[3]


# Spód prawdziwego znaku diakrytycznego leży nad x-height najwyżej o tyle
# (zmierzone na 168 fontach: mediana +0.08 em, maksimum +0.144 em). Wyżej
# znaczy, że glif jest projektowany do piętrzenia nad znakami CJK, a nie do
# siedzenia na łacińskiej literze — w ZenAntique taka kropka odlatywała
# dwukrotnie wyżej niż kreska w ś.
MARK_MAX_RISE = 0.20


def mark_is_sane(ops, kind, upm, xheight, standalone=False):
    """Odsiewa glify, które udają znak diakrytyczny, a nim nie są.

    Znaki odstępowe (´ ˙ ˛) bywają rysowane w środku kratki — w fontach CJK
    (np. Noto Sans SC) ˙ leży na wysokości POŁOWY litery, więc kropka lądowała
    w środku "z" zamiast nad nim. Zdarzają się też glify wielkości całej
    litery. Taki kandydat musi wypaść, żeby skrypt sięgnął po następny.

    Wysokość sprawdzamy tylko dla znaków SAMODZIELNYCH, bo tylko dla nich
    zgadujemy odniesienie (x-height). Znak wycięty z gotowego ó/ą przynosi
    własną wysokość odniesienia, więc nie ma czego weryfikować.
    """
    b = bbox(ops)
    if not b:
        return False
    w, h = b[2] - b[0], b[3] - b[1]
    if w <= 0 or h <= 0 or w > 0.45 * upm or h > 0.45 * upm:
        return False
    if kind in ("acute", "dot"):
        if h < 0.02 * upm:            # drobny odprysk konturu, nie akcent
            return False
        if b[1] <= xheight * 0.85:     # musi leżeć NAD literą, nie na niej
            return False
        return not standalone or b[1] <= xheight + MARK_MAX_RISE * upm
    return b[1] < 0.15 * upm           # ogonek: przy linii pisma lub niżej


# Regulacja kropki w ż/Ż. Skalujemy względem środka znaku, więc sam rozmiar
# nie rusza jej wysokości — od tego jest osobne obniżenie.
DOT_SCALE = 1.0    # rozmiar kropki (1.0 = tak, jak narysowana w foncie)
DOT_DROP = 0.03    # o ile opuścić kropkę bliżej litery (× upm)
DOT_MIN_GAP = 0.03  # minimalna przerwa między górą litery a kropką (× upm)


def scale_ops(ops, factor):
    """Skaluje kontury wokół ich własnego środka."""
    b = bbox(ops)
    if not b or factor == 1.0:
        return ops
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    rec = RecordingPen()
    replay(ops, TransformPen(rec, (factor, 0, 0, factor,
                                   cx * (1 - factor), cy * (1 - factor))))
    return rec.value


def find_mark(glyph_set, cmap, kind, upm, xheight):
    """Zwraca (kontury akcentu, wysokość odniesienia) albo None."""
    found = None
    ascii_outlines = _ascii_outlines(glyph_set, cmap)

    def poisoned(ch):
        # przesunięta cmap (patrz missing_characters) zatruwa wycinanie różnicy
        return (ord(ch) > 0x7F and _is_ascii_clone(glyph_set, cmap[ord(ch)], ascii_outlines))

    for pre_ch, base_ch in MARK_PAIRS[kind]:
        if ord(pre_ch) in cmap and ord(base_ch) in cmap and not poisoned(pre_ch):
            result = extract_mark_from_pair(glyph_set, cmap, pre_ch, base_ch, kind, upm)
            if result and mark_is_sane(result[0], kind, upm, xheight):
                found = result
                break
    if found is None:
        for mark_ch in MARK_STANDALONE[kind]:
            if ord(mark_ch) in cmap and not poisoned(mark_ch):
                ops = record_glyph(glyph_set, cmap[ord(mark_ch)])
                if mark_is_sane(ops, kind, upm, xheight, standalone=True):
                    found = (ops, xheight)
                    break
    if found is None and kind == "acute":
        # Brak własnej kreski: lustrzane odbicie własnego akcentu słabego (`)
        # ma kształt i grubość kroju, a rysowany akcent bywa w ciężkim kroju
        # slab (courier_bold) nie do odróżnienia od kropki - ź wyglądało jak ż.
        for mark_ch in ("̀", "`", "ˋ"):   # combining grave, `, ˋ
            if ord(mark_ch) not in cmap:
                continue
            ops = record_glyph(glyph_set, cmap[ord(mark_ch)])
            b = bbox(ops)
            if not b:
                continue
            rec = RecordingPen()
            replay(ops, TransformPen(rec, (-1, 0, 0, 1, b[0] + b[2], 0)))
            if mark_is_sane(rec.value, kind, upm, xheight, standalone=True):
                found = (rec.value, xheight)
                break
    if found is None and kind == "dot" and ord("i") in cmap and xheight:
        # Kropka musi być oddzielona od laski. W all-caps małe i jest I,
        # a wysoko położone drobne kontury mogą być tylko jego fakturą.
        i_ops = record_glyph(glyph_set, cmap[ord("i")])
        detached = detached_top_mark(i_ops, upm)
        if detached and mark_is_sane(detached[0], kind, upm, xheight):
            found = detached
    if found and kind == "dot":
        ops = scale_ops(found[0], DOT_SCALE)
        if DOT_DROP:
            ops = translate_ops(ops, 0, -DOT_DROP * upm)
        found = (ops, found[1])
    return found


STROKE_THICK = 0.62     # grubość belki (× grubość laski litery)
STROKE_THICK_MIN = 0.022   # widełki grubości (× upm)
STROKE_THICK_MAX = 0.10
# Zasięg liczymy jako POŁOWA LASKI + wystawka, nie jako wielokrotność laski.
# Inaczej w kroju display z laską 0.40 em (KH2 ALL MENU) każde ograniczenie
# "× upm" wychodziło węższe od samej laski i belka w ogóle nie była widoczna.
STROKE_OVERHANG = 0.85     # ile belka wystaje za laskę z każdej strony (× laska)
STROKE_OVERHANG_MIN = 0.045   # widełki wystawki (× upm)
STROKE_OVERHANG_MAX = 0.10
STROKE_SLOPE = 0.75    # nachylenie: podniesienie = SLOPE × zasięg (~37 stopni)
STROKE_SLOPE_MAX = 0.16    # ale nie wyżej niż tyle (× upm), żeby długa belka
                           # w ciężkim kroju nie przecinała litery na wylot
STROKE_Y_UPPER = 0.42  # środek belki nad linią bazową (× wysokość litery)
STROKE_Y_LOWER = 0.58  # w minuskule wyżej: kreska ł siedzi nad wysokością x
STROKE_STEM_GAP = 0.015  # drobne ubytki faktury łączymy podczas pomiaru laski (× em)


def ink_runs_at_y(polylines, y):
    """Poziome odcinki tuszu na wysokości y, od lewej: [(x1, x2), ...]."""
    crossings = []
    for points in polylines:
        closed = points + [points[0]]
        for (x1, y1), (x2, y2) in zip(closed, closed[1:]):
            if y1 == y2:
                continue
            if (y1 <= y < y2) or (y2 <= y < y1):
                crossings.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    crossings.sort()
    return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def stroke_stem_span(runs, upm):
    """Pełny pień mimo drobnych dziur i odprysków w chropowatym kroju.

    Pierwszy odcinek tuszu może być jednopikselowym fragmentem przed dziurą,
    nie całą laską. Łączymy bliskie odcinki i wybieramy grupę z największą
    ilością tuszu. Odległe drobiny poza literą nie wyznaczają jej środka.
    """
    groups = []
    for left, right in sorted((a, b) for a, b in runs if b > a):
        if groups and left - groups[-1][1] <= STROKE_STEM_GAP * upm:
            groups[-1][2] += max(0, right - max(left, groups[-1][1]))
            groups[-1][1] = max(groups[-1][1], right)
        else:
            groups.append([left, right, right - left])
    if not groups:
        return None
    left, right, _ = max(groups, key=lambda group: (group[2], -group[0]))
    return left, right


def stroke_geometry(base_bb, upm, upper, stem=None, ink_at_y=None):
    """Wspólna geometria belki dla konturów TTF i pikseli atlasu TMP.

    Zasięg to połowa zmierzonej laski PLUS wystawka z obu stron. Nie używamy
    szerokości stopki L ani limitu wykluczającego grube/wąskie pionowe laski.
    Kilka przekrojów stabilizuje pomiar na poszarpanych krawędziach.
    """
    x_min, y_min, x_max, y_max = base_bb
    if not stem:
        stem = min(max(x_max - x_min, 0.04 * upm), 0.12 * upm)
    cy = (STROKE_Y_UPPER if upper else STROKE_Y_LOWER) * y_max
    cx = x_min + 0.5 * stem
    if ink_at_y is not None:
        spans = [stroke_stem_span(ink_at_y(cy + offset * upm), upm)
                 for offset in (-0.01, 0.0, 0.01)]
        spans = [span for span in spans if span is not None]
        if spans:
            mid = len(spans) // 2
            left = sorted(span[0] for span in spans)[mid]
            right = sorted(span[1] for span in spans)[mid]
            cx, stem = (left + right) / 2, right - left
    thick = min(max(STROKE_THICK * stem, STROKE_THICK_MIN * upm), STROKE_THICK_MAX * upm)
    overhang = min(max(STROKE_OVERHANG * stem, STROKE_OVERHANG_MIN * upm),
                   STROKE_OVERHANG_MAX * upm)
    hx = stem / 2 + overhang
    rise = min(STROKE_SLOPE * hx, STROKE_SLOPE_MAX * upm)
    return cx, cy, hx, rise, thick / 2


def make_stroke(base_bb, upm, upper, stem=None, base_ops=None):
    """Syntetyczna ukośna belka przekreślająca pełną laskę ł/Ł."""
    polylines = [flatten_contour(c) for c in split_contours(base_ops)] if base_ops else []
    measure = (lambda y: ink_runs_at_y(polylines, y)) if polylines else None
    cx, cy, hx, rise, t = stroke_geometry(base_bb, upm, upper, stem, measure)
    pts = [(cx - hx, cy - rise + t), (cx + hx, cy + rise + t),
           (cx + hx, cy + rise - t), (cx - hx, cy - rise - t)]
    pts = [(round(x), round(y)) for x, y in pts]
    return [("moveTo", (pts[0],)), ("lineTo", (pts[1],)),
            ("lineTo", (pts[2],)), ("lineTo", (pts[3],)), ("closePath", ())]


# --- syntetyczny ogonek (gdy w foncie nie ma żadnego dawcy) ------------------
# Proporcje zmierzone na 73 fontach z prawdziwym "ą": haczyk jest zaskakująco
# stały w jednostkach em, niezależnie od tego, czy siedzi pod a, e, A czy E
# (szerokość ~0.18 em; głębokość ograniczamy wizualnie do ~0.14 em), więc skalujemy do upm,
# a nie do szerokości litery.
OGONEK_DEPTH = 0.185    # punkt sterujący; krzywa schodzi ok. 0.8 tej wartości.
                        # Głębszy ogonek wyglądał na opuszczony w małych atlasach.
OGONEK_BACK = 0.11      # ile czubek wywija się w PRAWO od zaczepienia (× upm)
OGONEK_BULGE = 0.05     # ile haczyk wybrzusza się w LEWO po drodze (× upm)
OGONEK_THICK = 0.80     # grubość u nasady (× grubość laski litery)
OGONEK_THICK_MIN = 0.030   # widełki grubości (× upm), żeby nie wyszła nitka...
OGONEK_THICK_MAX = 0.095   # ...ani kluska przy bardzo ciężkich krojach
OGONEK_TIP = 0.55       # grubość na końcu (× grubość u nasady)
OGONEK_TIP_RISE = 0.42  # na jakiej wysokości kończy się czubek (× głębokość);
                        # mniej = mocniej wywinięty do góry
OGONEK_MERGE = 0.02     # ile wchodzi w literę, żeby się z nią skleić (× upm)
OGONEK_ATTACH_MAX = 0.80  # preferowany zaczep (× szer. litery), o ile leży w tuszu.
                          # Zmierzone na prawdziwych ą: nasada wypada na 0.815
                          # szerokości litery, a czubek sięga do 0.996 — wyżej
                          # ustawiony limit wypychałby czubek poza literę.
OGONEK_DONOR_LEFT = 0.03  # przenoszony ogonek lekko w lewo, pod laskę e/E
OGONEK_DONOR_OVERLAP = 0.0   # wspólna krawędź, bez powierzchni wycinanej przez even-odd


def flatten_contour(contour, steps=6):
    """Kontur zamieniony na łamaną (krzywe rozbite na odcinki).

    Same punkty zapisu konturu nie wystarczą do mierzenia dołu litery: dolna
    krawędź laski w "a" to jeden odcinek, którego końce leżą poza szukanym
    miejscem, więc pomiar "po punktach" trafiał w dziurę i wskazywał środek
    litery zamiast jej spodu.
    """
    pts, cur = [], None
    for op, args in contour:
        if op in ("moveTo", "lineTo"):
            cur = args[0]
            pts.append(cur)
        elif op == "curveTo":
            c1, c2, end = args[-3], args[-2], args[-1]
            p0 = cur or c1
            for i in range(1, steps + 1):
                t = i / steps
                u = 1 - t
                pts.append((u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                            u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1]))
            cur = end
        elif op == "qCurveTo":
            ctrls = list(args)
            end = ctrls.pop()
            if end is None:            # kontur bez punktów on-curve (same krzywe)
                end = ctrls[0]
            p0 = cur or ctrls[0]
            for j, ctrl in enumerate(ctrls):
                # przy kilku punktach sterujących pod rząd punkt on-curve
                # leży w połowie odcinka między nimi (reguła TrueType)
                nxt = ctrls[j + 1] if j + 1 < len(ctrls) else end
                if j + 1 < len(ctrls):
                    nxt = ((ctrl[0] + nxt[0]) / 2, (ctrl[1] + nxt[1]) / 2)
                for i in range(1, steps + 1):
                    t = i / steps
                    u = 1 - t
                    pts.append((u * u * p0[0] + 2 * u * t * ctrl[0] + t * t * nxt[0],
                                u * u * p0[1] + 2 * u * t * ctrl[1] + t * t * nxt[1]))
                p0 = nxt
            cur = end
    return pts


def contour_area(points):
    """Pole ze znakiem; znak określa kierunek konturu."""
    if len(points) < 3:
        return 0
    closed = points + [points[0]]
    return sum(x1 * y2 - x2 * y1
               for (x1, y1), (x2, y2) in zip(closed, closed[1:])) / 2


def dominant_winding(ops):
    """Znak pola największego konturu: +1 = przeciwnie do wskazówek, -1 = zgodnie."""
    best_area, sign = 0.0, 0
    for contour in split_contours(ops):
        area = contour_area(flatten_contour(contour))
        if abs(area) > abs(best_area):
            best_area, sign = area, (1 if area > 0 else -1)
    return sign


def reverse_ops(ops):
    rec = RecordingPen()
    replay(ops, ReverseContourPen(rec))
    return rec.value


def orient_like(accent_ops, base_ops):
    """Obraca kontury akcentu tak, żeby biegły w tę samą stronę co litera bazowa.

    Fonty wypełnia się regułą nonzero winding: kontur biegnący w PRZECIWNĄ stronę,
    nałożony na literę, znosi jej powierzchnię i zostawia białą dziurę. Dotyczy to
    wszystkiego, co wchodzi w literę: przekreślenia ł/Ł oraz ogonka wklejanego
    z zapasem OGONEK_MERGE w spód a/e/A/E.

    Kierunku nie da się założyć na sztywno, bo zależy od narzędzia, którym font
    zbudowano: TrueType każe rysować kontur zewnętrzny zgodnie z ruchem wskazówek,
    PostScript odwrotnie, a eksportery (np. TTF wypluty z fontów Scaleform przez
    JPEXS FFDec) trzymają się jednej z tych konwencji niezależnie od formatu.
    Dlatego mierzymy kierunek na samej literze i dopasowujemy do niej akcent.
    """
    want = dominant_winding(base_ops)
    if not want:
        return accent_ops
    out = []
    for contour in split_contours(accent_ops):
        area = contour_area(flatten_contour(contour))
        if area and (1 if area > 0 else -1) != want:
            contour = reverse_ops(contour)
        out.extend(contour)
    return out


# Błąd dopuszczalny przy zamianie krzywych sześciennych (tak zwraca skia) na
# kwadratowe konturów TrueType - w jednostkach em (× upm).
UNION_MAX_ERR = 0.001
_warned_no_pathops = False


def bbox_overlap(a, b):
    """Czy prostokąty mają wspólne POLE (sam styk krawędzią to za mało)."""
    if not a or not b:
        return False
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def union_ops(ops, upm, quadratic):
    """Kontury scalone w jeden zarys bez nakładek (suma logiczna).

    Litera i dorobiony znak to dwa osobne kontury, które muszą na siebie
    zachodzić, żeby się skleiły: belka przecina laskę ł, ogonek wchodzi w spód
    a/e (OGONEK_MERGE). Regułą nonzero taki glif wypełnia się poprawnie, ale
    rasteryzer even-odd wycina część wspólną - belka zostawia w lasce białą
    szparę, a ogonek wygryza róg litery. Skia liczy tu prawdziwą sumę, więc
    wynik wygląda tak samo w obu regułach.

    Bez modułu pathops zwracamy wejście bez zmian - lepiej nakładka niż brak
    znaku.
    """
    global _warned_no_pathops
    if pathops is None:
        if not _warned_no_pathops:
            _warned_no_pathops = True
            print("  ! brak modulu skia-pathops (pip install skia-pathops) -"
                  " litera i dorobiony znak zostaja osobnymi konturami;"
                  " rasteryzer even-odd wytnie ich czesc wspolna")
        return ops
    try:
        path = pathops.Path()
        replay(ops, path.getPen())
        path.simplify(fix_winding=True, keep_starting_points=False)
        rec = RecordingPen()
        if quadratic:
            # glyf trzyma wyłącznie krzywe kwadratowe, skia zwraca sześcienne
            path.draw(Cu2QuPen(rec, UNION_MAX_ERR * upm))
        else:
            path.draw(rec)
        return rec.value or ops
    except Exception:
        return ops


def clip_merged_ogonek(contours, cutoff, base_bottom):
    """Wycina spod litery ogonek zespolony z jej zewnętrznym konturem."""
    def clip(points, inside, intersect):
        clipped = []
        previous = points[-1]
        previous_inside = inside(previous)
        for current in points:
            current_inside = inside(current)
            if current_inside != previous_inside:
                clipped.append(intersect(previous, current))
            if current_inside:
                clipped.append(current)
            previous, previous_inside = current, current_inside
        return clipped

    out = []
    for contour in contours:
        points = flatten_contour(contour, steps=12)
        depth = cutoff - base_bottom
        deep = [(x, y) for x, y in points if y < base_bottom - depth / 2]
        if not deep:
            continue
        left = min(x for x, _ in deep) - depth / 3
        clipped = clip(
            points, lambda p: p[1] <= cutoff,
            lambda a, b: (a[0] + (b[0] - a[0]) * (cutoff - a[1]) / (b[1] - a[1]), cutoff))
        clipped = clip(
            clipped, lambda p: p[0] >= left,
            lambda a, b: (left, a[1] + (b[1] - a[1]) * (left - a[0]) / (b[0] - a[0])))
        if len(clipped) < 3:
            continue
        out.append(("moveTo", ((round(clipped[0][0]), round(clipped[0][1])),)))
        out.extend(("lineTo", ((round(x), round(y)),)) for x, y in clipped[1:])
        out.append(("closePath", ()))
    return out


def stem_width(polylines, base_bb, upm):
    """Grubość laski litery — żeby haczyk pasował wagą do kroju.

    Tniemy literę poziomo w kilku miejscach i bierzemy medianę szerokości
    pasm tuszu: w "a"/"e" to lewy brzuch i prawa laska, więc mediana wypada
    na typowej grubości kreski. Bez tego ogonek byłby nitką w Blacku i kluchą
    w Lightcie.
    """
    y0, y1 = base_bb[1], base_bb[3]
    runs = []
    for frac in (0.30, 0.45, 0.60):
        y = y0 + (y1 - y0) * frac
        xs = []
        for pts in polylines:
            if len(pts) < 2:
                continue
            seq = pts + [pts[0]]
            for (x1, ya), (x2, yb) in zip(seq, seq[1:]):
                if (ya <= y < yb) or (yb <= y < ya):   # przecięcie w jedną stronę
                    xs.append(x1 + (x2 - x1) * (y - ya) / (yb - ya))
        xs.sort()
        runs += [b - a for a, b in zip(xs[::2], xs[1::2]) if b > a]
    if not runs:
        return OGONEK_THICK_MIN * upm
    runs.sort()
    return runs[len(runs) // 2]


def ink_bottom_at(polylines, x):
    """Najniższy punkt litery na pionowej linii o danym x (albo None)."""
    ys = []
    for pts in polylines:
        if len(pts) < 2:
            continue
        seq = pts + [pts[0]]
        for (x1, y1), (x2, y2) in zip(seq, seq[1:]):
            if min(x1, x2) <= x <= max(x1, x2):
                ys.append(y1 if x1 == x2 else y1 + (y2 - y1) * (x - x1) / (x2 - x1))
    return min(ys) if ys else None


def ogonek_anchor_x(runs, x0, x1, stem):
    """Zaczep wewnątrz prawej nóżki/podstawy, nie nad nią na skosie A.

    Reguła z ttf_polish_glyphs: prawy odcinek przy spodzie litery, cofnięty
    o pół trzonu. Limit 80% nie może wypchnąć zaczepu poza ten odcinek:
    w A prawa nóżka często zaczyna się dopiero za 80% szerokości.
    Ta sama funkcja obsługuje kontury TTF i przekroje pikseli atlasu TMP.
    """
    left, right = runs[-1]
    inset = min(stem * 0.5, (right - left) * 0.5)
    preferred = min(right - stem * 0.55, x0 + OGONEK_ATTACH_MAX * (x1 - x0))
    return max(left + inset, min(preferred, right - inset))


def find_attach(polys, base_bb, upm):
    """Punkt pod prawą nóżką/podstawą, mierzony z rzeczywistego tuszu.

    Gdy brak przekroju przy spodzie ozdobnej litery, szukamy najniższego
    punktu w jej prawej części. Sam prawy dolny róg ramki nie wystarcza:
    pod "e" prawy brzeg zakręca do góry i haczyk zawisłby w powietrzu.
    """
    x0, y0, x1, y1 = base_bb
    runs = ink_runs_at_y(polys, y0 + (y1 - y0) * 0.05)
    if runs:
        x = ogonek_anchor_x(runs, x0, x1, stem_width(polys, base_bb, upm))
        bottom = ink_bottom_at(polys, x)
        if bottom is not None:
            return x, bottom
    w = x1 - x0
    lo, hi = x0 + 0.45 * w, x0 + OGONEK_ATTACH_MAX * w
    samples = []
    for i in range(21):
        x = lo + (hi - lo) * i / 20
        bottom = ink_bottom_at(polys, x)
        if bottom is not None:
            samples.append((x, bottom))
    if not samples:
        return hi, y0
    lowest = min(b for _, b in samples)
    flat = [s for s in samples if s[1] <= lowest + 0.02 * upm]
    return max(flat, key=lambda s: s[0])


def make_ogonek(base_ops, base_bb, upm):
    """Rysuje polski haczyk: w dół z odchyleniem w LEWO, a czubkiem z powrotem
    w PRAWO i do góry.

    Kierunek nie jest dowolny — na 73 fontach z prawdziwym "ą" nasada wypada
    na 0.815 szerokości litery, lewe wybrzuszenie na 0.611, a czubek wraca na
    0.996. Odbity haczyk (czubek w lewo) czyta się jak cudzy znak.
    """
    polys = [flatten_contour(ct) for ct in split_contours(base_ops)]
    ax, ay = find_attach(polys, base_bb, upm)
    # oś haczyka jako krzywa Béziera 3. stopnia (od nasady do czubka)
    p0 = (ax, ay + OGONEK_MERGE * upm)
    p1 = (ax - OGONEK_BULGE * upm, ay - 0.09 * upm)
    p2 = (ax - 0.01 * upm, ay - OGONEK_DEPTH * upm)
    p3 = (ax + OGONEK_BACK * upm, ay - OGONEK_DEPTH * upm * OGONEK_TIP_RISE)

    steps = 28
    axis = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        axis.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                     u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))

    # obudowanie osi grubością: kreska zwęża się ku końcowi, jak w prawdziwych
    # fontach (nasada zrośnięta z literą, czubek cienki)
    base_t = min(max(stem_width(polys, base_bb, upm) * OGONEK_THICK,
                     OGONEK_THICK_MIN * upm), OGONEK_THICK_MAX * upm)
    left, right = [], []
    for i, (x, y) in enumerate(axis):
        t = i / steps
        px, py = axis[max(i - 1, 0)]
        nx, ny = axis[min(i + 1, steps)]
        dx, dy = nx - px, ny - py
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        half = base_t * (1 - t * (1 - OGONEK_TIP)) / 2
        ox, oy = -dy / length * half, dx / length * half
        left.append((x + ox, y + oy))
        right.append((x - ox, y - oy))

    ring = left + right[::-1]
    outer = max(polys, key=lambda p: abs(contour_area(p)), default=[])
    if contour_area(ring) * contour_area(outer) < 0:
        # Nakładające się kontury o przeciwnych kierunkach wycinają dziurę
        # w miejscu połączenia ogonka z literą (reguła non-zero winding).
        ring.reverse()
    ops = [("moveTo", ((round(ring[0][0]), round(ring[0][1])),))]
    for x, y in ring[1:]:
        ops.append(("lineTo", ((round(x), round(y)),)))
    ops.append(("closePath", ()))
    return ops


# --- syntetyczna kreska i kropka (gdy w foncie nie ma żadnego dawcy) ---------
# Font "bez polskich znaków" bardzo często nie ma NICZEGO, z czego dałoby się
# wyciąć kreskę: ani ó/é/á, ani ´, ani znaku składającego (typowy przypadek to
# krój zrobiony pod jedną grę: VCR OSD Mono, dogica, Lusitana). Do tej pory
# zostawał wtedy tylko obcy font fallback albo transliteracja — a litera z
# fallbacku ma inny krój, inną szerokość i inną wysokość niż reszta napisu
# (w monospace, np. "WYJDŹ" w VCR OSD Mono, rzuca się to w oczy natychmiast).
# Dlatego kreskę i kropkę rysujemy tak samo, jak ogonek i przekreślenie.
#
# Proporcje w jednostkach em (jak wszystko w tym pliku), grubość liczona od
# grubości laski kroju — inaczej kreska byłaby nitką w Blacku i kluską w Light.
#
# Liczby nie są zgadnięte: zmierzone na 343 fontach systemowych (656 kresek nad
# minuskułą, 652 nad wersalikiem, 488 kropek) jako różnica konturów ó−o, é−e,
# Ó−O, ż−z. Mediany: kreska ma 0.209 em szerokości i 0.160 em wysokości, stoi
# 0.057 em nad minuskułą i 0.046 em nad wersalikiem, jej środek jest przesunięty
# 0.09 szerokości litery w prawo od jej środka; kropka: 0.123 em średnicy,
# 0.078 em nad minuskułą. Stałe niżej odtwarzają dokładnie te mediany, więc
# wierzchołek wypada tam, gdzie w prawdziwych fontach (0.90 em nad linią pisma
# dla wersalika, 0.72 em dla minuskuły).
ACUTE_HALF_W = 0.100       # połowa poziomego zasięgu kreski (× upm)
ACUTE_SLANT = 0.45         # nachylenie: podniesienie = SLANT × zasięg (~24°)
ACUTE_THICK = 0.75         # grubość pionowa (× grubość laski kroju)
ACUTE_THICK_MIN = 0.035    # widełki grubości (× upm)
ACUTE_THICK_MAX = 0.100
ACUTE_GAP = 0.050          # przerwa między górą litery a spodem kreski (× upm)
ACUTE_SHIFT = 0.090        # przesunięcie w prawo od środka litery (× jej szer.)
ACUTE_MAX_REL_W = 0.35     # zasięg nie większy niż tyle szerokości litery -
                           # w krojach silnie zwężonych (BlockGothic ExtraCond)
                           # kreska z medianowej szerokości byłaby szersza od
                           # samej litery

DOT_SYNTH_SIZE = 1.25      # średnica kropki (× grubość laski kroju)
DOT_SYNTH_MIN = 0.060      # widełki średnicy (× upm)
DOT_SYNTH_MAX = 0.150
DOT_SYNTH_GAP = 0.070      # przerwa między górą litery a spodem kropki (× upm)
DOT_MAX_REL_W = 0.35       # średnica nie większa niż tyle szerokości litery


# Litery, na których mierzymy grubość laski KROJU (osobno dla wersalików i
# minuskuł — kapitaliki są zwykle ździebko cięższe). Kreska i kropka mają być
# w całym foncie IDENTYCZNE, więc grubość liczy się raz dla kroju, a nie dla
# każdej litery bazowej osobno: mierzona na "Z" (sam ukos) wychodziła grubsza
# niż na "O", i akcent w "Ź" stał 2 px wyżej niż w "Ó".
STEM_REFS = {True: "IHELTF", False: "ilnhkbdt"}


def synth_thickness(base_ops, base_bb, upm, factor, lo, hi, stem=None):
    """Grubość dorysowanego znaku: laska × factor, przycięta do widełek."""
    if stem is None:
        polys = [flatten_contour(ct) for ct in split_contours(base_ops)]
        stem = stem_width(polys, base_bb, upm)
    return min(max(stem * factor, lo * upm), hi * upm)


def font_stem_width(glyph_set, cmap, upm, upper):
    """Grubość laski całego kroju: mediana pomiarów na kilku literach.

    Zwraca None, gdy żadnej litery odniesienia nie ma w foncie — wtedy wołający
    zmierzy literę bazową, tak jak przy ogonku.
    """
    widths = []
    for ch in STEM_REFS[upper]:
        gname = cmap.get(ord(ch))
        if not gname:
            continue
        try:
            ops = record_glyph(glyph_set, gname)
            bb = bbox(ops)
            if not bb or bb[3] <= bb[1]:
                continue
            polys = [flatten_contour(ct) for ct in split_contours(ops)]
            widths.append(stem_width(polys, bb, upm))
        except Exception:
            continue
    if not widths:
        return None
    widths.sort()
    return widths[len(widths) // 2]


def make_acute(base_ops, base_bb, upm, stem=None):
    """Syntetyczna kreska nad literą (ć ń ó ś ź) — ukośny równoległobok.

    Kształt jest ten sam co w make_stroke (ukośna belka o grubości odkładanej
    pionowo), tylko postawiony NAD literą i przesunięty ździebko w prawo od jej
    środka — tak stoi kreska w prawdziwych krojach (patrz stałe ACUTE_*).
    """
    x_min, _y_min, x_max, y_top = base_bb
    if y_top <= 0:
        return None
    t = synth_thickness(base_ops, base_bb, upm, ACUTE_THICK,
                        ACUTE_THICK_MIN, ACUTE_THICK_MAX, stem) / 2
    hx = min(ACUTE_HALF_W * upm, ACUTE_MAX_REL_W * (x_max - x_min))
    rise = ACUTE_SLANT * hx
    cx = (x_min + x_max) / 2 + ACUTE_SHIFT * (x_max - x_min)
    cy = y_top + ACUTE_GAP * upm + rise + t     # spód kreski = góra litery + przerwa
    pts = [(cx - hx, cy - rise + t), (cx + hx, cy + rise + t),
           (cx + hx, cy + rise - t), (cx - hx, cy - rise - t)]
    pts = [(round(x), round(y)) for x, y in pts]
    return [("moveTo", (pts[0],)), ("lineTo", (pts[1],)),
            ("lineTo", (pts[2],)), ("lineTo", (pts[3],)), ("closePath", ())]


def make_dot(base_ops, base_bb, upm, stem=None):
    """Syntetyczna kropka nad literą (ż Ż) — ośmiokąt wpisany w koło.

    Ośmiokąt, a nie kwadrat: kropka nad literą jest w większości krojów okrągła,
    a przy rozmiarach, w jakich ta kropka wychodzi (0.06–0.15 em), ośmiokąta nie
    da się odróżnić od koła. Wierzchołki są obrócone o 22.5°, więc kropka ma
    płaską górę i płaskie boki — nie ma piku, który rasteryzator zgubiłby
    w małym rozmiarze.
    """
    x_min, _y_min, x_max, y_top = base_bb
    if y_top <= 0:
        return None
    r = min(synth_thickness(base_ops, base_bb, upm, DOT_SYNTH_SIZE,
                            DOT_SYNTH_MIN, DOT_SYNTH_MAX, stem),
            DOT_MAX_REL_W * (x_max - x_min)) / 2
    cx = (x_min + x_max) / 2
    cy = y_top + DOT_SYNTH_GAP * upm + r
    rr = r / math.cos(math.pi / 8)          # promień na wierzchołki ośmiokąta
    pts = []
    for i in range(8):
        a = math.pi / 8 + i * math.pi / 4
        pts.append((round(cx + rr * math.cos(a)), round(cy + rr * math.sin(a))))
    ops = [("moveTo", (pts[0],))]
    ops += [("lineTo", (p,)) for p in pts[1:]]
    ops.append(("closePath", ()))
    return ops


def keep_sidebearings(ops, base_bb, advance):
    """Kontury i advance dorobionej litery z odstępami litery bazowej.

    Dorobiona litera dziedziczy advance po bazowej, ale jej tusz bywa SZERSZY:
    ogonek wywija się czubkiem w prawo poza obrys "a", a belka w ł wystaje poza
    laskę. Bez korekty prawy sidebearing schodzi do zera i litera skleja się
    z następną. Marginesy mają więc zostać takie jak w literze bazowej: co
    wystaje w prawo, powiększa advance, a co w lewo — przesuwa cały glif w prawo.
    """
    bb = bbox(ops)
    if not bb or not base_bb:
        return ops, advance
    rsb = max(advance - base_bb[2], 0)      # prawy odstęp litery bazowej
    dx = max(min(base_bb[0], 0) - bb[0], 0)  # ile tuszu wyszło w lewo poza nią
    if dx:
        ops = translate_ops(ops, dx, 0)
    return ops, max(advance + dx, round(bb[2] + dx + rsb))


def place_mark(kind, mark_ops, ref_top, base_bb, upm):
    """Przesuwa akcent nad/pod konkretną literę bazową."""
    mb = bbox(mark_ops)
    if kind in ("acute", "dot"):
        dx = (base_bb[0] + base_bb[2]) / 2 - (mb[0] + mb[2]) / 2
        dy = base_bb[3] - ref_top  # 0 dla małych liter, podbicie dla wersalików
    else:  # ogonek: dosunięty do prawej, zwisa z linii pisma
        dx = base_bb[2] - mb[2] - OGONEK_DONOR_LEFT * upm
        dy = base_bb[1] - ref_top
        mark_ops = clip_contours_top(
            mark_ops, ref_top + OGONEK_DONOR_OVERLAP * upm)
    if kind == "dot":
        # Kropka musi wisieć NAD literą. ref_top to zwykle xHeight z OS/2, a w
        # krojach z wysokimi minuskułami (Permanent Marker: z do 607, xHeight
        # niżej) kropka z ˙ lądowała w literze i po scaleniu konturów znikała.
        gap = DOT_MIN_GAP * upm
        if mb[1] + dy < base_bb[3] + gap:
            dy = base_bb[3] + gap - mb[1]
    return translate_ops(mark_ops, round(dx), round(dy))


def clip_contours_top(ops, top):
    """Odcina część konturów powyżej `top` i zamyka je płaską krawędzią."""
    out = []
    for contour in split_contours(ops):
        points = flatten_contour(contour, steps=12)
        if not points:
            continue
        clipped = []
        previous = points[-1]
        previous_inside = previous[1] <= top
        for current in points:
            current_inside = current[1] <= top
            if current_inside != previous_inside:
                dy = current[1] - previous[1]
                t = (top - previous[1]) / dy if dy else 0
                clipped.append((previous[0] + t * (current[0] - previous[0]), top))
            if current_inside:
                clipped.append(current)
            previous, previous_inside = current, current_inside
        if len(clipped) < 3:
            continue
        out.append(("moveTo", ((round(clipped[0][0]), round(clipped[0][1])),)))
        out.extend(("lineTo", ((round(x), round(y)),)) for x, y in clipped[1:])
        out.append(("closePath", ()))
    return out


# ------------------------------------------------------- dodawanie glifów

def add_glyph(font, name, ops, advance, lsb, base_glyph, reuse=False):
    """Zapisuje kontury `ops` jako glif `name`.

    reuse=True nadpisuje ISTNIEJĄCY glif o tej nazwie, nie dopisując nowego —
    tak recyklujemy martwe sloty w foncie, który stoi na limicie 65535 glifów
    (patrz GlyphSlots).
    """
    # hmtx/hhea przechowują liczby całkowite. BoundsPen/union_ops zwracają
    # floaty także dla całkowitych wartości (np. 902.0 w Electronic Highway Sign).
    # Zaokrąglamy przed zapisem również dla CFF, żeby oba zapisy metryk się zgadzały.
    advance, lsb = round(advance), round(lsb)
    if "glyf" in font:
        pen = TTGlyphPen(None)
        replay(ops, pen)
        font["glyf"].glyphs[name] = pen.glyph()  # dict: nadpisuje w miejscu
    else:
        cff = font["CFF "].cff
        top_dict = cff.topDictIndex[0]
        char_strings = top_dict.CharStrings
        cid_keyed = hasattr(top_dict, "ROS")
        if cid_keyed:
            # słownik prywatny bierzemy z FD litery bazowej
            fd = top_dict.FDSelect.gidArray[char_strings.charStrings[base_glyph]]
            private = top_dict.FDArray[fd].Private
        else:
            private = top_dict.Private
        pen = T2CharStringPen(advance, None)
        replay(ops, pen)
        charstring = pen.getCharString(private=private,
                                       globalSubrs=cff.GlobalSubrs)
        if reuse:
            gid = char_strings.charStrings[name]
            char_strings.charStringsIndex[gid] = charstring
            if cid_keyed:
                # charstring policzył szerokość względem FD litery bazowej,
                # więc slot musi dostać ten sam słownik prywatny
                top_dict.FDSelect.gidArray[gid] = fd
        else:
            char_strings.charStringsIndex.append(charstring)
            char_strings.charStrings[name] = len(char_strings.charStringsIndex) - 1
            top_dict.charset.append(name)
            if cid_keyed:
                top_dict.FDSelect.gidArray.append(fd)
                top_dict.CIDCount = max(top_dict.CIDCount, int(name[3:]) + 1)
    font["hmtx"][name] = (advance, lsb)
    if "vmtx" in font:  # fonty CJK: metryki pionowe kopiujemy z litery bazowej
        font["vmtx"][name] = font["vmtx"][base_glyph]
    order = list(font.getGlyphOrder())
    if name not in order:
        order.append(name)
    font.setGlyphOrder(order)
    if "glyf" in font:
        font["glyf"].glyphOrder = order  # glyf trzyma własną referencję do listy


def can_compose(font):
    return "glyf" in font or "CFF " in font


def is_cid_keyed(font):
    return "CFF " in font and hasattr(font["CFF "].cff.topDictIndex[0], "ROS")


CID_MAX = 65535  # CID w charset CFF jest zapisany jako Card16


def free_cids(font):
    """Iterator wolnych CID-ów dla fontu CID-keyed.

    Numerujemy dalej od najwyższego użytego, ale fonty CJK (np. Source Han
    Sans) sięgają CID-em blisko limitu Card16, a mają luki w numeracji —
    wtedy dobieramy najniższe wolne numery, bo inaczej charset nie da się
    skompilować ("'H' format requires 0 <= number <= 65535").
    """
    used = {int(n[3:]) for n in font.getGlyphOrder()
            if n.startswith("cid") and n[3:].isdigit()}
    start = (max(used) + 1) if used else 1
    for cid in range(start, CID_MAX + 1):
        if cid not in used:
            yield cid
    for cid in range(1, start):
        if cid not in used:
            yield cid


def new_glyph_name(font, ch, next_cid):
    """Nazwa nowego glifu: uniXXXX, a w fontach CID-keyed cidNNNNN."""
    if next_cid is not None:
        return f"cid{next_cid:05d}"
    name = f"uni{ord(ch):04X}"
    while name in font.getGlyphOrder():
        name += ".pl"
    return name


GLYPH_MAX = 65535  # numGlyphs w tablicy maxp to uint16 - twardy limit formatu


def _collect_glyph_names(obj, out, depth=0, seen=None):
    """Zbiera wszystkie nazwy glifów wymienione w gałęzi tablicy OpenType.

    Chodzi o zgrubne, ale bezpieczne oszacowanie "co GSUB może podstawić" —
    nadmiar (np. tagi feature'ów wzięte za nazwy glifów) tylko zmniejsza pulę
    slotów do recyklingu, więc jest po bezpiecznej stronie.
    """
    if depth > 24:
        return
    if isinstance(obj, str):
        out.add(obj)
        return
    if isinstance(obj, (list, tuple, set)):
        for x in obj:
            _collect_glyph_names(x, out, depth + 1, seen)
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str):
                out.add(k)
            _collect_glyph_names(v, out, depth + 1, seen)
        return
    attrs = getattr(obj, "__dict__", None)
    if not attrs:
        return
    if seen is None:
        seen = set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    for v in attrs.values():
        _collect_glyph_names(v, out, depth + 1, seen)


def dead_glyph_slots(font):
    """Glify, po które nie da się sięgnąć tekstem — kandydaci do recyklingu.

    Warunek: glif nie jest celem żadnego mapowania w unicode'owej cmap, nie
    występuje w GSUB (czyli nie da się go dostać podstawieniem z glifu, który
    w cmap jest) i nie jest komponentem żadnego glifu złożonego. Fonty CJK mają
    takich tysiące (Source Han Sans SC: 18 837), bo trzymają warianty pionowe
    i regionalne poza cmap.

    TMP w trybie dynamicznym pobiera glify po kodzie unicode (FT_Get_Char_Index)
    i nie stosuje shapingu, więc taki glif nigdy się nie wyrenderuje.
    """
    reachable = set()
    for table in font["cmap"].tables:
        reachable.update(table.cmap.values())
    if "GSUB" in font:
        try:
            _collect_glyph_names(font["GSUB"].table, reachable)
        except Exception:
            return iter(())  # nie wiemy, co GSUB rusza - nie ryzykujemy
    if "glyf" in font:
        # akcenty i kreski bywają trzymane poza cmap i wstawiane do liter jako
        # komponenty - nadpisanie takiego slotu zepsułoby gotowe litery
        try:
            glyf = font["glyf"]
            for name in font.getGlyphOrder():
                for comp in getattr(glyf[name], "components", ()) or ():
                    reachable.add(comp.glyphName)
        except Exception:
            return iter(())
    order = font.getGlyphOrder()
    return (n for n in order[1:] if n not in reachable)  # order[0] = .notdef


class GlyphSlots:
    """Rozdaje miejsca na nowe glify — z dopisywania albo z recyklingu.

    Normalnie glif dopisujemy na koniec fontu. Font na limicie 65535 glifów
    (Source Han Sans SC i inne pełne kroje CJK) nie przyjmie już ani jednego —
    `maxp.numGlyphs` jest uint16, więc fontTools wywala się przy zapisie na
    "Value 65536 does not fit in format H for numGlyphs". Wtedy zamiast
    dopisywać NADPISUJEMY glify nieosiągalne z cmap (patrz dead_glyph_slots),
    dzięki czemu liczba glifów się nie zmienia.
    """

    def __init__(self, font):
        self.font = font
        self.cid_keyed = is_cid_keyed(font)
        self.recycled = 0
        self._cids = free_cids(font) if self.cid_keyed else None
        self._next_cid = next(self._cids, None) if self._cids is not None else None
        self._dead = None
        self._next_dead = None

    def _can_append(self):
        return (len(self.font.getGlyphOrder()) < GLYPH_MAX
                and not (self.cid_keyed and self._next_cid is None))

    def _peek_dead(self):
        if self._dead is None:
            self._dead = dead_glyph_slots(self.font)
            self._next_dead = next(self._dead, None)
        return self._next_dead

    def available(self):
        """Czy jest jeszcze miejsce na choć jeden glif."""
        return self._can_append() or self._peek_dead() is not None

    def take(self, ch):
        """Zwraca (nazwa_glifu, reuse) albo (None, False), gdy brak miejsca."""
        if self._can_append():
            name = new_glyph_name(self.font, ch, self._next_cid)
            if self._cids is not None:
                self._next_cid = next(self._cids, None)
            return name, False
        name = self._peek_dead()
        if name is None:
            return None, False
        self._next_dead = next(self._dead, None)
        self.recycled += 1
        return name, True


def get_xheight(font, cmap, glyph_set, upm):
    os2 = font.get("OS/2")
    if os2 and getattr(os2, "sxHeight", 0) > 0:
        return os2.sxHeight
    if ord("x") in cmap:
        bb = bbox(record_glyph(glyph_set, cmap[ord("x")]))
        if bb:
            return bb[3]
    return 0.5 * upm


# ------------------------------------------------------------------ główna pętla

def fix_font(font, cmap, missing, add_accents=True, full_set=True):
    """Zwraca słownik metoda -> lista znaków: composed/synthesized/plain/unfixable.

    Klucz "_recycled" (metadana, nie lista znaków) mówi, ile glifów weszło na
    miejsce martwych slotów, bo font był na limicie 65535 glifów.
    """
    result = {"composed": [], "synthesized": [], "plain": [], "unfixable": []}
    glyph_set = font.getGlyphSet()
    upm = font["head"].unitsPerEm
    xheight = get_xheight(font, cmap, glyph_set, upm)
    composing = can_compose(font) and add_accents
    slots = GlyphSlots(font)
    mark_cache = {}
    stem_cache = {}      # grubość laski kroju (osobno wersaliki / minuskuły)
    subtables = [t for t in font["cmap"].tables if t.isUnicode()]
    new_ymax, new_ymin = 0, 0
    n_added = 0

    def map_char(ch, glyph_name):
        for st in subtables:
            st.cmap[ord(ch)] = glyph_name

    for ch in missing:
        base_ch, kind = ACCENTS[ch]
        base_glyph = cmap.get(ord(base_ch))
        if base_glyph is None:
            result["unfixable"].append(ch)
            continue
        if not slots.available():
            result["unfixable"].append(ch)  # font bez miejsca na nowe glify
            continue

        new_ops = None
        method = "plain"
        base_ops = None
        try:
            base_ops = record_glyph(glyph_set, base_glyph)
        except Exception:
            base_ops = None
        if composing and base_ops:
            try:
                base_bb = bbox(base_ops)
                if base_bb:
                    if not full_set and kind not in ("acute", "dot"):
                        accent = None  # tryb okrojony: tylko kreska i kropka
                    elif kind == "stroke":
                        upper = ch.isupper()
                        if upper not in stem_cache:
                            stem_cache[upper] = font_stem_width(glyph_set, cmap, upm, upper)
                        accent = make_stroke(base_bb, upm, upper, stem_cache[upper],
                                             base_ops=base_ops)
                        method = "synthesized"
                    elif kind == "ogonek":
                        # Samodzielny U+0328/U+02DB oraz ogonek wycięty z innej
                        # litery mają własne położenie bazowe. W części fontów po
                        # przeniesieniu zostawały kilka pikseli pod literą jako
                        # odłączone "c". Rysowany haczyk mierzy rzeczywisty spód
                        # docelowego a/e/A/E, więc zawsze styka się z literą.
                        accent = make_ogonek(base_ops, base_bb, upm)
                        method = "synthesized"
                    else:
                        if kind not in mark_cache:
                            mark_cache[kind] = find_mark(glyph_set, cmap, kind, upm, xheight)
                        mark = mark_cache[kind]
                        if mark:
                            accent = place_mark(kind, mark[0], mark[1], base_bb, upm)
                            method = "composed"
                        elif kind in ("acute", "dot"):
                            # Kreska i kropka też: bez tego font bez ani jednego
                            # akcentu (VCR OSD Mono, dogica) musiał brać ć ń ó ś ź
                            # z OBCEGO kroju albo iść w transliteracje.
                            upper = ch.isupper()
                            if upper not in stem_cache:
                                stem_cache[upper] = font_stem_width(
                                    glyph_set, cmap, upm, upper)
                            draw = make_acute if kind == "acute" else make_dot
                            accent = draw(base_ops, base_bb, upm, stem_cache[upper])
                            method = "synthesized"
                        else:
                            accent = None
                    if accent is not None:
                        accent = list(orient_like(accent, base_ops))
                        new_ops = list(base_ops) + accent
                        # znak wchodzący w literę (belka ł, ogonek) zostawia
                        # część wspólną - scalamy ją, żeby even-odd nie zrobił
                        # z niej dziury
                        if bbox_overlap(base_bb, bbox(accent)):
                            new_ops = union_ops(new_ops, upm, "glyf" in font)
            except Exception:
                new_ops = None
                method = "plain"

        # fallback bez akcentu: niezależna KOPIA litery bazowej (własny glif,
        # żeby edycja ó nie zmieniała o)
        if not new_ops and base_ops:
            new_ops = list(base_ops)
            method = "plain"

        if new_ops:
            name, reuse = slots.take(ch)
            if name is None:
                result["unfixable"].append(ch)
                continue
            advance, _ = font["hmtx"][base_glyph]
            new_ops, advance = keep_sidebearings(
                new_ops, bbox(base_ops) if base_ops else None, advance)
            full_bb = bbox(new_ops)
            add_glyph(font, name, new_ops, advance, round(full_bb[0]), base_glyph,
                      reuse=reuse)
            map_char(ch, name)
            n_added += 1
            new_ymax = max(new_ymax, full_bb[3])
            new_ymin = min(new_ymin, full_bb[1])
            result[method].append(ch)
        else:
            map_char(ch, base_glyph)  # ostateczność: brak konturów bazy
            result["plain"].append(ch)

    result["_recycled"] = slots.recycled
    # porządki po dodaniu glifów
    if n_added:
        font["maxp"].numGlyphs = len(font.getGlyphOrder())
        for tag in ("hdmx", "LTSH"):  # cache'e per-glif, nie znają nowych glifów
            if tag in font:
                del font[tag]
        if "post" in font and font["post"].formatType == 2.0:
            font["post"].formatType = 3.0  # nazwy glifów zbędne, unikamy przeliczania
        # zapas w metrykach, żeby akcenty nad wersalikami się nie ucinały
        hhea = font.get("hhea")
        os2 = font.get("OS/2")
        if hhea:
            hhea.ascent = max(hhea.ascent, round(new_ymax))
            hhea.descent = min(hhea.descent, round(new_ymin))
        if os2:
            os2.usWinAscent = max(os2.usWinAscent, round(new_ymax))
            os2.usWinDescent = max(os2.usWinDescent, round(-new_ymin))
    return result


# ------------------------------------------------- naprawa na bajtach pliku
# Wspolne wejscie dla narzedzi silnikowych (Unity: fix_tmp_polish_fonts.py,
# Unreal: tools/font_fixer/unreal/fix_unreal_polish_fonts.py). Kazde z nich wyciaga font
# ze swojego opakowania (TMP/Font asset, .ufont) i oddaje tu czyste bajty
# TTF/OTF/TTC - sama naprawa kroju jest w jednym miejscu.

def open_faces(data):
    """Otwiera plik fontu: (kolekcja albo None, lista TTFont).

    Pliki .ttc to kolekcje kilku krojow w jednym pliku (np. fusion-pixel ma
    warianty latin/zh_hans/zh_hant/ja/ko). Nie wiadomo, po ktory siega gra,
    wiec naprawiamy je wszystkie i zapisujemy z powrotem jako kolekcje.
    """
    if data[:4] == b"ttcf":
        from fontTools.ttLib import TTCollection
        coll = TTCollection(io.BytesIO(data), lazy=False)
        return coll, coll.fonts
    return None, [TTFont(io.BytesIO(data), lazy=False)]


def save_faces(coll, fonts):
    buf = io.BytesIO()
    if coll is not None:
        # bez shareTables wspolne tablice (glyf CJK!) zdubluja sie na kazdy
        # kroj i plik rosnie kilkukrotnie
        coll.save(buf, shareTables=True)
    else:
        fonts[0].save(buf)
    return buf.getvalue()


# kolejnosc "od najlepszej metody": przy kolekcji znak liczy sie tak, jak
# wyszedl w NAJGORSZYM kroju - inaczej obiecalibysmy akcent, ktorego czesc
# krojow nie ma
METHOD_RANK = {"composed": 0, "synthesized": 1, "plain": 2, "unfixable": 3}


def merge_reports(reports):
    worst = {}
    for rep in reports:
        for method, chars in rep.items():
            if method.startswith("_"):
                continue  # metadane fix_font (np. _recycled), nie lista znakow
            for ch in chars:
                cur = worst.get(ch)
                if cur is None or METHOD_RANK[method] > METHOD_RANK[cur]:
                    worst[ch] = method
    out = {k: [] for k in METHOD_RANK}
    for ch in POLISH_CHARS:
        if ch in worst:
            out[worst[ch]].append(ch)
    return out


def missing_in_bytes(data, chars=None):
    """Polskie znaki, ktorych brakuje w ktorymkolwiek kroju pliku."""
    _coll, fonts = open_faces(data)
    missing = []
    for f in fonts:
        for ch in missing_characters(f, list(chars or POLISH_CHARS)):
            if ch not in missing:
                missing.append(ch)
        f.close()
    return missing


def fix_font_bytes(data, chars=None, add_accents=True, full_set=True, on_face=None):
    """Dorabia brakujace polskie znaki w pliku TTF/OTF/TTC podanym jako bajty.

    Zwraca (nowe_bajty, raport) - raport jak z fix_font (composed / synthesized /
    plain / unfixable), scalony po krojach kolekcji; "_recycled" = suma.
    on_face(font, indeks, liczba_krojow) - opcjonalny zaczep na komunikaty.
    """
    coll, fonts = open_faces(data)
    wanted = [ch for ch in (chars or POLISH_CHARS) if ch in ACCENTS]
    reports = []
    for i, f in enumerate(fonts):
        if on_face:
            on_face(f, i, len(fonts))
        cmap = f.getBestCmap() or {}
        todo = missing_characters(f, wanted)
        reports.append(fix_font(f, cmap, todo, add_accents=add_accents,
                                full_set=full_set))
    out = save_faces(coll, fonts)
    report = merge_reports(reports)
    report["_recycled"] = sum(r.get("_recycled", 0) for r in reports)
    return out, report


def ask_yes_no(question, default=True):
    hint = "[T/n]" if default else "[t/N]"
    answer = input(f"{question} {hint}: ").strip().lower()
    if not answer:
        return default
    return answer in ("t", "tak", "y", "yes")


def main():
    folder = input("📂 Podaj ścieżkę do folderu z czcionkami: ").strip().strip('"').lstrip("﻿")
    folder = Path(folder)
    if not folder.is_dir():
        print(f"❌ Folder nie istnieje: {folder}")
        sys.exit(1)

    fonts = sorted(
        p for p in folder.rglob("*")
        if p.suffix.lower() in (".ttf", ".otf") and "fixed" not in p.parts
    )
    if not fonts:
        print("❌ Nie znaleziono plików .ttf / .otf")
        sys.exit(1)

    add_accents = ask_yes_no("✏️  Dorabiać polskie ogonki i kreski (nowe glify w foncie)?")
    full_set = True
    if add_accents:
        full_set = ask_yes_no(
            "   Wszystkie? (t = wszystkie, n = tylko kreska i kropka: ć ń ó ś ź ż)")
    else:
        print("   ➡️  Brakujące znaki będą tylko mapowane na litery bez ogonków")

    in_place = ask_yes_no("💾 Nadpisywać naprawiane pliki fontów wynikami?")
    if not in_place:
        print("   ➡️  Wyniki trafią do podfolderu 'fixed'")

    print(f"\n🔍 Znaleziono {len(fonts)} czcionek\n")

    out_dir = folder / "fixed"
    any_fixed = False

    for path in fonts:
        try:
            font = TTFont(path, lazy=False)
            cmap = font.getBestCmap()
        except Exception as e:
            print(f"⚠️  {path.name}: nie udało się otworzyć ({e})")
            continue

        missing = missing_characters(font, POLISH_CHARS)
        if not missing and add_accents:
            refresh = ask_yes_no(
                f"🔁 {path.name}: polskie znaki już są. Przerysować ą/ę/Ą/Ę?",
                default=False)
            if refresh:
                missing = list("ąęĄĘ")
        if not missing:
            print(f"✅ {path.name}: wszystkie polskie znaki obecne")
            font.close()
            continue

        print(f"❌ {path.name}: brakuje {len(missing)} znaków: {' '.join(missing)}")

        try:
            result = fix_font(font, cmap, missing, add_accents, full_set)
        except Exception as e:
            print(f"   ⚠️ Błąd naprawy: {e}")
            font.close()
            continue

        if result.get("_recycled"):
            print(f"   ♻️  Font na limicie {GLYPH_MAX} glifów - {result['_recycled']} "
                  f"nowych weszło na miejsce glifów nieosiągalnych z cmap")
        if result["composed"]:
            print(f"   🎨 Dorobione z akcentem: {' '.join(result['composed'])}")
        if result["synthesized"]:
            print(f"   🧪 Dorysowane wprost (ogonek / kreska / kropka / przekreślenie): "
                  f"{' '.join(result['synthesized'])}")
        if result["plain"]:
            print(f"   ⚠️  Tylko wersja bez ogonka (brak akcentu w foncie): {' '.join(result['plain'])}")
        if result["unfixable"]:
            print(f"   🚫 Brak litery bazowej, pominięto: {' '.join(result['unfixable'])}")

        if len(result["unfixable"]) < len(missing):
            if in_place:
                # zapis przez plik tymczasowy: font trzyma otwarte źródło,
                # więc nadpisujemy dopiero po zamknięciu
                tmp_path = path.with_name(path.name + ".tmp")
                font.save(tmp_path)
                font.close()
                os.replace(tmp_path, path)
                out_path = path
            else:
                out_dir.mkdir(exist_ok=True)
                out_path = out_dir / path.name
                font.save(out_path)
                font.close()
            any_fixed = True
            print(f"   💾 Zapisano: {out_path}")
        else:
            font.close()

    if any_fixed:
        target = "oryginalne pliki (nadpisane)" if in_place else str(out_dir)
        print(f"\n✨ Gotowe — poprawione czcionki: {target}")
    else:
        print("\n✨ Gotowe — nic do poprawy")


if __name__ == "__main__":
    main()
