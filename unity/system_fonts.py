# -*- coding: utf-8 -*-
"""
Fonty zainstalowane w systemie - szukanie TTF/OTF o tej samej nazwie co font gry.

Statyczny atlas SDF nie ma pliku TTF, wiec polskie litery trzeba skladac z jego
wlasnych glifow albo brac z obcego fontu. Jesli ten sam font jest zainstalowany
w systemie (np. Arial, Verdana, Liberation Sans) i ma polskie znaki, mozna z niego
wziac PRAWDZIWE glify w kroju oryginalu - patrz fix_tmp_polish_fonts.choose_ttf.

    import system_fonts
    cands = system_fonts.find("Arial Bold SDF", family="Arial", style="Bold")
    for c in cands: c.path, c.index, c.full_name
    data = cands[0].read_bytes()      # pojedynczy krój jako bajty TTF/OTF

Dopasowanie jest scisle (rowne po normalizacji nazwy), nigdy "zawiera": "Arial"
nie ma pasowac do "Arial Black" ani "Arial Narrow".

Folder `moje_fonty/` (obok fix_game_fonts.py, klucz my_fonts_dir w config.json) to
wlasne fonty uzytkownika: sa przeszukiwane PRZED fontami systemowymi, a ich nazwa
pliku tez liczy sie jako nazwa fontu (Inter.ttf pasuje do assetu "Inter SDF").
Pozostale pliki z tego folderu trafiaja do menu wyboru fontu (user_font_refs).
"""

from __future__ import annotations

import io
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")
# slowa doklejane do nazw assetow TMP, ktorych nie ma w nazwie prawdziwego fontu
_ASSET_NOISE = re.compile(
    r"\b(sdf|atlas|fallback|glow|outline|shadow|material|bitmap|dynamic|static|crisp|tmp)\b",
    re.IGNORECASE)
_REGULAR = {"", "regular", "normal", "book", "roman", "medium"}


def norm(text: str) -> str:
    """Male litery, tylko litery i cyfry: 'Liberation Sans' == 'LiberationSans'."""
    return re.sub(r"[^0-9a-z]+", "", (text or "").lower())


def clean_asset_name(name: str) -> str:
    """'LiberationSans SDF - Fallback' -> 'LiberationSans'."""
    return re.sub(r"[\s\-_]+$", "", _ASSET_NOISE.sub(" ", name or ""))


MY_FONTS_DIRNAME = "moje_fonty"


def my_fonts_dir() -> Path:
    """Folder z wlasnymi fontami uzytkownika (config.json: my_fonts_dir)."""
    here = Path(__file__).resolve().parent
    try:
        sys.path.insert(0, str(here.parent))
        import ff_config
        p = ff_config.path("my_fonts_dir")
        if p:
            return p
    except Exception:
        pass
    finally:
        try:
            sys.path.remove(str(here.parent))
        except ValueError:
            pass
    return here.parent / MY_FONTS_DIRNAME


def font_dirs() -> list[Path]:
    dirs: list[Path] = [my_fonts_dir()]
    if sys.platform.startswith("win"):
        win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        dirs.append(Path(win) / "Fonts")
        local = os.environ.get("LOCALAPPDATA")
        if local:
            dirs.append(Path(local) / "Microsoft" / "Windows" / "Fonts")
    elif sys.platform == "darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"),
                 Path.home() / "Library" / "Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
                 Path.home() / ".fonts", Path.home() / ".local" / "share" / "fonts"]
    return [d for d in dirs if d.is_dir()]


