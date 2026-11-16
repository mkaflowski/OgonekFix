#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Polskie znaki w fontach gier na Unreal Engine (4 i 5) - szuka, naprawia, pakuje.

    python tools/font_fixer/unreal/fix_unreal_polish_fonts.py
    python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\\SteamLibrary\\steamapps\\common\\Gra"
    python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\\...\\Gra" --auto [--install]

Co robi:
  1. pyta o katalog gry, znajduje Content/Paks, czyta wersje silnika z exe
     i wersje formatu z samych pakow (to ona decyduje o budowie moda),
  2. listuje wszystkie paki (repak) i wyciaga z nich fonty gry: *.ufont oraz luzne
     *.ttf / *.otf / *.ttc; fonty silnika z Engine/ pomija (--include-engine),
  3. rozpoznaje FORME pliku .ufont (patrz nizej) i sprawdza polskie znaki,
  4. dorabia brakujace litery w kroju tego samego fontu - ta sama technika
     i te same domyslne ustawienia co tools/font_fixer/unity/fix_tmp_polish_fonts.py
     (silnik: tools/font_fixer/fix_polish_fonts.py),
  5. renderuje podglad PNG kazdego naprawionego fontu,
  6. buduje mod <NAZWA>_P.pak z samymi fontami i (na zyczenie) kopiuje go do gry.

Formy pliku .ufont:
  * "surowy"     - zwykly TTF/OTF pod inna nazwa (zmiana rozszerzenia wystarcza),
  * "z naglowkiem" - [uint32 LE = dlugosc fontu - 4][TTF/OTF]; po samej zmianie
                   rozszerzenia NIE otwiera sie w edytorze fontow. Skrypt zdejmuje
                   naglowek, naprawia font i zaklada naglowek z powrotem
                   z przeliczona dlugoscia.

Fonty OFFLINE (atlas liter zaszyty w .uasset - TextRender, czesc HUD) tez sa
wykrywane i naprawiane: offline_font.py dorysowuje brakujace litery w wolnym
miejscu atlasu, w stylu dopasowanym do istniejacych liter, i powstaje osobny mod
<NAZWA>_OFFLINE_P (IoStore: .utoc/.ucas/.pak przez retoc, klasycznie: .pak).

Czego nie robi: fontow zaszytych w samym .uasset jako FontFace "Inline" (tylko
wypisywane) oraz fontow offline o budowie innej niz PF_G8 + Characters
indeksowane kodem znaku (odmowa z podanym powodem).

Tryb --auto: zadnych pytan, wszedzie odpowiedz spod Entera (EKSPORT paka do
katalogu wyjsciowego, gra nietknieta; --install dodatkowo kopiuje pak do gry).
Kody wyjscia: 0 = naprawione, 1 = czesc fontow sie nie udala, 2 = nie bylo czego
naprawiac / nie znaleziono fontow.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parents[2]
MODDING_DIR = Path(os.environ.get("UNREAL_MODDING_DIR", r"E:\Programy\UnrealEngineModding"))

sys.path.insert(0, str(SCRIPT_DIR.parent))
import ff_config  # noqa: E402  (sciezki: tools/font_fixer/config.json)
try:
    import fix_polish_fonts as composer  # noqa: E402
except Exception as _e:  # brak fontTools itp.
    print(f"! nie udalo sie zaimportowac tools/font_fixer/fix_polish_fonts.py ({_e})")
    print("  pip install fonttools skia-pathops")
    sys.exit(1)

GREEN, YELLOW, RED, CYAN, GREY, RESET = (
    "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[90m", "\033[0m")

