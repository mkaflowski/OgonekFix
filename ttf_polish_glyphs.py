"""Dokladanie polskich glifow do fontu TrueType (tabela ``glyf``).

Brakujace ``a c e l n o s z`` z ogonkiem / kreska / kropka budujemy ze skladnikow,
ktore font juz ma -- ``acutecomb`` (kreska), ``uni0328`` (ogonek), ``period``
(kropka) -- skladajac je z litera bazowa w glif zlozony (composite). Dzieki temu
akcent jest w kroju fontu, a nie doklejony z obcego pliku. Kreske w ``l``/``L``
oraz ogonek, gdy font nie ma znaku laczacego ``U+0328``, rysujemy proceduralnie.

Kreske nad litera stawiamy tam, gdzie font stawia ja sam (``aacute`` kontra
``acutecomb``). Ogonek sadzamy na styk: jego gorna krawedz laduje na dolnej
krawedzi litery, pod jej prawym trzonem. Proporcje kreski w ``ł``/``Ł`` sa
zdjete z krojow, ktore ten znak maja narysowany (Arial, Verdana, Calibri,
Times): grubosc ~0,85 trzonu, szerokosc ~2,5 trzonu razem ze skosem, srodek na
44% wysokosci litery.

CEDYLLA NIE JEST DAWCA OGONKA. Wczesniej w krojach bez ``U+0328`` bralismy
``cedilla`` -- i to jest blad widoczny golym okiem: cedylla zakreca czubkiem
w LEWO, a polski ogonek w PRAWO i do gory. W fontach MGS4 (``SCE-PS3-*``)
dawalo to font, w ktorym ``ą``/``ę`` (dorysowane) i ``Ą``/``Ę`` (z cedylli)
mialy haczyk odwrocony wzgledem siebie. Gdy nie ma prawdziwego dawcy, ogonek
rysujemy -- proporcjami z badania 73 krojow, ktore opisuje ``fix_polish_fonts``.

Font otwieraj z ``recalcBBoxes=False``. Z domyslnym ``True`` fontTools przy
przebudowie tabeli ``glyf`` potrafi przesunac wspolrzedne istniejacych glifow
o jedna jednostke -- niby nic, ale to zmiana w cudzym foncie, ktorej nie
zamawialismy. Bboxy nowych glifow ta funkcja liczy sama.

Uzycie::

    from fontTools.ttLib import TTFont
    ft = TTFont("font.ttf", recalcBBoxes=False)
    added = add_polish_glyphs(ft)
    ft.save("font_pl.ttf")
"""

from __future__ import annotations

from dataclasses import dataclass

from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent, GlyphCoordinates

# polskie znaki i sposob ich zlozenia
ACUTE = "acute"      # kreska ukosna nad litera
OGONEK = "ogonek"    # haczyk pod litera
DOT = "dot"          # kropka nad litera
STROKE = "stroke"    # kreska przez trzon (tylko l/L)

# znak -> (litera bazowa, rodzaj akcentu, nazwa glifu)
POLISH: dict[str, tuple[str, str, str]] = {
    "ą": ("a", OGONEK, "aogonek"),      # a
    "ć": ("c", ACUTE, "cacute"),        # c
    "ę": ("e", OGONEK, "eogonek"),      # e
    "ł": ("l", STROKE, "lslash"),       # l
    "ń": ("n", ACUTE, "nacute"),        # n
    "ó": ("o", ACUTE, "oacute"),        # o (zwykle juz jest)
    "ś": ("s", ACUTE, "sacute"),        # s
    "ź": ("z", ACUTE, "zacute"),        # z
    "ż": ("z", DOT, "zdotaccent"),      # z z kropka
    "Ą": ("A", OGONEK, "Aogonek"),
    "Ć": ("C", ACUTE, "Cacute"),
    "Ę": ("E", OGONEK, "Eogonek"),
    "Ł": ("L", STROKE, "Lslash"),
    "Ń": ("N", ACUTE, "Nacute"),
    "Ó": ("O", ACUTE, "Oacute"),
    "Ś": ("S", ACUTE, "Sacute"),
    "Ź": ("Z", ACUTE, "Zacute"),
    "Ż": ("Z", DOT, "Zdotaccent"),
}

PL_CHARS = "".join(POLISH)


