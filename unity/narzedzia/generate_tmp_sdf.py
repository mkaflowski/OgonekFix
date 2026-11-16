#!/usr/bin/env python3
"""
Generator czcionek TMP SDF dla Unity (TextMeshPro FontAsset).

Przyjmuje plik czcionki (TTF/OTF) oraz dump MonoBehaviour istniejacego
TMP_FontAsset z gry (format tekstowy UABEA jak file2.txt albo JSON jak
file2.json) i generuje:
  - atlas SDF (PNG, do zaimportowania w UABEA do Texture2D atlasu),
  - nowy dump MonoBehaviour z podmienionymi tabelami glifow/znakow,
    metrykami FaceInfo i rozmiarem atlasu (reszta pol - PPtr, hashe,
    materialy - zostaje nietknieta, wiec dump importuje sie 1:1).

SDF renderowany jest natywnym modulem "sdf" FreeType (>= 2.11) ze
spreadem rownym paddingowi - czyli dokladnie ta sama konwencja, ktorej
uzywa Unity FontEngine przy trybie SDFAA (0.5 na krawedzi, rampa
+/- padding pikseli).

Przyklad:
  python generate_tmp_sdf.py Roboto.ttf file2.txt -r 0020-017F -o roboto_pl
"""

import argparse
import copy
import ctypes
import json
import re
import sys
from pathlib import Path

import freetype
import numpy as np
from freetype import raw as ft_raw
from PIL import Image

# ---------------------------------------------------------------------------
# FreeType helpers
# ---------------------------------------------------------------------------

FT_SFNT_OS2 = 2


class TT_OS2(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_ushort),
        ("xAvgCharWidth", ctypes.c_short),
        ("usWeightClass", ctypes.c_ushort),
        ("usWidthClass", ctypes.c_ushort),
        ("fsType", ctypes.c_ushort),
        ("ySubscriptXSize", ctypes.c_short),
        ("ySubscriptYSize", ctypes.c_short),
        ("ySubscriptXOffset", ctypes.c_short),
        ("ySubscriptYOffset", ctypes.c_short),
        ("ySuperscriptXSize", ctypes.c_short),
        ("ySuperscriptYSize", ctypes.c_short),
        ("ySuperscriptXOffset", ctypes.c_short),
        ("ySuperscriptYOffset", ctypes.c_short),
        ("yStrikeoutSize", ctypes.c_short),
        ("yStrikeoutPosition", ctypes.c_short),
        ("sFamilyClass", ctypes.c_short),
        ("panose", ctypes.c_ubyte * 10),
        ("ulUnicodeRange1", ctypes.c_ulong),
        ("ulUnicodeRange2", ctypes.c_ulong),
        ("ulUnicodeRange3", ctypes.c_ulong),
        ("ulUnicodeRange4", ctypes.c_ulong),
        ("achVendID", ctypes.c_char * 4),
        ("fsSelection", ctypes.c_ushort),
        ("usFirstCharIndex", ctypes.c_ushort),
        ("usLastCharIndex", ctypes.c_ushort),
        ("sTypoAscender", ctypes.c_short),
        ("sTypoDescender", ctypes.c_short),
        ("sTypoLineGap", ctypes.c_short),
        ("usWinAscent", ctypes.c_ushort),
        ("usWinDescent", ctypes.c_ushort),
        ("ulCodePageRange1", ctypes.c_ulong),
        ("ulCodePageRange2", ctypes.c_ulong),
        ("sxHeight", ctypes.c_short),
        ("sCapHeight", ctypes.c_short),
        ("usDefaultChar", ctypes.c_ushort),
        ("usBreakChar", ctypes.c_ushort),
        ("usMaxContext", ctypes.c_ushort),
    ]


def get_os2_table(face):
    fn = ft_raw.FT_Get_Sfnt_Table
    fn.restype = ctypes.c_void_p  # bez tego wskaznik jest obcinany do 32 bit
    fn.argtypes = [ctypes.c_void_p, ctypes.c_int]
    ptr = fn(ctypes.cast(face._FT_Face, ctypes.c_void_p), FT_SFNT_OS2)
    if not ptr:
        return None
    return ctypes.cast(ptr, ctypes.POINTER(TT_OS2)).contents


def set_sdf_spread(spread):
    lib = freetype.get_handle()
    value = ctypes.c_int(spread)
    err = ft_raw.FT_Property_Set(lib, b"sdf", b"spread", ctypes.byref(value))
    if err:
        raise RuntimeError(f"FT_Property_Set(sdf/spread={spread}) blad {err} "
                           f"(FreeType wymaga spread w zakresie 2..32)")


# ---------------------------------------------------------------------------
# Tryb renderowania atlasu (m_AtlasRenderMode)
#
# To NIE enum, a maska bitowa GlyphRasterModes Unity - dlatego rozpoznajemy ja
# bitami, a nie porownaniem do listy wartosci. Przyklady z Chained Echoes:
#   4169 = 0x1049 -> 1X|SDF8|HINTED|8BIT      (LiberationSans SDF, NotoSansSC)
#   4122 = 0x101A -> 1X|BITMAP|MONO|HINTED    (CE, CE_tmp, JF-Dot-MPlus12)
#   4117 = 0x1015 -> 1X|BITMAP|NO_HINTING|8BIT (neodgm_tmp)
#
# Fonty BITMAPOWE trzymaja w atlasie zwykla rasteryzacje, nie pole odleglosci.
# Renderowanie dla nich SDF daje rozmyta szara plame, ktora dodatkowo nie
# osiaga pelnej bieli - przy malym pointSize rampa spreadu jest szersza niz
# same kreski litery. Dlatego collect_glyphs() musi znac tryb celu.
# ---------------------------------------------------------------------------