PL_CHARS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
SFNT_MAGICS = (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf")
FONT_EXTS = (".ufont", ".ttf", ".otf", ".ttc")
DEFAULT_MOD_NAME = "FONTY_PL"
PREVIEW_TEXT = ("Zażółć gęślą jaźń", "ZAŻÓŁĆ GĘŚLĄ JAŹŃ", "ąćęłńóśźż ĄĆĘŁŃÓŚŹŻ 0123")

AUTO = False
ASK = "\033[96m"       # blekitny: kazdy tekst, na ktory trzeba odpowiedziec
BOLD = "\033[1m"
_OUT_ROOT: Path | None = None    # katalog roboczy biezacego przebiegu (do sprzatania)
WORK_DIRS = ("oryginalne", "assety_fontow", "_kontrola_kontener", "_kontrola_legacy")


def q(prompt: str) -> str:
    """Pytanie do uzytkownika na blekitno (wciecie i puste linie zostaja bez koloru)."""
    body = prompt.lstrip("\n ")
    return f"{prompt[:len(prompt) - len(body)]}{ASK}{body.rstrip(' ')}{RESET} "


def ask(prompt: str, default: str = "") -> str:
    """Kazde pytanie skryptu idzie tedy - w --auto zwraca odpowiedz spod Entera."""
    if AUTO:
        print(f"{q(prompt)}{default}  {GREY}(automat){RESET}")
        return default
    try:
        return input(q(prompt)).strip()
    except EOFError:
        return default


def offer_cleanup(out_root: Path, names: tuple[str, ...]) -> None:
    """Pyta, czy skasowac pliki robocze. Zostaja gotowe mody, podglady i raporty."""
    work = [out_root / n for n in names if (out_root / n).is_dir()]
    if not work:
        return
    size = sum(f.stat().st_size for d in work for f in d.rglob("*") if f.is_file())
    print(f"\nPliki robocze w {out_root}:")
    for d in work:
        print(f"    {d.name}/")
    print(f"  razem {size / 1048576:.1f} MB; gotowe mody, podglady i raporty zostaja.")
    if not ask_yes_no("Skasowac pliki robocze?", True):
        print("  Zostawione.")
        return
    left = []
    for d in work:
        shutil.rmtree(d, ignore_errors=True)
        if d.exists():
            left.append(d.name)
    print(f"  {YELLOW}Nie udalo sie usunac: {', '.join(left)}{RESET}" if left else "  Skasowane.")


def ask_yes_no(question: str, default: bool) -> bool:
    hint = "[T/n]" if default else "[t/N]"
    ans = ask(f"{question} {hint}: ", "t" if default else "n").lower()
    if not ans:
        return default
    return ans in ("t", "tak", "y", "yes")


def _enable_ansi() -> None:
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


# ----------------------------------------------------------------- narzedzia

def find_tool(name: str, *candidates: Path) -> Path | None:
    for c in candidates:
        if c.is_file():
            return c
    found = shutil.which(name)
    return Path(found) if found else None


# kolejnosc: config.json -> PATH -> stare domyslne polozenia
REPAK = ff_config.tool("repak") or find_tool(
    "repak", MODDING_DIR / "repak" / "repak.exe", SCRIPT_DIR / "repak.exe")
RETOC = ff_config.tool("retoc") or find_tool(
    "retoc", MODDING_DIR / "retoc.exe", SCRIPT_DIR / "retoc.exe")


def run_repak(args: list[str], aes: str | None, binary: bool = False):
    cmd = [str(REPAK)]
    if aes:
        cmd += ["-a", aes]
    cmd += args
    p = subprocess.run(cmd, capture_output=True)
    if binary:
        return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


# -------------------------------------------------------------- rozpoznanie gry

def clean_path(raw: str) -> str:
    return raw.strip().strip('"').strip("'").lstrip("\ufeff")


def find_paks_dirs(game_dir: Path) -> list[Path]:
    dirs: dict[Path, int] = {}
    for root, _dirs, files in os.walk(game_dir):
        n = sum(1 for f in files if f.lower().endswith(".pak"))
        if n:
            dirs[Path(root)] = n
    # glowny katalog to <Projekt>/Content/Paks; podkatalogi (~mods, LogicMods) tez bierzemy
    return sorted(dirs, key=lambda d: (len(d.parts), str(d).lower()))


def project_name(paks_dir: Path) -> str:
    parts = paks_dir.parts
    for i in range(len(parts) - 1, 1, -1):
        if parts[i].lower() == "paks" and parts[i - 1].lower() == "content":
            return parts[i - 2]
    return paks_dir.parent.name


def exe_engine_version(game_dir: Path) -> str | None:
    """Wersja silnika z VS_FIXEDFILEINFO pliku *-Shipping.exe (np. 5.5.4)."""
    exes = sorted(game_dir.rglob("*-Shipping.exe"), key=lambda p: -p.stat().st_size)
    if not exes:
        exes = sorted((p for p in game_dir.rglob("*.exe")
                       if "Binaries" in p.parts), key=lambda p: -p.stat().st_size)
    for exe in exes[:2]:
        try:
            size = exe.stat().st_size
            with open(exe, "rb") as fh:
                # zasoby (.rsrc) leza pod koniec pliku - czytamy ogon
                fh.seek(max(0, size - 64 * 1024 * 1024))
                data = fh.read()
            i = data.rfind(b"\xbd\x04\xef\xfe")
            while i >= 0:
                ms, ls = struct.unpack_from("<II", data, i + 8)
                major, minor, patch = ms >> 16, ms & 0xFFFF, ls >> 16
                if major in (4, 5) and minor < 60:
                    return f"{major}.{minor}.{patch}"
                i = data.rfind(b"\xbd\x04\xef\xfe", 0, i)
        except OSError:
            continue
    return None


def pak_info(pak: Path, aes: str | None) -> dict:
    rc, out, err = run_repak(["info", str(pak)], aes)
    info = {"ok": rc == 0, "err": err.strip()}
    for line in out.splitlines():
        m = re.fullmatch(r"\s*(\d+) file entries\s*", line)
        if m:
            info["entries"] = m.group(1)
        elif ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    return info


# ------------------------------------------------------------- formy .ufont

class FontBlob:
    """Font wyjety z opakowania .ufont: payload = czysty sfnt.

    Forma "z naglowkiem" (zmierzona na 59 plikach z 4 gier, bez wyjatku):
        [uint32 LE = dlugosc_fontu - 4][caly font]
    Licznik jest o 4 MNIEJSZY niz font, a tabele fontu siegaja do samego konca
    pliku (Samson: glyf konczy sie na ostatnim bajcie) - dlatego payload to cala
    reszta pliku, a nie "tyle bajtow, ile mowi licznik".
    """

    def __init__(self, data: bytes):
        self.form = "nieznana"
        self.payload = b""
        if data[:4] in SFNT_MAGICS:
            self.form = "surowy"
            self.payload = data
        elif len(data) > 16 and data[4:8] in SFNT_MAGICS:
            n = struct.unpack_from("<I", data, 0)[0]
            if n <= len(data) - 4:
                self.form = "z naglowkiem"
                self.payload = data[4:]
        elif data[:4] in (b"wOFF", b"wOF2"):
            self.form = "WOFF"

    @property
    def readable(self) -> bool:
        return bool(self.payload)

    def wrap(self, new_payload: bytes) -> bytes:
        if self.form != "z naglowkiem":
            return new_payload
        # Wyrownanie do 4 i 4 bajty zer na koncu: gdyby silnik czytal dokladnie
        # "licznik" bajtow, dostanie caly font; gdy czyta reszte pliku - zera
        # za ostatnia tabela sa obojetne. Licznik zostaje = reszta - 4, jak w grze.
        body = new_payload + b"\x00" * (-len(new_payload) % 4) + b"\x00" * 4
        return struct.pack("<I", len(body) - 4) + body


open_faces = composer.open_faces


def cjk_count(cmap: dict) -> int:
    return sum(1 for cp in cmap
               if 0x3040 <= cp <= 0x30FF or 0x4E00 <= cp <= 0x9FFF or 0xAC00 <= cp <= 0xD7AF)


def inspect_font(payload: bytes) -> dict:
    """Braki polskich znakow (suma po krojach kolekcji) + cechy do odsiewania."""
    _coll, fonts = open_faces(payload)
    missing: list[str] = []
    cjk = 0
    latin = 0
    for f in fonts:
        cmap = f.getBestCmap() or {}
        cjk = max(cjk, cjk_count(cmap))
        latin = max(latin, sum(1 for ch in "abcdefghijklmnopqrstuvwxyz" if ord(ch) in cmap))
        for ch in composer.missing_characters(f, list(PL_CHARS)):
            if ch not in missing:
                missing.append(ch)
    family = ""
    try:
        family = fonts[0]["name"].getDebugName(4) or fonts[0]["name"].getDebugName(1) or ""
    except Exception:
        pass
    for f in fonts:
        f.close()
    return {"missing": missing, "cjk": cjk, "latin": latin, "family": family,
            "faces": len(fonts)}


def fix_payload(payload: bytes, marks_only: bool) -> tuple[bytes, dict]:
    """Naprawa czystego TTF/OTF/TTC - wspolny silnik z narzedziem Unity."""
    new_bytes, report = composer.fix_font_bytes(payload, add_accents=True,
                                                full_set=not marks_only)
    report.pop("_recycled", None)
    return new_bytes, report


def render_preview(payload: bytes, out_png: Path, title: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
        size = 44
        font = ImageFont.truetype(io.BytesIO(payload), size)
        small = ImageFont.load_default()
        w, h = 1100, 40 + len(PREVIEW_TEXT) * (size + 26)
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)
        d.text((12, 8), title, fill=(120, 120, 120), font=small)
        y = 34
        for line in PREVIEW_TEXT:
            d.text((14, y), line, fill="black", font=font)
            y += size + 26
        out_png.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_png)
        return True
    except Exception as e:
        print(f"    {GREY}(podglad sie nie udal: {e}){RESET}")
        return False


