#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polskie znaki w fontach gry - jedno wejscie dla wszystkich silnikow.

    napraw_fonty.bat / napraw_fonty.sh          (dwuklik; argumenty ida dalej)
    python tools/font_fixer/fix_game_fonts.py
    python tools/font_fixer/fix_game_fonts.py "E:\\SteamLibrary\\steamapps\\common\\Gra"
    python tools/font_fixer/fix_game_fonts.py "E:\\...\\Gra" --auto [opcje narzedzia silnika]

Pyta o katalog gry, rozpoznaje silnik i odpala wlasciwe narzedzie, przekazujac
mu sciezke oraz wszystkie pozostale argumenty bez zmian:

    Unity   -> tools/font_fixer/unity/fix_tmp_polish_fonts.py   (TMP, Font, bitmapowe)
    Unreal  -> tools/font_fixer/unreal/fix_unreal_polish_fonts.py      (.ufont / .ttf w pakach)

Dodatkowo (luzne pliki fontow .ttf/.otf/.ttc lezace w grze albo w innych folderach,
tool: loose_fonts.py - nie wymaga rozpoznania silnika):

    --files               po narzedziu silnika przeszukaj tez luzne pliki fontow w folderze gry
    --files-only          TYLKO luzne pliki (bez wykrywania silnika)
    --fonts-dir DIR       dodatkowy folder do przeszukania (mozna powtarzac; wlacza --files)
    --files-out DIR       gdzie zapisac poprawione kopie (z --files-only wystarczy --out)

Bez tych flag launcher po narzedziu silnika pyta o luzne pliki ([t/N]).
Flagi --patch / --marks-only / --include-cjk / --list dzialaja tez na pliki.

Narzedzia silnikowe zajmuja sie tylko OPAKOWANIEM fontu (assety Unity, .ufont
i paki Unreala). Sama naprawa kroju TTF/OTF jest wspolna i siedzi obok, w
fix_polish_fonts.py (fix_font / fix_font_bytes).

Kod wyjscia = kod wyjscia odpalonego narzedzia (0 naprawione, 1 czesc sie nie
udala, 2 nie bylo czego naprawiac); 3 = nie rozpoznano silnika.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

REPO_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ff_config  # noqa: E402  (sciezki: config.json obok tego pliku)

_OLD_TOOLS = {
    "unity": Path(__file__).resolve().parent / "unity" / "fix_tmp_polish_fonts.py",
    "unreal": Path(__file__).resolve().parent / "unreal" / "fix_unreal_polish_fonts.py",
}
TOOLS = {"unity": ff_config.path("unity_tool") or _OLD_TOOLS["unity"],
         "unreal": ff_config.path("unreal_tool") or _OLD_TOOLS["unreal"]}
LABELS = {"unity": "Unity", "unreal": "Unreal Engine"}


def check_config() -> int:
    """--check: wypisuje, co jest w config.json i czy to istnieje."""
    print(f"Konfiguracja: {ff_config.CONFIG_PATH}")
    if ff_config.load_error:
        print(f"  ! {ff_config.load_error}")
    bad = 0
    for key, kind, where, ok in ff_config.report():
        print(f"  [{'OK  ' if ok else 'BRAK'}] {key:<18} {kind:<18} {where}")
        bad += not ok
    print("\nBiblioteki Pythona:")
    for mod, need in (("fontTools", "oba silniki"), ("pathops", "oba silniki (skia-pathops)"),
                      ("PIL", "oba silniki (pillow)"), ("scipy", "Unreal: fonty offline"),
                      ("UnityPy", "Unity"),
                      ("TypeTreeGeneratorAPI", "Unity"), ("freetype", "Unity (freetype-py)"),
                      ("numpy", "Unity")):
        try:
            __import__(mod)
            state = "OK  "
        except Exception:
            state, bad = "BRAK", bad + 1
        print(f"  [{state}] {mod:<22} {need}")
    return 0 if not bad else 3

UNITY_MARKERS = ("globalgamemanagers", "data.unity3d", "resources.assets", "mainData")
MAX_DEPTH = 4       # <gra>/<Projekt>/Content/Paks to 3 poziomy


ASK, RESET = "\033[96m", "\033[0m"   # blekitny: tekst, na ktory trzeba odpowiedziec

if os.name == "nt":
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass


def q(prompt: str) -> str:
    """Pytanie do uzytkownika na blekitno (wciecie i puste linie zostaja bez koloru)."""
    body = prompt.lstrip("\n ")
    return f"{prompt[:len(prompt) - len(body)]}{ASK}{body.rstrip(' ')}{RESET} "


def clean_path(raw: str) -> str:
    return raw.strip().strip('"').strip("'").lstrip("\ufeff")


def _walk(root: Path, max_depth: int):
    base = len(root.parts)
    for cur, dirs, files in os.walk(root):
        depth = len(Path(cur).parts) - base
        if depth >= max_depth:
            dirs[:] = []
        yield Path(cur), dirs, files


def detect_engine(game_dir: Path) -> tuple[str | None, str]:
    """Zwraca (silnik, uzasadnienie). Silnik: 'unity' / 'unreal' / None."""
    unity = unreal = None
    for cur, dirs, files in _walk(game_dir, MAX_DEPTH):
        low = {f.lower() for f in files}
        if unity is None:
            if "unityplayer.dll" in low or "unityplayer.so" in low:
                unity = f"{cur.name}/UnityPlayer"
            elif cur.name.endswith("_Data") or cur.name == "Data":
                hit = next((m for m in UNITY_MARKERS if m.lower() in low), None)
                if hit:
                    unity = f"{cur.name}/{hit}"
        if unreal is None:
            if cur.name.lower() == "paks" and any(f.endswith((".pak", ".utoc")) for f in low):
                unreal = f"{cur.parent.parent.name}/Content/Paks"
            elif any(f.endswith("-shipping.exe") for f in low):
                unreal = f"{cur.name}/*-Shipping.exe"
        if unity and unreal:
            break
    if unity and not unreal:
        return "unity", unity
    if unreal and not unity:
        return "unreal", unreal
    if unity and unreal:
        return None, f"znaleziono slady obu silnikow ({unity}; {unreal})"
    return None, "brak *_Data z plikami Unity i brak Content/Paks z plikami .pak"


def pop_flag(argv: list[str], name: str) -> bool:
    found = name in argv
    while name in argv:
        argv.remove(name)
    return found


def pop_values(argv: list[str], name: str) -> list[str]:
    """Wyciaga `--flaga WARTOSC` / `--flaga=WARTOSC` (moze wystapic kilka razy)."""
    values, i = [], 0
    while i < len(argv):
        if argv[i] == name and i + 1 < len(argv):
            values.append(argv[i + 1])
            del argv[i:i + 2]
        elif argv[i].startswith(name + "="):
            values.append(argv[i][len(name) + 1:])
            del argv[i]
        else:
            i += 1
    return [clean_path(v) for v in values]


def combine_codes(engine_rc: int | None, files_rc: int | None) -> int:
    """0 naprawione, 1 cos sie nie udalo, 2 nie bylo czego naprawiac, 3 blad."""
    rcs = [r for r in (engine_rc, files_rc) if r is not None]
    if not rcs:
        return 3
    if 1 in rcs or (3 in rcs and len(rcs) > 1 and 0 in rcs):
        return 1
    for code in (0, 2):
        if code in rcs:
            return code
    return rcs[0]


def run_loose_fonts(game_dir: Path | None, extra_dirs: list[str], argv: list[str],
                    auto: bool, interactive_extras: bool, out: str | None = None) -> int:
    """Luzne pliki fontow (.ttf/.otf/.ttc) w folderze gry i dodatkowych folderach."""
    import loose_fonts
    roots = [game_dir] if game_dir else []
    roots += [Path(d) for d in extra_dirs]
    if interactive_extras and not auto:
        try:
            raw = input(q("\nDodatkowe foldery z fontami (kilka po srednikach, Enter = tylko folder gry): "))
        except EOFError:
            raw = ""
        roots += [Path(clean_path(p)) for p in raw.split(";") if p.strip()]
    bad = [r for r in roots if not r.is_dir()]
    for r in bad:
        print(f"  Pomijam - nie ma takiego folderu: {r}")
    roots = [r for r in roots if r.is_dir()]
    print("\n" + "=" * 66)
    print("  Luzne pliki fontow (.ttf / .otf / .ttc)")
    print("=" * 66)
    return loose_fonts.run(
        roots, auto=auto, patch="--patch" in argv, marks_only="--marks-only" in argv,
        include_cjk="--include-cjk" in argv, list_only="--list" in argv,
        out=Path(out) if out else None,
        label=(game_dir or roots[0] if roots else Path("fonty")).name)


