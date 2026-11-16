#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Luzne pliki fontow (.ttf / .otf / .ttc / .otc) w podanych folderach:
szuka, sprawdza polskie znaki i dorabia brakujace.

    python tools/font_fixer/loose_fonts.py "E:\\Gry\\Gra"
    python tools/font_fixer/loose_fonts.py "E:\\Gry\\Gra" "E:\\inne\\fonty" --auto
    python tools/font_fixer/loose_fonts.py "E:\\Gry\\Gra" --auto --patch
    python tools/font_fixer/loose_fonts.py "E:\\Gry\\Gra" --list

To uzupelnienie narzedzi silnikowych (Unity / Unreal czytaja fonty tylko ze
swoich assetow i pakow): fonty lezace w grze jako zwykle pliki - StreamingAssets,
Godot, silniki wlasne, mody, a takze dowolny folder z fontami - nie wymagaja
rozpoznawania silnika. Sama naprawa kroju jest wspolna (fix_polish_fonts.py).

Tryby zapisu:
    EKSPORT (domyslny) - poprawione kopie ukladaja sie w katalogu wyjsciowym tak
                         samo jak w folderze zrodlowym (mozna je skopiowac na gre),
                         gra nietknieta,
    PATCH (--patch)    - nadpisuje pliki w miejscu; oryginal laduje obok jako
                         <plik>.bak_plfont (tworzony tylko, gdy jeszcze go nie ma).

Tryb --auto: zadnych pytan, wszedzie odpowiedz spod Entera (EKSPORT, wszystkie
fonty do naprawy, dorabiane wszystkie litery).

Kody wyjscia: 0 naprawione, 1 czesc sie nie udala, 2 nie bylo czego naprawiac,
3 blad uzycia (brak folderu / brak fontow).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ff_config  # noqa: E402

FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc")
SFNT_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
PL_CHARS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
# katalogi wyjsciowe naszych narzedzi i smieci - nie skanujemy ich
SKIP_DIRS = {"fixed", "fixed_fonts", "fixed_preview", "font_preview", "unreal_fonts_out",
             "loose_fonts_out", "__pycache__", ".git", "node_modules"}
BACKUP_SUFFIX = ".bak_plfont"

GREEN, YELLOW, RED, CYAN, GREY, RESET = (
    "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[90m", "\033[0m")
AUTO = False


def _enable_ansi() -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def ask(prompt: str, default: str = "") -> str:
    """Kazde pytanie idzie tedy - w --auto zwraca odpowiedz spod Entera."""
    body = prompt.lstrip("\n ")
    shown = f"{prompt[:len(prompt) - len(body)]}{CYAN}{body.rstrip(' ')}{RESET} "
    if AUTO:
        print(f"{shown}{default}  {GREY}(automat){RESET}")
        return default
    try:
        return input(shown).strip()
    except EOFError:
        return default


def ask_yes_no(question: str, default: bool) -> bool:
    hint = "[T/n]" if default else "[t/N]"
    ans = ask(f"{question} {hint}:", "t" if default else "n").lower()
    return default if not ans else ans in ("t", "tak", "y", "yes")


# ------------------------------------------------------------------- skan

def find_font_files(roots: list[Path], skip: list[Path] | None = None) -> list[tuple[Path, Path]]:
    """[(plik, korzen skanu)] - bez katalogow wyjsciowych i bez `skip`."""
    skip_res = [p.resolve() for p in (skip or [])]
    found: dict[Path, Path] = {}
    for root in roots:
        for cur, dirs, files in os.walk(root):
            curp = Path(cur)
            dirs[:] = [d for d in dirs
                       if d.lower() not in SKIP_DIRS
                       and not any((curp / d).resolve() == s for s in skip_res)]
            for name in files:
                if name.lower().endswith(FONT_EXTS):
                    p = curp / name
                    found.setdefault(p.resolve(), root)
    return sorted(found.items(), key=lambda kv: str(kv[0]).lower())


def cjk_count(cmap: dict) -> int:
    return sum(1 for cp in cmap
               if 0x3040 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF or 0xAC00 <= cp <= 0xD7AF)