# ------------------------------------------------------------------ skan gry

def scan_paks(paks: list[Path], aes: str | None, skip_names: set[str],
              include_engine: bool = False):
    """Zwraca (fonty {sciezka w grze: pak}, infos {pak: info}, nieczytelne paki)."""
    fonts: dict[str, Path] = {}
    infos: dict[Path, dict] = {}
    broken: list[tuple[Path, str]] = []
    # najpierw paki bazowe, potem patche _P - pozniejszy wygrywa (tak jak w grze)
    ordered = sorted(paks, key=lambda p: (p.stem.lower().endswith("_p"), p.name.lower()))
    for pak in ordered:
        if pak.name.lower() in skip_names:
            print(f"  {GREY}- {pak.name}: nasz wczesniejszy mod z fontami, pomijam{RESET}")
            continue
        info = pak_info(pak, aes)
        infos[pak] = info
        if not info["ok"]:
            broken.append((pak, info["err"]))
            continue
        rc, out, err = run_repak(["list", str(pak)], aes)
        if rc != 0:
            broken.append((pak, err.strip()))
            continue
        n = n_engine = 0
        for line in out.splitlines():
            path = line.strip().replace("\\", "/")
            if path.lower().endswith(FONT_EXTS):
                # Engine/ to fonty silnika (Roboto, DroidSans, fallbacki Slate) -
                # gra renderuje tekst wlasnymi, z katalogu projektu
                if path.lower().startswith("engine/") and not include_engine:
                    n_engine += 1
                    continue
                fonts[path] = pak
                n += 1
        print(f"  - {pak.name}: {info.get('version', '?')}, "
              f"plikow {info.get('entries', '?')}, "
              f"fontow {n}"
              + (f" {GREY}(+{n_engine} z Engine/ - pominiete){RESET}" if n_engine else ""))
    return fonts, infos, broken


def _is_offline_font(uasset: bytes, path: str) -> bool:
    # Font "offline": klasa Font + WLASNE strony atlasu <NazwaAssetu>_PageA.. jako
    # Texture2D (material, ktory tylko wskazuje na cudzy atlas, to nie font)
    stem = path.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return (stem + "_PageA").encode("ascii", "ignore") in uasset and b"Texture2D" in uasset