@dataclass
class SystemFont:
    path: Path
    index: int            # numer kroju w kolekcji (.ttc), 0 dla zwyklego pliku
    family: str
    style: str
    full_name: str
    ps_name: str
    user: bool = False    # z folderu moje_fonty

    @property
    def keys(self) -> set[str]:
        keys = {norm(self.full_name), norm(self.ps_name), norm(self.family + self.style)}
        if self.user:
            keys.add(norm(self.path.stem))     # wlasny plik: nazwa pliku to nazwa fontu
        if self.style.lower() in _REGULAR:
            keys.add(norm(self.family))
        keys.discard("")
        return keys

    @property
    def label(self) -> str:
        where = f"{MY_FONTS_DIRNAME}/" if self.user else ""
        return f"{self.full_name or self.family} ({where}{self.path.name}" + \
               (f" #{self.index}" if self.index else "") + ")"

    def read_bytes(self) -> bytes:
        """Jeden krój jako samodzielny TTF/OTF (kolekcje .ttc sa rozpakowywane)."""
        from fontTools.ttLib import TTFont
        if self.path.suffix.lower() in (".ttc", ".otc"):
            font = TTFont(str(self.path), fontNumber=self.index, lazy=False)
            buf = io.BytesIO()
            font.save(buf)
            font.close()
            return buf.getvalue()
        return self.path.read_bytes()


def _name(font, *ids: int) -> str:
    table = font["name"]
    for i in ids:
        rec = table.getDebugName(i)
        if rec:
            return rec
    return ""


def _faces_in(path: Path, user: bool = False) -> list[SystemFont]:
    from fontTools.ttLib import TTFont, TTCollection
    out = []
    try:
        if path.suffix.lower() in (".ttc", ".otc"):
            coll = TTCollection(str(path), lazy=True)
            fonts = list(coll.fonts)
        else:
            fonts = [TTFont(str(path), lazy=True)]
    except Exception:
        return out
    for i, f in enumerate(fonts):
        try:
            out.append(SystemFont(path, i, _name(f, 16, 1), _name(f, 17, 2),
                                  _name(f, 4), _name(f, 6), user))
        except Exception:
            pass
        finally:
            try:
                f.close()
            except Exception:
                pass
    return out


_INDEX: list[SystemFont] | None = None


def index(refresh: bool = False) -> list[SystemFont]:
    """Wszystkie kroje z katalogow systemowych (skan raz na proces)."""
    global _INDEX
    if _INDEX is None or refresh:
        found: list[SystemFont] = []
        seen: set[Path] = set()
        mine = my_fonts_dir()
        for root in font_dirs():
            for cur, _dirs, files in os.walk(root):
                for name in files:
                    if name.lower().endswith(FONT_EXTS):
                        p = Path(cur) / name
                        try:
                            rp = p.resolve()
                        except OSError:
                            continue
                        if rp not in seen:
                            seen.add(rp)
                            found += _faces_in(p, user=(root == mine))
        _INDEX = found
    return _INDEX


def find(asset_name: str, family: str = "", style: str = "") -> list[SystemFont]:
    """Kroje systemowe pasujace do fontu gry (lista, najlepsze dopasowanie pierwsze).

    Klucze fontu gry: nazwa assetu bez dopiskow SDF/Atlas/Fallback, rodzina + styl
    z m_FaceInfo oraz sama rodzina, gdy styl to Regular. Pasuje font systemowy,
    ktorego pelna nazwa / nazwa PostScript / rodzina+styl daja ten sam klucz.
    """
    wanted: dict[str, int] = {}
    for rank, key in enumerate((norm(clean_asset_name(asset_name)),
                                norm(family + style),
                                norm(family) if (style or "").lower() in _REGULAR else "")):
        if key and key not in wanted:
            wanted[key] = rank
    if not wanted:
        return []
    hits = []
    for sf in index():
        ranks = [wanted[k] for k in sf.keys if k in wanted]
        if ranks:
            hits.append((min(ranks), sf))
    hits.sort(key=lambda h: (not h[1].user, h[0],
                             h[1].path.suffix.lower() not in (".ttf", ".otf"),
                             str(h[1].path).lower()))
    return [sf for _rank, sf in hits]


def user_font_refs() -> list[dict]:
    """Fonty z folderu moje_fonty jako pozycje menu wyboru fontu (jak fonty z gry)."""
    refs = []
    for sf in index():
        if sf.user:
            try:
                size = sf.path.stat().st_size
            except OSError:
                size = 0
            refs.append({"name": sf.full_name or sf.family or sf.path.stem,
                         "size": size, "path": str(sf.path), "local_sf": sf})
    return refs