def main() -> int:
    argv = sys.argv[1:]
    ff_config.load()
    if "--check" in argv:
        return check_config()
    engine_arg = None
    for flag in ("--unity", "--unreal"):
        if flag in argv:
            argv.remove(flag)
            engine_arg = flag[2:]
    files_only = pop_flag(argv, "--files-only")
    want_files = pop_flag(argv, "--files") or files_only
    extra_dirs = pop_values(argv, "--fonts-dir")
    want_files = want_files or bool(extra_dirs)
    # --out ma w narzedziach silnikowych inne znaczenie (katalog roboczy Unreala),
    # dlatego do plikow trafia tylko w trybie --files-only albo jako --files-out
    files_out = (pop_values(argv, "--files-out") or [None])[0]
    if files_only and not files_out:
        files_out = (pop_values(argv, "--out") or [None])[0]
    auto = any(a in ("--auto", "-y", "--yes") for a in argv)
    # pierwszy argument bez myslnika, ktory jest istniejaca sciezka = katalog gry
    game_idx = next((i for i, a in enumerate(argv)
                     if not a.startswith("-") and os.path.exists(clean_path(a))), None)
    raw = argv.pop(game_idx) if game_idx is not None else ""

    print("=" * 66)
    print("  Polskie znaki w fontach gry - Unity / Unreal Engine / pliki fontow")
    print("=" * 66)
    # sam --files-only z --fonts-dir nie potrzebuje katalogu gry
    game_dir: Path | None = None
    need_game = not (files_only and extra_dirs)
    while need_game or raw:
        if not raw:
            if auto:
                print("! --auto wymaga podania katalogu gry")
                return 3
            try:
                raw = input(q("\nKatalog gry: "))
            except EOFError:
                return 3
        game_dir = Path(clean_path(raw))
        if game_dir.is_file():
            game_dir = game_dir.parent
        if game_dir.is_dir():
            break
        print(f"  Nie ma takiego katalogu: {game_dir}")
        game_dir, raw = None, ""

    engine_rc: int | None = None
    ask_extras = False
    if not files_only:
        engine, why = (engine_arg, "wymuszone flaga") if engine_arg else detect_engine(game_dir)
        if engine is None:
            print(f"\nNie rozpoznalem silnika: {why}.")
            if auto and not want_files:
                print("  Wymus silnik flaga --unity albo --unreal, albo uzyj --files-only"
                      " (luzne pliki fontow).")
                return 3
            if auto:
                print("  Pomijam narzedzie silnikowe - zostaja luzne pliki fontow.")
            else:
                ans = input(q("  [1] Unity   [2] Unreal   [3] tylko luzne pliki fontow"
                              "   [Enter] rezygnuje: ")).strip()
                engine = {"1": "unity", "2": "unreal"}.get(ans)
                if ans == "3":
                    want_files = ask_extras = True
                elif engine is None:
                    return 3

        if engine:
            tool = TOOLS[engine]
            print(f"\n  Silnik:    {LABELS[engine]}  ({why})")
            print(f"  Narzedzie: {tool}\n")
            if not tool.is_file():
                print(f"! brak pliku {tool}")
                print(f"  Popraw sciezke w {ff_config.CONFIG_PATH} (klucz \"{engine}_tool\").")
                return 3
            export_dir = ff_config.path("unity_export_dir")
            if engine == "unity" and export_dir and not any(
                    a.startswith("--export-dir") or a == "--patch" for a in argv):
                argv += ["--export-dir", str(export_dir)]
            sys.stdout.flush()
            engine_rc = subprocess.run([sys.executable, str(tool), str(game_dir), *argv]).returncode

    if not want_files and not auto and game_dir is not None:
        print()
        try:
            ans = input(q("Przeszukac tez luzne pliki fontow (.ttf/.otf/.ttc) w folderze gry"
                          " i innych folderach? [t/N]: ")).strip().lower()
        except EOFError:
            ans = ""
        want_files = ans in ("t", "tak", "y", "yes")
        ask_extras = want_files
    if not want_files:
        return combine_codes(engine_rc, None)
    sys.stdout.flush()
    files_rc = run_loose_fonts(game_dir, extra_dirs, argv, auto, ask_extras, files_out)
    return combine_codes(engine_rc, files_rc)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        sys.exit(130)