RASTER_MODE_8BIT = 0x01
RASTER_MODE_MONO = 0x02
RASTER_MODE_NO_HINTING = 0x04
RASTER_MODE_HINTED = 0x08
RASTER_MODE_BITMAP = 0x10
RASTER_MODE_SDF = 0x20
RASTER_MODE_SDF8 = 0x40
RASTER_MODE_SDF16 = 0x80
RASTER_MODE_SDF32 = 0x100

SDF_MODES = (RASTER_MODE_SDF | RASTER_MODE_SDF8
             | RASTER_MODE_SDF16 | RASTER_MODE_SDF32)

_MODE_FLAG_NAMES = (
    (RASTER_MODE_SDF32, "SDF32"), (RASTER_MODE_SDF16, "SDF16"),
    (RASTER_MODE_SDF8, "SDF8"), (RASTER_MODE_SDF, "SDF"),
    (RASTER_MODE_BITMAP, "BITMAP"), (RASTER_MODE_HINTED, "HINTED"),
    (RASTER_MODE_NO_HINTING, "NO_HINTING"), (RASTER_MODE_MONO, "MONO"),
    (RASTER_MODE_8BIT, "8BIT"),
)


def is_sdf_render_mode(render_mode):
    """Czy m_AtlasRenderMode oznacza pole odleglosci (SDF), a nie bitmape.

    None = brak informacji; zakladamy SDF, bo tak dziala kazdy font "* SDF"
    i taka byla dotychczasowa (jedyna) sciezka generatora.
    """
    if render_mode is None:
        return True
    return bool(int(render_mode) & SDF_MODES)


def is_mono_render_mode(render_mode):
    """Czy atlas jest 1-bitowy (RASTER / RASTER_HINTED) - bez antyaliasingu."""
    if render_mode is None:
        return False
    return bool(int(render_mode) & RASTER_MODE_MONO)


def render_mode_desc(render_mode):
    """Opis trybu do logu, np. '4122 = BITMAP|MONO|HINTED'."""
    if render_mode is None:
        return "brak (zakladam SDF)"
    mode = int(render_mode)
    flags = [name for bit, name in _MODE_FLAG_NAMES if mode & bit]
    return f"{mode} = {'|'.join(flags) if flags else '?'}"


def set_sdf_overlaps(enabled):
    """Przelacznik algorytmu SDF dla nachodzacych konturow (FreeType >= 2.11).

    Zaden z dwoch trybow nie jest bezpieczny globalnie:
      overlaps=0 - psuje litery z OGONKIEM (ą ę Ą Ę): tam, gdzie ogonek nachodzi
                   na litere, wnetrze wychodzi odwrocone,
      overlaps=1 - naprawia ogonki, ale w czesci krojow (np. Calibri) CALKOWICIE
                   odwraca glify z osobnym akcentem (ć ń ż).
    Dlatego wybieramy tryb per glif - patrz sdf_mismatch()/collect_glyphs().
    """
    lib = freetype.get_handle()
    value = ctypes.c_bool(bool(enabled))
    return ft_raw.FT_Property_Set(lib, b"sdf", b"overlaps", ctypes.byref(value)) == 0


def sdf_mismatch(sdf, left_s, top_s, cov, left_n, top_n):
    """Ulamek pikseli, ktore zwykla rasteryzacja uznaje za WNETRZE glifu,
    a SDF za zewnetrze. Zwykly raster jest tu zrodlem prawdy, wiec 0.0 =
    polaryzacja SDF sie zgadza."""
    inside = cov > 200
    if not inside.any():
        return 0.0
    x0, y0 = left_n - left_s, top_s - top_n
    sub = sdf[y0:y0 + cov.shape[0], x0:x0 + cov.shape[1]]
    if sub.shape != cov.shape:
        return 0.0
    return float((sub[inside] < 128).mean())


def set_var_coords(face, var_spec):
    """var_spec np. 'wght=500,wdth=100' - ustawia osie czcionki zmiennej."""
    wanted = {}
    for part in var_spec.split(","):
        tag, _, val = part.partition("=")
        if not val:
            raise ValueError(f"Zly format --var: '{part}' (oczekiwano tag=wartosc)")
        wanted[tag.strip()] = float(val)
    info = face.get_variation_info()
    coords = []
    for axis in info.axes:
        tag = axis.tag.decode() if isinstance(axis.tag, bytes) else axis.tag
        coords.append(wanted.pop(tag, axis.default))
    if wanted:
        raise ValueError(f"Czcionka nie ma osi: {', '.join(wanted)}")
    n = len(coords)
    arr = (ctypes.c_long * n)(*[int(round(c * 65536)) for c in coords])
    err = ft_raw.FT_Set_Var_Design_Coordinates(face._FT_Face, n, arr)
    if err:
        raise RuntimeError(f"FT_Set_Var_Design_Coordinates blad {err}")