@dataclass
class _Box:
    x_min: int
    y_min: int
    x_max: int
    y_max: int

    @property
    def cx(self) -> float:
        return (self.x_min + self.x_max) / 2

    @property
    def width(self) -> int:
        return self.x_max - self.x_min


def _best_cmap(font: TTFont) -> dict[int, str]:
    """``getBestCmap()``, ale pusty slownik zamiast ``None``.

    Fonty symboliczne (np. ``BSSYM7.TTF``) maja wylacznie podtabele ``(1,0)``
    i ``(3,0)`` -- bez zadnej unikodowej ``getBestCmap()`` zwraca ``None``,
    a kazde ``kod in cmap`` wysypywalo sie wtedy na ``TypeError``.
    """
    return font.getBestCmap() or {}


# znaki pomocnicze, ktore font moze trzymac pod kodem, a nie pod nazwa
_BY_CODE = {"acutecomb": 0x0301, "period": 0x002E,
            "aacute": 0x00E1, "Aacute": 0x00C1}


def _glyph_for(font: TTFont, glyf, name: str) -> str | None:
    """Nazwa, pod ktora TEN font trzyma dany glif -- szukana po ``cmap``.

    Nie kazdy krój nazywa litery po ludzku: ``Inter`` ma ``uni0061`` zamiast
    ``a``, wiec szukanie po nazwie nie znajdowalo ani liter bazowych, ani
    dawcow akcentow i font wychodzil bez ani jednego polskiego znaku.
    Pierwszenstwo ma ``cmap``, bo to ona decyduje, co sie naprawde rysuje.
    """
    cp = ord(name) if len(name) == 1 else _BY_CODE.get(name)
    if cp is not None:
        found = _best_cmap(font).get(cp)
        if found and found in glyf:
            return found
    return name if name in glyf else None


def _bbox(glyf, name: str | None) -> _Box | None:
    if not name or name not in glyf:
        return None
    g = glyf[name]
    if not getattr(g, "numberOfContours", 0):
        return None
    g.recalcBounds(glyf)
    return _Box(g.xMin, g.yMin, g.xMax, g.yMax)


def _offset(glyf, composed: str | None, component: str | None, axis: str) -> int | None:
    """O ile font przesuwa ``component``, skladajac gotowy glif ``composed``."""
    a, b = _bbox(glyf, composed), _bbox(glyf, component)
    if not (a and b):
        return None
    return (a.y_max - b.y_max) if axis == "top" else (a.y_min - b.y_min)


def _make_composite(parts: list[tuple[str, float, float]]) -> Glyph:
    """Glif zlozony z komponentow ``(nazwa, dx, dy)``."""
    g = Glyph()
    g.numberOfContours = -1
    g.components = []
    for name, dx, dy in parts:
        c = GlyphComponent()
        c.glyphName = name
        c.x, c.y = int(round(dx)), int(round(dy))
        c.flags = 0x0002 | 0x0004  # ARGS_ARE_XY_VALUES | ROUND_XY_TO_GRID
        g.components.append(c)
    # litera bazowa narzuca metryki calego glifu, akcent ich nie rusza
    g.components[0].flags |= 0x0200 | 0x0400  # USE_MY_METRICS | OVERLAP_COMPOUND
    return g


def _quad(p0, c, p1, steps: int = 8) -> list[tuple[float, float]]:
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1])
            for t in (i / steps for i in range(1, steps + 1))]


