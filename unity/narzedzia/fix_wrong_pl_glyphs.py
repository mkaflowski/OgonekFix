#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Naprawia polskie znaki, ktore w wyeksportowanym atlasie maja ZLY GLIF.

Problem, ktory to lapie: font, ktory TWIERDZI, ze ma dana litere (jest w
m_CharacterTable), ale pod jej kodem siedzi zupelnie inny znak. Klasyk to
fonty DOS-owe mapowane po CP437 zamiast po Unicode - "Perfect DOS VGA 437"
rysuje pod U+00F3 (ó) znak '<=' (0xF3 w CP437), a pod U+00D3 (Ó) fragment
ramki. W grze wyglada to tak:

    Powinienem p<=jsc  ...zamiast...  Powinienem pojsc

fix_tmp_polish_fonts.py tego nie widzi: dorabia tylko litery NIEOBECNE w
tabeli znakow, a ó/Ó "sa". Dlatego dostaja poprawiony atlas ze wszystkimi
ogonkami i jednym-dwoma znakami-krzakami.

Co robi ten skrypt (na gotowym eksporcie z fixed_fonts/, bez plikow gry):
  1. wycina z atlasu (PNG) glify wszystkich znakow (extract_existing_glyphs),
  2. sprawdza, czy litera z akcentem zawiera w sobie swoja litere bazowa
     (ó musi zawierac o) - z tolerancja na przesuniecie, zeby 1-pikselowe
     rozjazdy w fontach pikselowych nie robily falszywych alarmow,
  3. jesli caly blok Latin-1 fontu jest przemapowany (wiekszosc liter z
     akcentem nie pasuje do swojej bazy), uznaje glify polskich liter
     wziete Z ORYGINALNEGO fontu za krzaki - te sklada od nowa z litery
     bazowej i akcentu WYCIETEGO z liter juz poprawnych w tym atlasie
     (ć/ń/ś/ź), czyli dokladnie tak, jak powstala reszta ogonkow,
  4. przepakowuje atlas i nadpisuje <font>.json + <font>.png w fixed_fonts/.

Glify skladane wczesniej przez fix_tmp_polish_fonts (indeks >= 2 000 000)
i wziete z fontu fallback (>= 1 000 000) NIE sa ruszane - one juz przeszly
przez recznie zatwierdzony eksport.

Uzycie:
  python fix_wrong_pl_glyphs.py                        # fixed_fonts/ obok fix_tmp_polish_fonts.py
  python fix_wrong_pl_glyphs.py <katalog fixed_fonts>
  python fix_wrong_pl_glyphs.py <katalog> --check      # tylko raport, bez zapisu
  python fix_wrong_pl_glyphs.py <katalog> --only DOS   # tylko fonty z DOS w nazwie