def bitmap_to_array(bitmap):
    """Slot bitmap (8bpp gray) -> numpy uint8 [rows, width]."""
    w, h, pitch = bitmap.width, bitmap.rows, bitmap.pitch
    if w == 0 or h == 0:
        return np.zeros((0, 0), dtype=np.uint8)
    buf = np.array(bitmap.buffer, dtype=np.uint8).reshape(h, abs(pitch))
    if pitch < 0:
        buf = buf[::-1]
    return buf[:, :w].copy()


# ---------------------------------------------------------------------------
# Pakowanie atlasu (skyline bottom-left)
# ---------------------------------------------------------------------------

class SkylinePacker:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.nodes = [(0, 0, width)]  # (x, y, szerokosc)

    def _fit(self, index, w, h):
        x = self.nodes[index][0]
        if x + w > self.width:
            return None
        remaining = w
        y = 0
        i = index
        while remaining > 0:
            if i >= len(self.nodes):
                return None
            y = max(y, self.nodes[i][1])
            if y + h > self.height:
                return None
            remaining -= self.nodes[i][2]
            i += 1
        return y

    def insert(self, w, h):
        best = None  # ((top, x), index, y)
        for i in range(len(self.nodes)):
            y = self._fit(i, w, h)
            if y is not None:
                key = (y + h, self.nodes[i][0])
                if best is None or key < best[0]:
                    best = (key, i, y)
        if best is None:
            return None
        _, index, y = best
        x = self.nodes[index][0]
        # nowy wezel nad wstawionym prostokatem
        new_node = (x, y + h, w)
        self.nodes.insert(index, new_node)
        # przytnij / usun wezly przykryte przez nowy
        i = index + 1
        while i < len(self.nodes):
            nx, ny, nw = self.nodes[i]
            if nx < x + w:
                shrink = x + w - nx
                if nw <= shrink:
                    del self.nodes[i]
                    continue
                self.nodes[i] = (nx + shrink, ny, nw - shrink)
            break
        # scal sasiadow o tej samej wysokosci
        i = 0
        while i < len(self.nodes) - 1:
            x1, y1, w1 = self.nodes[i]
            x2, y2, w2 = self.nodes[i + 1]
            if y1 == y2:
                self.nodes[i] = (x1, y1, w1 + w2)
                del self.nodes[i + 1]
            else:
                i += 1
        return (x, y)


# ---------------------------------------------------------------------------
# Renderowanie glifow
# ---------------------------------------------------------------------------

SDF_MISMATCH_TOL = 0.005  # ponizej tego progu roznice to zwykly antyaliasing


def render_sdf(face, gi, load_flags, overlaps=False):
    """Renderuje glif jako SDF w zadanym trybie overlaps.

    Zwraca (bitmapa, bitmap_left, bitmap_top). Glif trzeba zaladowac na nowo,
    bo render konsumuje slot.
    """
    set_sdf_overlaps(overlaps)
    face.load_glyph(gi, load_flags)
    slot = face.glyph
    slot.render(freetype.FT_RENDER_MODE_SDF)
    return bitmap_to_array(slot.bitmap), slot.bitmap_left, slot.bitmap_top


def render_bitmap(face, gi, load_flags, mono):
    """Rasteryzacja glifu jak w trybach SMOOTH/RASTER - bez pola odleglosci.

    Tryb MONO robimy przez zwykly antyaliasing + prog 128, zeby nie rozpakowywac
    upakowanych bitow FT_PIXEL_MODE_MONO; wynik jest tak samo twardy (0/255),
    czyli dokladnie taki, jak glify lezace juz w bitmapowym atlasie gry.
    """
    face.load_glyph(gi, load_flags)
    slot = face.glyph
    slot.render(freetype.FT_RENDER_MODE_NORMAL)
    cov = bitmap_to_array(slot.bitmap)
    if mono and cov.size:
        cov = np.where(cov >= 128, 255, 0).astype(np.uint8)
    return cov