def _cubic(p0, c1, c2, p1, steps: int = 8) -> list[tuple[float, float]]:
    return [((1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * c1[0]
             + 3 * (1 - t) * t * t * c2[0] + t ** 3 * p1[0],
             (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * c1[1]
             + 3 * (1 - t) * t * t * c2[1] + t ** 3 * p1[1])
            for t in (i / steps for i in range(1, steps + 1))]


def _outline(font: TTFont, name: str) -> list[list[tuple[float, float]]]:
    """Kontury glifu jako wielokaty -- krzywe probkujemy, komponenty rozwijamy.

    Do pomiarow (trzon litery, punkt zaczepu ogonka) taka dokladnosc wystarcza,
    a w odroznieniu od czytania ``glyf`` wprost dziala tak samo na glifach
    prostych i zlozonych.
    """
    glyph_set = font.getGlyphSet()
    if name not in glyph_set:
        return []
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(pen)

    out: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    start = None
    for op, args in pen.value:
        if op == "moveTo":
            if cur:
                out.append(cur)
            start = args[0]
            cur = [start]
        elif op == "lineTo":
            cur.append(args[0])
        elif op == "qCurveTo":
            pts = list(args)
            if pts[-1] is None:  # kontur z samych punktow sterujacych
                pts[-1] = start
            # miedzy dwoma kolejnymi punktami sterujacymi TrueType dorozumiewa
            # punkt na konturze -- w polowie odcinka miedzy nimi
            ctrl, end = pts[:-1], pts[-1]
            for i, c in enumerate(ctrl):
                nxt = end if i + 1 == len(ctrl) else (
                    (c[0] + ctrl[i + 1][0]) / 2, (c[1] + ctrl[i + 1][1]) / 2)
                cur.extend(_quad(cur[-1], c, nxt))
        elif op == "curveTo":
            pts = list(args)
            cur.extend(_cubic(cur[-1], pts[0], pts[1], pts[-1]))
        elif op in ("closePath", "endPath"):
            if cur:
                out.append(cur)
                cur = []
    if cur:
        out.append(cur)
    return out


def _box(font: TTFont, name: str) -> _Box | None:
    """Ramka glifu policzona z konturow (takze dla glifow zlozonych)."""
    outline = _outline(font, name)
    if not outline:
        return None
    xs = [p[0] for c in outline for p in c]
    ys = [p[1] for c in outline for p in c]
    return _Box(min(xs), min(ys), max(xs), max(ys))


def _spans_at(polys, y: float) -> list[tuple[float, float]]:
    """Poziome odcinki wnetrza glifu na wysokosci ``y``, od lewej."""
    xs: list[float] = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if (y1 <= y < y2) or (y2 <= y < y1):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)]


def _spans_v(polys, x: float) -> list[tuple[float, float]]:
    """Pionowe odcinki wnetrza glifu na prostej ``x``, od dolu."""
    ys: list[float] = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            if (x1 <= x < x2) or (x2 <= x < x1):
                ys.append(y1 + (x - x1) * (y2 - y1) / (x2 - x1))
    ys.sort()
    return [(ys[i], ys[i + 1]) for i in range(0, len(ys) - 1, 2)]


# nazwy i kody, pod ktorymi font moze trzymac gotowy ogonek
_OGONEK_NAMES = ("uni0328", "ogonek", "ogonekcomb")
_OGONEK_CODES = (0x0328, 0x02DB)


def _ogonek_source(font: TTFont) -> str | None:
    """Glif z PRAWDZIWYM ogonkiem albo ``None``, gdy trzeba go dorysowac.

    Fonty japonskie (``NR``/``SR``) maja znak laczacy ``U+0328`` narysowany
    przez projektanta kroju i to jego uzywamy -- zmierzone szerokosci (0,236
    i 0,247 em) mieszcza sie w normie prawdziwych ogonkow (Arial 0,166,
    Calibri 0,184, Verdana 0,233 em).

    Cedylli tu NIE MA i byc nie moze -- to inny znak, zakrecony w druga
    strone. Patrz naglowek modulu.
    """
    order = set(font.getGlyphOrder())
    for name in _OGONEK_NAMES:
        if name in order:
            return name
    cmap = _best_cmap(font)
    for cp in _OGONEK_CODES:
        if cp in cmap:
            return cmap[cp]
    return None