def offline_font_assets(paks_dirs: list[Path], paks: list[Path], aes: str | None,
                        engine: str | None, work_dir: Path) -> dict[str, Path]:
    """Fonty OFFLINE: gotowy atlas bitmapowy/SDF zaszyty w .uasset (TextRender, HUD).

    Nie maja pliku .ufont i maja staly zestaw znakow (czesto same Latin-1), wiec
    brak ogonkow w grze przy "wszystkie .ufont OK" to prawie zawsze one.
    Zwraca {sciezka w grze: plik .uasset w formacie legacy w work_dir} (.uexp obok).
    """
    found: dict[str, Path] = {}
    if work_dir.exists():
        shutil.rmtree(work_dir)
    # klasyczne paki: .uasset lezy w paku wprost
    for pak in paks:
        rc, out, _ = run_repak(["list", str(pak)], aes)
        if rc != 0:
            continue
        names = {line.strip().replace("\\", "/") for line in out.splitlines()}
        for path in sorted(names):
            low = path.lower()
            if low.endswith(".uasset") and "font" in low and not low.startswith("engine/"):
                rc2, data, _ = run_repak(["get", str(pak), path], aes, binary=True)
                if rc2 != 0 or not _is_offline_font(data, path):
                    continue
                uexp = path[:-len(".uasset")] + ".uexp"
                rc3, data2, _ = run_repak(["get", str(pak), uexp], aes, binary=True)
                if rc3 != 0:
                    continue
                write_atomic(work_dir / path, data)
                write_atomic(work_dir / uexp, data2)
                found[path] = work_dir / path
    # IoStore: assety trzeba przekonwertowac do legacy, zeby zobaczyc tabele nazw
    utocs = [d for d in paks_dirs if list(d.glob("*.utoc"))]
    if utocs and RETOC is not None and engine:
        for d in utocs:
            for flt in ("Font", "font"):
                cmd = [str(RETOC)] + (["-a", aes] if aes else []) + [
                    "to-legacy", "--version", ue_tag(engine), "--no-shaders",
                    "--no-script-objects", "-f", flt, str(d), str(work_dir)]
                subprocess.run(cmd, capture_output=True)
        for ua in work_dir.rglob("*.uasset"):
            rel = ua.relative_to(work_dir).as_posix()
            if rel.lower().startswith("engine/") or rel in found:
                continue
            try:
                if _is_offline_font(ua.read_bytes(), rel) and ua.with_suffix(".uexp").is_file():
                    found[rel] = ua
            except OSError:
                pass
    return dict(sorted(found.items()))


def ue_tag(engine: str) -> str:
    major, minor = engine.split(".")[:2]
    return f"UE{major}_{minor}"


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.lower(), b.lower()):
        if x != y:
            break
        n += 1
    return n


def fix_offline_fonts(offline: dict[str, Path], entries: list[dict], args, *, iostore: bool,
                      engine: str | None, aes: str | None, main_paks: Path, out_root: Path,
                      pak_version: str, sigs: list[Path]) -> tuple[int, int]:
    """Dopisuje polskie litery do fontow offline i buduje z nich osobny mod.

    Zwraca (naprawione, nieudane). Gra z IoStore dostaje trojke .utoc/.ucas/.pak
    (asset jest pakietem, wiec musi isc przez retoc), klasyczna - sam .pak.
    """
    try:
        import offline_font as of
    except Exception as e:
        print(f"  {YELLOW}naprawa fontow offline niedostepna:{RESET} {e}"
              " (pip install numpy scipy pillow)")
        return 0, len(offline)

    mod = f"{args.name}_OFFLINE_P"
    staged = out_root / mod
    if staged.exists():
        shutil.rmtree(staged)
    # zrodla kroju: wszystkie lacinskie fonty gry, najpierw te o podobnej nazwie
    sources = [e for e in entries if e.get("blob") is not None and e["blob"].readable
               and e["status"] in ("ok", "do naprawy")]
    fixed = failed = 0
    reports = []
    for rel, ua_path in offline.items():
        name = rel.rsplit("/", 1)[-1]
        print(f"{BOLD}{name}{RESET}  (font offline)")
        try:
            ua, ue = ua_path.read_bytes(), ua_path.with_suffix(".uexp").read_bytes()
            info = of.parse(ua, ue)
            missing = of.missing_chars(info)
        except of.Unsupported as e:
            print(f"    {YELLOW}pomijam:{RESET} {e}")
            failed += 1
            continue
        if not missing:
            print(f"    {GREEN}polskie OK{RESET} ({info['count']} pozycji w Characters)")
            continue
        print(f"    brak: {missing}   (Characters: {info['count']} pozycji,"
              f" stron atlasu: {len(info['pages'])})")
        stem = name.rsplit(".", 1)[0]
        cands = sorted(sources, key=lambda e: -_common_prefix(
            stem, e["path"].rsplit("/", 1)[-1]))
        cands = [e for e in cands if _common_prefix(stem, e["path"].rsplit("/", 1)[-1]) >= 4] \
            or cands
        if args.offline_ttf:
            cands = [{"path": args.offline_ttf, "missing": [],
                      "blob": FontBlob(Path(args.offline_ttf).read_bytes())}]
        result, why = None, "brak fontu zrodlowego w grze (podaj --offline-ttf <plik>)"
        for e in cands[:6]:
            ttf = e["blob"].payload
            try:
                if e["missing"]:           # zrodlo samo nie ma polskich liter - najpierw dorob
                    ttf, _rep = fix_payload(ttf, False)
                src = e["path"].rsplit("/", 1)[-1]
                result = of.patch(ua, ue, ttf, log=lambda m, src=src: print(f"    {src}: {m}"))
                break
            except of.Unsupported as ex:
                why = str(ex)
                print(f"    {GREY}{e['path'].rsplit('/', 1)[-1]}: {ex}{RESET}")
            except Exception as ex:
                why = f"blad: {ex}"
        if result is None:
            print(f"    {RED}nie naprawiony:{RESET} {why}")
            failed += 1
            continue
        new_ua, new_ue, preview, report = result
        write_atomic(staged / rel, new_ua)
        write_atomic((staged / rel).with_suffix(".uexp"), new_ue)
        png = out_root / "podglad" / (stem + "_offline.png")
        png.parent.mkdir(parents=True, exist_ok=True)
        preview.save(png)
        print(f"    dopisane: {report['added']}   (Characters {report['chars_before']} ->"
              f" {report['chars_after']})")
        reports.append({"path": rel, **report})
        fixed += 1
    if not fixed:
        return 0, failed

    made: list[Path] = []
    if iostore:
        utoc = out_root / f"{mod}.utoc"
        for old in out_root.glob(f"{mod}.*"):
            if old.is_file():
                old.unlink()
        cmd = [str(RETOC)] + (["-a", aes] if aes else []) + [
            "to-zen", "--version", ue_tag(engine), str(staged), str(utoc)]
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode != 0 or not utoc.is_file():
            print(f"  {RED}retoc to-zen nie powiodl sie:{RESET}"
                  f" {p.stderr.decode('utf-8', 'replace')[-400:]}")
            return 0, failed + fixed
        made = sorted(q for q in out_root.glob(f"{mod}.*") if q.is_file())
        # kontrola: mod -> legacy -> porownanie bajt w bajt z tym, co spakowalismy
        box, back = out_root / "_kontrola_kontener", out_root / "_kontrola_legacy"
        for d in (box, back):
            if d.exists():
                shutil.rmtree(d)
        box.mkdir(parents=True)
        for q in made:
            shutil.copy2(q, box / q.name)
        for g in ("global.utoc", "global.ucas"):
            if (main_paks / g).is_file():
                shutil.copy2(main_paks / g, box / g)
        subprocess.run([str(RETOC), "to-legacy", "--version", ue_tag(engine), "--no-shaders",
                        "--no-script-objects", str(box), str(back)], capture_output=True)
        same = all((back / r["path"]).is_file()
                   and (back / r["path"]).read_bytes() == (staged / r["path"]).read_bytes()
                   and (back / r["path"]).with_suffix(".uexp").read_bytes()
                   == (staged / r["path"]).with_suffix(".uexp").read_bytes() for r in reports)
        shutil.rmtree(box, ignore_errors=True)
        shutil.rmtree(back, ignore_errors=True)
        if not same:
            print(f"  {RED}Kontrola zwrotna kontenera nie przeszla - nie instaluj tego moda.{RESET}")
            return 0, failed + fixed
        print(f"  kontener {mod}.utoc/.ucas/.pak zbudowany, kontrola zwrotna: zgodny bajt w bajt")
    else:
        out_pak = out_root / f"{mod}.pak"
        rc, out, err = run_repak(["pack", "--version", pak_version, "--mount-point", "../../../",
                                  str(staged), str(out_pak)], None)
        if rc != 0 or not out_pak.is_file():
            print(f"  {RED}repak pack nie powiodl sie:{RESET} {err.strip() or out.strip()}")
            return 0, failed + fixed
        made = [out_pak]
        print(f"  pak {out_pak.name} zbudowany")
    if sigs and not args.no_sig:
        donor = min(sigs, key=lambda q: (q.stem.lower().endswith("_p"), q.stat().st_size))
        sig = out_root / f"{mod}.sig"
        shutil.copyfile(donor, sig)
        made.append(sig)
    (out_root / "raport_offline.json").write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Podglady: {out_root / 'podglad'}  (*_offline.png)")
    names = ", ".join(q.name for q in made)
    if args.install or (not AUTO and ask_yes_no(
            f"  Skopiowac mod fontow offline ({names}) do gry?", False)):
        for q in made:
            write_atomic(main_paks / q.name, q.read_bytes())
        print(f"  {GREEN}Zainstalowano w:{RESET} {main_paks}")
    else:
        print(f"  Instalacja: skopiuj {names}\n    z {out_root}\n    do {main_paks}")
    return fixed, failed