def collect_glyphs(face, codepoints, point_size, padding, render_mode=None):
    """Zwraca (chars, glyphs, missing).

    chars:  lista (unicode, glyph_index)
    glyphs: dict glyph_index -> dane glifu (metryki, bitmapa, offsety)

    render_mode: m_AtlasRenderMode fontu DOCELOWEGO. Dla trybow bitmapowych
    (SMOOTH/RASTER) glify sa rasteryzowane zwyczajnie, a padding zostaje samym
    przezroczystym marginesem - inaczej dorobione litery bylyby rozmytym polem
    odleglosci wsrod twardych glifow z gry.
    """
    sdf_mode = is_sdf_render_mode(render_mode)
    mono = is_mono_render_mode(render_mode)
    if sdf_mode:
        set_sdf_spread(padding)
    face.set_char_size(point_size * 64)
    load_flags = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP

    chars = []
    glyphs = {}
    missing = []
    for cp in codepoints:
        gi = face.get_char_index(cp)
        if gi == 0:
            missing.append(cp)
            continue
        chars.append((cp, gi))
        if gi in glyphs:
            continue

        face.load_glyph(gi, load_flags)
        slot = face.glyph
        m = slot.metrics
        metrics = {
            "width": m.width / 64.0,
            "height": m.height / 64.0,
            "bearing_x": m.horiBearingX / 64.0,
            "bearing_y": m.horiBearingY / 64.0,
            "advance": m.horiAdvance / 64.0,
        }

        if slot.outline.n_contours == 0:
            glyphs[gi] = {"metrics": metrics, "empty": True,
                          "cell_w": 1, "cell_h": 1,
                          "sdf": np.zeros((1, 1), dtype=np.uint8),
                          "inner": (0, 0, 1, 1)}
            continue

        # --- font bitmapowy: zwykla rasteryzacja + pusty margines paddingu ---
        if not sdf_mode:
            cov = render_bitmap(face, gi, load_flags, mono)
            hn, wn = cov.shape
            if wn == 0 or hn == 0:
                glyphs[gi] = {"metrics": metrics, "empty": True,
                              "cell_w": 1, "cell_h": 1,
                              "sdf": np.zeros((1, 1), dtype=np.uint8),
                              "inner": (0, 0, 1, 1)}
                continue
            cell_w, cell_h = wn + 2 * padding, hn + 2 * padding
            cell = np.zeros((cell_h, cell_w), dtype=np.uint8)
            cell[padding:padding + hn, padding:padding + wn] = cov
            glyphs[gi] = {"metrics": metrics, "empty": False,
                          "cell_w": cell_w, "cell_h": cell_h,
                          "sdf": cell, "inner": (padding, padding, wn, hn)}
            continue

        # render zwykly -> wymiary wewnetrznego prostokata glifu (jak w TMP)
        # oraz wzorzec "co jest wnetrzem" do kontroli polaryzacji SDF
        slot.render(freetype.FT_RENDER_MODE_NORMAL)
        wn, hn = slot.bitmap.width, slot.bitmap.rows
        left_n, top_n = slot.bitmap_left, slot.bitmap_top
        cov = bitmap_to_array(slot.bitmap)

        # render SDF (bitmapa powiekszona o spread z kazdej strony); gdy
        # polaryzacja sie nie zgadza (odwrocony ogonek / akcent), probujemy
        # drugiego trybu overlaps i zostawiamy ten wariant, ktory blizszy
        # jest zwyklej rasteryzacji
        sdf, left_s, top_s = render_sdf(face, gi, load_flags)
        bad = sdf_mismatch(sdf, left_s, top_s, cov, left_n, top_n)
        if bad > SDF_MISMATCH_TOL:
            alt_sdf, alt_l, alt_t = render_sdf(face, gi, load_flags, overlaps=True)
            if sdf_mismatch(alt_sdf, alt_l, alt_t, cov, left_n, top_n) < bad:
                sdf, left_s, top_s = alt_sdf, alt_l, alt_t
            set_sdf_overlaps(False)
        hs, ws = sdf.shape

        # polozenie wewnetrznego prostokata w bitmapie SDF
        x0 = left_n - left_s
        y0_top = top_s - top_n
        y0_bottom = hs - y0_top - hn

        glyphs[gi] = {"metrics": metrics, "empty": False,
                      "cell_w": ws, "cell_h": hs,
                      "sdf": sdf, "inner": (x0, y0_bottom, wn, hn)}
    return chars, glyphs, missing


def pack_atlas(glyphs, width, height, allow_grow, max_size=8192):
    """Pakuje glify; zwraca (width, height, placements, free_rects).

    placements: glyph_index -> (cell_x, cell_y)  (uklad od dolu-lewej)
    """
    order = sorted(glyphs.keys(),
                   key=lambda gi: (-glyphs[gi]["cell_h"], -glyphs[gi]["cell_w"]))
    w, h = width, height
    while True:
        packer = SkylinePacker(w, h)
        placements = {}
        ok = True
        for gi in order:
            g = glyphs[gi]
            pos = packer.insert(g["cell_w"], g["cell_h"])
            if pos is None:
                ok = False
                break
            placements[gi] = pos
        if ok:
            top = max((placements[gi][1] + glyphs[gi]["cell_h"]
                       for gi in placements), default=0)
            free = []
            if top < h:
                free.append((0, top, w, h - top))
            return w, h, placements, free
        if not allow_grow:
            raise SystemExit(
                f"BLAD: glify nie mieszcza sie w atlasie {w}x{h}. "
                f"Zmniejsz --point-size albo pozwol na powiekszenie (bez --no-grow).")
        # Przy prostokatnym atlasie jedna os moze juz byc na limicie.
        # Wtedy nadal mozemy powiekszyc druga, zamiast przedwczesnie odmawiac.
        if w <= h and w < max_size:
            w = min(w * 2, max_size)
        elif h < max_size:
            h = min(h * 2, max_size)
        elif w < max_size:
            w = min(w * 2, max_size)
        else:
            raise SystemExit(
                f"BLAD: glify nie mieszcza sie w atlasie {w}x{h};"
                f" maksymalny wymiar to {max_size}.")
        print(f"  ! atlas za maly, powiekszam do {w}x{h}")


def compose_atlas(glyphs, placements, width, height):
    atlas = np.zeros((height, width), dtype=np.uint8)  # [y od dolu, x]
    for gi, (cx, cy) in placements.items():
        g = glyphs[gi]
        cw, ch = g["cell_w"], g["cell_h"]
        atlas[cy:cy + ch, cx:cx + cw] = np.flipud(g["sdf"])
    return atlas


# ---------------------------------------------------------------------------
# FaceInfo
# ---------------------------------------------------------------------------