# --- rysowany ogonek --------------------------------------------------------
# Proporcje z badania 73 krojow z prawdziwym ``ą`` (liczby i uzasadnienie:
# ``fix_polish_fonts.py``, sekcja "syntetyczny ogonek"). Haczyk idzie W DOL
# z odchyleniem w LEWO, a czubkiem wraca w PRAWO i do gory: nasada wypada na
# 0,815 szerokosci litery, lewe wybrzuszenie na 0,611, czubek na 0,996.
# Skalujemy do ``upem``, nie do szerokosci litery -- w prawdziwych krojach
# haczyk jest zaskakujaco staly (szer. ~0,18 em; glebokosc ograniczona wizualnie
# do ~0,14 em) niezaleznie
# od tego, czy siedzi pod ``a``, ``e``, ``A`` czy ``E``.
_OG_DEPTH = 0.185       # punkt sterujacy; glebszy haczyk wygladal na opuszczony
_OG_BACK = 0.11         # ile czubek wywija sie w PRAWO od nasady (x em)
_OG_BULGE = 0.05        # ile haczyk wybrzusza sie w LEWO po drodze (x em)
_OG_THICK = 0.80        # grubosc u nasady (x grubosc trzonu litery)
_OG_THICK_MIN = 0.030   # widelki grubosci (x em), zeby nie wyszla nitka...
_OG_THICK_MAX = 0.095   # ...ani kluska przy bardzo ciezkich krojach
_OG_TIP = 0.55          # grubosc czubka (x grubosc u nasady)
_OG_TIP_RISE = 0.42     # na jakiej wysokosci konczy sie czubek (x glebokosc)
_OG_MERGE = 0.02        # ile wchodzi w litere, zeby sie z nia skleic (x em)
_OG_ATTACH_MAX = 0.80   # najdalej w prawo, gdzie wolno zaczepic (x szer. litery)
_OG_STEPS = 28          # na ile odcinkow dzielimy os haczyka


def _contour_area(pts) -> float:
    """Pole ze znakiem -- znak mowi, w ktora strone biegnie kontur."""
    total = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        total += x1 * y2 - x2 * y1
    return total / 2


def _make_ogonek(outline, base: _Box, upem: int, stem_w: float,
                 attach: tuple[float, float]) -> Glyph:
    """Rysuje polski haczyk pod litera i zwraca go jako osobny glif.

    Os haczyka to krzywa Beziera 3. stopnia, obudowana gruboscia zwezajaca sie
    ku czubkowi (nasada zrosnieta z litera, czubek cienki) -- tak jak w krojach,
    ktore ten znak maja narysowany.
    """
    ax, ay = attach
    p0 = (ax, ay + _OG_MERGE * upem)
    p1 = (ax - _OG_BULGE * upem, ay - 0.09 * upem)
    p2 = (ax - 0.01 * upem, ay - _OG_DEPTH * upem)
    p3 = (ax + _OG_BACK * upem, ay - _OG_DEPTH * upem * _OG_TIP_RISE)

    axis = [p0]
    axis.extend(_cubic(p0, p1, p2, p3, steps=_OG_STEPS))

    thick = min(max(stem_w * _OG_THICK, _OG_THICK_MIN * upem), _OG_THICK_MAX * upem)
    left, right = [], []
    last = len(axis) - 1
    for i, (x, y) in enumerate(axis):
        t = i / last
        px, py = axis[max(i - 1, 0)]
        nx, ny = axis[min(i + 1, last)]
        dx, dy = nx - px, ny - py
        length = (dx * dx + dy * dy) ** 0.5 or 1.0
        half = thick * (1 - t * (1 - _OG_TIP)) / 2
        ox, oy = -dy / length * half, dx / length * half
        left.append((x + ox, y + oy))
        right.append((x - ox, y - oy))

    ring = left + right[::-1]
    # Nakladajace sie kontury o PRZECIWNYCH kierunkach wycinaja dziure w miejscu,
    # gdzie ogonek styka sie z litera (reguła non-zero winding) -- ten sam blad,
    # ktory dawal "kraciasta kokardke" w ``ł`` (patrz ``_make_stroke``).
    outer = max(outline, key=lambda c: abs(_contour_area(c)), default=[])
    if outer and _contour_area(ring) * _contour_area(outer) < 0:
        ring.reverse()

    pts: list[tuple[int, int]] = []
    for x, y in ring:
        p = (int(round(x)), int(round(y)))
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()

    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates(pts)
    g.flags = bytearray([1] * len(pts))  # wszystkie punkty na konturze
    g.endPtsOfContours = [len(pts) - 1]
    g.program = _empty_program()
    return g


def _fit_advance(x_max: float, advance: int, upem: int, max_shift: float) -> float:
    """Przesuniecie w lewo, gdy czubek ogonka wychodzi za szerokosc znaku.

    Ogonek wystajacy za ``advance`` wchodzi na nastepna litere, a w interfejsach
    o stalej szerokosci komorki (menu gry) bywa przycinany. Zmierzone na krojach
    z prawdziwym ogonkiem: Arial +0,2% em, Times i Calibri w ogole nie wychodza,
    Verdana do +8,7% -- wiec ciut tolerancji zostawiamy, ale bez przesady.
    Cofamy najwyzej o grubosc trzonu, zeby haczyk nie odklejil sie od litery.
    """
    over = x_max - (advance + upem * 0.02)
    return -min(over, max_shift) if over > 0 else 0.0


