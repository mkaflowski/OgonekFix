"""Bitmapowe assety `Font` Unity (stary UI Text / TextMesh) — operacje na atlasie.

Taki font NIE ma TTF-a (`m_FontData` puste). Ma gotowy atlas (Texture2D, zwykle
Alpha8) i tabelę `m_CharacterRects`; każdy wpis:

    index    - kod znaku (Unicode)
    uv       - prostokąt w atlasie, w jednostkach 0..1; `height` bywa ujemne
    vert     - prostokąt glifu względem pióra: x = lewa krawędź, y = GÓRA (nad
               linią bazową), width, height (ujemne = w dół)
    advance  - przesunięcie pióra
    flipped  - glif upakowany w atlasie OBRÓCONY o 90 stopni

Mapowanie narożników (UnityEngine.CharacterInfo):
    nieobrócony: TL=(x, y+h)  TR=(x+w, y+h)  BL=(x, y)
    obrócony:    TL=(x+w, y)  TR=(x+w, y+h)  BL=(x, y)
z (x, y, w, h) = uv. Na tym opiera się `sample_glyph` — działa niezależnie od
znaków w uv, więc obsługuje każdy wariant, jaki wypluje importer fontów Unity.

Atlas trzymamy jako tablicę BOTTOM-UP (wiersz 0 = v=0), czyli dokładnie
w kolejności surowych danych tekstury Unity.

Moduł jest czysty (numpy + PIL): wycina glify do formatu `glyphs` używanego
przez fix_tmp_polish_fonts.compose_marks_from_glyphs, dokłada nowe glify
w wolne miejsce atlasu i renderuje podgląd napisu.
"""
import hashlib
import json

import numpy as np

INK = 128