def build_face_info(face, point_size):
    upem = face.units_per_EM
    s = point_size / upem
    os2 = get_os2_table(face)

    def measured_top(char):
        try:
            face.load_char(char, freetype.FT_LOAD_NO_HINTING)
            return face.glyph.metrics.horiBearingY / 64.0
        except Exception:
            return None

    cap = mean = None
    if os2 is not None and os2.version >= 2:
        if os2.sCapHeight > 0:
            cap = os2.sCapHeight * s
        if os2.sxHeight > 0:
            mean = os2.sxHeight * s
    if cap is None:
        cap = measured_top("H") or face.ascender * s * 0.7
    if mean is None:
        mean = measured_top("x") or cap * 0.7

    strike_off = mean * 0.5
    strike_size = face.underline_thickness * s if face.underline_thickness else point_size * 0.05
    if os2 is not None:
        if os2.yStrikeoutPosition:
            strike_off = os2.yStrikeoutPosition * s
        if os2.yStrikeoutSize:
            strike_size = os2.yStrikeoutSize * s

    family = face.family_name.decode("utf-8", "replace") if face.family_name else ""
    style = face.style_name.decode("utf-8", "replace") if face.style_name else ""

    return {
        "m_FamilyName": family,
        "m_StyleName": style,
        "m_PointSize": point_size,
        "m_UnitsPerEM": upem,
        "m_LineHeight": face.height * s,
        "m_AscentLine": face.ascender * s,
        "m_CapLine": cap,
        "m_MeanLine": mean,
        "m_DescentLine": face.descender * s,
        "m_SuperscriptOffset": face.ascender * s,
        "m_SubscriptOffset": face.descender * s,
        "m_UnderlineOffset": face.underline_position * s,
        "m_UnderlineThickness": face.underline_thickness * s,
        "m_StrikethroughOffset": strike_off,
        "m_StrikethroughThickness": strike_size,
    }


# ---------------------------------------------------------------------------
# Zapis dumpa tekstowego (format UABEA)
# ---------------------------------------------------------------------------

def detect_decimal_sep(text):
    return "," if re.search(r"\bfloat [\w]+ = -?\d+,\d+", text) else "."


def make_fmt(sep):
    def fmt(v):
        if isinstance(v, (int, np.integer)) or float(v) == int(v):
            return str(int(v))
        s = repr(float(v))
        if "e" in s or "E" in s:
            s = f"{float(v):.8f}".rstrip("0")
        return s.replace(".", sep)
    return fmt


def replace_block(text, start_marker, end_marker, new_block):
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start == -1 or end == -1:
        raise SystemExit(f"BLAD: nie znaleziono sekcji '{start_marker.strip()}' w szablonie.")
    return text[:start] + new_block + text[end:]


def replace_scalar(text, pattern, value, required=True):
    new_text, n = re.subn(pattern, lambda mm: mm.group(1) + str(value), text, count=1)
    if n == 0 and required:
        raise SystemExit(f"BLAD: nie znaleziono pola wg wzorca: {pattern}")
    return new_text


def glyph_table_block(glyph_rows, fmt):
    lines = [" 0 Glyph m_GlyphTable",
             f"  1 Array Array ({len(glyph_rows)} items)",
             f"   0 int size = {len(glyph_rows)}"]
    for i, g in enumerate(glyph_rows):
        lines += [
            f"   [{i}]",
            "    0 Glyph data",
            f"     0 unsigned int m_Index = {g['index']}",
            "     0 GlyphMetrics m_Metrics",
            f"      0 float m_Width = {fmt(g['w'])}",
            f"      0 float m_Height = {fmt(g['h'])}",
            f"      0 float m_HorizontalBearingX = {fmt(g['bx'])}",
            f"      0 float m_HorizontalBearingY = {fmt(g['by'])}",
            f"      0 float m_HorizontalAdvance = {fmt(g['adv'])}",
            "     0 GlyphRect m_GlyphRect",
            f"      0 int m_X = {g['rx']}",
            f"      0 int m_Y = {g['ry']}",
            f"      0 int m_Width = {g['rw']}",
            f"      0 int m_Height = {g['rh']}",
            "     0 float m_Scale = 1",
            "     0 int m_AtlasIndex = 0",
            "     0 int m_ClassDefinitionType = 0",
        ]
    return "\n".join(lines) + "\n"


def character_table_block(chars):
    lines = [" 0 TMP_Character m_CharacterTable",
             f"  1 Array Array ({len(chars)} items)",
             f"   0 int size = {len(chars)}"]
    for i, (cp, gi) in enumerate(chars):
        lines += [
            f"   [{i}]",
            "    0 TMP_Character data",
            "     1 UInt8 m_ElementType = 1",
            f"     0 unsigned int m_Unicode = {cp}",
            f"     0 unsigned int m_GlyphIndex = {gi}",
            "     0 float m_Scale = 1",
        ]
    return "\n".join(lines) + "\n"


def rects_block(name, rects):
    lines = [f" 0 GlyphRect {name}",
             f"  1 Array Array ({len(rects)} items)",
             f"   0 int size = {len(rects)}"]
    for i, (x, y, w, h) in enumerate(rects):
        lines += [
            f"   [{i}]",
            "    0 GlyphRect data",
            f"     0 int m_X = {x}",
            f"     0 int m_Y = {y}",
            f"     0 int m_Width = {w}",
            f"     0 int m_Height = {h}",
        ]
    return "\n".join(lines) + "\n"


