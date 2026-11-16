#!/usr/bin/env python3
"""
Sklada NAPIS z naprawionego fontu - podglad tego, co gracz zobaczy w grze, bez
wgrywania czegokolwiek do gry i bez jej odpalania.

Dwa zastosowania:
  1. z linii polecen na gotowym folderze fixed_fonts/ (patrz "Uzycie" nizej),
  2. z fix_tmp_polish_fonts.py w trakcie naprawy - to on zapisuje podglady
     do folderu fixed_preview/ (funkcje preview_static / preview_dynamic /
     save_preview sa napisane tak, zeby dzialaly na danych trzymanych
     w pamieci, jeszcze przed zapisem czegokolwiek na dysk).

Po co, skoro jest font_preview/? Tamten podglad pokazuje ATLAS (litery ustawione
w kratke, bez metryk) i stan PRZED naprawa, a wiekszosc bledow w polskich
literach widac tylko w ZLOZONYM NAPISIE:
  - litera z obcego fontu fallback ma inny krój, inna szerokosc i inna wysokosc,
    wiec "wystaje" z wyrazu (tak wygladal "[WYJDŹ]" w VCR OSD Mono: Ź w Interze
    posrodku monospace'owego kroju),
  - akcent postawiony za wysoko albo w innym miejscu niz w pozostalych literach,
  - zlepione litery (advance mniejszy od tuszu).

Do napisu dochodzi raport: SKAD wzieta jest kazda polska litera.
  wlasna     - font mial ja od poczatku,
  zlozona    - litera bazowa + akcent wyciety albo dorysowany (indeks glifu
               >= COMPOSED_GLYPH_OFFSET),
  FALLBACK   - glif z OBCEGO fontu (indeks >= FALLBACK_GLYPH_OFFSET);
               to jedyny wariant, ktory zmienia krój i rozmiar litery,
  translit.  - ten sam glif co litera bez ogonka (ź -> z).

Uzycie:
  python render_text_sample.py <fixed_fonts | plik.json> [...]
  python render_text_sample.py fixed_fonts --text "DZIĘKI [WYJDŹ]"
  python render_text_sample.py fixed_fonts --out C:\\tmp\\render --scale 4

Wynik: <out>/<nazwa fontu>.png (domyslnie <fixed_fonts>/../fixed_preview)
plus raport na konsoli.
"""
import argparse
import io
import json
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # fix_tmp_polish_fonts.py lezy poziom wyzej
import fix_tmp_polish_fonts as fx  # noqa: E402

DEFAULT_TEXT = ("DZIĘKI [WYJDŹ] ŻÓŁĆ GĘŚLĄ JAŹŃ\n"
                "OÓ CĆ NŃ SŚ ZŹ ZŻ AĄ EĘ LŁ\n"
                "oó cć nń sś zź zż aą eę lł")
PREVIEW_DIR_NAME = "fixed_preview"

# Ile razy wyzej od litery bazowej moze siegac akcent, zanim uznamy, ze cos jest
# nie tak. Zmierzone na prawdziwych fontach: wierzcholek kreski to 0.90 em przy
# wersaliku 0.70 em (+29%) i 0.72 em przy minuskule 0.50 em (+44%). Progi sa
# z duzym zapasem, bo kroje odreczne maja niska litere bazowa.
TOP_MAX_UPPER = 0.55
TOP_MAX_LOWER = 0.85
# Odstepstwo advance liczymy TYLKO w krojach monospace - w proporcjonalnym
# poszerzenie jest normalne (ogonek w "ą" i belka w "ł" wystaja poza obrys
# litery bazowej, patrz _keep_sidebearings).
MONO_TOLERANCE = 0.02


# ---------------------------------------------------------------------------
# raport: skad pochodzi kazda polska litera
# ---------------------------------------------------------------------------

def glyph_source(gi, base_gi):
    if gi >= fx.COMPOSED_GLYPH_OFFSET:
        return "zlozona"
    if gi >= fx.FALLBACK_GLYPH_OFFSET:
        return "FALLBACK"
    if base_gi is not None and gi == base_gi:
        return "translit."
    return "wlasna"


