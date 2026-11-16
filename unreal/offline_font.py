# -*- coding: utf-8 -*-
"""
Unreal: polskie litery w foncie OFFLINE (atlas liter zaszyty w .uasset).

Font offline (UFont, FontCacheType = Offline) to tablica `Characters` + strony
atlasu jako Texture2D w tym samym pakiecie. Uzywaja go TextRender i czesc HUD-ow.
Nie ma pliku .ufont, wiec zestaw znakow jest staly - zwykle Latin-1.

Modul robi trzy rzeczy na parze legacy (.uasset + .uexp):
  parse()      - znajduje tablice Characters, eksporty i strony atlasu (PF_G8),
  calibrate()  - dopasowuje render zrodlowego TTF do ISTNIEJACYCH liter atlasu
                 (rozmiar, linia bazowa, model: pole odleglosci SDF albo zwykle
                 krycie) - bez tego dorysowane litery odstawalyby od reszty,
  patch()      - renderuje brakujace litery, wkleja je w wolne miejsce atlasu,
                 wydluza Characters i poprawia rozmiary/offsety w naglowku.

Zalozenia (kazde jest sprawdzane; niespelnione = Unsupported z powodem):
  * Characters indeksowane WPROST kodem znaku (IsRemapped = false),
  * strony w formacie PF_G8 (1 bajt na piksel), dane mipa inline w eksporcie,
  * w atlasie jest wolne miejsce na nowe litery.

Sprawdzone na: Crisol Theater of Idols (UE 5.5, SDF, 4 strony 256x256).
"""

from __future__ import annotations

import io
import math
import struct
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage

CHAR_FMT = "<iiiiBi"      # StartU, StartV, USize, VSize, TextureIndex, VerticalOffset
CHAR_SIZE = 21
PAGE_TRAILER = 24         # za danymi mipa: SizeX, SizeY, SizeZ + 12 bajtow
PL = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
FIT_LETTERS = "OAHnepldEDs"
# Sredni blad dopasowania w poziomach szarosci; powyzej - odmowa. Crisol: wlasciwy
# font 3.2, inny kroj z tej samej gry 8.6 - prog musi je rozdzielac.
MAX_RMS = 6.0


class Unsupported(Exception):
    """Font offline ma budowe, ktorej nie umiemy bezpiecznie zmienic."""


# ------------------------------------------------------------------ parsowanie

def find_exports(ua: bytes, uexp_len: int) -> list[tuple[int, int, int]]:
    """[(pozycja pola SerialSize w .uasset, rozmiar, offset)] w kolejnosci w pliku.

    Wpis tabeli eksportow ma pare int64 (SerialSize, SerialOffset); pierwszy eksport
    zaczyna sie tam, gdzie konczy naglowek, kolejny tam, gdzie poprzedni.
    """
    out, off, end = [], len(ua), len(ua) + uexp_len - 4
    while off < end:
        hits = [i for i in range(len(ua) - 16)
                if struct.unpack_from("<q", ua, i + 8)[0] == off
                and 0 < struct.unpack_from("<q", ua, i)[0] <= end - off]
        if len(hits) != 1:
            raise Unsupported(f"nie umiem jednoznacznie znalezc eksportu o offsecie {off}")
        size = struct.unpack_from("<q", ua, hits[0])[0]
        out.append((hits[0], size, off))
        off += size
    if off != end:
        raise Unsupported("lancuch eksportow nie konczy sie na koncu .uexp")
    return out


def _find_char_table(ue: bytes, start: int, end: int) -> tuple[int, int] | None:
    """(offset licznika, liczba) tablicy Characters w eksporcie [start, end)."""
    for o in range(start, min(start + 96, end - 8)):
        n = struct.unpack_from("<i", ue, o)[0]
        if not 64 <= n <= 70000 or o + 4 + n * CHAR_SIZE > end:
            continue
        ok = True
        for i in range(n):
            u, v, w, h, t, vo = struct.unpack_from(CHAR_FMT, ue, o + 4 + i * CHAR_SIZE)
            if not (0 <= u <= 16384 and 0 <= v <= 16384 and 0 <= w <= 2048
                    and 0 <= h <= 2048 and t < 64 and -4096 <= vo <= 4096):
                ok = False
                break
        if ok:
            return o, n
    return None