def inspect(data: bytes, composer) -> dict:
    """Braki polskich znakow (suma po krojach) + cechy do odsiewania."""
    _coll, fonts = composer.open_faces(data)
    missing: list[str] = []
    cjk = latin = 0
    family = ""
    try:
        for f in fonts:
            cmap = f.getBestCmap() or {}
            cjk = max(cjk, cjk_count(cmap))
            latin = max(latin, sum(1 for ch in "abcdefghijklmnopqrstuvwxyz" if ord(ch) in cmap))
            for ch in composer.missing_characters(f, list(PL_CHARS)):
                if ch not in missing:
                    missing.append(ch)
        try:
            family = fonts[0]["name"].getDebugName(4) or fonts[0]["name"].getDebugName(1) or ""
        except Exception:
            pass
    finally:
        for f in fonts:
            f.close()
    return {"missing": missing, "cjk": cjk, "latin": latin, "family": family,
            "faces": len(fonts)}


def analyse(files: list[tuple[Path, Path]], composer, include_cjk: bool) -> list[dict]:
    entries = []
    for path, root in files:
        e = {"path": path, "root": root, "status": "", "why": "", "missing": [],
             "data": None, "info": {}, "sha": ""}
        entries.append(e)
        try:
            data = path.read_bytes()
        except OSError as ex:
            e["status"], e["why"] = "blad odczytu", str(ex)[:100]
            continue
        if data[:4] not in SFNT_MAGICS:
            e["status"], e["why"] = "nieznana forma", f"poczatek pliku: {data[:8].hex()}"
            continue
        try:
            e["info"] = inspect(data, composer)
        except Exception as ex:
            e["status"], e["why"] = "nieczytelny font", str(ex)[:100]
            continue
        e["data"] = data
        e["sha"] = hashlib.sha1(data).hexdigest()
        e["missing"] = e["info"]["missing"]
        if not e["missing"]:
            e["status"] = "ok"
        elif e["info"]["latin"] < 20:
            e["status"], e["why"] = "pominiety", "brak liter lacinskich (font ikonowy/symboliczny)"
        elif e["info"]["cjk"] > 500 and not include_cjk:
            e["status"] = "pominiety"
            e["why"] = f"font CJK ({e['info']['cjk']} znakow) - w polskiej wersji nieuzywany"
        else:
            e["status"] = "do naprawy"
    return entries


def print_report(entries: list[dict]) -> list[dict]:
    todo = [e for e in entries if e["status"] == "do naprawy"]
    for e in entries:
        st = e["status"]
        if st == "ok":
            tag = f"{GREEN}polskie OK{RESET}      "
        elif st == "do naprawy":
            tag = f"{RED}BRAK polskich{RESET}   "
        elif st == "pominiety":
            tag = f"{GREY}pominiety{RESET}       "
        else:
            tag = f"{YELLOW}{st:<16}{RESET}"
        num = f"[{todo.index(e) + 1:>2}]" if e in todo else "    "
        extra = ""
        if st == "do naprawy":
            extra = f"  brak: {''.join(e['missing'])}"
        elif e["why"]:
            extra = f"  {GREY}{e['why']}{RESET}"
        faces = f" (x{e['info']['faces']})" if e["info"].get("faces", 1) > 1 else ""
        print(f" {num} {tag} {e['display']}{faces}{extra}")
    return todo


def parse_selection(text: str, count: int) -> list[int] | None:
    """'' / 'w' -> wszystkie, 'n' -> nic, '1,3-5' -> wskazane; None = zly zapis."""
    text = text.strip().lower()
    if text in ("", "w", "wszystkie", "t", "tak"):
        return list(range(count))
    if text in ("n", "nie", "0"):
        return []
    chosen: set[int] = set()
    try:
        for part in text.replace(" ", "").split(","):
            if "-" in part:
                a, b = part.split("-", 1)
                chosen.update(range(int(a) - 1, int(b)))
            elif part:
                chosen.add(int(part) - 1)
    except ValueError:
        return None
    return sorted(i for i in chosen if 0 <= i < count) if all(0 <= i < count for i in chosen) else None