"""
import argparse
import copy
import json
import os
import sys

import numpy as np
from PIL import Image

for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # fix_tmp_polish_fonts.py lezy poziom wyzej
import fix_tmp_polish_fonts as fx      # noqa: E402  (silnik: skladanie, pakowanie)
import generate_tmp_sdf as gen         # noqa: E402

PL_CHARS = fx.PL_CHARS

# litery z akcentem z bloku Latin-1 i ich litery bazowe - na nich sprawdzamy,
# czy font nie jest przemapowany (to ten blok cierpi w fontach CP437)
LATIN1_ACCENTED = {
    "á": "a", "à": "a", "â": "a", "ä": "a", "ã": "a", "å": "a",
    "é": "e", "è": "e", "ê": "e", "ë": "e",
    "í": "i", "ì": "i", "î": "i", "ï": "i",
    "ó": "o", "ò": "o", "ô": "o", "ö": "o", "õ": "o",
    "ú": "u", "ù": "u", "û": "u", "ü": "u", "ý": "y",
    "ñ": "n", "ç": "c",
    "Á": "A", "À": "A", "Â": "A", "Ä": "A", "Ã": "A",
    "É": "E", "È": "E", "Ê": "E", "Ë": "E",
    "Í": "I", "Ó": "O", "Ô": "O", "Ö": "O", "Ú": "U", "Ü": "U",
    "Ñ": "N", "Ç": "C",
}
# samodzielne znaki diakrytyczne z Latin-1 / Spacing Modifiers: w przemapowanym
# foncie sa krzakami, a compose_marks_from_glyphs chetnie z nich bierze akcent
STANDALONE_MARKS = "\u00b4\u00a8\u02d9\u02db\u02ca\u0301\u0307\u0328"

# dawcy akcentu DOPISYWANI na koniec MARK_PAIRS: polskie litery, ktore w tym
# atlasie sa juz poprawne (zlozone przez fix_tmp_polish_fonts). Dzieki temu
# odtworzone ó ma DOKLADNIE ten sam akcent, co ć/ń/ś/ź obok.
#
# Celowo TYLKO male litery: w przemapowanym foncie wersalik-dawca (Ó = fragment
# ramki w CP437) daje "akcent" w postaci dwoch klockow (wyglada jak ¨).
# Gdy dawcy tej samej wielkosci nie ma, _get_mark bierze malego i podnosi go
# nad wersalik - i to jest wlasnie to, czego chcemy.
PL_MARK_DONORS = {
    "acute": [("ć", "c"), ("ń", "n"), ("ś", "s"), ("ź", "z")],
    "dot": [("ż", "z")],
    "ogonek": [("ą", "a"), ("ę", "e")],
}

COVER_MIN = 0.6          # ponizej tego litera "nie zawiera" swojej bazy
REMAP_MIN_SAMPLES = 4    # mniej liter Latin-1 = za maly material na wyrok
REMAP_MIN_RATIO = 0.5    # tyle z nich musi byc zlych, zeby uznac przemapowanie


# ---------------------------------------------------------------------------
# porownywanie glifow
# ---------------------------------------------------------------------------

def _ink(g):
    ix, iy, iw, ih = g["inner"]
    return g["sdf"][iy:iy + ih, ix:ix + iw] >= fx.INK_LEVEL


def base_coverage(g_acc, g_base, slack):
    """Ile tuszu litery bazowej pokrywa litera z akcentem (0..1).

    Oba glify ustawiane w ukladzie piora (x od pozycji piora, y od linii
    bazowej), z tolerancja +-slack pikseli na przesuniecie - fonty pikselowe
    rysuja ó o piksel wezsze niz o i to jest normalne, nie zly glif.
    """
    a, b = _ink(g_acc), _ink(g_base)
    if b.sum() == 0:
        return 1.0
    ma, mb = g_acc["metrics"], g_base["metrics"]
    off = 2 * slack + 2
    x_min = int(min(ma["bearing_x"], mb["bearing_x"])) - off
    x_max = int(max(ma["bearing_x"] + a.shape[1],
                    mb["bearing_x"] + b.shape[1])) + off
    y_top = int(max(ma["bearing_y"], mb["bearing_y"])) + off
    y_bottom = int(min(ma["bearing_y"] - a.shape[0],
                       mb["bearing_y"] - b.shape[0])) - off
    h, w = y_top - y_bottom, x_max - x_min

    def put(ink, m, dx=0, dy=0):
        c = np.zeros((h, w), dtype=bool)
        y = y_top - int(round(m["bearing_y"])) + dy
        x = int(round(m["bearing_x"])) - x_min + dx
        c[y:y + ink.shape[0], x:x + ink.shape[1]] = ink
        return c

    A = put(a, ma)
    best = 0.0
    for dy in range(-slack, slack + 1):
        for dx in range(-slack, slack + 1):
            B = put(b, mb, dx, dy)
            best = max(best, float((A & B).sum()) / float(B.sum()))
            if best > 0.99:
                return best
    return best


def glyph_source(gi):
    if gi >= fx.COMPOSED_GLYPH_OFFSET:
        return "zlozony"
    if gi >= fx.FALLBACK_GLYPH_OFFSET:
        return "fallback"
    return "oryginal"


# ---------------------------------------------------------------------------
# analiza jednego eksportu
# ---------------------------------------------------------------------------

class Export:
    """Wyeksportowany font statyczny: <nazwa>.json + <nazwa>.png."""

    def __init__(self, json_path):
        self.json_path = json_path
        self.png_path = os.path.splitext(json_path)[0] + ".png"
        with open(json_path, encoding="utf-8") as f:
            self.meta = json.load(f)
        self.label = self.meta.get("label", os.path.basename(json_path))
        self.legacy = None
        tree = self.meta["tmp_tree"]
        if fx.is_legacy_tmp(tree):
            self.legacy = tree
            tree = fx.legacy_to_modern(tree)
        self.tree = tree
        self.padding = int(tree["m_AtlasPadding"])
        self.atlas_w = int(tree["m_AtlasWidth"])
        self.atlas_h = int(tree["m_AtlasHeight"])
        self.point_size = int(tree["m_FaceInfo"]["m_PointSize"])
        self.render_mode = tree.get("m_AtlasRenderMode")
        atlas = np.asarray(Image.open(self.png_path).convert("L"))
        self.chars, self.glyphs = fx.extract_existing_glyphs(atlas, tree, self.padding)
        self.have = {}
        for cp, gi in self.chars:
            self.have.setdefault(cp, gi)
        xheight = max((self.glyphs[self.have[ord(c)]]["metrics"]["bearing_y"]
                       for c in fx.XHEIGHT_REFS if ord(c) in self.have), default=0.0)
        self.em_px = fx._estimate_em_px(self.point_size, xheight)
        self.slack = max(2, int(round(0.07 * self.em_px)))

    def coverage(self, ch, base):
        gi, gb = self.have.get(ord(ch)), self.have.get(ord(base))
        if gi is None or gb is None:
            return None
        ga, gbg = self.glyphs.get(gi), self.glyphs.get(gb)
        if ga is None or gbg is None or ga.get("empty") or gbg.get("empty"):
            return None
        return base_coverage(ga, gbg, self.slack)

    def latin1_verdict(self):
        """(przemapowany?, zle, sprawdzone, szczegoly) dla bloku Latin-1."""
        bad, total, detail = 0, 0, []
        for ch, base in LATIN1_ACCENTED.items():
            gi = self.have.get(ord(ch))
            if gi is None or gi >= fx.FALLBACK_GLYPH_OFFSET:
                continue          # nie ma albo to NASZ glif, nie fontu
            cov = self.coverage(ch, base)
            if cov is None:
                continue
            total += 1
            if cov < COVER_MIN:
                bad += 1
                detail.append(f"{ch}={cov:.2f}")
        remapped = (total >= REMAP_MIN_SAMPLES and bad / total >= REMAP_MIN_RATIO)
        return remapped, bad, total, detail

    def broken_pl(self, remapped):
        """Polskie litery z ORYGINALNYM glifem, ktory nie zawiera swojej bazy."""
        out = []
        for ch in PL_CHARS:
            gi = self.have.get(ord(ch))
            if gi is None or gi >= fx.FALLBACK_GLYPH_OFFSET:
                continue
            base = fx.accent_composer.ACCENTS[ch][0]
            cov = self.coverage(ch, base)
            if cov is None or cov >= COVER_MIN:
                continue
            # bez potwierdzenia, ze caly blok Latin-1 jest przemapowany, nie
            # ruszamy niczego: pojedynczy niski wynik to zwykle inny rysunek
            # litery w foncie pikselowym, a nie krzak
            if remapped:
                out.append((ch, cov, gi))
        return out

    def upper_acute_composed(self):
        """Wersaliki z kreska ZLOZONE wczesniej z (nieufnego) bloku Latin-1.

        W przemapowanym foncie dawca dla wersalika (Ó, É) to znak ramki, wiec
        Ć/Ń/Ś/Ź dostaly "kreske" z dwoch klockow (wyglada jak ¨). Male litery
        w tych fontach wychodza dobrze, bo ich dawca (ó = '<=') zostawia po
        odjeciu 'o' ukosna kreske.
        """
        out = []
        for ch in PL_CHARS:
            if not ch.isupper() or fx.accent_composer.ACCENTS[ch][1] != "acute":
                continue
            gi = self.have.get(ord(ch))
            if gi is None or gi < fx.COMPOSED_GLYPH_OFFSET:
                continue          # nie nasz zlozony glif - nie ruszamy
            out.append((ch, gi))
        return out


# ---------------------------------------------------------------------------
# naprawa
# ---------------------------------------------------------------------------

def _with_pl_donors():
    """MARK_PAIRS z dopisanymi (na KONIEC) dawcami z polskich liter."""
    orig = fx.accent_composer.MARK_PAIRS
    merged = {k: list(v) for k, v in orig.items()}
    for kind, pairs in PL_MARK_DONORS.items():
        merged.setdefault(kind, [])
        for p in pairs:
            if p not in merged[kind]:
                merged[kind].append(p)
    return orig, merged


def recompose(exp, broken, extra=(), log=print):
    """Sklada od nowa zepsute litery. Zwraca (ile naprawionych, atlas)."""
    bogus_cps = {ord(ch) for ch, _cov, _gi in broken} | {ord(ch) for ch, _gi in extra}
    # Blok Latin-1 tego fontu jest przemapowany, wiec NIE UFAMY MU W CALOSCI:
    # na czas skladania wypisujemy z tabeli znakow wszystkie jego litery z
    # akcentem. Inaczej _get_mark wezmie "kreske" z pierwszej, ktora akurat
    # przeszla test pokrycia (é = Θ w CP437 daje daszek, Ö = ¸ daje dwie
    # kropki) i ó dostanie akcent nie z tego fontu, co ć/ń/ś/ź obok.
    drop = set(bogus_cps)
    for ch in LATIN1_ACCENTED:
        gi = exp.have.get(ord(ch))
        if gi is not None and gi < fx.FALLBACK_GLYPH_OFFSET:
            drop.add(ord(ch))
    for ch in STANDALONE_MARKS:
        gi = exp.have.get(ord(ch))
        if gi is not None and gi < fx.FALLBACK_GLYPH_OFFSET:
            drop.add(ord(ch))

    removed = [(cp, gi) for cp, gi in exp.chars if cp in drop]
    chars = [(cp, gi) for cp, gi in exp.chars if cp not in drop]
    glyphs = exp.glyphs

    orig_pairs, merged_pairs = _with_pl_donors()
    fx.accent_composer.MARK_PAIRS = merged_pairs
    try:
        chars, glyphs, still, composed = fx.compose_marks_from_glyphs(
            chars, glyphs, sorted(bogus_cps), exp.padding,
            point_size=exp.point_size, render_mode=exp.render_mode, quiet=True)
    finally:
        fx.accent_composer.MARK_PAIRS = orig_pairs

    fixed = sorted(bogus_cps - set(still))
    if not fixed:
        log("      ! nie udalo sie zlozyc zadnej z tych liter "
            "(brak litery bazowej albo akcentu do wyciecia)")
        return 0, None
    log("      zlozone od nowa: " + "".join(chr(c) for c in fixed)
        + (" | nadal zle: " + "".join(chr(c) for c in still) if still else ""))

    # wracaja znaki wypisane tylko na czas skladania (poza tymi naprawionymi -
    # te maja juz nowy, zlozony glif)
    for cp, gi in removed:
        if cp not in fixed:
            chars.append((cp, gi))
    chars.sort(key=lambda t: t[0])

    # glify, do ktorych nikt sie juz nie odwoluje (stary krzak ó), wypadaja
    used = {gi for _cp, gi in chars}
    glyphs = {gi: g for gi, g in glyphs.items() if gi in used}

    try:
        w, h, placements, free = gen.pack_atlas(glyphs, exp.atlas_w, exp.atlas_h,
                                                allow_grow=False)
    except SystemExit as e:
        log(f"      ! {e}")
        log("      ! atlas musialby zostac powiekszony - to wymaga tez zmiany "
            "_TextureWidth/_TextureHeight w materialach, wiec przerywam")
        return 0, None

    atlas = gen.compose_atlas(glyphs, placements, w, h)
    write_export(exp, glyphs, placements, chars, w, h)
    return len(fixed), atlas


def write_export(exp, glyphs, placements, chars, atlas_w, atlas_h):
    """Nadpisuje <font>.json i <font>.png (tak samo jak finalize_font_asset
    w trybie EKSPORT, tylko bez plikow gry)."""
    tree = exp.tree
    glyph_rows, used_rects = [], []
    for gi in sorted(glyphs.keys()):
        g = glyphs[gi]
        cx, cy = placements[gi]
        ix, iy, iw, ih = g["inner"]
        m = g["metrics"]
        glyph_rows.append((gi, m, cx + ix, cy + iy, iw, ih))
        used_rects.append((cx, cy, g["cell_w"], g["cell_h"]))

    gproto = copy.deepcopy(tree["m_GlyphTable"][0]) if tree["m_GlyphTable"] \
        else copy.deepcopy(fx.GLYPH_PROTO)
    garr = []
    for gi, m, rx, ry, rw, rh in glyph_rows:
        e = copy.deepcopy(gproto)
        e["m_Index"] = gi
        e["m_Metrics"].update({"m_Width": float(m["width"]),
                               "m_Height": float(m["height"]),
                               "m_HorizontalBearingX": float(m["bearing_x"]),
                               "m_HorizontalBearingY": float(m["bearing_y"]),
                               "m_HorizontalAdvance": float(m["advance"])})
        e["m_GlyphRect"].update({"m_X": rx, "m_Y": ry, "m_Width": rw, "m_Height": rh})
        e["m_Scale"] = 1.0
        e["m_AtlasIndex"] = 0
        garr.append(e)
    tree["m_GlyphTable"] = garr

    cproto = copy.deepcopy(tree["m_CharacterTable"][0]) if tree["m_CharacterTable"] \
        else copy.deepcopy(fx.CHAR_PROTO)
    carr = []
    for cp, gi in chars:
        e = copy.deepcopy(cproto)
        e.update({"m_ElementType": 1, "m_Unicode": cp, "m_GlyphIndex": gi,
                  "m_Scale": 1.0})
        carr.append(e)
    tree["m_CharacterTable"] = carr

    def rect_arr(rects):
        return [{"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h}
                for x, y, w, h in rects]

    tree["m_UsedGlyphRects"] = rect_arr(used_rects)
    tree["m_FreeGlyphRects"] = rect_arr(free_rects_of(used_rects, atlas_w, atlas_h))
    tree["m_AtlasWidth"] = atlas_w
    tree["m_AtlasHeight"] = atlas_h

    save_tree = tree
    if exp.legacy is not None:
        save_tree = fx.modern_to_legacy(exp.legacy, tree)
    exp.meta["tmp_tree"] = save_tree
    exp.meta["atlas_w"] = atlas_w
    exp.meta["atlas_h"] = atlas_h


def free_rects_of(used_rects, atlas_w, atlas_h):
    top = max((y + h for _x, y, _w, h in used_rects), default=0)
    return [(0, top, atlas_w, atlas_h - top)] if top < atlas_h else []


def save_files(exp, atlas):
    """Zapis dopiero, gdy wszystko sie udalo (JSON + PNG razem)."""
    png_tmp = exp.png_path + ".tmp"
    json_tmp = exp.json_path + ".tmp"
    Image.fromarray(np.flipud(atlas), "L").save(png_tmp, format="PNG")
    with open(json_tmp, "w", encoding="utf-8") as f:
        json.dump(exp.meta, f, ensure_ascii=False)
    os.replace(png_tmp, exp.png_path)
    os.replace(json_tmp, exp.json_path)


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Naprawia polskie znaki z podmienionym glifem w eksporcie "
                    "fixed_fonts/ (fonty mapowane po CP437 itp.).")
    ap.add_argument("fixed_dir", nargs="?",
                    default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "fixed_fonts"),
                    help="katalog z eksportem (domyslnie fixed_fonts/ obok fix_tmp_polish_fonts.py)")
    ap.add_argument("--check", action="store_true",
                    help="tylko raport, bez zapisu")
    ap.add_argument("--only", default="",
                    help="tylko fonty, ktorych nazwa zawiera ten tekst")
    ap.add_argument("--upper-acute", action="store_true",
                    help="w przemapowanym foncie skladaj TAKZE wersaliki z kreska "
                         "(Ć Ń Ó Ś Ź) od nowa - ich kreska pochodzi z ramki CP437 "
                         "i wyglada jak dwie kropki; nowa idzie z malych liter")
    ap.add_argument("--refresh-ogonek", action="store_true",
                    help="przerysuj ą/ę/Ą/Ę aktualna geometria ogonka")
    args = ap.parse_args()

    if not os.path.isdir(args.fixed_dir):
        sys.exit(f"Nie ma katalogu: {args.fixed_dir}")

    print("=" * 64)
    print("  Polskie znaki z PODMIENIONYM glifem (fixed_fonts/)")
    print("=" * 64)
    print(f"Katalog: {args.fixed_dir}\n")

    files = [f for f in sorted(os.listdir(args.fixed_dir)) if f.endswith(".json")]
    total_bad = total_fixed = 0
    for fname in files:
        path = os.path.join(args.fixed_dir, fname)
        try:
            with open(path, encoding="utf-8") as f:
                head = json.load(f)
        except Exception as e:
            print(f"[?] {fname}: nie moge wczytac ({type(e).__name__}: {e})")
            continue
        if head.get("type", "static_atlas") != "static_atlas":
            continue          # fonty dynamiczne to TTF, nie atlas - inna sciezka
        if args.only and args.only.lower() not in head.get("label", "").lower():
            continue
        if not os.path.isfile(os.path.splitext(path)[0] + ".png"):
            print(f"[?] {head.get('label')}: brak PNG atlasu - pomijam")
            continue

        try:
            exp = Export(path)
        except Exception as e:
            print(f"[?] {head.get('label')}: {type(e).__name__}: {e}")
            continue

        remapped, bad, total, detail = exp.latin1_verdict()
        broken = exp.broken_pl(remapped)
        extra = exp.upper_acute_composed() if (remapped and args.upper_acute) else []
        if args.refresh_ogonek:
            present = [(ch, exp.have.get(ord(ch))) for ch in "ąęĄĘ"]
            forced = [(ch, 0.0, gi) for ch, gi in present if gi is not None]
            known = {ch for ch, _cov, _gi in broken}
            broken.extend(item for item in forced if item[0] not in known)
        if not broken and not extra:
            note = ""
            if bad and total:
                note = f"  (Latin-1: {bad}/{total} nie pasuje" \
                       f"{', ale za maly material na wyrok' if not remapped else ''})"
            print(f"[OK] {exp.label}{note}")
            continue

        total_bad += len(broken)
        print(f"[!!] {exp.label}")
        print(f"      Latin-1 przemapowany: {bad}/{total} liter nie zawiera swojej "
              f"bazy ({' '.join(detail[:8])}{' ...' if len(detail) > 8 else ''})")
        if broken:
            print("      polskie litery z krzakiem: "
                  + ", ".join(f"{ch} (pokrycie {cov:.2f}, glif {gi} = "
                              f"{glyph_source(gi)})" for ch, cov, gi in broken))
        if extra:
            print("      wersaliki z kreska do zlozenia od nowa (--upper-acute): "
                  + "".join(ch for ch, _gi in extra))
        elif broken and remapped and not args.upper_acute:
            hint = exp.upper_acute_composed()
            if hint:
                print("      uwaga: wersaliki " + "".join(ch for ch, _gi in hint)
                      + " maja kreske zlozona z ramki CP437 (wyglada jak ¨) - "
                        "przelacznik --upper-acute sklada je od nowa")
        if args.check:
            continue
        n, atlas = recompose(exp, broken, extra)
        if n and atlas is not None:
            save_files(exp, atlas)
            total_fixed += n
            print(f"      zapisano: {os.path.basename(exp.json_path)} + .png")

    print()
    if args.check:
        print(f"Znalezione zle glify: {total_bad} (tryb --check, nic nie zapisano)")
    else:
        print(f"Znalezione zle glify: {total_bad}, naprawione: {total_fixed}")
    if total_fixed:
        print("Wgraj fonty do gry na nowo (patch_fixed_fonts.py / instalator).")


if __name__ == "__main__":
    main()