def is_monospace(chars, glyphs):
    """Czy krój jest monospace - wtedy KAZDA rozna szerokosc jest bledem."""
    have = {}
    for cp, gi in chars:
        have.setdefault(cp, gi)
    advances = []
    for ch in "acenoszACENOSZ":
        gi = have.get(ord(ch))
        if gi in glyphs and not glyphs[gi].get("empty"):
            advances.append(glyphs[gi]["metrics"]["advance"])
    if len(advances) < 6 or max(advances) <= 0:
        return False
    return (max(advances) - min(advances)) / max(advances) <= MONO_TOLERANCE


def check_pl_letters(chars, glyphs):
    """(linie raportu, liczba liter, ktore w grze wyjda inaczej niz reszta).

    Litery zlozone z wlasnych glifow fontu (to POZADANY wynik) sa zbite w jedna
    linijke; osobno wypisane jest tylko to, co wymaga uwagi - stad `problems`.
    Linie sa gotowe do wypisania (bez wciecia).
    """
    have = {}
    for cp, gi in chars:
        have.setdefault(cp, gi)
    mono = is_monospace(chars, glyphs)
    composed, translit, warnings, problems = [], [], [], 0
    for ch in fx.PL_CHARS:
        gi = have.get(ord(ch))
        base_ch = fx.accent_composer.ACCENTS[ch][0] if fx.accent_composer else None
        base_gi = have.get(ord(base_ch)) if base_ch else None
        if gi is None:
            warnings.append(f"! {ch} BRAK w tablicy znakow - gra wezmie go"
                            f" z fontu fallback (inny krój i rozmiar)")
            problems += 1
            continue
        src = glyph_source(gi, base_gi)
        note = ""
        if base_gi is not None and base_gi in glyphs and gi in glyphs:
            mb, mg = glyphs[base_gi]["metrics"], glyphs[gi]["metrics"]
            if mono and mb["advance"] > 0:
                dadv = mg["advance"] / mb["advance"] - 1.0
                if abs(dadv) > 0.03:
                    note += (f" advance {dadv:+.0%} vs '{base_ch}'"
                             f" (krój monospace!)")
            if mb["bearing_y"] > 0:
                dtop = mg["bearing_y"] / mb["bearing_y"] - 1.0
                limit = TOP_MAX_UPPER if ch.isupper() else TOP_MAX_LOWER
                if dtop > limit:
                    note += f" akcent {dtop:+.0%} nad '{base_ch}'"
        if src == "FALLBACK":
            problems += 1
            warnings.append(f"! {ch} z OBCEGO fontu (FALLBACK){note}"
                            f" - bedzie odstawac od reszty napisu")
        elif src == "translit.":
            problems += 1
            translit.append(ch)
        else:
            if src == "zlozona":
                composed.append(ch)
            if note:
                problems += 1
                warnings.append(f"! {ch}{note}")
    lines = []
    if composed:
        lines.append(f"zlozone z wlasnych glifow fontu: {''.join(composed)}")
    if translit:
        lines.append(f"! bez akcentu (transliteracja): {''.join(translit)}")
    return lines + warnings, problems


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render_glyphs(text, chars, glyphs, face_info, threshold=True):
    """Napis zlozony z `glyphs` (format jak w fix_tmp_polish_fonts).

    threshold=True progu je pole SDF na poziomie krawedzi glifu (INK_LEVEL) -
    czyli pokazuje to, co gra narysuje jako tusz. False = surowe pole.
    """
    have = {}
    for cp, gi in chars:
        have.setdefault(cp, gi)
    lines = text.split("\n")
    line_h = float(face_info.get("m_LineHeight") or 0)
    asc = float(face_info.get("m_AscentLine") or 0)
    desc = float(face_info.get("m_DescentLine") or 0)
    if line_h <= 0:
        line_h = (asc - desc) or 64.0
    pad = int(line_h * 0.35) + 4
    widths = []
    for ln in lines:
        w = 0.0
        for ch in ln:
            gi = have.get(ord(ch))
            w += glyphs[gi]["metrics"]["advance"] if gi in glyphs else line_h * 0.4
        widths.append(w)
    W = int(max(widths or [1])) + 2 * pad
    H = int(line_h * len(lines) + (asc - desc) * 0.5) + 2 * pad
    canvas = np.zeros((H, W), dtype=np.uint8)
    missing = []
    for i, ln in enumerate(lines):
        baseline = pad + asc + i * line_h
        pen = float(pad)
        for ch in ln:
            gi = have.get(ord(ch))
            if gi not in glyphs:
                if not ch.isspace():
                    missing.append(ch)
                pen += line_h * 0.4
                continue
            g = glyphs[gi]
            ox, oy = fx._glyph_origin(g)
            src = g["sdf"]
            dx, dy = int(round(pen + ox)), int(round(baseline - oy))
            y0, x0 = max(0, dy), max(0, dx)
            y1 = min(H, dy + src.shape[0])
            x1 = min(W, dx + src.shape[1])
            if y1 > y0 and x1 > x0:
                sub = src[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
                np.maximum(canvas[y0:y1, x0:x1], sub, out=canvas[y0:y1, x0:x1])
            pen += g["metrics"]["advance"]
    if threshold:
        canvas = ((canvas >= fx.INK_LEVEL) * 255).astype(np.uint8)
    return Image.fromarray(canvas, "L"), missing


def preview_static(tree, atlas_top_down, padding, text=DEFAULT_TEXT, raw=False):
    """Podglad fontu statycznego wprost z atlasu (numpy, wiersz 0 = gora).

    Zwraca (obrazek, brakujace znaki, linie raportu, liczba problemow).
    `tree` musi byc widokiem NOWOCZESNYM (m_GlyphTable/m_CharacterTable) -
    dla starego TMP przepusc go przez fix_tmp_polish_fonts.legacy_to_modern.
    """
    chars, glyphs = fx.extract_existing_glyphs(atlas_top_down, tree, padding)
    lines, problems = check_pl_letters(chars, glyphs)
    img, missing = render_glyphs(text, chars, glyphs, tree["m_FaceInfo"],
                                 threshold=not raw)
    return img, missing, lines, problems


def preview_dynamic(ttf_bytes, text=DEFAULT_TEXT, px=48):
    """Podglad fontu dynamicznego - napis wyrenderowany wprost z pliku TTF.

    Zwraca (obrazek, brakujace znaki). Raportu pochodzenia liter tu nie ma:
    w TTF nie da sie odroznic litery dorobionej od tej, ktora font mial od
    poczatku (a te wklejone z fallbacku i tak sa juz przeskalowane do kroju).
    """
    import freetype
    face = freetype.Face(io.BytesIO(ttf_bytes))
    face.set_char_size(int(px) * 64)
    lines = text.split("\n")
    line_h = (face.size.height / 64.0) or px * 1.2
    asc = face.size.ascender / 64.0
    pad = int(px * 0.4) + 4
    canvas = np.zeros((int(line_h * len(lines) + px) + 2 * pad, 16), dtype=np.uint8)
    H = canvas.shape[0]
    missing = []
    for i, ln in enumerate(lines):
        baseline = int(pad + asc + i * line_h)
        pen = pad
        for ch in ln:
            if not ch.isspace() and face.get_char_index(ch) == 0:
                missing.append(ch)
            face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            g = face.glyph
            arr = fx.gen.bitmap_to_array(g.bitmap)
            advance = g.advance.x >> 6
            x, y = max(0, pen + g.bitmap_left), max(0, baseline - g.bitmap_top)
            need = max(x + arr.shape[1], pen + advance) + pad
            if need > canvas.shape[1]:
                canvas = np.pad(canvas, ((0, 0), (0, need - canvas.shape[1])))
            if arr.size and y + arr.shape[0] <= H:
                region = canvas[y:y + arr.shape[0], x:x + arr.shape[1]]
                np.maximum(region, arr[:, :region.shape[1]], out=region)
            pen += advance
    return Image.fromarray(canvas, "L"), missing


def save_preview(img, out_dir, name, scale=2):
    """Zapisuje podglad jako <out_dir>/<name>.png (zwraca sciezke albo None)."""
    try:
        os.makedirs(out_dir, exist_ok=True)
        if scale and scale != 1:
            img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
        dst = os.path.join(out_dir, (fx.safe_name(name) or "font") + ".png")
        img.save(dst)
        return dst
    except OSError:
        # paczka moze lezec na nosniku tylko do czytania - podglad to wygoda,
        # nie powod, zeby przerywac naprawe fontu
        return None


# ---------------------------------------------------------------------------
# CLI: podglad z gotowego folderu fixed_fonts/
# ---------------------------------------------------------------------------

def one_font(path_json, text, out_dir, scale, raw, log=print):
    name = os.path.splitext(os.path.basename(path_json))[0]
    with open(path_json, encoding="utf-8") as f:
        meta = json.load(f)
    kind = meta.get("type")
    log(f"== {name}  ({kind})")

    if kind == "dynamic_font_data":
        ttf = os.path.splitext(path_json)[0] + ".ttf"
        if not os.path.exists(ttf):
            log("    ! brak pliku .ttf obok .json")
            return
        with open(ttf, "rb") as f:
            img, missing = preview_dynamic(text=text, ttf_bytes=f.read())
        lines, problems = [], 0
    else:
        png = os.path.splitext(path_json)[0] + ".png"
        if not os.path.exists(png):
            log("    ! brak atlasu .png obok .json")
            return
        tree = meta["tmp_tree"]
        if fx.is_legacy_tmp(tree):
            tree = fx.legacy_to_modern(tree)     # stary TMP: m_fontInfo + lista
        atlas = np.array(Image.open(png).convert("L"))
        padding = int(meta.get("padding") or tree.get("m_AtlasPadding") or 0)
        img, missing, lines, problems = preview_static(tree, atlas, padding,
                                                      text=text, raw=raw)
    for ln in lines:
        log("    " + ln)
    if missing:
        log(f"    ! font nie ma znakow: {''.join(sorted(set(missing)))}")
    if not problems and kind != "dynamic_font_data":
        log("    OK: kazda polska litera z wlasnych glifow fontu")
    dst = save_preview(img, out_dir, name, scale)
    log(f"    {dst}" if dst else "    ! nie udalo sie zapisac podgladu")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Sklada napis z fixed_fonts/ (podglad bez odpalania gry)")
    ap.add_argument("paths", nargs="+",
                    help="folder fixed_fonts albo pojedyncze pliki .json")
    ap.add_argument("--text", default=DEFAULT_TEXT,
                    help="tekst do zlozenia (\\n dzieli wiersze)")
    ap.add_argument("--out", default=None,
                    help=f"folder na PNG (domyslnie <fixed_fonts>/../{PREVIEW_DIR_NAME})")
    ap.add_argument("--scale", type=int, default=2, help="powiekszenie PNG")
    ap.add_argument("--raw", action="store_true",
                    help="nie progowac pola SDF (podglad surowego atlasu)")
    args = ap.parse_args(argv)

    jsons = []
    for p in args.paths:
        if os.path.isdir(p):
            jsons += [os.path.join(p, f) for f in sorted(os.listdir(p))
                      if f.endswith(".json")]
        else:
            jsons.append(p)
    if not jsons:
        print("Nie znalazlem plikow .json")
        return 1
    text = args.text.replace("\\n", "\n")
    src_dir = os.path.dirname(os.path.abspath(jsons[0]))
    out_dir = args.out or os.path.join(os.path.dirname(src_dir), PREVIEW_DIR_NAME)
    for p in jsons:
        try:
            one_font(p, text, out_dir, max(1, args.scale), args.raw)
        except Exception as e:
            print(f"!! {os.path.basename(p)}: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