# ----------------------------------------------------------------- zapis

def write_atomic(path: Path, data: bytes) -> None:
    """Zapis przez .tmp + os.replace; po wyczerpaniu ponowien nadpisanie w miejscu."""
    import time
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    for _ in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(1)
    path.write_bytes(data)          # antywirus/indekser trzyma uchwyt - zwykly zapis przejdzie
    tmp.unlink(missing_ok=True)


def out_path_for(e: dict, out_root: Path, multi_root: bool) -> Path:
    rel = e["path"].relative_to(e["root"].resolve())
    return out_root / (e["root"].name if multi_root else "") / rel


def verify(new_bytes: bytes, composer) -> list[str]:
    """Co dalej nie ma polskich znakow w naprawionym foncie (kazdy kroj kolekcji)."""
    return composer.missing_in_bytes(new_bytes, PL_CHARS)


# ------------------------------------------------------------------- main

def run(roots: list[Path], *, auto: bool = False, patch: bool = False,
        out: Path | None = None, marks_only: bool = False, include_cjk: bool = False,
        list_only: bool = False, label: str = "") -> int:
    """Skanuje foldery i naprawia fonty. Zwraca kod wyjscia (patrz opis modulu)."""
    global AUTO
    AUTO = auto or AUTO
    _enable_ansi()
    try:
        import fix_polish_fonts as composer
    except Exception as ex:
        print(f"{RED}! nie udalo sie zaimportowac fix_polish_fonts.py ({ex}){RESET}")
        print("  pip install fonttools skia-pathops")
        return 3

    roots = [r for r in (Path(x) for x in roots) if r.is_dir()]
    if not roots:
        print(f"{RED}! brak istniejacych folderow do przeszukania{RESET}")
        return 3
    label = label or roots[0].name
    out_root = out or ((ff_config.path("loose_fonts_out") or Path.cwd() / "loose_fonts_out") / label)

    print("Przeszukuje foldery:")
    for r in roots:
        print(f"    {r}")
    files = find_font_files(roots, skip=[out_root])
    if not files:
        print(f"\n{YELLOW}Nie znaleziono plikow {'/'.join(FONT_EXTS)}.{RESET}")
        return 3
    multi = len(roots) > 1
    print(f"\nZnaleziono {len(files)} plikow fontow - sprawdzam polskie znaki...\n")
    entries = analyse(files, composer, include_cjk)
    for e in entries:
        rel = e["path"].relative_to(e["root"].resolve())
        e["display"] = str(Path(e["root"].name) / rel) if multi else str(rel)
    todo = print_report(entries)

    if list_only:
        return 0 if not todo else 1
    if not todo:
        print("\nNic do naprawy.")
        return 2

    # --- co naprawiamy
    if not AUTO:
        while True:
            ans = ask(f"\nKtore naprawic? [Enter = wszystkie {len(todo)}, numery np. 1,3-5, n = zadne]:", "")
            sel = parse_selection(ans, len(todo))
            if sel is not None:
                break
            print("  Nie rozumiem - podaj numery z listy.")
        todo = [todo[i] for i in sel]
        if not todo:
            print("Nic nie wybrano.")
            return 2
    if not marks_only and not AUTO:
        marks_only = not ask_yes_no("Dorabiac wszystkie litery? (n = tylko kreska i kropka: ć ń ó ś ź ż)", True)
    if not AUTO and not patch:
        patch = ask(f"Tryb zapisu: [1] EKSPORT do {out_root} (gra nietknieta)  "
                    f"[2] PATCH w miejscu (kopia {BACKUP_SUFFIX}) [Enter = 1]:", "1") == "2"

    # --- naprawa (identyczne pliki naprawiamy raz)
    cache: dict[str, tuple[bytes, dict] | Exception] = {}
    fixed = failed = 0
    print()
    for e in todo:
        sha = e["sha"]
        if sha not in cache:
            try:
                new_bytes, rep = composer.fix_font_bytes(e["data"], add_accents=True,
                                                         full_set=not marks_only)
                rep.pop("_recycled", None)
                cache[sha] = (new_bytes, rep)
            except Exception as ex:
                cache[sha] = ex
        res = cache[sha]
        if isinstance(res, Exception):
            print(f" {RED}BLAD{RESET}  {e['display']}: {res}")
            failed += 1
            continue
        new_bytes, rep = res
        if len(new_bytes) < len(e["data"]) * 0.5:
            print(f" {RED}BLAD{RESET}  {e['display']}: wynik podejrzanie maly "
                  f"({len(new_bytes)} B z {len(e['data'])} B) - pomijam")
            failed += 1
            continue
        left = verify(new_bytes, composer)
        notes = []
        if rep.get("composed"):
            notes.append(f"z akcentem: {''.join(rep['composed'])}")
        if rep.get("synthesized"):
            notes.append(f"dorysowane: {''.join(rep['synthesized'])}")
        if rep.get("plain"):
            notes.append(f"{YELLOW}bez ogonka: {''.join(rep['plain'])}{RESET}")
        if rep.get("unfixable"):
            notes.append(f"{RED}pominiete (brak litery bazowej): {''.join(rep['unfixable'])}{RESET}")
        try:
            if patch:
                bak = e["path"].with_name(e["path"].name + BACKUP_SUFFIX)
                if not bak.exists():
                    bak.write_bytes(e["data"])
                write_atomic(e["path"], new_bytes)
                dest = e["path"]
            else:
                dest = out_path_for(e, out_root, multi)
                write_atomic(dest, new_bytes)
        except OSError as ex:
            print(f" {RED}BLAD ZAPISU{RESET}  {e['display']}: {ex}")
            failed += 1
            continue
        incomplete = bool(left)
        tag = f"{YELLOW}CZESCIOWO{RESET}" if incomplete else f"{GREEN}OK{RESET}"
        print(f" {tag}  {e['display']}  {GREY}{'; '.join(notes)}{RESET}")
        if incomplete:
            print(f"        {YELLOW}dalej brak w foncie: {''.join(left)}{RESET}")
        fixed += 1
        failed += incomplete

    print()
    if patch:
        print(f"Zapisano w miejscu ({fixed}); oryginaly: <plik>{BACKUP_SUFFIX}.")
    elif fixed:
        print(f"Poprawione kopie ({fixed}): {out_root}")
        print("  Uklad katalogow jak w folderze zrodlowym - skopiuj na miejsce oryginalow.")
    if failed:
        print(f"{YELLOW}Nie wszystko sie udalo ({failed}).{RESET}")
    return 1 if failed else (0 if fixed else 2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Luzne pliki fontow: szukanie, sprawdzanie i naprawa polskich znakow")
    ap.add_argument("folders", nargs="*", help="foldery do przeszukania (rekurencyjnie)")
    ap.add_argument("--auto", action="store_true", help="bez pytan, odpowiedzi spod Entera")
    ap.add_argument("--patch", action="store_true", help=f"nadpisz pliki w miejscu (kopia {BACKUP_SUFFIX})")
    ap.add_argument("--out", help="katalog wyjsciowy trybu EKSPORT")
    ap.add_argument("--marks-only", action="store_true", help="dorabiaj tylko kreske i kropke")
    ap.add_argument("--include-cjk", action="store_true", help="naprawiaj tez fonty CJK")
    ap.add_argument("--list", action="store_true", help="tylko raport, nic nie naprawiaj")
    args = ap.parse_args()

    ff_config.load()
    folders = [f.strip().strip('"').strip("'") for f in args.folders]
    if not folders:
        if args.auto:
            print("! --auto wymaga podania folderu")
            return 3
        while True:
            raw = ask("Foldery z fontami (kilka oddziel srednikiem):", "")
            folders = [p.strip().strip('"').strip("'") for p in raw.split(";") if p.strip()]
            if folders and all(os.path.isdir(p) for p in folders):
                break
            print("  Podaj istniejace foldery.")
    return run([Path(f) for f in folders], auto=args.auto, patch=args.patch,
               out=Path(args.out) if args.out else None, marks_only=args.marks_only,
               include_cjk=args.include_cjk, list_only=args.list)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        sys.exit(130)