def parse(ua: bytes, ue: bytes) -> dict:
    exports = find_exports(ua, len(ue))
    hdr = len(ua)
    font = table = None
    for k, (_pos, size, off) in enumerate(exports):
        table = _find_char_table(ue, off - hdr, off - hdr + size)
        if table:
            font = k
            break
    if font is None:
        raise Unsupported("nie znalazlem tablicy Characters")
    count_off, count = table
    chars = [list(struct.unpack_from(CHAR_FMT, ue, count_off + 4 + CHAR_SIZE * i))
             for i in range(count)]

    pages = []                      # (indeks eksportu, poczatek danych, koniec, W, H)
    for k, (_pos, size, off) in enumerate(exports):
        if k == font:
            continue
        a, b = off - hdr, off - hdr + size
        if b"PF_G8" not in ue[a:b]:
            if size > 4096:
                raise Unsupported("strona atlasu nie jest w formacie PF_G8")
            continue
        w, h, d = struct.unpack_from("<iii", ue, b - PAGE_TRAILER)
        if not (16 <= w <= 8192 and 16 <= h <= 8192 and d == 1 and w * h <= size - PAGE_TRAILER):
            raise Unsupported("nie umiem odczytac wymiarow strony atlasu")
        pages.append((k, b - PAGE_TRAILER - w * h, b - PAGE_TRAILER, w, h))
    if not pages:
        raise Unsupported("brak stron atlasu PF_G8")
    used = [c for c in chars if c[2] > 0]
    if not used or max(c[4] for c in used) >= len(pages):
        raise Unsupported("Characters wskazuje na strone, ktorej nie ma")
    for u, v, w, h, t, _ in used:
        if u + w > pages[t][3] or v + h > pages[t][4]:
            raise Unsupported("komorka znaku wychodzi poza strone atlasu")
    return {"exports": exports, "font": font, "count_off": count_off, "count": count,
            "chars": chars, "pages": pages}


def page_arrays(ue: bytes, info: dict) -> list[np.ndarray]:
    return [np.frombuffer(ue[a:b], dtype=np.uint8).reshape(h, w).copy()
            for _k, a, b, w, h in info["pages"]]


def missing_chars(info: dict, wanted: str = PL) -> str:
    chars = info["chars"]
    return "".join(ch for ch in wanted if ord(ch) >= len(chars) or chars[ord(ch)][2] == 0)


# ----------------------------------------------------------------- kalibracja

def _fields(font, ch: str, w: int, cell_h: int, ss: int, pad: int):
    """(pole odleglosci, krycie) na plotnie (3*cell_h, w+2*pad); linia bazowa w 2*cell_h."""
    W, H = (w + 2 * pad) * ss, 3 * cell_h * ss
    img = Image.new("L", (W, H), 0)
    ImageDraw.Draw(img).text((pad * ss, 2 * cell_h * ss), ch, font=font, fill=255, anchor="ls")
    mask = np.asarray(img) > 127
    sd = (ndimage.distance_transform_edt(mask) - ndimage.distance_transform_edt(~mask)) / ss
    shape = (3 * cell_h, ss, w + 2 * pad, ss)
    return sd.reshape(shape).mean(axis=(1, 3)), mask.reshape(shape).mean(axis=(1, 3))


def calibrate(ttf: bytes, info: dict, pages: list[np.ndarray], log=None) -> dict:
    """Dopasowuje render TTF do liter atlasu. Zwraca parametry + 'rms'."""
    chars = info["chars"]
    letters = [c for c in FIT_LETTERS if ord(c) < len(chars) and chars[ord(c)][2] > 3][:7]
    if len(letters) < 4:
        raise Unsupported("za malo liter lacinskich w atlasie, zeby dopasowac styl")
    cell_h = Counter(chars[ord(c)][3] for c in letters).most_common(1)[0][0]
    letters = [c for c in letters if chars[ord(c)][3] == cell_h]
    cells = {}
    for c in letters:
        u, v, w, h, t, _ = chars[ord(c)]
        cells[c] = pages[t][v:v + h, u:u + w].astype(np.float32)
    ss, pad = 4, 8
    best = None
    sizes = [s / 2 for s in range(int(cell_h * 0.5) * 2, int(cell_h * 1.05) * 2 + 1)]
    for size in sizes:
        try:
            font = ImageFont.truetype(io.BytesIO(ttf), max(8, int(round(size * ss))))
        except Exception as e:
            raise Unsupported(f"nie umiem otworzyc fontu zrodlowego: {e}")
        fields = {c: _fields(font, c, cells[c].shape[1], cell_h, ss, pad) for c in letters}
        for oy in range(int(cell_h * 0.45), cell_h + 1):
            top = 2 * cell_h - oy
            for model in (0, 1):                      # 0 = SDF, 1 = krycie
                err, fits = 0.0, []
                for c in letters:
                    a = cells[c]
                    w = a.shape[1]
                    m = a > 0
                    if m.sum() < 8:
                        continue
                    e_best = None
                    for ox in range(-2, 4):
                        src = fields[c][model][top:top + cell_h, pad - ox:pad - ox + w]
                        if model == 0:
                            x = src[m]
                            if x.std() < 1e-3:
                                continue
                            k, b = np.polyfit(x, a[m], 1)
                            e = float(((k * x + b - a[m]) ** 2).mean())
                        else:
                            k, b = 255.0, 0.0
                            e = float(((src * 255.0 - a) ** 2).mean())
                        if e_best is None or e < e_best[0]:
                            e_best = (e, k, b, ox)
                    if e_best is None:
                        err = float("inf")
                        break
                    err += e_best[0]
                    fits.append(e_best)
                if not fits or not math.isfinite(err):
                    continue
                err /= len(fits)
                if best is None or err < best["mse"]:
                    best = {"mse": err, "size": size, "baseline": oy, "model": model,
                            "slope": float(np.median([f[1] for f in fits])),
                            "edge": float(np.median([f[2] for f in fits])),
                            "ox": int(round(float(np.median([f[3] for f in fits])))),
                            "cell_h": cell_h}
    if best is None:
        raise Unsupported("dopasowanie stylu sie nie udalo")
    best["rms"] = best["mse"] ** 0.5
    if best["model"] == 0 and best["slope"] <= 0:
        raise Unsupported("dopasowanie dalo odwrocone pole odleglosci")
    # najmniejsza niezerowa wartosc atlasu = prog, ponizej ktorego oryginal ma zero
    nz = np.concatenate([a[a > 0].ravel() for a in cells.values()])
    best["floor"] = int(np.percentile(nz, 1)) if best["model"] == 0 else 0
    # szerokosc komorki wzgledem szerokosci znaku w foncie
    font = ImageFont.truetype(io.BytesIO(ttf), int(round(best["size"] * 64)))
    best["w_extra"] = float(np.median([cells[c].shape[1] - font.getlength(c) / 64
                                       for c in letters]))
    if log:
        log(f"dopasowanie: {'SDF' if best['model'] == 0 else 'krycie'}, em {best['size']} px,"
            f" linia bazowa {best['baseline']}, blad {best['rms']:.1f} poziomu")
    return best


