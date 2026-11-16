# -*- coding: utf-8 -*-
"""Sciezki narzedzi fontow - jedno miejsce: config.json obok tego pliku.

    import ff_config
    ff_config.path("repak")          # Path albo None (pusty wpis / brak klucza)
    ff_config.tool("repak")          # jak wyzej, a gdy pliku nie ma - szuka w PATH
    ff_config.report()               # [(klucz, sciezka, czy istnieje)] do diagnostyki

Sciezki wzgledne licza sie od folderu z config.json, wiec caly folder mozna
przeniesc razem z plikiem. FONT_FIXER_CONFIG wskazuje inny plik konfiguracji.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("FONT_FIXER_CONFIG") or HERE / "config.json")

# wartosci, gdy klucza nie ma w pliku (albo pliku nie ma wcale)
DEFAULTS = {
    "unity_tool": "unity/fix_tmp_polish_fonts.py",
    "unreal_tool": "unreal/fix_unreal_polish_fonts.py",
    "repak": "",
    "retoc": "",
    "unreal_output_dir": "",
    "unity_export_dir": "",
    "loose_fonts_out": "",
}
KINDS = {"unity_tool": "plik", "unreal_tool": "plik", "repak": "program", "retoc": "program",
         "unreal_output_dir": "katalog wyjsciowy", "unity_export_dir": "katalog wyjsciowy",
         "loose_fonts_out": "katalog wyjsciowy"}

_cache: dict | None = None
load_error = ""


def load() -> dict:
    global _cache, load_error
    if _cache is None:
        data = dict(DEFAULTS)
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            data.update({k: v for k, v in raw.items() if not k.startswith("_")})
        except FileNotFoundError:
            load_error = f"brak pliku {CONFIG_PATH} - uzywam wartosci domyslnych"
        except (OSError, ValueError) as e:
            load_error = f"nie umiem wczytac {CONFIG_PATH}: {e} - uzywam wartosci domyslnych"
        _cache = data
    return _cache


def path(key: str) -> Path | None:
    value = str(load().get(key) or "").strip()
    if not value:
        return None
    p = Path(os.path.expandvars(os.path.expanduser(value)))
    return p if p.is_absolute() else (CONFIG_PATH.parent / p).resolve()


def tool(key: str, *names: str) -> Path | None:
    """Program z configu; gdy wpis pusty albo plik nie istnieje - szukaj w PATH."""
    p = path(key)
    if p and p.is_file():
        return p
    for name in names or (key,):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def report() -> list[tuple[str, str, str, bool]]:
    """[(klucz, rodzaj, sciezka albo opis, czy jest)] - do wypisania w --check."""
    rows = []
    for key in DEFAULTS:
        kind = KINDS[key]
        if kind == "program":
            p = tool(key)
            rows.append((key, kind, str(p) if p else f"{path(key) or '(pusty wpis)'} - nie ma, w PATH tez nie",
                         p is not None))
        elif kind == "plik":
            p = path(key)
            rows.append((key, kind, str(p), bool(p and p.is_file())))
        else:
            p = path(key)
            rows.append((key, kind, str(p) if p else "(domyslny narzedzia)", True))
    return rows