def inline_font_assets(paks_dirs: list[Path], aes: str | None, external: set[str]) -> list[str]:
    """Assety o nazwie wskazujacej na font, ktore NIE maja pliku .ufont obok.

    Tylko IoStore (retoc list) - podpowiedz, ze font moze byc zaszyty w .uasset.
    """
    if RETOC is None:
        return []
    known = {p.rsplit(".", 1)[0].lower() for p in external}
    hits: list[str] = []
    for d in paks_dirs:
        for utoc in sorted(d.glob("*.utoc")):
            if utoc.stem.lower() == "global":
                continue
            cmd = [str(RETOC)] + (["-a", aes] if aes else []) + ["list", "--path", str(utoc)]
            p = subprocess.run(cmd, capture_output=True)
            for line in p.stdout.decode("utf-8", "replace").splitlines():
                m = re.search(r"\.\./\.\./\.\./(\S.*\.uasset)\s*$", line)
                if not m:
                    continue
                path = m.group(1)
                low = path.lower()
                if low.startswith("engine/"):
                    continue
                if "/fonts/" not in low and "/font/" not in low and "/faces/" not in low:
                    continue
                stem = low[:-len(".uasset")]
                if stem in known or stem.endswith(("_font", "_fonttextrender")):
                    continue
                if any(k in low for k in ("material", "distancefield", "minifont", "_mat", "mi_", "m_")):
                    continue
                hits.append(path)
    return sorted(set(hits))


# --------------------------------------------------------------------- zapis

def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    for attempt in range(40):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 0:
                print(f"    plik zajety, ponawiam: {path.name}")
            time.sleep(1)
    path.write_bytes(data)   # awaryjnie w miejscu
    try:
        tmp.unlink()
    except OSError:
        pass


def parse_selection(raw: str, count: int) -> list[int] | None:
    picked: list[int] = []
    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if not m:
            return None
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if not (1 <= a <= b <= count):
            return None
        picked.extend(range(a - 1, b))
    return sorted(set(picked))


# ---------------------------------------------------------------------- main

def main() -> int:
    """Przebieg + pytanie o sprzatanie na koncu (takze po bledzie i przy --list)."""
    rc = _run()
    if _OUT_ROOT is not None and _OUT_ROOT.is_dir() and "--keep-work" not in sys.argv:
        offer_cleanup(_OUT_ROOT, WORK_DIRS + _STAGED)
    return rc


_STAGED: tuple[str, ...] = ()