def _top_anchor(outline) -> tuple[float, float]:
    """Punkt, ktorym akcent styka sie z litera: srodek jego gornej krawedzi."""
    pts = [p for c in outline for p in c]
    y_max = max(p[1] for p in pts)
    y_min = min(p[1] for p in pts)
    band = (y_max - y_min) * 0.10
    top = [p[0] for p in pts if p[1] >= y_max - band]
    return sum(top) / len(top), y_max


def _ref_stem(font: TTFont, upem: int) -> float:
    """Grubosc pionowego trzonu w tym kroju -- mierzona na ``l``/``I``/``E``."""
    for name in ("l", "I", "E", "L", "n", "H"):
        box = _box(font, name)
        if box is None:
            continue
        spans = _spans_at(_outline(font, name), box.y_max * 0.55)
        if spans:
            return spans[0][1] - spans[0][0]
    return upem * 0.09


def _ogonek_attach(font: TTFont, name: str, base: _Box,
                   stem_w: float) -> tuple[float, float]:
    """Miejsce, w ktore wchodzi ogonek: podstawa prawego trzonu litery.

    Tuz nad dolna krawedzia litery bierzemy skrajnie prawy odcinek jej wnetrza
    -- dla ``a``/``A`` to prawy trzon albo prawa noga, dla ``e``/``E`` prawy
    koniec podstawy. Cofamy sie od jego prawej krawedzi o pol trzonu, zeby
    ogonek wyrastal ze srodka kreski, a nie z jej brzegu.

    Nasade ograniczamy do ``_OG_ATTACH_MAX`` szerokosci litery. Bez tego limitu
    w ``SCE-PS3-NR-R-JPN`` zaczep uciekal na 0,71-0,76 szerokosci i czubek
    wychodzil 9-10% em za szerokosc znaku; badanie 73 krojow daje nasade na
    0,815 szerokosci litery.
    """
    outline = _outline(font, name)
    cap = base.x_min + _OG_ATTACH_MAX * base.width
    probe = base.y_min + (base.y_max - base.y_min) * 0.05
    spans = _spans_at(outline, probe)
    if not spans:
        return min(base.x_max - stem_w * 0.55, cap), base.y_min
    left, right = spans[-1]
    x = right - stem_w * 0.55
    if x < left + stem_w * 0.5:  # odcinek wezszy od trzonu -- bierzemy srodek
        x = (left + right) / 2
    x = min(x, cap)
    below = _spans_v(outline, x)
    y = min(s[0] for s in below) if below else base.y_min
    return x, y


def _stem(font: TTFont, name: str, base: _Box) -> tuple[float, float]:
    """Srodek i szerokosc pionowego trzonu litery ``l``/``L``.

    ``L`` ma u dolu pozioma stopke, wiec srodek jego ramki lezy daleko na prawo
    od trzonu -- kreske trzeba postawic wzgledem samego trzonu, nie ramki.
    Trzon mierzymy wysoko (55% wysokosci), gdzie stopki juz nie ma.
    """
    polys = _outline(font, name)
    spans = _spans_at(polys, base.y_max * 0.55) if polys else []
    if not spans:
        return base.cx, base.width
    left, right = spans[0]  # trzon to zawsze skrajnie lewy odcinek
    return (left + right) / 2, right - left