def face_info_field(text, name, value, fmt, is_string=False):
    if is_string:
        pattern = rf'(  1 string {name} = )"[^"]*"'
        repl = f'"{value}"'
    else:
        pattern = rf"(  0 (?:float|int) {name} = )[-\d,\.eE]+"
        repl = fmt(value) if not isinstance(value, int) else str(value)
    new_text, n = re.subn(pattern, lambda mm: mm.group(1) + repl, text, count=1)
    if n == 0:
        print(f"  ! pole FaceInfo '{name}' nie znalezione w szablonie - pomijam")
        return text
    return new_text


def write_txt_dump(template_text, out_path, face_info, glyph_rows, chars,
                   used_rects, free_rects, atlas_w, atlas_h, padding,
                   point_size, char_seq):
    sep = detect_decimal_sep(template_text)
    fmt = make_fmt(sep)
    text = template_text

    # --- FaceInfo: podmien pojedyncze pola wewnatrz bloku ---
    fi_start = text.find(" 0 FaceInfo m_FaceInfo")
    fi_end = text.find(" 0 Glyph m_GlyphTable")
    if fi_start == -1 or fi_end == -1:
        raise SystemExit("BLAD: nie znaleziono bloku FaceInfo w szablonie.")
    block = text[fi_start:fi_end]
    block = face_info_field(block, "m_FamilyName", face_info["m_FamilyName"], fmt, True)
    block = face_info_field(block, "m_StyleName", face_info["m_StyleName"], fmt, True)
    for key in ("m_PointSize", "m_UnitsPerEM"):
        block = face_info_field(block, key, int(face_info[key]), fmt)
    for key in ("m_LineHeight", "m_AscentLine", "m_CapLine", "m_MeanLine",
                "m_DescentLine", "m_SuperscriptOffset", "m_SubscriptOffset",
                "m_UnderlineOffset", "m_UnderlineThickness",
                "m_StrikethroughOffset", "m_StrikethroughThickness"):
        block = face_info_field(block, key, face_info[key], fmt)
    text = text[:fi_start] + block + text[fi_end:]

    # --- tabele ---
    text = replace_block(text, " 0 Glyph m_GlyphTable",
                         " 0 TMP_Character m_CharacterTable",
                         glyph_table_block(glyph_rows, fmt))
    text = replace_block(text, " 0 TMP_Character m_CharacterTable",
                         " 0 vector m_AtlasTextures",
                         character_table_block(chars))
    text = replace_block(text, " 0 GlyphRect m_UsedGlyphRects",
                         " 0 GlyphRect m_FreeGlyphRects",
                         rects_block("m_UsedGlyphRects", used_rects))
    text = replace_block(text, " 0 GlyphRect m_FreeGlyphRects",
                         " 0 FaceInfo_Legacy m_fontInfo",
                         rects_block("m_FreeGlyphRects", free_rects))

    # --- skalary ---
    text = replace_scalar(text, r"( 0 int m_AtlasWidth = )\d+", atlas_w)
    text = replace_scalar(text, r"( 0 int m_AtlasHeight = )\d+", atlas_h)
    text = replace_scalar(text, r"( 0 int m_AtlasPadding = )\d+", padding)
    text = replace_scalar(text, r"(  0 int pointSize = )\d+", point_size, required=False)
    text = replace_scalar(text, r"(  0 int padding = )\d+", padding, required=False)
    text = replace_scalar(text, r"(  0 int atlasWidth = )\d+", atlas_w, required=False)
    text = replace_scalar(text, r"(  0 int atlasHeight = )\d+", atlas_h, required=False)
    text = re.sub(r'(  1 string characterSequence = )"[^"]*"',
                  lambda mm: mm.group(1) + f'"{char_seq}"', text, count=1)

    Path(out_path).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Zapis dumpa JSON (format UABEA "Dump as JSON")
# ---------------------------------------------------------------------------

GLYPH_PROTO = {
    "m_Index": 0,
    "m_Metrics": {"m_Width": 0.0, "m_Height": 0.0, "m_HorizontalBearingX": 0.0,
                  "m_HorizontalBearingY": 0.0, "m_HorizontalAdvance": 0.0},
    "m_GlyphRect": {"m_X": 0, "m_Y": 0, "m_Width": 0, "m_Height": 0},
    "m_Scale": 1.0, "m_AtlasIndex": 0, "m_ClassDefinitionType": 0,
}
CHAR_PROTO = {"m_ElementType": 1, "m_Unicode": 0, "m_GlyphIndex": 0, "m_Scale": 1.0}
RECT_PROTO = {"m_X": 0, "m_Y": 0, "m_Width": 0, "m_Height": 0}


def proto_from_template(array_field, fallback):
    try:
        return copy.deepcopy(array_field["Array"][0])
    except (KeyError, IndexError, TypeError):
        return copy.deepcopy(fallback)