def render_cell(ttf: bytes, ch: str, cal: dict) -> np.ndarray:
    ss, pad = 8, 20
    font = ImageFont.truetype(io.BytesIO(ttf), int(round(cal["size"] * ss)))
    w = cell_width(ttf, ch, cal)
    sd, cov = _fields(font, ch, w, cal["cell_h"], ss, pad)
    top = 2 * cal["cell_h"] - cal["baseline"]
    sl = (slice(top, top + cal["cell_h"]), slice(pad - cal["ox"], pad - cal["ox"] + w))
    if cal["model"] == 0:
        val = np.rint(cal["slope"] * sd[sl] + cal["edge"])
        val[val < cal["floor"]] = 0
    else:
        val = np.rint(cov[sl] * 255.0)
    return np.clip(val, 0, 255).astype(np.uint8)


def cell_width(ttf: bytes, ch: str, cal: dict) -> int:
    font = ImageFont.truetype(io.BytesIO(ttf), int(round(cal["size"] * 64)))
    return max(1, int(round(font.getlength(ch) / 64 + cal["w_extra"])))


# ---------------------------------------------------------------------- latanie

def _layout(info: dict, cell_h: int) -> tuple[int, int, list[int]]:
    """(odstep w wierszu, krok wierszy, lista V wierszy) odczytane z ukladu atlasu."""
    rows: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for u, v, w, h, t, _ in info["chars"]:
        if w > 0 and h == cell_h:
            rows.setdefault((t, v), []).append((u, w))
    gaps, vs = Counter(), set()
    for (t, v), cells in rows.items():
        vs.add(v)
        cells.sort()
        for (u0, w0), (u1, _w1) in zip(cells, cells[1:]):
            gaps[u1 - u0 - w0] += 1
    gap = max(1, gaps.most_common(1)[0][0]) if gaps else 2
    vlist = sorted(vs)
    steps = Counter(b - a for a, b in zip(vlist, vlist[1:]) if b - a >= cell_h)
    step = steps.most_common(1)[0][0] if steps else cell_h + gap
    return gap, step, vlist


def _find_slots(info: dict, widths: dict[str, int], cell_h: int) -> dict[str, tuple[int, int, int]]:
    gap, step, vlist = _layout(info, cell_h)
    first_v = vlist[0] if vlist else gap
    left = min((c[0] for c in info["chars"] if c[2] > 0), default=gap)
    todo = sorted(widths, key=lambda ch: -widths[ch])
    slots: dict[str, tuple[int, int, int]] = {}
    for t in range(len(info["pages"]) - 1, -1, -1):
        _k, _a, _b, pw, ph = info["pages"][t]
        row_end: dict[int, int] = {}
        v = first_v
        while v + cell_h <= ph:
            row_end[v] = 0
            v += step
        foreign = False
        for u, cv, w, h, ct, _ in info["chars"]:
            if ct != t or w == 0:
                continue
            if cv in row_end:
                row_end[cv] = max(row_end[cv], u + w)
            else:
                foreign = True              # znak poza siatka wierszy - nie ryzykujemy
        if foreign:
            continue
        for v in sorted(row_end):
            x = row_end[v] + gap if row_end[v] else left
            for ch in list(todo):
                if x + widths[ch] <= pw:
                    slots[ch] = (x, v, t)
                    x += widths[ch] + gap
                    todo.remove(ch)
        if not todo:
            break
    if todo:
        raise Unsupported(f"brak miejsca w atlasie na: {''.join(todo)}")
    return slots