def _make_stroke(base: _Box, upem: int, stem_cx: float, stem_w: float) -> Glyph:
    """Ukosna kreska przez trzon ``l``/``L`` jako rownoleglobok.

    Wymiary sa zdjete z krojow, ktore ``ł`` maja narysowane: kreska jest gruba
    mniej wiecej jak trzon (0,82), szeroka na 2,5 trzonu RAZEM ze skosem
    i siedzi na 44% wysokosci litery. Wczesniej szerokosc liczylismy bez skosu
    i przy dwukrotnie wiekszym mnozniku, przez co w szeryfowym ``MT`` kreska
    wychodzila poza szeryfy i litera czytala sie jak krzyzyk.
    """
    cy = base.y_max * 0.44
    thick = min(max(stem_w * 0.82, upem * 0.045), upem * 0.105)
    slant = thick * 0.75
    width = min(max(stem_w * 2.5, upem * 0.19), upem * 0.30)
    half_w = max((width - slant) / 2, thick * 0.9)
    cx = stem_cx - slant / 2
    # kolejnosc ZGODNA z ruchem wskazowek zegara -- tak jak font rysuje kontury
    # zewnetrzne. Przeciwny kierunek przy wypelnianiu nonzero ZNOSI sie z kon-
    # turem trzonu i czesc wspolna kreski z litera robila sie biala (kreska
    # wygladala jak kraciasta kokardka, a nie jak jednolity ukos).
    pts = [
        (cx - half_w, cy - thick / 2),          # lewy dolny
        (cx - half_w + slant, cy + thick / 2),  # lewy gorny
        (cx + half_w + slant, cy + thick / 2),  # prawy gorny
        (cx + half_w, cy - thick / 2),          # prawy dolny
    ]
    g = Glyph()
    g.numberOfContours = 1
    g.coordinates = GlyphCoordinates([(int(round(x)), int(round(y))) for x, y in pts])
    g.flags = bytearray([1, 1, 1, 1])  # wszystkie punkty na konturze
    g.endPtsOfContours = [3]
    g.program = _empty_program()
    return g


def _empty_program():
    from fontTools.ttLib.tables import ttProgram

    p = ttProgram.Program()
    p.fromBytecode(b"")
    return p


def _cmap_add(font: TTFont, codepoint: int, glyph_name: str) -> None:
    for table in font["cmap"].tables:
        # format 0 adresuje tylko 0..255 -- polskie znaki tam nie wchodza
        if table.format == 0:
            continue
        table.cmap[codepoint] = glyph_name