def _run() -> int:
    global AUTO, _OUT_ROOT, _STAGED
    ap = argparse.ArgumentParser(description="Polskie znaki w fontach gier Unreal Engine")
    ap.add_argument("game_dir", nargs="?", help="katalog gry")
    ap.add_argument("--auto", action="store_true", help="bez pytan, odpowiedzi spod Entera")
    ap.add_argument("--install", action="store_true", help="skopiuj gotowy pak do Content/Paks gry")
    ap.add_argument("--aes", help="klucz AES (hex/base64), gdy paki sa zaszyfrowane")
    ap.add_argument("--out", help="katalog roboczy/wyjsciowy")
    ap.add_argument("--name", default=DEFAULT_MOD_NAME,
                    help=f"nazwa moda bez _P.pak (domyslnie {DEFAULT_MOD_NAME})")
    ap.add_argument("--marks-only", action="store_true",
                    help="dorabiaj tylko kreske i kropke (bez ogonka i przekreslenia)")
    ap.add_argument("--include-cjk", action="store_true",
                    help="naprawiaj tez fonty CJK (domyslnie pomijane)")
    ap.add_argument("--include-engine", action="store_true",
                    help="bierz tez fonty silnika z Engine/ (domyslnie pomijane)")
    ap.add_argument("--keep-work", action="store_true",
                    help="nie pytaj o skasowanie plikow roboczych, zostaw je")
    ap.add_argument("--no-offline", action="store_true",
                    help="nie naprawiaj fontow offline (atlasy w .uasset)")
    ap.add_argument("--offline-ttf",
                    help="plik TTF/OTF/.ufont jako zrodlo liter dla fontow offline")
    ap.add_argument("--no-sig", action="store_true",
                    help="nie dokladaj kopii .sig, gdy gra ma podpisy pakow")
    ap.add_argument("--list", action="store_true", help="tylko raport, nic nie naprawiaj")
    args = ap.parse_args()
    AUTO = args.auto
    _enable_ansi()

    print("=" * 66)
    print(f"  {GREEN}Unreal Engine - polskie znaki w fontach (.ufont){RESET}")
    print("=" * 66)

    if REPAK is None:
        print(f"{RED}Nie znaleziono repak.exe{RESET} - wpisz sciezke w {ff_config.CONFIG_PATH}"
              ' (klucz "repak") albo dodaj repak do PATH.')
        print("  https://github.com/trumank/repak/releases")
        return 2

    # --- katalog gry
    raw = args.game_dir or ""
    while True:
        if not raw:
            if AUTO:
                print(f"{RED}--auto wymaga podania katalogu gry{RESET}")
                return 2
            raw = input(q("\nKatalog gry (np. E:\\SteamLibrary\\steamapps\\common\\Gra): "))
        game_dir = Path(clean_path(raw))
        if game_dir.is_file():
            game_dir = game_dir.parent
        if game_dir.is_dir():
            break
        print(f"  {RED}Nie ma takiego katalogu:{RESET} {game_dir}")
        if AUTO:
            return 2
        raw = ""

    paks_dirs = find_paks_dirs(game_dir)
    if not paks_dirs:
        print(f"{RED}W tym katalogu nie ma zadnego pliku .pak{RESET} - to na pewno gra na Unrealu?")
        return 2
    main_paks = next((d for d in paks_dirs if d.name.lower() == "paks"), paks_dirs[0])
    project = project_name(main_paks)
    all_paks = sorted(p for d in paks_dirs for p in d.glob("*.pak"))
    iostore = any(list(d.glob("*.utoc")) for d in paks_dirs)
    sigs = [p for d in paks_dirs for p in d.glob("*.sig")
            if p.name.lower() not in (f"{args.name}_p.sig".lower(),
                                      f"{args.name}_offline_p.sig".lower())]
    engine = exe_engine_version(game_dir)

    print(f"\n  Gra:      {game_dir.name}")
    print(f"  Projekt:  {project}")
    print(f"  Silnik:   {'UE ' + engine if engine else 'nie odczytano z exe'}")
    print(f"  Paki:     {main_paks}  ({len(all_paks)} x .pak"
          f"{', IoStore .utoc/.ucas' if iostore else ''})")

    mod_file = f"{args.name}_P.pak"
    skip = {mod_file.lower(), f"{args.name}_offline_p.pak".lower()}

    print("\nCzytam indeksy pakow...")
    aes = args.aes
    fonts, infos, broken = scan_paks(all_paks, aes, skip, args.include_engine)
    if broken and not fonts and not aes and not AUTO:
        print(f"\n{YELLOW}Nie da sie odczytac pakow - sa zaszyfrowane?{RESET}")
        print(f"  {GREY}{broken[0][1][:200]}{RESET}")
        print("  Klucz znajdziesz przez UEAESKeyFinder (opcja 2 = Dump File na *-Shipping.exe).")
        aes = clean_path(input(q("  Klucz AES (0x...; Enter = rezygnuje): "))) or None
        if aes:
            fonts, infos, broken = scan_paks(all_paks, aes, skip, args.include_engine)
    for pak, err in broken:
        print(f"  {YELLOW}! {pak.name}: nieczytelny{RESET} {GREY}{err[:160]}{RESET}")
    if not fonts:
        print(f"\n{YELLOW}W pakach nie ma plikow .ufont/.ttf/.otf.{RESET}")
        inline = inline_font_assets(paks_dirs, aes, set())
        if inline:
            print("  Sa za to assety fontow w IoStore - font jest najpewniej zaszyty w .uasset")
            print("  (FontFace 'Inline') i tego narzedzia nie obsluguje:")
            for p in inline[:20]:
                print(f"    {p}")
        return 2

    # wersja paka dla moda = najczestsza wersja w pakach gry
    versions = [i.get("version") for p, i in infos.items() if i.get("ok") and i.get("version")]
    pak_version = max(set(versions), key=versions.count) if versions else "V8B"

    out_root = Path(args.out) if args.out else (
        (ff_config.path("unreal_output_dir")
         or (MODDING_DIR / "Output" / "Fonts" if MODDING_DIR.is_dir()
             else Path.cwd() / "unreal_fonts_out"))
        / game_dir.name)
    _OUT_ROOT = out_root
    _STAGED = (f"{args.name}_P", f"{args.name}_OFFLINE_P")
    orig_dir = out_root / "oryginalne"
    pack_dir = out_root / f"{args.name}_P"
    prev_dir = out_root / "podglad"

    # --- wyciaganie i analiza
    print(f"\nWyciagam {len(fonts)} fontow -> {orig_dir}")
    entries = []
    for path in sorted(fonts, key=str.lower):
        pak = fonts[path]
        rc, data, err = run_repak(["get", str(pak), path], aes, binary=True)
        e = {"path": path, "pak": pak, "status": "", "missing": [], "blob": None, "info": {}}
        entries.append(e)
        if rc != 0 or not data:
            e["status"] = "blad odczytu"
            e["why"] = err.strip()[:120]
            continue
        write_atomic(orig_dir / path, data)
        blob = FontBlob(data)
        e["blob"] = blob
        if not blob.readable:
            e["status"] = "nieznana forma"
            e["why"] = f"poczatek pliku: {data[:12].hex()}"
            continue
        try:
            e["info"] = inspect_font(blob.payload)
        except Exception as ex:
            e["status"] = "nieczytelny font"
            e["why"] = str(ex)[:120]
            continue
        # rozpakowana kopia do podejrzenia w zwyklym edytorze fontow
        if path.lower().endswith(".ufont"):
            ext = {b"OTTO": ".otf", b"ttcf": ".ttc"}.get(blob.payload[:4], ".ttf")
            write_atomic((orig_dir / path).with_suffix(ext), blob.payload)
        e["missing"] = e["info"]["missing"]
        if not e["missing"]:
            e["status"] = "ok"
        elif e["info"]["latin"] < 20:
            e["status"] = "pominiety"
            e["why"] = "brak liter lacinskich (font ikonowy/symboliczny)"
        elif e["info"]["cjk"] > 500 and not args.include_cjk:
            e["status"] = "pominiety"
            e["why"] = f"font CJK ({e['info']['cjk']} znakow) - w polskiej wersji nieuzywany"
        else:
            e["status"] = "do naprawy"

    print()
    todo = [e for e in entries if e["status"] == "do naprawy"]
    for e in entries:
        st = e["status"]
        form = e["blob"].form if e["blob"] else "-"
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
        elif e.get("why"):
            extra = f"  {GREY}{e['why']}{RESET}"
        print(f" {num} {tag} {form:<13} {e['path']}{extra}")
        if e["pak"].stem.lower().endswith("_p"):
            print(f"      {GREY}(z patcha {e['pak'].name}){RESET}")

    inline = inline_font_assets(paks_dirs, aes, set(fonts)) if iostore else []
    if inline:
        print(f"\n{YELLOW}Assety fontow BEZ pliku .ufont{RESET} (dane moga byc zaszyte w .uasset -"
              " tego narzedzie nie rusza):")
        for p in inline[:20]:
            print(f"    {p}")

    print("\nSzukam fontow offline (atlasy w .uasset)...")
    offline = offline_font_assets(paks_dirs, [p for p in all_paks if infos.get(p, {}).get("ok")],
                                  aes, engine, out_root / "assety_fontow")
    off_fixed = off_failed = 0
    if offline:
        print(f"{YELLOW}Gra ma fonty OFFLINE{RESET} - gotowy atlas znakow zaszyty w .uasset"
              " (TextRender, czesc HUD):")
        for p in offline:
            print(f"    {p}")
        if args.list or args.no_offline:
            print("  (tryb --list / --no-offline: nie sprawdzam ich i nie naprawiam)")
        else:
            off_fixed, off_failed = fix_offline_fonts(
                offline, entries, args, iostore=iostore, engine=engine, aes=aes,
                main_paks=main_paks, out_root=out_root, pak_version=pak_version, sigs=sigs)
    elif iostore and (RETOC is None or not engine):
        print(f"  {GREY}(pominiete: brak retoc.exe albo nieznana wersja silnika){RESET}")
    else:
        print("  brak")

    if args.list:
        return 0 if not todo else 1
    if not todo:
        print(f"\n{GREEN}Pliki fontow (.ufont/.ttf) maja polskie znaki - nic do naprawy.{RESET}")
        if off_failed:
            return 1
        return 0 if off_fixed else 2

    # --- wybor fontow i zakresu
    print(f"\nFontow bez polskich znakow: {len(todo)}")
    raw = ask("Ktore naprawic? (Enter = wszystkie, albo numery np. 1,3-5): ", "")
    if raw:
        sel = parse_selection(raw, len(todo))
        if sel is None:
            print(f"{RED}Nie rozumiem wyboru - biore wszystkie.{RESET}")
        else:
            todo = [todo[i] for i in sel]
    marks_only = args.marks_only
    if not marks_only:
        print(f"\n{ASK}Zakres dorabiania:")
        print("  [1] WSZYSTKIE brakujace litery: kreska i kropka z wlasnych glifow fontu,")
        print("      ogonek i przekreslenie dorysowane geometrycznie  [zalecane]")
        print(f"  [2] tylko kreska i kropka (ć ń ó ś ź ż); ą ę ł zostana bez ogonka{RESET}")
        marks_only = ask("Wybor [1]: ", "1") == "2"

    # --- naprawa
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    fixed, failed = 0, 0
    manifest = []
    print()
    for e in todo:
        name = e["path"].rsplit("/", 1)[-1]
        print(f"{BOLD}{name}{RESET}  ({e['blob'].form})")
        try:
            new_payload, rep = fix_payload(e["blob"].payload, marks_only)
            still = inspect_font(new_payload)["missing"]
        except Exception as ex:
            print(f"    {RED}naprawa nie powiodla sie:{RESET} {ex}")
            failed += 1
            continue
        if rep["composed"]:
            print(f"    akcent wyciety z wlasnych glifow: {' '.join(rep['composed'])}")
        if rep["synthesized"]:
            print(f"    dorysowane z proporcji fontu:     {' '.join(rep['synthesized'])}")
        if rep["plain"]:
            print(f"    {YELLOW}tylko litera bez ogonka:{RESET}          {' '.join(rep['plain'])}")
        if rep["unfixable"] or still:
            bad = sorted(set(rep["unfixable"]) | set(still))
            print(f"    {RED}nadal brak:{RESET} {' '.join(bad)}")
        if len(rep["unfixable"]) >= len(e["missing"]):
            failed += 1
            continue
        out_bytes = e["blob"].wrap(new_payload)
        # kontrola: to, co pojdzie do gry, musi dac sie z powrotem rozpakowac
        back = FontBlob(out_bytes)
        if back.form != e["blob"].form or not back.payload.startswith(new_payload):
            print(f"    {RED}opakowanie .ufont nie przeszlo kontroli - pomijam{RESET}")
            failed += 1
            continue
        write_atomic(pack_dir / e["path"], out_bytes)
        render_preview(new_payload, prev_dir / (name.rsplit(".", 1)[0] + ".png"),
                       f"{e['path']}  |  dorobionych liter: {len(e['missing'])}")
        manifest.append({"path": e["path"], "form": e["blob"].form,
                         "source_pak": e["pak"].name, "missing": "".join(e["missing"]),
                         "report": {k: "".join(v) for k, v in rep.items()},
                         "size_before": len(e["blob"].payload), "size_after": len(new_payload)})
        fixed += 1
        if rep["plain"] or rep["unfixable"] or still:
            failed += 1

    if not fixed:
        print(f"\n{RED}Zaden font nie dal sie naprawic.{RESET}")
        return 1

    # --- pak
    out_pak = out_root / mod_file
    cmd = ["pack", "--version", pak_version, "--mount-point", "../../../",
           str(pack_dir), str(out_pak)]
    print(f"\nBuduje {mod_file} (format {pak_version}, {fixed} fontow)...")
    rc, out, err = run_repak(cmd, None)
    if rc != 0 or not out_pak.is_file():
        print(f"{RED}repak pack nie powiodl sie:{RESET} {err.strip() or out.strip()}")
        return 1
    rc, listing, _ = run_repak(["list", str(out_pak)], None)
    packed = {l.strip().replace("\\", "/") for l in listing.splitlines() if l.strip()}
    want = {m["path"] for m in manifest}
    if packed != want:
        print(f"{RED}Zawartosc paka nie zgadza sie z lista fontow!{RESET}")
        print(f"  brakuje: {sorted(want - packed)}\n  nadmiar: {sorted(packed - want)}")
        return 1
    (out_root / "raport.json").write_text(
        json.dumps({"game": game_dir.name, "project": project, "engine": engine,
                    "pak_version": pak_version, "iostore": iostore, "fonts": manifest},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{GREEN}Gotowe.{RESET}")
    print(f"  Pak:       {out_pak}  ({out_pak.stat().st_size / 1024:.0f} KB)")
    print(f"  Podglady:  {prev_dir}")
    print(f"  Oryginaly: {orig_dir}")

    # Gra z podpisami pakow: mod bez pliku .sig o tej samej nazwie jest odrzucany
    # po cichu. Sprawdzona sztuczka: KOPIA dowolnego .sig gry pod nazwa moda
    # (silnik wymaga, zeby plik byl; skrotow blokow zwykle nie egzekwuje).
    out_sig = None
    if sigs and not args.no_sig:
        # najchetniej podpis paka bazowego; gdy zostaly tylko podpisy modow - dowolny
        donor = min(sigs, key=lambda p: (p.stem.lower().endswith("_p"), p.stat().st_size))
        out_sig = out_pak.with_suffix(".sig")
        shutil.copyfile(donor, out_sig)
        print(f"\n{YELLOW}Gra ma podpisy pakow (.sig).{RESET} Dolozylem {out_sig.name}"
              f" = kopia {donor.name}.")
        print("  Pak i .sig musza lezec razem. Jesli mimo to w grze nie ma ogonkow, gra")
        print("  sprawdza podpisy naprawde - wtedy potrzebny bypass (dsound.dll +")
        print(f"  UniversalSigBypasser.asi w {project}/Binaries/Win64).")
    elif sigs:
        print(f"\n{YELLOW}Gra ma podpisy pakow (.sig){RESET}, a --no-sig wylaczyl kopie podpisu"
              " - mod moze zostac odrzucony.")

    install = args.install or (not AUTO and ask_yes_no(
        f"\nSkopiowac {mod_file} do gry ({main_paks})?", False))
    if install:
        write_atomic(main_paks / mod_file, out_pak.read_bytes())
        print(f"  {GREEN}Zainstalowano:{RESET} {main_paks / mod_file}")
        if out_sig:
            write_atomic(main_paks / out_sig.name, out_sig.read_bytes())
        print("  Usuniecie moda = skasowanie tego pliku" + (" i jego .sig." if out_sig else "."))
    else:
        what = f"{mod_file} i {out_sig.name}" if out_sig else mod_file
        print(f"\n  Instalacja: skopiuj {what} do\n    {main_paks}")
    return 1 if (failed or off_failed) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        sys.exit(130)