def rects_sha(rects):
    """Odcisk tabeli znaków — instalator sprawdza nim, że gra ma TEN SAM font."""
    data = json.dumps(rects, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def glyph_size(rect):
    """(szerokość, wysokość) glifu w pikselach ekranu (z `vert`)."""
    v = rect["vert"]
    return int(round(abs(v["width"]))), int(round(abs(v["height"])))


def _corners(rect):
    """(TL, TR, BL) w uv."""
    u = rect["uv"]
    x, y, w, h = u["x"], u["y"], u["width"], u["height"]
    if rect.get("flipped"):
        return (x + w, y), (x + w, y + h), (x, y)
    return (x, y + h), (x + w, y + h), (x, y)


def sample_glyph(atlas_bu, rect):
    """Glif jako tablica TOP-DOWN (wiersz 0 = góra litery), gh x gw."""
    gw, gh = glyph_size(rect)
    if gw <= 0 or gh <= 0:
        return np.zeros((0, 0), dtype=np.uint8)
    H, W = atlas_bu.shape
    tl, tr, bl = _corners(rect)
    j = (np.arange(gw) + 0.5) / gw
    i = (np.arange(gh) + 0.5) / gh
    # p(i, j) = TL + j*(TR-TL) + i*(BL-TL)
    u = tl[0] + j[None, :] * (tr[0] - tl[0]) + i[:, None] * (bl[0] - tl[0])
    v = tl[1] + j[None, :] * (tr[1] - tl[1]) + i[:, None] * (bl[1] - tl[1])
    cols = np.clip(np.floor(u * W).astype(int), 0, W - 1)
    rows = np.clip(np.floor(v * H).astype(int), 0, H - 1)
    return atlas_bu[rows, cols]


def rect_pixels(rect, W, H):
    """(c0, c1, r0, r1) prostokąta uv w pikselach atlasu (bottom-up)."""
    u = rect["uv"]
    xs = sorted((u["x"], u["x"] + u["width"]))
    ys = sorted((u["y"], u["y"] + u["height"]))
    return (int(np.floor(xs[0] * W + 1e-6)), int(np.ceil(xs[1] * W - 1e-6)),
            int(np.floor(ys[0] * H + 1e-6)), int(np.ceil(ys[1] * H - 1e-6)))


def extract_glyphs(atlas_bu, rects, padding):
    """m_CharacterRects -> (chars, glyphs) w formacie compose_marks_from_glyphs.

    Metryki liczymy z TUSZU (nie z całego prostokąta `vert`), bo komórki
    bitmapowych fontów mają często puste wiersze nad literą - kreska nad
    literą stawałaby wtedy za wysoko."""
    chars, glyphs = [], {}
    for gi, r in enumerate(rects):
        cell = sample_glyph(atlas_bu, r)
        v = r["vert"]
        adv = float(r["advance"])
        hit = cell >= INK if cell.size else np.zeros((0, 0), bool)
        if not cell.size or not hit.any():
            glyphs[gi] = {"metrics": {"width": 0.0, "height": 0.0, "bearing_x": 0.0,
                                      "bearing_y": 0.0, "advance": adv},
                          "empty": True, "cell_w": 1, "cell_h": 1,
                          "sdf": np.zeros((1, 1), dtype=np.uint8), "inner": (0, 0, 1, 1)}
            chars.append((int(r["index"]), gi))
            continue
        rows = np.nonzero(hit.any(axis=1))[0]
        cols = np.nonzero(hit.any(axis=0))[0]
        r0, r1, c0, c1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
        ink = cell[r0:r1, c0:c1]
        h, w = ink.shape
        padded = np.zeros((h + 2 * padding, w + 2 * padding), dtype=np.uint8)
        padded[padding:padding + h, padding:padding + w] = ink
        top = float(v["y"]) if v["height"] < 0 else float(v["y"] + v["height"])
        glyphs[gi] = {
            "metrics": {"width": float(w), "height": float(h),
                        "bearing_x": float(v["x"]) + c0,
                        "bearing_y": top - r0,
                        "advance": adv},
            "empty": False,
            "cell_w": padded.shape[1], "cell_h": padded.shape[0],
            "sdf": padded,
            "inner": (padding, padding, w, h),
        }
        chars.append((int(r["index"]), gi))
    return chars, glyphs


def occupancy(atlas_bu, rects):
    """Maska zajętych pikseli: wszystkie prostokąty glifów + każdy tusz."""
    H, W = atlas_bu.shape
    used = atlas_bu > 0
    for r in rects:
        c0, c1, r0, r1 = rect_pixels(r, W, H)
        used[max(0, r0):min(H, r1), max(0, c0):min(W, c1)] = True
    return used


def _find_free(used, w, h, margin=1):
    """Lewy-dolny róg (c, r) wolnego obszaru w x h z marginesem, albo None."""
    H, W = used.shape
    bw, bh = w + 2 * margin, h + 2 * margin
    if bw > W or bh > H:
        return None
    integ = np.zeros((H + 1, W + 1), dtype=np.int32)
    integ[1:, 1:] = np.cumsum(np.cumsum(used.astype(np.int32), axis=0), axis=1)
    s = (integ[bh:, bw:] - integ[:-bh, bw:] - integ[bh:, :-bw] + integ[:-bh, :-bw])
    free = np.argwhere(s == 0)
    if not free.size:
        return None
    r, c = free[0]           # najniższy wiersz (bottom-up), potem najbardziej z lewej
    return int(c) + margin, int(r) + margin


def place_glyphs(atlas_bu, rects, new_cells, max_size=4096):
    """Dokłada glify w wolne miejsce atlasu (gdy brak - podwaja wysokość).

    new_cells: [(kod, cell_top_down, (x0, y_top), advance)] - (x0, y_top) to
    pozycja lewego-górnego piksela komórki względem pióra i linii bazowej.
    Zwraca (nowy_atlas_bu, nowe_rects). Istniejące wpisy dostają przeliczone
    uv tylko wtedy, gdy atlas urósł (piksele zostają na miejscu)."""
    atlas = atlas_bu.copy()
    rects = [json.loads(json.dumps(r)) for r in rects]
    used = occupancy(atlas, rects)
    added = []
    for cp, cell, (x0, y_top), adv in new_cells:
        h, w = cell.shape
        pos = _find_free(used, w, h)
        while pos is None:
            H, W = atlas.shape
            if H * 2 > max_size:
                raise RuntimeError(f"brak miejsca w atlasie {W}x{H} na glif U+{cp:04X}")
            # rośnie w górę (bottom-up = nowe wiersze na końcu): stare piksele i ich
            # v*H zostają, zmienia się tylko mianownik -> przeskalowanie uv.y/height
            grown = np.zeros((H * 2, W), dtype=atlas.dtype)
            grown[:H] = atlas
            grown_used = np.zeros((H * 2, W), dtype=bool)
            grown_used[:H] = used
            for r in rects + [a for a in added]:
                r["uv"]["y"] *= 0.5
                r["uv"]["height"] *= 0.5
            atlas, used = grown, grown_used
            pos = _find_free(used, w, h)
        c, r0 = pos
        H, W = atlas.shape
        # komórka top-down: góra litery w NIŻSZYM wierszu bottom-up (jak w imporcie Unity)
        atlas[r0:r0 + h, c:c + w] = cell
        used[r0 - 1:r0 + h + 1, c - 1:c + w + 1] = True
        added.append({
            "index": int(cp),
            "uv": {"x": c / W, "y": (r0 + h) / H, "width": w / W, "height": -h / H},
            "vert": {"x": float(x0), "y": float(y_top), "width": float(w), "height": float(-h)},
            "advance": float(adv),
            "flipped": False,
        })
    return atlas, rects + added


def render_text(atlas_bu, rects, text, scale=4, line_gap=2):
    """Podgląd napisu (PIL 'L', czarny tekst na białym), skala całkowita."""
    from PIL import Image

    by_cp = {int(r["index"]): r for r in rects}
    tops, bots = [], []
    for r in rects:
        v = r["vert"]
        top = v["y"] if v["height"] < 0 else v["y"] + v["height"]
        tops.append(top)
        bots.append(top - abs(v["height"]))
    asc, desc = max(tops or [10]), min(bots or [0])
    lines = text.split("\n")
    widths = []
    for line in lines:
        widths.append(sum(by_cp[ord(ch)]["advance"] if ord(ch) in by_cp else 4 for ch in line))
    lh = int(np.ceil(asc - desc)) + line_gap
    img = np.zeros((lh * len(lines) + 4, int(max(widths or [1])) + 8), dtype=np.uint8)
    for li, line in enumerate(lines):
        pen = 4.0
        base = 2 + li * lh + int(np.ceil(asc))
        for ch in line:
            r = by_cp.get(ord(ch))
            if r is None:
                pen += 4
                continue
            g = sample_glyph(atlas_bu, r)
            v = r["vert"]
            top = v["y"] if v["height"] < 0 else v["y"] + v["height"]
            y0 = base - int(round(top))
            x0 = int(round(pen + v["x"]))
            h, w = g.shape
            if h and w:
                ys, xs = max(0, y0), max(0, x0)
                ye, xe = min(img.shape[0], y0 + h), min(img.shape[1], x0 + w)
                if ye > ys and xe > xs:
                    np.maximum(img[ys:ye, xs:xe], g[ys - y0:ye - y0, xs - x0:xe - x0],
                               out=img[ys:ye, xs:xe])
            pen += r["advance"]
    out = Image.fromarray(255 - img)
    return out.resize((out.width * scale, out.height * scale), Image.NEAREST)