def add_polish_glyphs(font: TTFont, chars: str = PL_CHARS,
                      overwrite: bool = False) -> list[str]:
    """Dokłada brakujace polskie znaki. Zwraca liste dodanych znakow.

    Znak jest pomijany tylko wtedy, gdy pod jego kodem siedzi juz WLASCIWY
    glif (chyba ze ``overwrite``). Sam kod obecny w ``cmap`` nie wystarcza --
    patrz ``missing_polish``.
    """
    if "glyf" not in font:
        raise ValueError("font nie ma tabeli glyf (to nie jest TrueType)")

    glyf = font["glyf"]
    hmtx = font["hmtx"]
    upem = font["head"].unitsPerEm
    existing = _best_cmap(font)

    # fonty japonskie maja metryki pionowe -- musimy je rozpakowac, ZANIM
    # podniesiemy maxp.numGlyphs, bo inaczej dekompilacja uzna tabele za obcieta
    vmtx = font["vmtx"] if "vmtx" in font else None

    # dawcy akcentow pod nazwa, ktorej uzywa TEN font (patrz ``_glyph_for``)
    acute_name = _glyph_for(font, glyf, "acutecomb")
    period_name = _glyph_for(font, glyf, "period")

    # przesuniecia akcentow odczytane z gotowych glifow tego fontu
    dy_acute_low = _offset(glyf, _glyph_for(font, glyf, "aacute"), acute_name, "top") or 0
    dy_acute_up = _offset(glyf, _glyph_for(font, glyf, "Aacute"), acute_name, "top") or 0
    acute_box = _bbox(glyf, acute_name)
    dot_box = _bbox(glyf, period_name)

    ref_stem = _ref_stem(font, upem)

    added: list[str] = []
    new_glyphs: dict[str, tuple[Glyph, int]] = {}
    base_of: dict[str, str] = {}  # nowy glif -> litera, z ktorej bierze metryki
    hook_shift: dict[str, float] = {}  # dorysowany ogonek -> cofniecie w lewo

    for char in chars:
        if char not in POLISH:
            continue
        base_letter, kind, glyph_name = POLISH[char]
        # Pomijamy tylko wtedy, gdy pod tym kodem siedzi WLASCIWY glif. Samo
        # "kod jest w cmap" nie wystarcza: font czasem mapuje polska litere na
        # wizualnie podobny zastepnik (SCE-PS3-SR-R-JPN mial U+0104 -> Aring),
        # a wtedy trzeba zbudowac prawdziwy glif mimo obecnosci kodu. Ten
        # warunek czyni funkcje idempotentna takze na juz zalatanym foncie.
        if not overwrite and existing.get(ord(char)) == glyph_name:
            continue
        base_name = _glyph_for(font, glyf, base_letter)
        base = _bbox(glyf, base_name)
        if base is None:
            continue
        advance = hmtx[base_name][0]
        # wielkosc litery bierzemy ze ZNAKU, nie z nazwy glifu: dla ``uni0041``
        # ``isupper()`` jest falszem i wersalik dostawal kreske z minuskuly
        upper = char.isupper()

        if kind == ACUTE and acute_box is not None:
            dy = dy_acute_up if upper else dy_acute_low
            dx = base.cx - acute_box.cx
            glyph = _make_composite([(base_name, 0, 0), (acute_name, dx, dy)])
        elif kind == DOT and dot_box is not None and acute_box is not None:
            # kropke stawiamy na wysokosci, na ktorej font trzyma kreske
            dy = (acute_box.y_min + (dy_acute_up if upper else dy_acute_low)) - dot_box.y_min
            dx = base.cx - dot_box.cx
            glyph = _make_composite([(base_name, 0, 0), (period_name, dx, dy)])
        elif kind == OGONEK:
            attach = _ogonek_attach(font, base_name, base, ref_stem)
            # Dawcy U+0328/U+02DB miewają nietypową linię bazową i po
            # przesunięciu zostawiają odłączony haczyk. Geometria syntetyczna
            # mierzy spód konkretnej litery i bezpiecznie się z nim spawa.
            hook_name = f"{glyph_name}.hook"
            if hook_name not in new_glyphs:
                hook = _make_ogonek(_outline(font, base_name), base, upem,
                                    ref_stem, attach)
                new_glyphs[hook_name] = (hook, 0)
                hook.recalcBounds(glyf)
                hook_shift[hook_name] = _fit_advance(
                    hook.xMax, advance, upem, ref_stem)
            glyph = _make_composite([
                (base_name, 0, 0),
                (hook_name, hook_shift.get(hook_name, 0.0), 0),
            ])
        elif kind == STROKE:
            stroke_name = f"{glyph_name}.stroke"
            if stroke_name not in new_glyphs and stroke_name not in glyf:
                stem_cx, stem_w = _stem(font, base_name, base)
                new_glyphs[stroke_name] = (_make_stroke(base, upem, stem_cx, stem_w), 0)
            glyph = _make_composite([(base_name, 0, 0), (stroke_name, 0, 0)])
        else:
            continue

        new_glyphs[glyph_name] = (glyph, advance)
        base_of[glyph_name] = base_name
        added.append(char)

    if not new_glyphs:
        return []

    order = font.getGlyphOrder()
    for name, (glyph, _advance) in new_glyphs.items():
        if name not in order:
            order.append(name)
        glyf[name] = glyph
    font.setGlyphOrder(order)
    font["maxp"].numGlyphs = len(order)

    # bboxy licz dopiero, gdy wszystkie nowe glify sa juz w tabeli -- glif
    # zlozony potrzebuje wymiarow swoich komponentow
    for name in new_glyphs:
        glyf[name].recalcBounds(glyf)
    for name, (glyph, advance) in new_glyphs.items():
        hmtx[name] = (advance, glyf[name].xMin)
        if vmtx is not None:
            # kazdy glif musi miec wpis w vmtx, inaczej tabela jest za krotka
            # i font nie da sie wczytac; kreska do l/L nie ma litery bazowej
            vmtx[name] = vmtx.metrics.get(base_of.get(name, ""), (upem, 0))

    for char in added:
        _cmap_add(font, ord(char), POLISH[char][2])
    return added


def missing_polish(font: TTFont) -> str:
    """Polskie znaki, ktorych font nie renderuje wlasciwym glifem.

    Sprawdzamy NAZWE glifu pod danym kodem, nie samo istnienie kodu w ``cmap``.
    Font potrafi mapowac polska litere na wizualnie podobny zastepnik
    (``U+0104`` -> ``Aring``); dla gracza to krzak, wiec liczymy taki znak jako
    brakujacy.
    """
    cmap = _best_cmap(font)
    return "".join(c for c in PL_CHARS if cmap.get(ord(c)) != POLISH[c][2])
