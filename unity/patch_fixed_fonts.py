#!/usr/bin/env python3
"""
Instaluje naprawione fonty TMP z folderu fixed_fonts/ do dowolnej gry Unity.

Odpowiednik trybu PATCH z fix_tmp_polish_fonts.py, ale bez generowania -
dziala na gotowych plikach wyeksportowanych trybem EKSPORT:
  fixed_fonts/<nazwa>.json  (typ "static_atlas" + <nazwa>.png,
                             albo "dynamic_font_data" + <nazwa>.ttf,
                             albo "bitmap_font" + <nazwa>.png - asset Font
                             bez TTF-a: atlas + m_CharacterRects)

Nie wymaga FreeType/fontTools - nadaje sie na lekki instalator dla
uzytkownika koncowego. Wymaga typetree (GameAssembly.dll / Managed z gry).

Bundle Addressables zapisuje z packer="original" (domyslne save() rozpakowuje
bundle i rozdmuchuje go kilkukrotnie) i po zapisie przelicza m_Crc/m_BundleSize
w catalog.json - bez tego Unity odrzuca zmodyfikowany bundle (font znika albo
gra wcale nie wstaje).

Uzycie:
  python patch_fixed_fonts.py "E:\\Games\\Gra"
  (bez argumentu - zapyta o sciezke)

Pliki gry sa nadpisywane bez tworzenia kopii zapasowych.
"""
import json
import os
import sys
import time

# konsola Windows startuje w cp852/cp1250 i wywala UnicodeEncodeError na
# nazwach fontow z CJK (np. "日语mplus_hzk_12") - wymuszamy UTF-8 przed
# jakimkolwiek print()
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import UnityPy
# CELOWO BEZ numpy: wheele numpy >= 2.4 sa budowane z baseline x86-64-v2, wiec na
# CPU bez SSE4.2/POPCNT (sprzet z przed ~2009) samo `import numpy` rzuca
# RuntimeError("NumPy was built with baseline optimizations: (X86_V2) but your
# machine doesn't support...") i cala podmiana fontow padala u gracza. Tu numpy
# byl uzywany tylko do odwrocenia atlasu i zrzutu bajtow - PIL robi to samo.
# UnityPy importuje numpy wylacznie leniwie w export/SpriteHelper.py, w
# try/except ImportError, wiec instalator nie potrzebuje go wcale.
from PIL import Image, ImageOps

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unitypy_format23  # noqa: E402
unitypy_format23.enable()


def _raw_read_string(raw, pos):
    import struct
    size = struct.unpack_from("<i", raw, pos)[0]
    if size < 0 or pos + 4 + size > len(raw):
        raise ValueError(f"nieprawidlowa dlugosc stringa: {size}")
    start = pos + 4
    end = start + size
    return raw[start:end].decode("utf-8", "replace"), end + (-end % 4)


