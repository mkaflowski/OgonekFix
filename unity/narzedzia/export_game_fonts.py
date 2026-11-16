#!/usr/bin/env python3
"""
Eksportuje wszystkie pliki fontow (TTF/OTF/TTC) z dowolnej gry Unity.

Skanuje pliki .assets / bundle w poszukiwaniu assetow typu Font z osadzonymi
danymi (m_FontData) i zapisuje je do folderu exported_fonts/ obok skryptu.
Rozszerzenie jest rozpoznawane po naglowku pliku. Nie eksportuje atlasow
TMP (to tekstury, nie fonty) - do tego sluzy fix_tmp_polish_fonts.py.

Nie wymaga typetree/il2cpp - Font to standardowa klasa Unity.

Uzycie:
  python export_game_fonts.py "E:\\Games\\Gra"
  (bez argumentu - zapyta o sciezke)
"""
import os
import sys

import UnityPy

SKIP_SUFFIX = (".resS", ".resource", ".manifest", ".dll", ".json", ".xml",
               ".txt", ".png", ".jpg", ".config", ".info", ".dat", ".pdb",
               ".bak_plfont", ".bak_font", ".bak_pl", ".bak")


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


OUT_DIR = os.path.join(app_dir(), "exported_fonts")


def find_data_dir(game_path):
    game_path = os.path.abspath(game_path)
    candidates = []
    if game_path.endswith("_Data") and os.path.isdir(game_path):
        candidates.append(game_path)
    else:
        for root, dirs, _files in os.walk(game_path):
            for d in dirs:
                if d.endswith("_Data"):
                    candidates.append(os.path.join(root, d))
            if root.count(os.sep) - game_path.count(os.sep) >= 2:
                dirs[:] = []
    for data_dir in candidates:
        if os.path.exists(os.path.join(data_dir, "globalgamemanagers")) or \
                os.path.exists(os.path.join(data_dir, "resources.assets")) or \
                os.path.exists(os.path.join(data_dir, "data.unity3d")):
            return data_dir
    raise SystemExit(f"Nie znaleziono katalogu *_Data w: {game_path}")


def font_extension(data):
    if data[:4] == b"OTTO":
        return ".otf"
    if data[:4] in (b"\x00\x01\x00\x00", b"true"):
        return ".ttf"
    if data[:4] == b"ttcf":
        return ".ttc"
    if data[:4] == b"wOFF":
        return ".woff"
    if data[:4] == b"wOF2":
        return ".woff2"
    return ".bin"


def safe_name(name):
    return "".join(c if c.isalnum() or c in " -_." else "_" for c in name).strip() or "font"


def iter_asset_files(data_dir):
    for root, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs if d not in ("GI", "il2cpp_data", "Managed", "Plugins")]
        for fname in files:
            if fname.lower().endswith(SKIP_SUFFIX):
                continue
            yield os.path.join(root, fname)


def main():
    if len(sys.argv) > 1:
        game_path = sys.argv[1]
    else:
        game_path = input("Podaj sciezke do gry: ").strip().strip('"')
    data_dir = find_data_dir(game_path)
    print(f"Katalog danych: {data_dir}")
    print(f"Eksport do:     {OUT_DIR}\n")

    os.makedirs(OUT_DIR, exist_ok=True)
    seen = {}       # (nazwa, rozmiar) -> pierwsza sciezka (deduplikacja)
    exported = 0
    count = 0
    for fpath in iter_asset_files(data_dir):
        try:
            env = UnityPy.load(fpath)
        except Exception:
            continue
        count += 1
        for obj in env.objects:
            if obj.type.name != "Font":
                continue
            try:
                d = obj.read()
                data = d.m_FontData or b""
                if not isinstance(data, bytes):
                    data = bytes(data)
            except Exception:
                continue
            if len(data) < 1000:
                continue  # Font bez osadzonych danych (np. systemowy)
            name = safe_name(d.m_Name)
            key = (name, len(data))
            rel = os.path.relpath(fpath, data_dir)
            if key in seen:
                print(f"  = {name} ({len(data)} B) w {rel} - duplikat, pomijam")
                continue
            seen[key] = rel
            ext = font_extension(data)
            out_name = f"{name}{ext}"
            out_path = os.path.join(OUT_DIR, out_name)
            n = 2
            while os.path.exists(out_path):
                out_path = os.path.join(OUT_DIR, f"{name}_{n}{ext}")
                n += 1
            with open(out_path, "wb") as f:
                f.write(data)
            exported += 1
            print(f"  + {os.path.basename(out_path):45s} {len(data):9d} B  "
                  f"(path_id {obj.path_id}, {rel})")
        if count % 200 == 0:
            print(f"  ...przeskanowano {count} plikow", file=sys.stderr)

    print(f"\nPrzeskanowano {count} plikow, wyeksportowano {exported} fontow do {OUT_DIR}")
    if not exported:
        print("Gra nie ma assetow Font z osadzonymi danymi "
              "(teksty moga uzywac wylacznie atlasow TMP).")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e)
    except Exception:
        import traceback
        traceback.print_exc()
    input("\nNacisnij Enter, aby zakonczyc...")