def patch(ua: bytes, ue: bytes, ttf: bytes, wanted: str = PL, log=None):
    """Zwraca (nowy .uasset, nowy .uexp, podglad PIL, raport)."""
    info = parse(ua, ue)
    pages = page_arrays(ue, info)
    todo = missing_chars(info, wanted)
    if not todo:
        raise Unsupported("nie ma czego dopisywac")
    cal = calibrate(ttf, info, pages, log)
    if cal["rms"] > MAX_RMS:
        raise Unsupported(f"render fontu zrodlowego nie pasuje do atlasu (blad {cal['rms']:.1f}"
                          f" > {MAX_RMS:.0f}) - to nie ten font albo inna technika atlasu")
    chars = info["chars"]
    if max(ord(ch) for ch in todo) >= 0x10000:
        raise Unsupported("znak poza zakresem tablicy Characters")
    widths = {ch: cell_width(ttf, ch, cal) for ch in todo}
    slots = _find_slots(info, widths, cal["cell_h"])
    voff = chars[ord("a")][5] if chars[ord("a")][2] else 0

    for ch, (u, v, t) in slots.items():
        cell = render_cell(ttf, ch, cal)
        region = pages[t][v:v + cal["cell_h"], u:u + widths[ch]]
        if cal["model"] == 0 and region.max() > cal["edge"] - 12:
            raise Unsupported(f"miejsce wybrane na '{ch}' jest zajete")
        np.maximum(region, cell, out=region)

    count = info["count"]
    new_count = max(count, max(ord(ch) for ch in todo) + 1)
    chars = chars + [[0, 0, 0, 0, 0, 0] for _ in range(new_count - count)]
    for ch, (u, v, t) in slots.items():
        chars[ord(ch)] = [u, v, widths[ch], cal["cell_h"], t, voff]

    table = b"".join(struct.pack(CHAR_FMT, *c) for c in chars)
    co = info["count_off"]
    old_end = co + 4 + CHAR_SIZE * count
    out = bytearray(ue[:co] + struct.pack("<i", new_count) + table + ue[old_end:])
    delta = len(out) - len(ue)
    font_pos, font_size, font_off = info["exports"][info["font"]]
    for (_k, a, b, _w, _h), arr in zip(info["pages"], pages):
        shift = delta if a >= old_end else 0
        out[a + shift:b + shift] = arr.tobytes()

    hdr = bytearray(ua)
    struct.pack_into("<q", hdr, font_pos, font_size + delta)
    for pos, _size, off in info["exports"]:
        if off > font_off:
            struct.pack_into("<q", hdr, pos + 8, off + delta)
    if delta:
        total = len(ua) + len(ue) - 4
        hits = [i for i in range(len(ua) - 8) if struct.unpack_from("<q", ua, i)[0] == total]
        if len(hits) != 1:
            raise Unsupported("nie umiem jednoznacznie poprawic BulkDataStartOffset")
        struct.pack_into("<q", hdr, hits[0], total + delta)

    # podglad: litery wyciete wg tabeli, powiekszone tak, jak zrobi to karta graficzna
    show = [c for c in "Oo" if chars[ord(c)][2]] + sorted(slots, key=wanted.index)
    scale, x = 4, 0
    strip = Image.new("L", (sum(chars[ord(c)][2] * scale + 8 for c in show), cal["cell_h"] * scale), 0)
    thr = cal["edge"] if cal["model"] == 0 else 128
    for c in show:
        u, v, w, h, t, _ = chars[ord(c)]
        im = Image.fromarray(pages[t][v:v + h, u:u + w]).resize((w * scale, h * scale), Image.BILINEAR)
        strip.paste(im.point(lambda p: 255 if p >= thr else 0), (x, 0))
        x += w * scale + 8
    report = {"added": "".join(sorted(slots, key=wanted.index)), "chars_before": count,
              "chars_after": new_count, "model": "SDF" if cal["model"] == 0 else "krycie",
              "em_px": cal["size"], "baseline": cal["baseline"], "rms": round(cal["rms"], 2)}
    return bytes(hdr), bytes(out), strip, report