def write_json_dump(template, out_path, face_info, glyph_rows, chars,
                    used_rects, free_rects, atlas_w, atlas_h, padding,
                    point_size, char_seq):
    data = copy.deepcopy(template)

    fi = data.get("m_FaceInfo", {})
    for k, v in face_info.items():
        if k in fi:
            fi[k] = v if isinstance(v, (int, str)) else float(v)

    gproto = proto_from_template(data.get("m_GlyphTable", {}), GLYPH_PROTO)
    garr = []
    for g in glyph_rows:
        e = copy.deepcopy(gproto)
        e["m_Index"] = g["index"]
        e["m_Metrics"].update({"m_Width": float(g["w"]), "m_Height": float(g["h"]),
                               "m_HorizontalBearingX": float(g["bx"]),
                               "m_HorizontalBearingY": float(g["by"]),
                               "m_HorizontalAdvance": float(g["adv"])})
        e["m_GlyphRect"].update({"m_X": g["rx"], "m_Y": g["ry"],
                                 "m_Width": g["rw"], "m_Height": g["rh"]})
        e["m_Scale"] = 1.0
        e["m_AtlasIndex"] = 0
        garr.append(e)
    data["m_GlyphTable"] = {"Array": garr}

    cproto = proto_from_template(data.get("m_CharacterTable", {}), CHAR_PROTO)
    carr = []
    for cp, gi in chars:
        e = copy.deepcopy(cproto)
        e.update({"m_ElementType": 1, "m_Unicode": cp, "m_GlyphIndex": gi,
                  "m_Scale": 1.0})
        carr.append(e)
    data["m_CharacterTable"] = {"Array": carr}

    def rect_array(rects):
        out = []
        for x, y, w, h in rects:
            e = copy.deepcopy(RECT_PROTO)
            e.update({"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h})
            out.append(e)
        return {"Array": out}

    data["m_UsedGlyphRects"] = rect_array(used_rects)
    data["m_FreeGlyphRects"] = rect_array(free_rects)
    data["m_AtlasWidth"] = atlas_w
    data["m_AtlasHeight"] = atlas_h
    data["m_AtlasPadding"] = padding

    cs = data.get("m_CreationSettings")
    if isinstance(cs, dict):
        cs["pointSize"] = point_size
        cs["padding"] = padding
        cs["atlasWidth"] = atlas_w
        cs["atlasHeight"] = atlas_h
        cs["characterSequence"] = char_seq

    Path(out_path).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                              encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_ranges(spec):
    cps = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            cps.extend(range(int(a, 16), int(b, 16) + 1))
        else:
            cps.append(int(part, 16))
    return sorted(set(cps))


def ask_path(prompt, must_exist=True, default=None):
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{prompt}{suffix}: ").strip().strip('"').strip("'")
        if not value and default is not None:
            return default
        if not value:
            continue
        if must_exist and not Path(value).is_file():
            print("  ! plik nie istnieje, sprobuj jeszcze raz")
            continue
        return value


def interactive_args():
    print("=== Generator czcionek TMP SDF ===")
    font = ask_path("Plik czcionki (TTF/OTF)")
    template = ask_path("Dump MonoBehaviour z gry (.txt UABEA lub .json)")
    rng = ask_path("Zakres znakow hex", must_exist=False, default="0020-017F")
    default_out = str(Path(template).with_name(Path(template).stem + "_new"))
    output = ask_path("Prefiks plikow wyjsciowych", must_exist=False,
                      default=default_out)
    return [font, template, "-r", rng, "-o", output]


def main():
    ap = argparse.ArgumentParser(
        description="Generuje atlas SDF + dump MonoBehaviour TMP_FontAsset "
                    "na bazie szablonu z gry.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("font", help="plik czcionki TTF/OTF")
    ap.add_argument("template", help="dump MonoBehaviour z gry (.txt UABEA lub .json)")
    ap.add_argument("-r", "--range", default="0020-017F",
                    help="zakres(y) znakow hex, np. 0020-017F lub 0020-007F,0100-017F")
    ap.add_argument("-o", "--output", default=None,
                    help="prefiks plikow wyjsciowych (domyslnie <szablon>_new)")
    ap.add_argument("--point-size", type=int, default=None,
                    help="rozmiar probkowania w pt (domyslnie z szablonu)")
    ap.add_argument("--padding", type=int, default=None,
                    help="padding SDF w px (domyslnie z szablonu)")
    ap.add_argument("--atlas-width", type=int, default=None,
                    help="szerokosc atlasu (domyslnie z szablonu)")
    ap.add_argument("--atlas-height", type=int, default=None,
                    help="wysokosc atlasu (domyslnie z szablonu)")
    ap.add_argument("--no-grow", action="store_true",
                    help="nie powiekszaj atlasu automatycznie gdy sie nie miesci")
    ap.add_argument("--var", default=None,
                    help="osie czcionki zmiennej, np. wght=500,wdth=100")
    argv = sys.argv[1:] if len(sys.argv) > 1 else interactive_args()
    args = ap.parse_args(argv)

    template_path = Path(args.template)
    is_json = template_path.suffix.lower() == ".json"
    raw_text = template_path.read_text(encoding="utf-8")
    template_json = json.loads(raw_text) if is_json else None

    # domyslne parametry z szablonu
    if is_json:
        t_point = int(template_json.get("m_FaceInfo", {}).get("m_PointSize", 40))
        t_pad = int(template_json.get("m_AtlasPadding", 6))
        t_w = int(template_json.get("m_AtlasWidth", 1024))
        t_h = int(template_json.get("m_AtlasHeight", 512))
        t_mode = template_json.get("m_AtlasRenderMode")
    else:
        def grab(pattern, default):
            m = re.search(pattern, raw_text)
            return int(m.group(1)) if m else default
        t_point = grab(r" 0 int m_PointSize = (\d+)", 40)
        t_pad = grab(r" 0 int m_AtlasPadding = (\d+)", 6)
        t_w = grab(r" 0 int m_AtlasWidth = (\d+)", 1024)
        t_h = grab(r" 0 int m_AtlasHeight = (\d+)", 512)
        t_mode = grab(r" 0 int m_AtlasRenderMode = (\d+)", None)

    point_size = args.point_size or t_point
    padding = args.padding if args.padding is not None else t_pad
    atlas_w = args.atlas_width or t_w
    atlas_h = args.atlas_height or t_h
    sdf_mode = is_sdf_render_mode(t_mode)
    # spread SDF musi byc w zakresie 2..32; w bitmapie padding to zwykly margines
    if sdf_mode:
        padding = max(2, min(32, padding))

    out_prefix = Path(args.output) if args.output else \
        template_path.with_name(template_path.stem + "_new")

    codepoints = parse_ranges(args.range)
    print(f"Czcionka:  {args.font}")
    print(f"Szablon:   {template_path}  ({'JSON' if is_json else 'txt UABEA'})")
    print(f"Zakres:    {args.range}  ({len(codepoints)} znakow)")
    print(f"Parametry: pointSize={point_size} padding={padding} atlas={atlas_w}x{atlas_h}")
    print(f"Tryb:      {render_mode_desc(t_mode)}"
          f" -> render {'SDF' if sdf_mode else 'bitmapowy'}")

    face = freetype.Face(args.font)
    if args.var:
        set_var_coords(face, args.var)

    chars, glyphs, missing = collect_glyphs(face, codepoints, point_size, padding,
                                            render_mode=t_mode)
    if missing:
        shown = ", ".join(f"U+{cp:04X}" for cp in missing[:12])
        more = f" (+{len(missing) - 12} innych)" if len(missing) > 12 else ""
        print(f"  ! brak w czcionce {len(missing)} znakow: {shown}{more}")
    print(f"Glify: {len(glyphs)} unikalnych dla {len(chars)} znakow")

    atlas_w, atlas_h, placements, free_rects = pack_atlas(
        glyphs, atlas_w, atlas_h, allow_grow=not args.no_grow)

    atlas = compose_atlas(glyphs, placements, atlas_w, atlas_h)
    area = sum(glyphs[gi]["cell_w"] * glyphs[gi]["cell_h"] for gi in placements)
    print(f"Atlas: {atlas_w}x{atlas_h}, zajetosc {100.0 * area / (atlas_w * atlas_h):.1f}%")

    # wiersze tabeli glifow + used rects (posortowane po indeksie glifu)
    glyph_rows = []
    used_rects = []
    for gi in sorted(glyphs.keys()):
        g = glyphs[gi]
        cx, cy = placements[gi]
        ix, iy, iw, ih = g["inner"]
        m = g["metrics"]
        glyph_rows.append({
            "index": gi,
            "w": m["width"], "h": m["height"],
            "bx": m["bearing_x"], "by": m["bearing_y"], "adv": m["advance"],
            "rx": cx + ix, "ry": cy + iy, "rw": iw, "rh": ih,
        })
        used_rects.append((cx, cy, g["cell_w"], g["cell_h"]))

    face_info = build_face_info(face, point_size)

    # zapis atlasu: PNG RGBA (RGB = SDF dla podgladu, A = SDF dla Alpha8)
    png_path = out_prefix.with_suffix(".png")
    img = np.flipud(atlas)  # PNG ma poczatek u gory-lewej
    rgba = np.dstack([img, img, img, img])
    Image.fromarray(rgba, "RGBA").save(png_path)

    # zapis dumpa
    char_seq = args.range.upper()
    if is_json:
        dump_path = out_prefix.with_suffix(".json")
        write_json_dump(template_json, dump_path, face_info, glyph_rows, chars,
                        used_rects, free_rects, atlas_w, atlas_h, padding,
                        point_size, char_seq)
    else:
        dump_path = out_prefix.with_suffix(".txt")
        write_txt_dump(raw_text, dump_path, face_info, glyph_rows, chars,
                       used_rects, free_rects, atlas_w, atlas_h, padding,
                       point_size, char_seq)

    print(f"\nZapisano:")
    print(f"  dump:  {dump_path}")
    print(f"  atlas: {png_path}")
    print(f"\nImport w UABEA:")
    print(f"  1. MonoBehaviour fontu -> Import Dump ({dump_path.name})")
    print(f"  2. Texture2D atlasu -> Plugins/Edit texture -> wczytaj {png_path.name}")
    print(f"     (format tekstury najlepiej zostawic Alpha8)")
    if sdf_mode:
        print(f"  3. W materiale SDF pole _GradientScale musi byc = padding+1 = {padding + 1}")
    else:
        print(f"  3. Atlas bitmapowy - _GradientScale NIE dotyczy tego fontu")
    if atlas_w != t_w or atlas_h != t_h:
        print(f"  ! Rozmiar atlasu zmienil sie ({t_w}x{t_h} -> {atlas_w}x{atlas_h}) - "
              f"UABEA zaktualizuje wymiary tekstury przy imporcie PNG.")


if __name__ == "__main__":
    main()