def read_tmp_font_raw(obj):
    """Pola zmienne TMP_FontAsset z formatu Unity 6000.5."""
    import struct
    raw = obj.get_raw_data()
    pos = 28
    name, pos = _raw_read_string(raw, pos)
    version, pos = _raw_read_string(raw, pos)
    pos += 4
    family, pos = _raw_read_string(raw, pos)
    _style, pos = _raw_read_string(raw, pos)
    pos += 4 + 4 + 4 + 15 * 4 + 12
    _guid, pos = _raw_read_string(raw, pos)
    _source_name, pos = _raw_read_string(raw, pos)
    _creation_guid, pos = _raw_read_string(raw, pos)
    pos += 9 * 4
    for _ in range(3):
        _value, pos = _raw_read_string(raw, pos)
    pos += 16 + 12
    _source_path, pos = _raw_read_string(raw, pos)
    pos += 4 + 4
    glyph_count_offset = pos
    glyph_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    if version != "1.1.0" or not name or not family or glyph_count < 0 \
            or pos + glyph_count * 52 > len(raw):
        raise ValueError("nieznany wariant TMP_FontAsset")
    glyphs = []
    for _ in range(glyph_count):
        v = struct.unpack_from("<I5f4ifii", raw, pos)
        pos += 52
        glyphs.append({"m_Index": v[0],
                       "m_Metrics": {"m_Width": v[1], "m_Height": v[2],
                                     "m_HorizontalBearingX": v[3],
                                     "m_HorizontalBearingY": v[4],
                                     "m_HorizontalAdvance": v[5]},
                       "m_GlyphRect": {"m_X": v[6], "m_Y": v[7],
                                       "m_Width": v[8], "m_Height": v[9]},
                       "m_Scale": v[10], "m_AtlasIndex": v[11],
                       "m_ClassDefinitionType": v[12]})
    char_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    if char_count < 0 or pos + char_count * 16 > len(raw):
        raise ValueError("nieprawidlowa tablica znakow")
    chars = []
    for _ in range(char_count):
        element_type, unicode_, glyph_index, scale = struct.unpack_from("<IIIf", raw, pos)
        pos += 16
        chars.append({"m_ElementType": element_type, "m_Unicode": unicode_,
                      "m_GlyphIndex": glyph_index, "m_Scale": scale})
    middle_start = pos
    atlas_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    atlases = []
    for _ in range(atlas_count):
        file_id, path_id = struct.unpack_from("<iq", raw, pos)
        pos += 12
        atlases.append({"m_FileID": file_id, "m_PathID": path_id})
    atlas_index = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    # flagi 1,1,1 przed atlasem tez sa "potega dwojki" - wymagaj rozmiaru >= 32
    # (ta sama poprawka co w fix_tmp_polish_fonts.read_tmp_font_raw)
    atlas_values_offset = None
    for candidate in range(pos, min(pos + 64, len(raw) - 16), 4):
        width, height, padding, render_mode = struct.unpack_from("<4i", raw, candidate)
        if (32 <= width <= 16384 and width & (width - 1) == 0
                and 32 <= height <= 16384 and height & (height - 1) == 0
                and 0 <= padding <= 128 and 0 <= render_mode <= 0x1FFFF):
            atlas_values_offset = candidate
            break
    if atlas_values_offset is None:
        raise ValueError("nie znaleziono parametrow atlasu")
    width, height, padding, render_mode = struct.unpack_from(
        "<4i", raw, atlas_values_offset)
    pos = atlas_values_offset + 16
    rect_lists = []
    for _ in range(2):
        count = struct.unpack_from("<i", raw, pos)[0]
        pos += 4
        rects = []
        for _ in range(count):
            x, y, w, h = struct.unpack_from("<4i", raw, pos)
            pos += 16
            rects.append({"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h})
        rect_lists.append(rects)
    return {"m_Name": name, "m_GlyphTable": glyphs, "m_CharacterTable": chars,
            "m_AtlasTextures": atlases,
            "m_AtlasTextureIndex": atlas_index,
            "m_AtlasWidth": width, "m_AtlasHeight": height,
            "m_AtlasPadding": padding, "m_AtlasRenderMode": render_mode,
            "m_UsedGlyphRects": rect_lists[0], "m_FreeGlyphRects": rect_lists[1],
            "_raw_layout": {"prefix": raw[:glyph_count_offset],
                            "middle": raw[middle_start:atlas_values_offset],
                            "suffix": raw[pos:]}}


def write_tmp_font_raw(tree):
    import struct
    layout = tree["_raw_layout"]
    out = bytearray(layout["prefix"])
    out += struct.pack("<i", len(tree["m_GlyphTable"]))
    for glyph in tree["m_GlyphTable"]:
        m, r = glyph["m_Metrics"], glyph["m_GlyphRect"]
        out += struct.pack("<I5f4ifii", glyph["m_Index"], m["m_Width"],
                           m["m_Height"], m["m_HorizontalBearingX"],
                           m["m_HorizontalBearingY"], m["m_HorizontalAdvance"],
                           r["m_X"], r["m_Y"], r["m_Width"], r["m_Height"],
                           glyph["m_Scale"], glyph["m_AtlasIndex"],
                           glyph.get("m_ClassDefinitionType", 0))
    out += struct.pack("<i", len(tree["m_CharacterTable"]))
    for char in tree["m_CharacterTable"]:
        out += struct.pack("<IIIf", char.get("m_ElementType", 1),
                           char["m_Unicode"], char["m_GlyphIndex"],
                           char.get("m_Scale", 1.0))
    out += layout["middle"]
    out += struct.pack("<4i", tree["m_AtlasWidth"], tree["m_AtlasHeight"],
                       tree["m_AtlasPadding"], tree["m_AtlasRenderMode"])
    for key in ("m_UsedGlyphRects", "m_FreeGlyphRects"):
        out += struct.pack("<i", len(tree[key]))
        for r in tree[key]:
            out += struct.pack("<4i", r["m_X"], r["m_Y"], r["m_Width"], r["m_Height"])
    return bytes(out) + layout["suffix"]

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


FIXED_DIR = os.path.join(app_dir(), "fixed_fonts")


# ---------------------------------------------------------------------------
# TypeTreeGenerator (patch na UnityPy 1.25 - jak w fix_tmp_polish_fonts.py)
# ---------------------------------------------------------------------------

_GENERATOR = None
_GENERATOR_ERROR = None
_BYTE_ARRAY_WRITE_PATCHED = False


def _patch_fast_byte_array_write():
    """`write_value()` w UnityPy dla tablic bajtow (np. `m_FontData`) nie ma
    fast-pathu jak przy odczycie - pisze KAZDY bajt osobnym wywolaniem
    Pythona (patrz TypeTreeHelper.write_value, galaz `Array`). Dla fontu
    kilku MB to per-byte petla na miliony elementow => kilka minut na jeden
    font (obserwowane realnie). Pisemy takie tablice hurtowo przez bytes."""
    global _BYTE_ARRAY_WRITE_PATCHED
    if _BYTE_ARRAY_WRITE_PATCHED:
        return
    from UnityPy.helpers import TypeTreeHelper as tth

    orig_write_value = tth.write_value
    byte_types = {"UInt8", "SInt8", "char", "bool"}

    def write_value_fast(value, node, writer, config):
        if (isinstance(value, (bytes, bytearray))
                and node.m_Children and node.m_Children[0].m_Type == "Array"):
            subtype = node.m_Children[0].m_Children[1]
            if subtype.m_Type in byte_types:
                align = (tth.metaflag_is_aligned(node.m_MetaFlag)
                          or tth.metaflag_is_aligned(node.m_Children[0].m_MetaFlag))
                writer.write_int(len(value))
                writer.write_bytes(bytes(value))
                if align:
                    writer.align_stream()
                return
        orig_write_value(value, node, writer, config)

    tth.write_value = write_value_fast
    _BYTE_ARRAY_WRITE_PATCHED = True


def selftest_generator(unity_version="2019.4.40f1", timeout=90):
    """Czy natywna biblioteka typetree WSTAJE na tej maszynie? Sprawdzane w
    OSOBNYM procesie, bo jej awaria nie jest wyjatkiem Pythona.

    `TypeTreeGeneratorAPI.dll` to .NET NativeAOT ladowany przez ctypes. Gdy
    procesor nie ma instrukcji, z ktorymi zostala zbudowana (albo brakuje
    zaleznosci systemowej), proces ginie NATYCHMIAST - bez wyjatku, bez
    tracebacku, bez zadnego komunikatu. Instalator wygladal wtedy jak "urwal
    sie w polowie" (u gracza Kony: cisza po "Podmieniam fonty gry...").

    Zwraca `(ok, opis)`. W exe (frozen) probe pomijamy - nie ma jak odpalic
    samego interpretera, wiec zostaje logowanie do pliku.
    """
    if getattr(sys, "frozen", False):
        return True, "pominieto (zbudowany exe)"
    import subprocess

    code = ("import sys\n"
            "from TypeTreeGeneratorAPI.TypeTreeGenerator import TypeTreeGenerator\n"
            "TypeTreeGenerator(sys.argv[1])\n"
            "print('ok')\n")
    try:
        proc = subprocess.run([sys.executable, "-c", code, unity_version],
                              capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return False, f"nie udalo sie uruchomic testu ({type(exc).__name__}: {exc})"
    if proc.returncode == 0 and "ok" in (proc.stdout or ""):
        return True, "ok"
    detail = (proc.stderr or proc.stdout or "").strip().splitlines()
    detail = detail[-1] if detail else ""
    code_txt = f"kod wyjscia {proc.returncode}"
    if proc.returncode is not None and proc.returncode < 0 or (
            proc.returncode or 0) > 0x80000000:
        # Windows: 0xC000001D = niedozwolona instrukcja (za stary procesor),
        # 0xC0000005 = naruszenie ochrony pamieci
        code_txt = f"kod wyjscia 0x{proc.returncode & 0xFFFFFFFF:08X}"
    return False, f"{code_txt} {detail}".strip()


def get_generator(game_root, data_dir, unity_version):
    global _GENERATOR, _GENERATOR_ERROR
    if _GENERATOR is not None:
        return _GENERATOR
    if _GENERATOR_ERROR is not None:
        raise RuntimeError(_GENERATOR_ERROR)
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator, TypeTreeNode

    def get_nodes_fixed(self, assembly, fullname):
        if assembly.endswith(".dll"):
            assembly = assembly[:-4]
        key = (assembly, fullname)
        if key in self.cache:
            return self.cache[key]
        raw = self.get_nodes_as_json(assembly, fullname)
        if not raw:
            raise ValueError(f"brak typetree dla {assembly} {fullname}")
        data = json.loads(raw)
        nodes = TypeTreeNode.from_list([
            {"m_Level": n["m_Level"], "m_Type": n["m_Type"],
             "m_Name": n["m_Name"], "m_MetaFlag": n.get("m_MetaFlag", 0)}
            for n in data
        ])
        self.cache[key] = nodes
        return nodes

    TypeTreeGenerator.get_nodes_up = get_nodes_fixed

    _patch_fast_byte_array_write()

    print(f"[ttg] TypeTreeGenerator dla Unity {unity_version}...")
    ttg = TypeTreeGenerator(unity_version)
    # .dll = build windowsowy, .so = natywny linuksowy
    il2cpp = next((p for p in (os.path.join(game_root, n) for n in
                               ("GameAssembly.dll", "GameAssembly.so",
                                "libil2cpp.so"))
                   if os.path.isfile(p)), None)
    metadata = os.path.join(data_dir, "il2cpp_data", "Metadata", "global-metadata.dat")
    if il2cpp and os.path.exists(metadata):
        print(f"[ttg] gra IL2CPP - laduje {os.path.basename(il2cpp)} "
              f"+ global-metadata.dat")
        with open(il2cpp, "rb") as f:
            a = f.read()
        with open(metadata, "rb") as f:
            b = f.read()
        try:
            ttg.load_il2cpp(a, b)
        except Exception as e:
            _GENERATOR_ERROR = (
                f"TypeTreeGeneratorAPI nie obsluguje metadanych IL2CPP Unity"
                f" {unity_version}: {type(e).__name__}: {e}")
            raise RuntimeError(_GENERATOR_ERROR) from e
    else:
        print("[ttg] gra Mono - load_local_game()")
        ttg.load_local_game(game_root)
    _GENERATOR = ttg
    return ttg


def write_bytes_retrying(path, data, timeout=80):
    """Zapis w miejscu (bez .tmp+rename), z ponawianiem na PermissionError
    (antywirus/indexer trzyma uchwyt do swiezo zapisanego pliku).

    Celowo BEZ .tmp+os.replace jak w efd_lib.atomic_write_bytes: GameFiles
    ponizej trzyma wlasny otwarty uchwyt do tego samego pliku (UnityPy.load
    czyta bezposrednio ze sciezki), wiec os.replace() zawsze dostalby
    PermissionError od WLASNEGO procesu (rename wymaga FILE_SHARE_DELETE),
    niezaleznie od retry - to nie jest zewnetrzna, przejsciowa blokada."""
    deadline = time.time() + timeout
    while True:
        try:
            with open(path, "wb") as f:
                f.write(data)
            return
        except PermissionError:
            if time.time() > deadline:
                raise
            time.sleep(1)


def object_name(obj):
    """`m_Name` obiektu bez czytania calego assetu.

    Dla MonoBehaviour dziala nawet bez typetree skryptu - nazwa siedzi w polach
    bazowych, ktore UnityPy zna z wbudowanego typetree. Skan calego pliku jest
    tani (182 komponenty w 51 MB `sharedassets0.assets` = 0,01 s)."""
    try:
        if obj.type.name == "MonoBehaviour":
            # read(check_read=False) nadal generuje PELNE typetree skryptu.
            # Brak typu w IL2CPP wypisuje wtedy blad z natywnej biblioteki,
            # nawet gdy Python lapie wyjatek. Jawny naglowek omija generator.
            return obj.parse_monobehaviour_head().m_Name or None
        return getattr(obj.read(check_read=False), "m_Name", None) or None
    except Exception:
        return None


#: Pola TMP_FontAsset, ktore przenosimy z naszego eksportu do drzewa z GRY.
#: Reszta (PPtr-y `m_Script`, `atlas`, `material`, `m_GameObject`, hashe) zostaje
#: TAKA, JAKA JEST W GRZE - przepisanie naszych path_id wskazywaloby na obiekty
#: z NASZEGO builda, czyli u gracza na przypadkowe assety.
FONT_FIELDS_LEGACY = ("m_fontInfo", "m_glyphInfoList", "m_kerningInfo",
                      "m_kerningPair", "fontCreationSettings")
FONT_FIELDS_MODERN = ("m_FaceInfo", "m_GlyphTable", "m_CharacterTable",
                      "m_AtlasWidth", "m_AtlasHeight", "m_AtlasPadding",
                      "m_AtlasRenderMode", "m_AtlasTextureIndex",
                      "m_UsedGlyphRects", "m_FreeGlyphRects",
                      "m_KerningTable", "m_FontFeatureTable",
                      "m_CreationSettings", "m_AtlasPopulationMode")
FONT_FIELDS = FONT_FIELDS_LEGACY + FONT_FIELDS_MODERN
#: bez ktorych podmiana nie ma sensu (glify + metryki)
FONT_FIELDS_CRITICAL = ("m_glyphInfoList", "m_GlyphTable", "m_CharacterTable")


def merge_font_tree(dst, src):
    """Wklada nasze glify/metryki w drzewo fontu WCZYTANE Z GRY.

    Zwraca `(wpisane, pominiete)`. Pomijamy pole, ktorego nie ma po ktorejs
    stronie - to znaczy, ze gra ma inna wersje TextMesh Pro. Dzieki temu
    roznica wersji konczy sie czytelnym komunikatem, a nie `KeyError` w
    trzewiach UnityPy albo cicho polamanym fontem."""
    written, skipped = [], []
    for field in FONT_FIELDS:
        if field in src and field in dst:
            dst[field] = src[field]
            written.append(field)
        elif field in src or field in dst:
            skipped.append(field)
    return written, skipped


class GameFiles:
    def __init__(self, data_dir, game_root):
        self.data_dir = data_dir
        self.game_root = game_root
        self.envs = {}
        self.modified = set()
        self._name_indexes = {}

    def env(self, rel_path):
        path = os.path.abspath(os.path.join(self.data_dir, rel_path))
        if path not in self.envs:
            e = UnityPy.load(path)
            try:
                uv = next(iter(e.assets)).unity_version
                e.typetree_generator = get_generator(self.game_root, self.data_dir, uv)
            except (StopIteration, RuntimeError):
                pass
            self.envs[path] = e
        return self.envs[path]

    def named_objects(self, rel_path, name, type_name):
        env = self.env(rel_path)
        key = (id(env), type_name)
        if key not in self._name_indexes:
            index = {}
            for obj in env.objects:
                if obj.type.name == type_name:
                    index.setdefault(object_name(obj), []).append(obj)
            self._name_indexes[key] = index
        return list(self._name_indexes[key].get(name, ()))

    def find(self, rel_path, name, type_name, path_id=None, serialized_name=None):
        """Obiekt po NAZWIE, z `path_id` traktowanym tylko jako podpowiedz.

        path_id w plikach Unity jest lokalny dla konkretnego BUILDA gry: inna
        latka, inny sklep czy inna platforma przenumerowuja wszystko. Zapis
        naszego drzewa pod stary path_id trafial wtedy w losowy komponent
        (u gracza Kony wyszlo to jako `KeyError: 'm_Padding'` /
        `'m_Material'` - to pola UnityEngine.UI, nie TMP_FontAsset).

        Dlatego: sprawdzamy, czy pod path_id naprawde lezy obiekt o oczekiwanej
        nazwie i typie, a jesli nie - szukamy po nazwie w calym pliku.
        Gdy nazwy nie ma, rzucamy wyjatek z diagnoza (co tam jest zamiast),
        zeby NIGDY nie nadpisac obcego assetu.
        """
        env = self.env(rel_path)

        def same_file(obj):
            return (not serialized_name
                    or getattr(getattr(obj, "assets_file", None), "name", None)
                    == serialized_name)

        # Nazwy indeksujemy raz na srodowisko i typ. Najpierw rozstrzygamy
        # plik wewnatrz bundla, dopiero potem lokalny path_id.
        by_name = self.named_objects(rel_path, name, type_name)
        if len(by_name) > 1:
            in_file = [o for o in by_name if same_file(o)]
            if in_file:
                by_name = in_file
        if len(by_name) > 1:
            hint = [o for o in by_name if o.path_id == path_id]
            if len(hint) == 1:
                return hint[0]
        if len(by_name) == 1:
            found = by_name[0]
            if path_id is not None and found.path_id != path_id:
                print(f"  (path_id {path_id} -> {found.path_id}: inny build gry, "
                      f"znalazlem {name!r} po nazwie)")
            return found
        if len(by_name) > 1:
            raise RuntimeError(
                f"w {rel_path} jest {len(by_name)} obiektow {type_name} o nazwie "
                f"{name!r} - nie wiem, ktory podmienic")

        # 3. nie ma - powiedz, co lezy pod naszym path_id
        what = "brak obiektu o tym path_id"
        raw = [o for o in env.objects if o.path_id == path_id]
        if raw:
            what = ", ".join(sorted({f"{o.type.name} {object_name(o)!r}" for o in raw}))
        raise RuntimeError(
            f"nie znalazlem {type_name} o nazwie {name!r} w {rel_path} "
            f"(pod path_id {path_id}: {what}). Twoja wersja gry rozni sie od tej, "
            f"z ktorej robilismy fonty")

    def obj(self, rel_path, path_id, serialized_name=None):
        """Obiekt po path_id, rozrozniajac pliki wewnatrz bundla po nazwie.

        Zostawione dla zgodnosci (i dla obiektow bez nazwy). Do fontow uzywaj
        `find()`, ktore weryfikuje, ze trafiamy we wlasciwy asset.

        W bundlach scenowych path_id sa male i powtarzaja sie miedzy kolejnymi
        CAB-ami, wiec pierwsze trafienie moze byc calkiem innym assetem.
        serialized_name (z fixed_fonts/*.json) rozstrzyga, o ktory chodzi;
        starsze eksporty go nie maja - wtedy dziala tylko dla path_id
        wystepujacego w pliku raz."""
        env = self.env(rel_path)
        matches = [o for o in env.objects if o.path_id == path_id]
        if serialized_name:
            for o in matches:
                if getattr(getattr(o, "assets_file", None), "name", None) == serialized_name:
                    return o
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise RuntimeError(f"Brak obiektu {path_id} w {rel_path}"
                               + (f" ({serialized_name})" if serialized_name else ""))
        names = sorted({str(getattr(getattr(o, "assets_file", None), "name", None))
                        for o in matches})
        raise RuntimeError(f"path_id {path_id} w {rel_path}: {len(matches)} obiektow "
                           f"({', '.join(names)})"
                           + (f", brak w {serialized_name}" if serialized_name else ""))

    def mark(self, rel_path):
        self.modified.add(os.path.abspath(os.path.join(self.data_dir, rel_path)))

    def save_modified(self):
        for path in sorted(self.modified):
            # packer="original" - domyslne save() zapisuje bundle BEZ kompresji,
            # co rozdmuchuje go kilkukrotnie (i tak czy siak rozjezdza CRC)
            if path.lower().endswith(".bundle"):
                data = self.envs[path].file.save(packer="original")
            else:
                data = self.envs[path].file.save()
            write_bytes_retrying(path, data)
            print(f"Zapisano: {path}")

    def touched_bundles(self):
        return [p for p in sorted(self.modified) if p.lower().endswith(".bundle")]


def fix_addressables(data_dir):
    """Uzgadnia m_Crc/m_BundleSize w catalog.json ze zmienionymi bundlami.

    Bez tego Unity odrzuca bundle z niezgodnym CRC - w najlepszym razie znika
    font, w najgorszym gra nie wstaje, bo nie da sie zaladowac zasobu.
    `fix_addressables_crc` zostawia po sobie catalog.json.bak - kasujemy go."""
    import pathlib

    # <repo>/tools/font_fixer/unity/patch_fixed_fonts.py -> <repo>/unity_tools
    # (w paczce zrodlowej ten sam uklad pod src/)
    unity_tools = os.path.join(pathlib.Path(os.path.abspath(__file__)).parents[3],
                               "unity_tools")
    for p in (unity_tools, getattr(sys, "_MEIPASS", None)):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    try:
        import fix_addressables_crc as fac
    except Exception as e:
        print(f"  ! nie moge zaimportowac fix_addressables_crc "
              f"({type(e).__name__}: {e}) - CRC katalogu NIE zostalo przeliczone")
        return

    cats = [p for p in pathlib.Path(data_dir).rglob("catalog.json")]
    cats += [p for p in pathlib.Path(data_dir).rglob("catalog.bin")]
    if not cats:
        print("  (brak catalog.json/bin - gra nie uzywa Addressables, "
              "nic do przeliczania)")
        return
    for cat in cats:
        try:
            if cat.suffix == ".json":
                fac.process_catalog_json(cat, False)
            else:
                fac.process_catalog_bin(cat, None, False)
        except Exception as e:
            print(f"  ! blad przy {cat}: {type(e).__name__}: {e}")
        for junk in (cat.with_suffix(cat.suffix + ".bak"),
                     cat.with_suffix(".json.bak"), cat.with_suffix(".bin.bak")):
            try:
                if junk.exists():
                    junk.unlink()
            except OSError:
                pass


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
    sw = os.path.join(game_path, "Data")          # romfs Switcha
    if os.path.isfile(os.path.join(sw, "globalgamemanagers")):
        candidates.append(sw)
    for data_dir in candidates:
        if os.path.exists(os.path.join(data_dir, "globalgamemanagers")) or \
                os.path.exists(os.path.join(data_dir, "resources.assets")) or \
                os.path.exists(os.path.join(data_dir, "data.unity3d")):
            return data_dir, os.path.dirname(data_dir)
    raise SystemExit(f"Nie znaleziono katalogu *_Data w: {game_path}")


# ---------------------------------------------------------------------------
# Instalacja
# ---------------------------------------------------------------------------

def _switch_swizzle_alpha8(tex_obj, tex_tree, img, data):
    """Tekstury na Switchu sa block-linear (m_PlatformBlob). Zwraca dane
    zaswizzlowane (z paddingiem) i poprawia ostatnie 8 B blobu (rozmiar).
    Poza Switchem zwraca data bez zmian. Patrz switch-unity-texture-swizzle."""
    import struct
    try:
        from UnityPy.enums import TextureFormat
        from UnityPy.helpers import TextureSwizzler as TS
    except Exception:
        return data
    blob = list(tex_tree.get("m_PlatformBlob") or [])
    platform = getattr(getattr(tex_obj, "assets_file", None), "target_platform", None)
    if len(blob) < 12:
        return data
    gobs = 1 << struct.unpack("<I", bytes(blob[8:12]))[0]
    if int(platform or 0) != 38:
        return data
    block = TS.TEXTURE_FORMAT_BLOCK_SIZE_MAP[TextureFormat.Alpha8]
    w, h = img.width, img.height
    pw, ph = TS.get_padded_texture_size(w, h, *block, gobs)
    flipped = ImageOps.flip(img)
    if (pw, ph) != (w, h):
        padded = Image.new("L", (pw, ph), 0)
        padded.paste(flipped, (0, 0))
        flipped = padded
    out = bytes(TS.swizzle(flipped.tobytes(), pw, ph, *block, gobs))
    tex_tree["m_PlatformBlob"] = list(bytes(blob[:-8])
                                      + struct.pack("<II", len(out), len(out)))
    print(f"  swizzle Switch (gobs={gobs}), dane {len(out)} B")
    return out


def atlas_pptr(font_tree):
    """PPtr do tekstury atlasu Z DRZEWA GRY (nowy TMP i stary TMP)."""
    textures = font_tree.get("m_AtlasTextures") or []
    if textures:
        idx = font_tree.get("m_AtlasTextureIndex") or 0
        if not 0 <= idx < len(textures):
            idx = 0
        return textures[idx]
    return font_tree.get("atlas")


def _deref_tree_ptr(owner, pointer, type_name):
    """Rozwiaz PPtr wzgledem jego wlasciciela, rowniez miedzy plikami bundla."""
    from UnityPy.classes.PPtr import PPtr
    if not pointer or not pointer.get("m_PathID"):
        raise RuntimeError(f"brak referencji do {type_name}")
    try:
        obj = PPtr(m_FileID=pointer["m_FileID"], m_PathID=pointer["m_PathID"],
                   assetsfile=owner.assets_file).deref()
    except (KeyError, ValueError, FileNotFoundError) as exc:
        raise RuntimeError(f"nie mozna rozwiazac referencji do {type_name}: {exc}") from exc
    if obj.type.name != type_name:
        raise RuntimeError(f"referencja do {type_name} wskazuje na {obj.type.name}")
    return obj


def _material_main_texture(material_obj):
    """Obiekt Texture2D z `_MainTex` materialu albo None."""
    tree = material_obj.read_typetree()
    tex_envs = tree.get("m_SavedProperties", {}).get("m_TexEnvs", [])
    main_tex = next((value.get("m_Texture") for name, value in tex_envs
                     if name == "_MainTex"), None)
    if not main_tex or not main_tex.get("m_PathID"):
        return None
    return _deref_tree_ptr(material_obj, main_tex, "Texture2D")


def check_material_atlas(font_obj, game_tree):
    """Rzuca RuntimeError, gdy material fontu rysuje z INNEJ tekstury niz atlas.

    Wgrywamy atlas do tekstury z `m_AtlasTextures`, ale shader probkuje
    `_MainTex` materialu fontu. Zwykle to ta sama tekstura - ale nie zawsze:
    `RedSawNumber` w Doloc Town ma Alpha8 `RedSawNumber Atlas` w
    `m_AtlasTextures` i RGBA `RedSawNumber Atlas 1` (cyfry z cieniem) w
    materiale. Nasze przestawione glify trafialy wtedy w stara teksture
    i liczby przedmiotow w ekwipunku znikaly - bez zadnego bledu po drodze.

    Sprawdzamy to PRZED jakakolwiek zmiana w drzewie fontu, zeby font zostal
    w grze nietkniety. Gdy czegos nie da sie rozwiazac (brak materialu,
    referencja do innego pliku), nie blokujemy - to tylko bezpiecznik.
    """
    mat_ptr = game_tree.get("material") or {}
    tex_ptr = atlas_pptr(game_tree) or {}
    if not mat_ptr.get("m_PathID") or not tex_ptr.get("m_PathID"):
        return
    try:
        atlas = _deref_tree_ptr(font_obj, tex_ptr, "Texture2D")
        material = _deref_tree_ptr(font_obj, mat_ptr, "Material")
        main = _material_main_texture(material)
    except Exception:
        return
    if main is None:
        return
    if main.assets_file is atlas.assets_file and main.path_id == atlas.path_id:
        return
    raise RuntimeError(
        f"material {object_name(material)!r} rysuje z tekstury "
        f"{object_name(main)!r} ({main.path_id}), a atlas fontu to "
        f"{object_name(atlas)!r} ({atlas.path_id}) - podmiana atlasu nie "
        f"bylaby widoczna w grze i rozjechalaby istniejace glify. "
        f"Font pozostawiony bez zmian")


def patch_static_materials(gf, meta, font_obj, game_tree):
    """Dobierz material po nazwie ORAZ atlasie z gry; popraw tylko parametry SDF.

    Nazwa materialu nie musi byc unikalna nawet w jednym SerializedFile.
    Stare path_id nie sa dowodem, ze material nalezy do tego fontu.
    """
    materials = meta.get("materials", [])
    if not materials:
        return False
    atlas = _deref_tree_ptr(font_obj, atlas_pptr(game_tree), "Texture2D")
    gs = meta.get("gradient_scale", meta["padding"] + 1)
    targets = {"_TextureWidth": float(meta["atlas_w"]),
               "_TextureHeight": float(meta["atlas_h"])}
    if gs is not None:
        targets["_GradientScale"] = float(gs)
    changed_any = False
    seen = set()
    for mat in materials:
        matches = []
        for obj in gf.named_objects(mat["assets_rel"], mat["name"], "Material"):
            tree = obj.read_typetree()
            tex_envs = tree.get("m_SavedProperties", {}).get("m_TexEnvs", [])
            main_tex = next((value.get("m_Texture") for name, value in tex_envs
                             if name == "_MainTex"), None)
            try:
                texture = _deref_tree_ptr(obj, main_tex, "Texture2D")
            except RuntimeError:
                continue
            if (texture.assets_file is atlas.assets_file
                    and texture.path_id == atlas.path_id):
                matches.append((obj, tree))
        if not matches:
            raise RuntimeError(f"brak materialu {mat['name']!r} powiazanego z atlasem "
                               f"{atlas.assets_file.name}|{atlas.path_id}")
        for obj, tree in matches:
            identity = (id(obj.assets_file), obj.path_id)
            if identity in seen:
                continue
            seen.add(identity)
            floats = tree.get("m_SavedProperties", {}).get("m_Floats", [])
            changed = False
            for i, (name, value) in enumerate(floats):
                if name in targets and value != targets[name]:
                    print(f"Material {obj.path_id} ({mat['name']!r}): "
                          f"{name} {value} -> {targets[name]}")
                    floats[i] = (name, targets[name])
                    changed = True
            if changed:
                obj.save_typetree(tree)
                gf.mark(mat["assets_rel"])
                changed_any = True
    return changed_any


def install_static(gf, meta, png_path):
    print(f"\n=== {meta['label']} (static_atlas) ===")
    src_tree = meta["tmp_tree"]
    font_name = src_tree.get("m_Name") or meta["label"]

    # 1. TMP_FontAsset - szukamy PO NAZWIE i scalamy nasze glify z drzewem z gry
    tmp_obj = gf.find(meta["assets_rel"], font_name, "MonoBehaviour",
                      meta["tmp_path_id"], meta.get("serialized_name"))
    raw_mode = meta.get("tmp_raw_layout") == "unity_6000_5"
    game_tree = read_tmp_font_raw(tmp_obj) if raw_mode else tmp_obj.read_typetree()
    # przed merge_font_tree: po nim game_tree ma juz NASZE pola
    check_material_atlas(tmp_obj, game_tree)
    game_atlas_ptr = dict(atlas_pptr(game_tree) or {})
    written, skipped = merge_font_tree(game_tree, src_tree)
    if not any(f in written for f in FONT_FIELDS_CRITICAL):
        raise RuntimeError(
            f"font w grze ma inny format TMP niz nasz eksport "
            f"(nasze pola: {sorted(set(FONT_FIELDS) & set(src_tree))}, "
            f"pola gry: {sorted(set(FONT_FIELDS) & set(game_tree))}) - "
            f"trzeba wyeksportowac fonty z TEJ wersji gry")
    if raw_mode:
        tmp_obj.set_raw_data(write_tmp_font_raw(game_tree))
    else:
        tmp_obj.save_typetree(game_tree)
    gf.mark(meta["assets_rel"])
    # stary TMP (Unity 5.x) trzyma znaki w m_glyphInfoList, nie m_CharacterTable
    n_chars = len(game_tree.get("m_CharacterTable")
                  or game_tree.get("m_glyphInfoList") or [])
    print(f"TMP {tmp_obj.path_id} ({meta['assets_rel']}): {n_chars} znakow, "
          f"atlas {meta['atlas_w']}x{meta['atlas_h']}, padding {meta['padding']}")
    if skipped:
        print(f"  (pola nieprzeniesione - inna wersja TMP: {', '.join(skipped)})")

    # 2. tekstura (PNG grayscale -> Alpha8 bottom-up)
    if meta.get("tex_path_id"):
        img = Image.open(png_path).convert("L")
        if (img.height, img.width) != (meta["atlas_h"], meta["atlas_w"]):
            raise ValueError(f"PNG {(img.height, img.width)} nie pasuje do "
                             f"{meta['atlas_h']}x{meta['atlas_w']}")
        # Unity trzyma teksture bottom-up, PNG jest top-down; tobytes() dla trybu
        # "L" pakuje wiersze bez paddingu, wiec wychodzi surowy Alpha8
        data = ImageOps.flip(img).tobytes()
        # atlas bierzemy z referencji W PLIKU GRY - nasze tex_path_id jest z
        # naszego builda. Gdy PPtr wskazuje na inny plik (m_FileID != 0), wracamy
        # do metadanych.
        tex_ptr = game_atlas_ptr
        tex_rel = meta["tex_assets_rel"]
        tex_pid = meta["tex_path_id"]
        if tex_ptr.get("m_PathID"):
            # PPtr jest wzgledem pliku, w ktorym lezy TMP (po nazwie moze to byc
            # inny plik serializowany niz w naszym buildzie), wiec rozwiazujemy go
            # wzgledem tmp_obj, a nie szukamy path_id w calym bundlu.
            tex_obj = _deref_tree_ptr(tmp_obj, tex_ptr, "Texture2D")
            tex_pid = tex_obj.path_id
            tex_rel = meta["assets_rel"]
        else:
            tex_obj = gf.obj(tex_rel, tex_pid, meta.get("tex_serialized_name"))
        if tex_obj.type.name != "Texture2D":
            raise RuntimeError(f"pod path_id {tex_pid} w {tex_rel} nie ma tekstury, "
                               f"jest {tex_obj.type.name} - inna wersja gry")
        tex_tree = tex_obj.read_typetree()
        data = _switch_swizzle_alpha8(tex_obj, tex_tree, img, data)
        tex_tree["m_Width"] = meta["atlas_w"]
        tex_tree["m_Height"] = meta["atlas_h"]
        tex_tree["m_TextureFormat"] = 1  # Alpha8
        tex_tree["m_MipCount"] = 1
        tex_tree["m_CompleteImageSize"] = len(data)
        tex_tree["image data"] = data
        if "m_StreamData" in tex_tree:
            tex_tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
        tex_obj.save_typetree(tex_tree)
        gf.mark(tex_rel)
        print(f"Tekstura {tex_pid} ({tex_rel}): osadzono {len(data)} B")

    # 3. Materialy wskazujace na atlas tego fontu (nazwy bywaja powielone).
    patch_static_materials(gf, meta, tmp_obj, game_tree)


def clear_dynamic_tmp_caches(gf, meta, source_font):
    """Odswiez jawnie wskazane cache TMP po podmianie zrodlowego TTF.

    Dynamiczny TMP moze miec glify wypieczone juz w buildzie. Samo m_FontData
    ich nie zmienia: trzeba wyzerowac tabele, stan pakowania i piksele atlasu.
    Wskazniki i tryb dynamiczny zostaja z gry. Nie dotyczy zwyklego UI Text.
    Takze przy identycznym TTF naprawiamy cache pozostawiony przez starszy importer.
    """
    pending = []
    for target in meta.get("clear_tmp_caches", []):
        rel = target["assets_rel"]
        obj = gf.find(rel, target["name"], "MonoBehaviour",
                      target.get("path_id"), target.get("serialized_name"))
        tree = obj.read_typetree()
        if tree.get("m_AtlasPopulationMode") != 1:
            raise RuntimeError(f"{target['name']}: cache mozna czyscic tylko w dynamicznym TMP")
        source = _deref_tree_ptr(obj, tree.get("m_SourceFontFile"), "Font")
        if (source.assets_file is not source_font.assets_file
                or source.path_id != source_font.path_id):
            raise RuntimeError(f"{target['name']}: TMP korzysta z innego zrodlowego TTF")
        atlases = tree.get("m_AtlasTextures") or []
        if len(atlases) != 1:
            raise RuntimeError(f"{target['name']}: odswiezanie wymaga pojedynczego atlasu TMP")
        check_material_atlas(obj, tree)
        tex_obj = _deref_tree_ptr(obj, atlases[0], "Texture2D")
        tex_tree = tex_obj.read_typetree()
        width, height = tree["m_AtlasWidth"], tree["m_AtlasHeight"]
        if (not tex_tree.get("m_IsReadable") or tex_tree.get("m_TextureFormat") != 1
                or tex_tree.get("m_MipCount") != 1
                or (tex_tree.get("m_Width"), tex_tree.get("m_Height")) != (width, height)):
            raise RuntimeError(f"{target['name']}: oczekiwano czytelnego atlasu Alpha8 bez mipmap")
        import copy
        new_tree = copy.deepcopy(tree)
        old_count = len(tree["m_CharacterTable"])
        for field in ("m_GlyphTable", "m_CharacterTable", "m_UsedGlyphRects"):
            new_tree[field] = []
        new_tree["m_AtlasTextureIndex"] = 0
        # TMP ClearFontAssetData: bitmapy nie potrzebuja brzegu, SDF odejmuje 1 px.
        border = 0 if tree["m_AtlasRenderMode"] & 0x10 else 1
        new_tree["m_FreeGlyphRects"] = [{"m_X": 0, "m_Y": 0,
                                         "m_Width": width - border,
                                         "m_Height": height - border}]
        features = new_tree.get("m_FontFeatureTable", {})
        if "m_GlyphPairAdjustmentRecords" in features:
            features["m_GlyphPairAdjustmentRecords"] = []
        if "kerningPairs" in new_tree.get("m_KerningTable", {}):
            new_tree["m_KerningTable"]["kerningPairs"] = []
        new_tex = dict(tex_tree)
        new_tex["image data"] = bytes(width * height)
        new_tex["m_CompleteImageSize"] = width * height
        if "m_StreamData" in new_tex:
            new_tex["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
        # Wszystkie cele sprawdzamy przed pierwszym zapisem do srodowiska gry.
        pending.append((rel, target["name"], obj, tree, new_tree,
                        tex_obj, tex_tree, new_tex, old_count))
    changed = 0
    for rel, name, obj, tree, new_tree, tex_obj, tex_tree, new_tex, old_count in pending:
        dirty = False
        if new_tree != tree:
            obj.save_typetree(new_tree)
            dirty = True
        if (bytes(tex_tree.get("image data", b"")) != new_tex["image data"]
                or tex_tree.get("m_StreamData") != new_tex.get("m_StreamData")
                or tex_tree.get("m_CompleteImageSize") != new_tex["m_CompleteImageSize"]):
            tex_obj.save_typetree(new_tex)
            dirty = True
        if dirty:
            gf.mark(rel)
            changed += 1
            print(f"Cache TMP {name!r}: {old_count} -> 0 znakow; atlas wyczyszczony,"
                  " gra odtworzy go z poprawionego TTF")
        else:
            print(f"Cache TMP {name!r}: juz odswiezony")
    return changed


def install_dynamic(gf, meta, ttf_path):
    print(f"\n=== {meta['label']} (dynamic_font_data) ===")
    # Instalatory moga podpiac wlasny generator i ominac get_generator().
    # Wielomegabajtowe TTF zapisujemy hurtowo, nie w petli bajt po bajcie.
    _patch_fast_byte_array_write()
    with open(ttf_path, "rb") as f:
        ttf = f.read()
    # Tu nazwa assetu Font (TTF) to NIE `label` (label to nazwa TMP_FontAsset,
    # np. "Cubic SDF - Dynamic", a font w srodku nazywa sie "Cubic"). Dopasowanie
    # po nazwie robimy wiec tylko, gdy eksport ja zapisal; inaczej zostaje
    # path_id, ale przynajmniej sprawdzamy TYP obiektu, zeby nie wpisac TTF-a
    # w losowy asset.
    font_name = meta.get("font_name")
    if font_name:
        obj = gf.find(meta["font_assets_rel"], font_name, "Font",
                      meta["font_path_id"], meta.get("font_serialized_name"))
    else:
        obj = gf.obj(meta["font_assets_rel"], meta["font_path_id"],
                     meta.get("font_serialized_name"))
        if obj.type.name != "Font":
            raise RuntimeError(
                f"pod path_id {meta['font_path_id']} w {meta['font_assets_rel']} "
                f"nie ma fontu, jest {obj.type.name} {object_name(obj)!r} - "
                f"Twoja wersja gry rozni sie od tej, z ktorej robilismy fonty")
    ftree = obj.read_typetree()
    clear_dynamic_tmp_caches(gf, meta, obj)
    if bytes(ftree.get("m_FontData", b"")) == ttf:
        print(f"Font {obj.path_id} ({ftree.get('m_Name')!r}): TTF juz zgodny")
    else:
        print(f"Font {obj.path_id} ({ftree.get('m_Name')!r}): "
              f"{len(ftree.get('m_FontData', b''))} -> {len(ttf)} B")
        ftree["m_FontData"] = ttf
        obj.save_typetree(ftree)
        gf.mark(meta["font_assets_rel"])


def _rects_sha(rects):
    """Ten sam odcisk co bitmap_font_atlas.rects_sha (bez importu numpy)."""
    import hashlib
    data = json.dumps(rects, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def _bitmap_font_texture(gf, rel, ftree):
    """(rel, Texture2D) atlasu fontu bitmapowego - z m_Texture albo z _MainTex
    materialu m_DefaultMaterial (kopie "(Crisp)" maja m_Texture puste). Bierzemy
    wskazniki z drzewa W GRZE, nie z eksportu (path_id sa lokalne dla builda)."""
    tex = ftree.get("m_Texture") or {}
    if tex.get("m_PathID"):
        if tex.get("m_FileID", 0):
            raise RuntimeError("tekstura fontu w innym pliku - nieobslugiwane")
        return rel, gf.obj(rel, tex["m_PathID"])
    mat = ftree.get("m_DefaultMaterial") or {}
    if not mat.get("m_PathID") or mat.get("m_FileID", 0):
        raise RuntimeError("font bez tekstury i bez materialu w tym samym pliku")
    mtree = gf.obj(rel, mat["m_PathID"]).read_typetree()
    for name, te in mtree.get("m_SavedProperties", {}).get("m_TexEnvs", []):
        t = te.get("m_Texture", {})
        if name == "_MainTex" and t.get("m_PathID"):
            if t.get("m_FileID", 0):
                raise RuntimeError("tekstura materialu fontu w innym pliku - nieobslugiwane")
            return rel, gf.obj(rel, t["m_PathID"])
    raise RuntimeError("material fontu nie ma _MainTex")


def install_bitmap(gf, meta, png_path):
    """Font bitmapowy (asset Font bez TTF): nowa tabela m_CharacterRects + atlas.

    Eksport zawiera PELNA tabele znakow po naprawie i odcisk tabeli PRZED
    naprawa. Instalujemy tylko wtedy, gdy font w grze ma dokladnie te tabele,
    z ktorej robilismy eksport - inna wersja gry moze miec inny atlas i nasze uv
    wskazywalyby w losowe miejsca."""
    print(f"\n=== {meta['label']} (bitmap_font) ===")
    rel = meta["font_assets_rel"]
    obj = gf.find(rel, meta["font_name"], "Font", meta["font_path_id"],
                  meta.get("font_serialized_name"))
    ftree = obj.read_typetree()
    current = _rects_sha(ftree.get("m_CharacterRects") or [])
    if current == _rects_sha(meta["rects"]):
        print(f"Font {obj.path_id} ({meta['font_name']!r}): juz zainstalowany")
        return
    if current != meta["source_rects_sha"]:
        raise RuntimeError(
            f"font {meta['font_name']!r} w grze ma inna tabele znakow niz ta, z ktorej "
            f"robilismy eksport - trzeba wyeksportowac fonty z TEJ wersji gry")
    tex_rel, tex_obj = _bitmap_font_texture(gf, rel, ftree)
    if tex_obj.type.name != "Texture2D":
        raise RuntimeError(f"atlas fontu to {tex_obj.type.name}, nie Texture2D")
    img = Image.open(png_path).convert("L")
    if (img.height, img.width) != (meta["atlas_h"], meta["atlas_w"]):
        raise ValueError(f"PNG {(img.height, img.width)} nie pasuje do "
                         f"{meta['atlas_h']}x{meta['atlas_w']}")
    data = ImageOps.flip(img).tobytes()       # Unity trzyma teksture bottom-up
    tex_tree = tex_obj.read_typetree()
    tex_tree["m_Width"] = meta["atlas_w"]
    tex_tree["m_Height"] = meta["atlas_h"]
    tex_tree["m_TextureFormat"] = 1  # Alpha8
    tex_tree["m_MipCount"] = 1
    tex_tree["m_CompleteImageSize"] = len(data)
    tex_tree["image data"] = data
    if "m_StreamData" in tex_tree:
        tex_tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    tex_obj.save_typetree(tex_tree)
    gf.mark(tex_rel)
    ftree["m_CharacterRects"] = meta["rects"]
    obj.save_typetree(ftree)
    gf.mark(rel)
    print(f"Font {obj.path_id} ({meta['font_name']!r}): +{meta.get('added', '')},"
          f" atlas {tex_obj.path_id} {meta['atlas_w']}x{meta['atlas_h']}")


# ---------------------------------------------------------------------------
# Wspolny silnik dla instalatorow (tools/font_fixer/unity/instalator/ i innych)
# ---------------------------------------------------------------------------

import re

_HASHED_BUNDLE_RE = re.compile(r"^(.+)_[0-9a-f]{32}(\.bundle)$", re.IGNORECASE)


def load_font_metas(fixed_dir):
    """[(nazwa_pliku.json, meta)] z `fixed_fonts/`. Pliki JSON bez pola `label`
    (nie z eksportu fontow) sa pomijane. Zwraca `(metas, bledne_pliki)`."""
    metas, bad = [], []
    if not os.path.isdir(fixed_dir):
        return metas, bad
    for fname in sorted(os.listdir(fixed_dir)):
        if not fname.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(fixed_dir, fname), "r", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            bad.append(fname)
            continue
        if isinstance(meta, dict) and meta.get("label"):
            metas.append((fname, meta))
    return metas, bad


def meta_files(fixed_dir, fname, meta):
    """Pliki towarzyszace metadanym fontu (png / ttf) i ktorych z nich brakuje."""
    base = os.path.join(fixed_dir, os.path.splitext(fname)[0])
    mtype = meta.get("type", "static_atlas")
    if mtype in ("static_atlas", "bitmap_font"):
        needed = [base + ".png"]
    elif mtype == "dynamic_font_data":
        needed = [os.path.join(fixed_dir, meta.get("ttf_file", ""))]
    else:
        return [], []
    return needed, [p for p in needed if not os.path.isfile(p)]


def _aa_platform_dir(data_dir):
    """Podkatalog platformy w StreamingAssets/aa (StandaloneWindows64 /
    StandaloneLinux64 / Switch) - ten, ktory faktycznie ma bundle."""
    aa = os.path.join(data_dir, "StreamingAssets", "aa")
    try:
        names = sorted(n for n in os.listdir(aa)
                       if (n.startswith("Standalone") or n == "Switch")
                       and os.path.isdir(os.path.join(aa, n)))
    except OSError:
        return None
    for name in names:
        try:
            if any(f.endswith(".bundle") for f in os.listdir(os.path.join(aa, name))):
                return name
        except OSError:
            pass
    return names[0] if names else None


def localize_rel(rel, data_dir):
    """Sciezka relatywna do <Data> dopasowana do TEGO buildu gry.

    Metadane fixed_fonts/*.json pochodza z jednego buildu (zwykle windowsowego):
    maja backslashe, `StandaloneWindows64` i windowsowe hashe w nazwach bundli.
    Pod Linuksem backslash to zwykly znak nazwy pliku, a natywny build ma inny
    katalog platformy i inny hash. Jesli plik istnieje tak, jak zapisano -
    nic nie zmieniamy."""
    parts = [p for p in rel.replace("\\", "/").split("/") if p]
    if not parts:
        return rel
    if os.path.exists(os.path.join(data_dir, *parts)):
        return os.path.join(*parts)
    plat = _aa_platform_dir(data_dir)
    if plat:
        parts = [plat if p.startswith("Standalone") else p for p in parts]
    path = os.path.join(data_dir, *parts)
    m = _HASHED_BUNDLE_RE.match(parts[-1])
    if not os.path.exists(path) and m:
        directory = os.path.dirname(path)
        try:
            hits = [n for n in os.listdir(directory)
                    if n.lower().endswith(m.group(2).lower())
                    and _HASHED_BUNDLE_RE.match(n)
                    and _HASHED_BUNDLE_RE.match(n).group(1) == m.group(1)]
        except OSError:
            hits = []
        if len(hits) == 1:
            parts[-1] = hits[0]
    return os.path.join(*parts)


def localize_font_meta(meta, data_dir):
    """Plytka kopia metadanych ze sciezkami dopasowanymi do tego buildu gry
    (`tmp_tree` ma kilkadziesiat MB - nie kopiujemy go)."""
    out = dict(meta)
    for key in ("assets_rel", "tex_assets_rel", "font_assets_rel"):
        if out.get(key):
            out[key] = localize_rel(out[key], data_dir)
    for key in ("materials", "clear_tmp_caches"):
        if out.get(key):
            items = []
            for item in out[key]:
                item = dict(item)
                if item.get("assets_rel"):
                    item["assets_rel"] = localize_rel(item["assets_rel"], data_dir)
                items.append(item)
            out[key] = items
    return out


def meta_font_name(meta):
    """`m_Name` assetu, ktory ten eksport podmienia (TMP_FontAsset albo Font)."""
    return ((meta.get("tmp_tree") or {}).get("m_Name") or meta.get("font_name")
            or meta.get("label"))


def meta_in_game(meta, data_dir, max_scan=512 << 20):
    """Czy font z eksportu lezy w tej grze? `True` / `False` / `None` (nie da sie
    stwierdzic tanio).

    Szuka nazwy fontu (z prefiksem dlugosci) jako bajtow w pliku gry (nazwa assetu
    siedzi w pliku jawnym tekstem), bez parsowania Unity - sprawdzenie kilkudziesieciu gier trwa
    sekundy. Skompresowane bundle (UnityFS) i pliki wieksze niz `max_scan`
    zwracaja None: tam nazwy nie da sie znalezc bez rozpakowania."""
    rel = meta.get("assets_rel") or meta.get("font_assets_rel")
    name = meta_font_name(meta)
    if not rel or not name:
        return None
    path = os.path.join(data_dir, localize_rel(rel, data_dir))
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if f.read(7) in (b"UnityFS", b"UnityWe", b"UnityRa") or size > max_scan:
                return None
            if size == 0:
                return False
            import mmap
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                # nazwa z prefiksem dlugosci (int32 LE) - inaczej "LiberationSans SDF"
                # trafialoby tez w "LiberationSans SDF Material" itp.
                raw = name.encode("utf-8")
                import struct
                return mm.find(struct.pack("<i", len(raw)) + raw) != -1
    except (OSError, ValueError):
        return False


def write_atomic(dest, data, attempts=20, delay=2.0):
    """Zapis przez `.tmp` + `os.replace()` z ponawianiem na PermissionError.

    Pliki gry czytamy do pamieci (MemoryGameFiles), wiec WLASNY proces nie
    trzyma uchwytu - blokada pochodzi od antywirusa/indeksera i zwykle znika
    po kilku sekundach. Gdy nie zniknie, nadpisujemy plik w miejscu: te
    programy trzymaja uchwyt bez FILE_SHARE_DELETE (to blokuje rename), ale nie
    zwykly zapis."""
    tmp = dest + ".tmp_pl"
    with open(tmp, "wb") as f:
        f.write(data)
    for i in range(attempts):
        try:
            os.replace(tmp, dest)
            return
        except PermissionError:
            if i == 0 or (i + 1) % 5 == 0:
                print(f"    ...plik zajety (pewnie antywirus), czekam "
                      f"({i + 1}/{attempts})")
            if i < attempts - 1:
                time.sleep(delay)
    try:
        with open(dest, "wb") as f:
            f.write(data)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


class MemoryGameFiles(GameFiles):
    """`GameFiles`, ktore czyta pliki gry DO PAMIECI i zapisuje atomowo.

    `UnityPy.load(sciezka)` trzyma otwarty uchwyt do pliku, a na Windows blokuje
    to `os.replace()` na tym samym pliku. Tu uchwytu nie ma, wiec zapis idzie
    bezpiecznie przez `.tmp` + rename (przerwanie nie zostawia polowy pliku)."""

    def __init__(self, data_dir, game_root):
        super().__init__(data_dir, game_root)
        self.sizes = {}

    def env(self, rel_path):
        import io
        path = os.path.abspath(os.path.join(self.data_dir, rel_path))
        if path not in self.envs:
            with open(path, "rb") as f:
                raw = f.read()
            e = UnityPy.Environment(path=os.path.dirname(path))
            e.load_file(io.BytesIO(raw), name=path)
            if len(e.files) == 1:
                e.file = next(iter(e.files.values()))
            try:
                uv = next(iter(e.assets)).unity_version
                e.typetree_generator = get_generator(self.game_root, self.data_dir, uv)
            except (StopIteration, RuntimeError):
                pass
            self.envs[path] = e
            self.sizes[path] = len(raw)
        return self.envs[path]

    def save_modified(self, dry_run=False):
        """Zapisuje zmienione pliki. Zwraca `(zapisane, bledy)`, gdzie bledy to
        `{sciezka: opis}` - jeden zly plik nie przerywa zapisu reszty."""
        written, errors = [], {}
        for path in sorted(self.modified):
            try:
                env = self.envs[path]
                if path.lower().endswith(".bundle"):
                    data = env.file.save(packer="original")
                else:
                    data = env.file.save()
                src = self.sizes.get(path) or os.path.getsize(path)
                if len(data) < src // 2:
                    raise RuntimeError(f"wynik {len(data)} B to <50% zrodla {src} B "
                                       f"- zapis odrzucony")
                if not dry_run:
                    write_atomic(path, data)
                written.append((path, src, len(data)))
            except Exception as e:
                errors[path] = f"{type(e).__name__}: {e}"
        return written, errors


def install_fonts(gf, metas, fixed_dir, localize=True):
    """Instaluje wszystkie fonty z `metas` w `gf` (nic jeszcze nie zapisuje).

    Zwraca liste `(label, ok, komunikat)`. Blad jednego fontu nie przerywa
    reszty - np. Steam i Xbox maja inne hashe bundli, wiec jakiegos obiektu moze
    po prostu nie byc w tej wersji gry."""
    results = []
    for fname, meta in metas:
        label = meta.get("label", fname)
        if localize:
            meta = localize_font_meta(meta, gf.data_dir)
        base = os.path.join(fixed_dir, os.path.splitext(fname)[0])
        mtype = meta.get("type", "static_atlas")
        try:
            if mtype in ("static_atlas", "bitmap_font"):
                png = base + ".png"
                if not os.path.exists(png):
                    results.append((label, False, f"brak pliku {os.path.basename(png)}"))
                    continue
                (install_static if mtype == "static_atlas" else install_bitmap)(
                    gf, meta, png)
            elif mtype == "dynamic_font_data":
                ttf = os.path.join(fixed_dir, meta.get("ttf_file", ""))
                if not os.path.isfile(ttf):
                    results.append((label, False,
                                    f"brak pliku {meta.get('ttf_file') or 'TTF'}"))
                    continue
                install_dynamic(gf, meta, ttf)
            else:
                results.append((label, False, f"nieznany typ {mtype!r}"))
                continue
        except Exception as e:
            results.append((label, False, f"{type(e).__name__}: {e}"))
            continue
        results.append((label, True, mtype))
    return results


def main():
    print("=" * 60)
    print("  Instalacja naprawionych fontow TMP (fixed_fonts/)")
    print("=" * 60)

    metas, _bad = load_font_metas(FIXED_DIR)
    if not metas:
        print(f"\n[BLAD] Brak plikow .json w {FIXED_DIR}")
        print("Najpierw wyeksportuj fonty przez fix_tmp_polish_fonts.py (tryb EKSPORT).")
        return

    print(f"\nFonty w {FIXED_DIR}:")
    for fname, meta in metas:
        print(f"  - {meta['label']}  [{meta.get('type', 'static_atlas')}]  "
              f"-> {meta.get('assets_rel') or meta.get('font_assets_rel')}")

    if len(sys.argv) > 1:
        game_path = sys.argv[1]
    else:
        game_path = input("\nPodaj sciezke do gry: ").strip().strip('"')
    data_dir, game_root = find_data_dir(game_path)
    print(f"Katalog danych: {data_dir}")

    gf = GameFiles(data_dir, game_root)
    for label, ok, msg in install_fonts(gf, metas, FIXED_DIR, localize=False):
        if not ok:
            print(f"  ! BLAD przy {label}: {msg}")

    if gf.modified:
        print(f"\nZapisywanie {len(gf.modified)} plikow...")
        gf.save_modified()
        if gf.touched_bundles():
            print("\nPrzeliczam CRC bundli w katalogu Addressables...")
            fix_addressables(data_dir)
        print("\nGotowe. Przetestuj w grze.")
    else:
        print("\nNic nie zmieniono.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e)
    except Exception:
        import traceback
        traceback.print_exc()
    try:
        input("\nNacisnij Enter, aby zakonczyc...")
    except EOFError:
        pass
