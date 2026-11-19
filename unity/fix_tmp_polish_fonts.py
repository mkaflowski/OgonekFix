#!/usr/bin/env python3
"""
Naprawia polskie znaki w fontach TMP (TextMeshPro) dowolnej gry Unity.

Dziala na plikach .assets / bundle. Dla kazdego TMP_FontAsset bez polskich
znakow:
  1. szuka zrodlowego TTF wsrod assetow Font w grze (po nazwie rodziny),
  2. jesli nie ma - pyta o wybor: font z gry albo plik TTF/OTF z dysku,
  3. jesli TTF nie ma polskich znakow, do wyboru:
       - INNY font (podmiana calkowita),
       - font FALLBACK: oryginalny font zostaje, tylko brakujace litery
         (np. ąęśź) sa dorabiane z drugiego fontu do tego samego atlasu,
       - uzycie mimo brakow / pominiecie,
   3a. brakujace polskie litery sklada z WLASNYCH glifow fontu; zakres tego
      skladania wybiera sie na poczatku (pytanie o tryb dorabiania):
        [1] WSZYSTKIE (domyslnie, jak font_fixer/fix_polish_fonts.py): kreska
            i kropka sa WYCIETE z fontu (akcent = roznica 'ó' i 'o', kropka =
            gorka z 'i'), a ogonek (ą ę) i przekreslenie (ł) sa DORYSOWANE
            geometrycznie w tych samych proporcjach co font_fixer, tylko na
            pikselach atlasu zamiast na konturach - font fallback jest wtedy
            potrzebny tylko na resztki,
        [2] TYLKO kreska i kropka (ć ń ó ś ź ż) - ą ę ł ida z fontu FALLBACK,
      Gdy w foncie nie ma z czego wyciac kreski ani kropki (krój zrobiony pod
      jedna gre nie ma ani jednego akcentu, ani ´ / ˙), sa one DORYSOWANE - i to
      niezaleznie od trybu. Litera z obcego fontu fallback ma inna szerokosc
      i inna wysokosc, wiec w napisie widac ja jako "inny rozmiar",
  4. regeneruje statyczny atlas SDF (generate_tmp_sdf.py) i wstrzykuje:
     tabele glifow/znakow, teksture atlasu (osadzona, streaming zerowany),
     _GradientScale we wszystkich materialach uzywajacych atlasu.

Fonty DYNAMICZNE (m_AtlasPopulationMode=1) nie maja atlasu do wypiekania -
glify dorabiaja sobie same w runtime, ale tylko z tego, co jest w ich
zrodlowym TTF (m_SourceFontFile). Braki liczy sie wiec po cmap TEGO pliku
(m_CharacterTable bywa prawie pusta i nic nie mowi), a naprawa idzie w kontury
fontu. Do wyboru:
  [1] dorobienie brakujacych liter wprost w konturach fontu - w zakresie
      wybranego trybu (wszystkie albo tylko kreska i kropka), a to, czego nie
      udalo sie zlozyc, wklejane z fontu FALLBACK,
  [2] podmiana calego pliku TTF/OTF,
  [3] transliteracja - brakujace znaki dostaja glify bez ogonkow.
Pliki .ttc (kolekcje kilku krojow) sa naprawiane w calosci - kazdy kroj
osobno, zapis z shareTables, zeby plik nie napuchl.

Gry bez TextMesh Pro (stare UI Text / GUIStyle) renderuja wprost z assetow
Font, czyli z TTF-a osadzonego w m_FontData. Takie fonty przechodza dokladnie
ten sam zabieg, co zrodlowy TTF fontu dynamicznego (dorobienie liter w
konturach, fallback, transliteracja albo podmiana calego pliku) i wracaja do
m_FontData. Gdy w grze sa i fonty TMP, i zwykle - po naprawie TMP-ow skrypt
pyta o reszte; zrodla fontow dynamicznych sa z tej listy odsiewane, bo poszly
juz razem ze swoim TMP-em.

Stary TextMesh Pro (<= 1.0.x, gry z Unity 5.x/2017) ma inny typetree -
m_fontInfo + m_glyphInfoList zamiast m_FaceInfo + m_GlyphTable/m_CharacterTable,
wspolrzedne glifow liczone od gory atlasu. Takie fonty sa tlumaczone na widok
nowoczesny przy odczycie i z powrotem przy zapisie (legacy_to_modern /
modern_to_legacy), wiec cala reszta dziala bez zmian.

Ograniczenia FreeType: spread SDF <= 32, wiec padding > 32 jest zmniejszany
do 32 z proporcjonalnym przeskalowaniem pointSize (proporcje efektow typu
glow zostaja zachowane). Gdy glify sie nie mieszcza, atlas jest najpierw
powiekszany (do ATLAS_MAX; _TextureWidth/Height w materialach sa wtedy
aktualizowane), a dopiero w ostatecznosci zmniejszany jest pointSize.

Fonty, ktorymi polskiego tekstu i tak nie da sie wyswietlic - azjatyckie
(jp/ko/zh) i inne bez lacinskiego alfabetu (ikony, symbole) albo bez podstawowych liter a c e l n o s z - sa ODSIEWANE
przed naprawa: zostaja na liscie z powodem, ale nie maja podgladu i nie wchodza
do domyslnego zestawu do naprawy (mozna je wskazac numerem recznie). Kryterium
jest realne pokrycie fontu (m_CharacterTable / cmap zrodlowego TTF), nie nazwa.

Przed pytaniem "ktore naprawic?" kazdy nieodsiany font jest zrzucany jako PNG
do folderu font_preview/ obok skryptu (numer w nazwie = numer na liscie):
statyczne jako biezacy atlas SDF, dynamiczne jako probka tekstu z ich TTF.

Po naprawie kazdy font dostaje drugi podglad - tym razem ZLOZONY NAPIS - do
folderu fixed_preview/ (obok fixed_fonts/, a w trybie PATCH obok skryptu), razem
z kontrola pochodzenia polskich liter: czy sa z wlasnych glifow fontu, zlozone,
z OBCEGO fontu fallback (jedyny wariant, ktory zmienia krój i rozmiar litery),
czy tylko transliterowane. Atlas tego nie pokazuje, bo nie widac na nim metryk -
patrz render_text_sample.py.

Tryby pracy (pytanie na poczatku):
  [1] PATCH   - naprawione fonty sa od razu wstrzykiwane do plikow gry
                (backup: <plik>.bak_plfont),
  [2] EKSPORT - naprawione fonty trafiaja do folderu fixed_fonts/ obok
                skryptu (<nazwa>.json z typetree TMP + metadanymi oraz
                <nazwa>.png z atlasem; dla fontow dynamicznych i zwyklych
                assetow Font <nazwa>.ttf),
                a ich podglady do fixed_preview/. Gra nie jest modyfikowana.

Skan plikow gry idzie w kilku procesach (pliki sa niezalezne, a caly czas siedzi
w rozpakowywaniu bundli i parsowaniu naglowkow obiektow) - patrz --jobs.

Tryb --auto (dla skryptow i CI): skrypt nie zadaje ZADNEGO pytania - kazde
z nich dostaje odpowiedz domyslna, czyli te, ktora daje Enter: EKSPORT do
fixed_fonts/, wszystkie fonty bez polskich znakow, glify zostaja z biezacego
atlasu i dopisywane sa tylko brakujace litery, fonty UI Text tez naprawiane.
Tryb interaktywny (z pelnym menu wyborow) jest nadal DOMYSLNY - --auto to
tylko skrot, nie zamiennik. Kod wyjscia: 0 = naprawiono, 1 = czesc fontow
sie nie udala, 2 = nie bylo czego naprawiac.

Uzycie:
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra"            # cala gra, pytania jak dotad
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra" shared     # tylko pliki z "shared" w nazwie
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra" --jobs 8   # 8 procesow skanu (1 = bez rownoleglosci)
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra" --auto     # bez pytan, eksport do fixed_fonts/
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra" --auto --patch            # bez pytan, wprost do gry
  python fix_tmp_polish_fonts.py "E:\\Games\\Gra" --auto --fallback Inter.ttf \\
      --export-dir game_specific/unity/gra/fixed_fonts
  python fix_tmp_polish_fonts.py --help                      # pelna lista opcji
"""
import copy
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import warnings

import UnityPy
import freetype
import numpy as np

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# pomocnicze moduly (generate_tmp_sdf, render_text_sample...) leza w narzedzia/
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "narzedzia"))
import generate_tmp_sdf as gen  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unitypy_format23  # noqa: E402
unitypy_format23.enable()
import system_fonts  # noqa: E402  (ten sam font zainstalowany w systemie)

# font_fixer/fix_polish_fonts.py umie DOROBIC polska litere w samym foncie
# (litera bazowa + akcent wyciety z innego glifu tego samego kroju, a ogonek
# i przekreslenie narysowane od zera) zamiast renderowac znak calkowicie obcy
# krojowo z fallbacku. Bierzemy z niego zarowno gotowe fix_font (dla plikow
# TTF: fonty dynamiczne i fallback), jak i same stale proporcje ogonka/belki,
# ktore odtwarzamy na pikselach atlasu - patrz SYNTH_FULL nizej.
# font_fixer siedzi w tools/ (dawniej w korzeniu repo). Bez niego po cichu
# znika cale skladanie liter z wlasnych glifow atlasu - zostaje tylko fallback
# i transliteracja - wiec szukamy w obu miejscach i glosno mowimy, gdy go brak.
# fix_polish_fonts.py lezy poziom wyzej (tools/font_fixer/), to ten sam silnik
# kroju, ktorego uzywa narzedzie dla Unreala
_FONT_FIXER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    sys.path.insert(0, _FONT_FIXER_DIR)
    import fix_polish_fonts as accent_composer  # noqa: E402
except ImportError as _e:
    print(f"! nie udalo sie zaimportowac font_fixer/fix_polish_fonts.py ({_e}) -"
          f" dorabianie liter z wlasnych glifow fontu bedzie niedostepne")
    accent_composer = None

ACUTE_CHARS = ({ch for ch, (_, kind) in accent_composer.ACCENTS.items() if kind == "acute"}
              if accent_composer else set())

# Zakres dorabiania brakujacych liter z WLASNYCH glifow naprawianego fontu:
#   True  - wszystkie (jak fix_polish_fonts.py z full_set): kreska i kropka
#           wyciete z fontu, ogonek (ą ę) i przekreslenie (ł) dorysowane
#           geometrycznie. Font fallback zostaje tylko na resztki.
#   False - tylko kreska i kropka (ć ń ó ś ź ż); ą ę ł ida z fallbacku.
# Kreska i kropka, gdy nie ma ich z czego wyciac, sa dorysowywane w OBU trybach
# (SYNTH_ALWAYS_KINDS) - alternatywa jest litera z obcego kroju.
# Ustawiane raz na starcie (ask_synth_mode) i uzywane we wszystkich sciezkach:
# atlas statyczny, regeneracja z TTF i naprawa konturow fontu dynamicznego.
SYNTH_FULL = True

# Tryb "nie pytaj wiecej": wlaczany opcja "dorob z wlasnych glifow DLA WSZYSTKICH"
# w menu naprawy fontu. Od tego momentu kazdy kolejny font (statyczny i dynamiczny)
# leci ta sama sciezka bez pytania.
AUTO_SYNTH = False
# Font fallback wybrany kiedykolwiek przez uzytkownika - w trybie AUTO_SYNTH
# uzywamy go ponownie zamiast pytac; None = zostaje transliteracja.
AUTO_FALLBACK = None
# Szukanie w systemie (C:\Windows\Fonts, ~/.fonts...) tego samego fontu co w grze,
# zeby polskie litery statycznego atlasu SDF wziac z prawdziwego TTF. --no-system-fonts
# wylacza.
USE_SYSTEM_FONTS = True

# Tryb --auto: skrypt NIE zadaje ani jednego pytania. Kazde `ask()` zwraca
# wartosc domyslna (ta sama, ktora daje Enter w trybie interaktywnym), wiec
# da sie go wolac z innego skryptu / CI, gdzie nie ma kogo pytac.
AUTO = False


def ask(prompt, default=""):
    """input() z obsluga trybu --auto (zwraca `default` bez pytania).

    Wszystkie pytania skryptu ida przez te funkcje - dzieki temu --auto nie
    moze zawisnac na zapomnianym input(), a w logu widac, co automat wybral.
    """
    if AUTO:
        print(f"{ask_color(prompt)}{default or '<Enter>'}   (automat)")
        return default
    return input(ask_color(prompt))


def ask_color(prompt):
    """Pytanie do uzytkownika na blekitno (wciecie i puste linie bez koloru)."""
    body = prompt.lstrip("\n ")
    return f"{prompt[:len(prompt) - len(body)]}\033[96m{body.rstrip(' ')}\033[0m "


def remember_fallback(fb, desc):
    """Zapamietuje ostatni wybrany font fallback (do trybu AUTO_SYNTH)."""
    global AUTO_FALLBACK
    if fb:
        AUTO_FALLBACK = (fb, desc)


def auto_fallback(need):
    """(bajty, opis) zapamietanego fallbacku albo (None, None)."""
    if not AUTO_SYNTH or AUTO_FALLBACK is None:
        return None, None
    fb, desc = AUTO_FALLBACK
    print(f"  (automat) fallback dla {''.join(need)}: {desc!r}")
    return fb, desc


def ask_synth_mode():
    """Pytanie o zakres dorabiania liter z wlasnych glifow fontu."""
    global SYNTH_FULL
    if accent_composer is None:
        print("\n! brak modulu font_fixer/fix_polish_fonts.py - dorabianie liter"
              " z wlasnych glifow bedzie niedostepne")
        SYNTH_FULL = False
        return
    if AUTO:
        print("\nTryb dorabiania (automat): "
              + ("wszystkie litery z wlasnych glifow" if SYNTH_FULL
                 else "tylko kreska i kropka"))
        return
    print("\nDorabianie brakujacych polskich liter z WLASNYCH glifow fontu:")
    print("  [1] WSZYSTKIE (ą ć ę ł ń ó ś ź ż) - kreska i kropka wyciete z fontu,"
          " ogonek i")
    print("      przekreslenie dorysowane geometrycznie (jak font_fixer);"
          " fallback tylko na resztki")
    print("  [2] TYLKO kreska i kropka (ć ń ó ś ź ż) - ą ę ł biora sie"
          " z fontu FALLBACK")
    print("      (kreska i kropka, gdy nie ma ich z czego wyciac, sa dorysowywane"
          " w obu trybach)")
    while True:
        ans = ask("Wybor [1]: ", "1" if SYNTH_FULL else "2").strip()
        if ans in ("", "1"):
            SYNTH_FULL = True
            break
        if ans == "2":
            SYNTH_FULL = False
            break
    print("Tryb dorabiania: " + ("wszystkie litery z wlasnych glifow"
                                 if SYNTH_FULL else "tylko kreska i kropka"))


# ---------------------------------------------------------------------------
# Switch: bundle pakowane streamowanym LZ4 (bloki zalezne od poprzednich).
# python-lz4 nie umie takich blokow, wiec bloki nie do zdekodowania standardowo
# dekodujemy recznie z 64KB historia; zdekodowany blok moze zawierac na
# poczatku powtorke koncowki poprzedniego bloku - bierzemy ostatnie `size` B.
# ---------------------------------------------------------------------------

def _lz4_decode_with_history(src, hist):
    out = bytearray(hist)
    base = len(out)
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1
                lit += b
                if b != 255:
                    break
        if lit:
            out += src[i:i + lit]
            i += lit
        if i >= n:
            break
        offs = src[i] | (src[i + 1] << 8); i += 2
        ml = (token & 15) + 4
        if (token & 15) == 15:
            while True:
                b = src[i]; i += 1
                ml += b
                if b != 255:
                    break
        if offs == 0 or offs > len(out):
            raise ValueError("LZ4: offset poza oknem")
        if offs >= ml:
            s = len(out) - offs
            out += out[s:s + ml]
        else:
            pattern = bytes(out[-offs:])
            out += (pattern * (ml // offs + 1))[:ml]
    return bytes(out[base:])


def patch_unitypy_switch_lz4():
    from UnityPy.files.BundleFile import BundleFile
    if getattr(BundleFile, "_switch_lz4_patched", False):
        return
    orig = BundleFile.decompress_data

    def patched(self, compressed_data, uncompressed_size, flags, index=0):
        comp = int(flags) & 0x3F
        try:
            res = orig(self, compressed_data, uncompressed_size, flags, index)
        except Exception:
            if comp not in (2, 3):  # 2/3 = LZ4/LZ4HC
                raise
            hist = getattr(self, "_switch_lz4_hist", b"")
            res = _lz4_decode_with_history(compressed_data, hist)
            if len(res) < uncompressed_size:
                raise
            res = res[-uncompressed_size:]
        if comp in (2, 3):
            self._switch_lz4_hist = res[-65536:]
        return res

    BundleFile.decompress_data = patched
    BundleFile._switch_lz4_patched = True


# ---------------------------------------------------------------------------
# Addressables: MonoScripty leza w innym bundlu niz assety. UnityPy szuka
# CAB-ow jako plikow na dysku, wiec budujemy indeks CAB -> bundle (czytajac
# tylko naglowki bundli) i doladowujemy wlasciwy bundle na zadanie.
# ---------------------------------------------------------------------------

_cab_index_cache = {}


def _bundle_cab_names(path):
    """Lista nazw CAB-ow w bundlu UnityFS bez dekompresji danych."""
    import lz4.block
    with open(path, "rb") as f:
        head = f.read(64)
        if not head.startswith(b"UnityFS\0"):
            return []
        f.seek(0)
        data = f.read(4096)
        off = data.index(b"\0") + 1
        ver = struct.unpack_from(">I", data, off)[0]; off += 4
        off = data.index(b"\0", off) + 1
        off = data.index(b"\0", off) + 1
        size, cbis, ubis, flags = struct.unpack_from(">QIII", data, off)
        off += 20
        if ver >= 7:
            off = (off + 15) & ~15
        comp = flags & 0x3F
        if flags & 0x80:  # blocksInfo na koncu pliku
            f.seek(-cbis, 2)
            raw = f.read(cbis)
        else:
            if off + cbis > len(data):
                f.seek(off)
                raw = f.read(cbis)
            else:
                raw = data[off:off + cbis]
        if comp in (2, 3):
            bi = lz4.block.decompress(raw, ubis)
        elif comp == 0:
            bi = raw
        else:
            return []  # lzma - nieistotne tutaj
        bo = 16
        nblocks = struct.unpack_from(">i", bi, bo)[0]; bo += 4 + nblocks * 10
        nnodes = struct.unpack_from(">i", bi, bo)[0]; bo += 4
        names = []
        for _ in range(nnodes):
            bo += 20  # offset u64 + size u64 + flags u32
            end = bi.index(b"\0", bo)
            names.append(bi[bo:end].decode("utf8", "replace"))
            bo = end + 1
        return names


def _get_cab_index(folder):
    folder = os.path.abspath(folder)
    if folder in _cab_index_cache:
        return _cab_index_cache[folder]
    index = {}
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            if not fn.lower().endswith(".bundle"):
                continue
            fp = os.path.join(root, fn)
            try:
                for cab in _bundle_cab_names(fp):
                    index[cab.lower()] = fp
            except Exception:
                continue
    _cab_index_cache[folder] = index
    return index


def patch_unitypy_cab_resolver():
    from UnityPy.environment import Environment, simplify_name
    if getattr(Environment, "_cab_resolver_patched", False):
        return
    orig = Environment.find_file

    def patched(self, name, is_dependency=True):
        try:
            return orig(self, name, is_dependency)
        except FileNotFoundError:
            if not self.path or not os.path.isdir(self.path):
                raise
            simple = simplify_name(name)
            target = _get_cab_index(self.path).get(simple)
            if not target:
                raise
            self.load_file(target, is_dependency=True)
            cab = self.get_cab(simple)
            if cab:
                return cab
            raise

    Environment.find_file = patched
    Environment._cab_resolver_patched = True


patch_unitypy_switch_lz4()
patch_unitypy_cab_resolver()

PL_CHARS = "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"
# 00A0-00BF = symbole Latin-1 (© ° « » ± itd.), BEZ liter akcentowanych
# 00C0-00FF (à é ñ ü ...): nie dogenerowujemy ich - font, ktory je ma, zachowa
# je przez unie z m_CharacterTable; fontom, ktore ich nie mialy, tylko zapychaly
# atlas (60 glifow). 00D7/00F7 = znaki mnozenia/dzielenia, Ó/ó sa w PL_CHARS.
RANGES = "0020-007E,00A0-00BF,00D7,00F7,2010-2030"
MAX_SPREAD = 32
MIN_POINT_SIZE = 40
ATLAS_MAX = 16384  # limit tekstury Unity; rosnie tylko potrzebna os, bez skalowania glifow
BACKUP_SUFFIX = ".bak_plfont"
# porownywane z fname.lower(), wiec WSZYSTKIE wpisy musza byc male literami -
# ".resS" nie pasowal do niczego i pliki .resS byly niepotrzebnie otwierane
SKIP_SUFFIX = (".ress", ".resource", ".manifest", ".dll", ".json", ".xml",
               ".txt", ".png", ".jpg", ".config", ".info", ".dat", ".pdb",
               ".bak_plfont", ".bak_font", ".bak_pl", ".bak")

ANSI_GREEN = "\033[92m"
ANSI_BOLD = "\033[1m"
ANSI_RESET = "\033[0m"


def _enable_ansi_windows():
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        kernel32.GetConsoleMode(h, ctypes.byref(mode))
        kernel32.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


_enable_ansi_windows()


def green(text):
    return f"{ANSI_GREEN}{text}{ANSI_RESET}"


def bold(text):
    return f"{ANSI_BOLD}{text}{ANSI_RESET}"


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def safe_name(name):
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip()


# (path, serialized_name, path_id) -> nazwa bazowa plikow w fixed_fonts/
_export_keys = {}


def export_key(font_info):
    """Nazwa bazowa plikow eksportu. Ta sama nazwa fontu wystepuje czesto w
    kilku plikach gry (np. 4x 'LiberationSans SDF'), a kazde wystapienie to
    OSOBNY asset do spatchowania - bez rozroznienia nadpisywalyby sie w
    fixed_fonts/. Pierwsze wystapienie zostaje przy czystej nazwie (zgodnosc
    z wczesniej wyeksportowanymi folderami), kolejne dostaja sufiks."""
    ident = (os.path.abspath(font_info["path"]), font_info.get("serialized_name"),
             font_info["path_id"])
    if ident in _export_keys:
        return _export_keys[ident]
    base = safe_name(font_info["name"]) or "font"
    key = base
    if key in _export_keys.values():
        src = safe_name(os.path.splitext(os.path.basename(font_info["path"]))[0])
        key = f"{base}__{src}__{font_info['path_id']}"
        n = 1
        while key in _export_keys.values():
            n += 1
            key = f"{base}__{src}__{font_info['path_id']}_{n}"
    _export_keys[ident] = key
    return key


GLYPH_PROTO = {
    "m_Index": 0,
    "m_Metrics": {"m_Width": 0.0, "m_Height": 0.0, "m_HorizontalBearingX": 0.0,
                  "m_HorizontalBearingY": 0.0, "m_HorizontalAdvance": 0.0},
    "m_GlyphRect": {"m_X": 0, "m_Y": 0, "m_Width": 0, "m_Height": 0},
    "m_Scale": 1.0, "m_AtlasIndex": 0, "m_ClassDefinitionType": 0,
}
CHAR_PROTO = {"m_ElementType": 1, "m_Unicode": 0, "m_GlyphIndex": 0, "m_Scale": 1.0}


# ---------------------------------------------------------------------------
# STARY TextMesh Pro (<= 1.0.x, gry z Unity 5.x / 2017)
#
# Ma zupelnie inny typetree niz TMP 1.4+, na ktorym oparta jest reszta skryptu:
#   m_fontInfo          zamiast m_FaceInfo (pola bez prefiksu m_, PointSize,
#                       Padding, AtlasWidth/AtlasHeight jako float),
#   atlas (jeden PPtr)  zamiast tablicy m_AtlasTextures,
#   m_glyphInfoList     = POLACZONA tabela glifow i znakow - kluczem jest wprost
#                       unicode ("id"), a prostokat w atlasie jest TOP-DOWN
#                       (y liczone od gory atlasu, nie od dolu jak m_GlyphRect),
#   brak m_AtlasRenderMode i m_AtlasPopulationMode - atlas jest zawsze
#                       statyczny, a o SDF vs bitmapa mowi fontAssetType
#                       (0 = bitmapa, 1 = SDF).
#
# Zamiast dublowac cala logike naprawy, taki font tlumaczymy raz na widok
# "nowoczesny" (legacy_to_modern), pracujemy na nim jak na kazdym innym,
# a tuz przed zapisem wracamy do oryginalnego ukladu (modern_to_legacy).
# ---------------------------------------------------------------------------

# m_fontInfo -> m_FaceInfo
LEGACY_FACE_FIELDS = {
    "Name": "m_FamilyName",
    "PointSize": "m_PointSize",
    "Scale": "m_Scale",
    "LineHeight": "m_LineHeight",
    "Baseline": "m_Baseline",
    "Ascender": "m_AscentLine",
    "CapHeight": "m_CapLine",
    "Descender": "m_DescentLine",
    "CenterLine": "m_MeanLine",
    "SuperscriptOffset": "m_SuperscriptOffset",
    "SubscriptOffset": "m_SubscriptOffset",
    "SubSize": "m_SubscriptSize",
    "Underline": "m_UnderlineOffset",
    "UnderlineThickness": "m_UnderlineThickness",
    "strikethrough": "m_StrikethroughOffset",
    "strikethroughThickness": "m_StrikethroughThickness",
    "TabWidth": "m_TabWidth",
}


def is_legacy_tmp(tree):
    return "m_fontInfo" in tree and "m_FaceInfo" not in tree


def legacy_to_modern(tree):
    """Widok starego TMP_FontAsset w polach TMP 1.4+ (tylko do odczytu przez
    reszte skryptu - oryginal zostaje nietkniety)."""
    fi = tree["m_fontInfo"]
    atlas_w = int(round(float(fi["AtlasWidth"])))
    atlas_h = int(round(float(fi["AtlasHeight"])))

    face = {LEGACY_FACE_FIELDS[k]: v for k, v in fi.items() if k in LEGACY_FACE_FIELDS}
    face.setdefault("m_FamilyName", tree.get("m_Name", ""))
    face.setdefault("m_StyleName", "")

    glyphs, chars, seen = [], [], set()
    for g in tree.get("m_glyphInfoList") or []:
        cp = int(g["id"])
        if cp in seen:      # aliasy tego samego znaku - liczy sie pierwszy
            continue
        seen.add(cp)
        w, h = float(g["width"]), float(g["height"])
        rw, rh = int(round(w)), int(round(h))
        # (x, y) starego TMP to LEWY-GORNY rog rectu liczony od gory atlasu;
        # m_GlyphRect liczy od dolu
        rx = int(round(float(g["x"])))
        ry_top = int(round(float(g["y"])))
        glyphs.append({
            "m_Index": cp,
            "m_Metrics": {"m_Width": w, "m_Height": h,
                          "m_HorizontalBearingX": float(g["xOffset"]),
                          "m_HorizontalBearingY": float(g["yOffset"]),
                          "m_HorizontalAdvance": float(g["xAdvance"])},
            "m_GlyphRect": {"m_X": rx, "m_Y": atlas_h - ry_top - rh,
                            "m_Width": rw, "m_Height": rh},
            "m_Scale": 1.0, "m_AtlasIndex": 0, "m_ClassDefinitionType": 0,
        })
        # w starym formacie glif JEST znakiem, wiec indeks glifu = unicode
        chars.append({"m_ElementType": 1, "m_Unicode": cp, "m_GlyphIndex": cp,
                      "m_Scale": 1.0})

    return {
        "m_Name": tree.get("m_Name", ""),
        "m_FaceInfo": face,
        "m_GlyphTable": glyphs,
        "m_CharacterTable": chars,
        "m_AtlasTextures": [dict(tree.get("atlas") or {})],
        "m_AtlasWidth": atlas_w,
        "m_AtlasHeight": atlas_h,
        "m_AtlasPadding": int(round(float(fi["Padding"]))),
        "m_AtlasPopulationMode": 0,     # stary TMP nie zna fontow dynamicznych
        "m_AtlasRenderMode": (None if int(tree.get("fontAssetType", 1)) == 1
                              else gen.RASTER_MODE_BITMAP | gen.RASTER_MODE_8BIT),
        "m_UsedGlyphRects": [],
        "m_FreeGlyphRects": [],
    }


def modern_to_legacy(legacy, modern):
    """Wynik naprawy z widoku nowoczesnego z powrotem do starego typetree.
    Modyfikuje `legacy` w miejscu i zwraca go (to on idzie do save_typetree)."""
    fi = legacy["m_fontInfo"]
    atlas_w, atlas_h = int(modern["m_AtlasWidth"]), int(modern["m_AtlasHeight"])
    face = modern["m_FaceInfo"]
    for lk, mk in LEGACY_FACE_FIELDS.items():
        if lk in fi and mk in face:
            fi[lk] = face[mk] if isinstance(fi[lk], str) else float(face[mk])
    fi["AtlasWidth"] = float(atlas_w)
    fi["AtlasHeight"] = float(atlas_h)
    fi["Padding"] = float(modern["m_AtlasPadding"])

    by_index = {g["m_Index"]: g for g in modern["m_GlyphTable"]}
    out = []
    for c in modern["m_CharacterTable"]:
        g = by_index.get(c["m_GlyphIndex"])
        if g is None:
            continue
        r = g["m_GlyphRect"]
        rw, rh = int(r["m_Width"]), int(r["m_Height"])
        m = g["m_Metrics"]
        out.append({
            "id": int(c["m_Unicode"]),
            "x": float(r["m_X"]),
            "y": float(atlas_h - int(r["m_Y"]) - rh),
            # jedno pole opisuje i rozmiar quada, i wycinek atlasu - musi wiec
            # byc rozmiarem RECTU (inaczej glif bylby rozciagniety)
            "width": float(rw), "height": float(rh),
            "xOffset": float(m["m_HorizontalBearingX"]),
            "yOffset": float(m["m_HorizontalBearingY"]),
            "xAdvance": float(m["m_HorizontalAdvance"]),
            "scale": 1.0,
        })
    legacy["m_glyphInfoList"] = out
    if "CharacterCount" in fi:
        fi["CharacterCount"] = len(out)
    return legacy


# ---------------------------------------------------------------------------
# TypeTreeGenerator (patch na UnityPy 1.25: dziala tylko get_nodes_as_json,
# nazwa assembly musi byc bez ".dll")
# ---------------------------------------------------------------------------

_GENERATOR = None
_GENERATOR_ERROR = None


def patch_typetree_generator():
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


def find_dll_folder(data_dir):
    """Folder z DLLami Mono (Managed), o ile w ogóle zawiera .dll."""
    managed = os.path.join(data_dir, "Managed")
    if os.path.isdir(managed) and any(f.endswith(".dll") for f in os.listdir(managed)):
        return managed
    return None


def ask_reference_dlls(data_dir):
    """Konsolowe buildy (Switch) sa IL2CPP i NIE maja DLLi - jest tylko
    global-metadata.dat, a kodu natywnego (main/NSO) nie ma nawet w Data.

    TypeTreeGenerator nie ma z czego zbudowac typetree, wiec bierzemy DLLe
    z wersji Mono TEJ SAMEJ gry (zwykle PC). Uklad pol MonoBehaviour jest
    ten sam, o ile zgadza sie wersja gry i Unity.
    """
    env = os.environ.get("TTG_DLL_DIR")
    if env:
        print(f"[ttg] DLLe referencyjne z TTG_DLL_DIR: {env}")
        return env

    meta = os.path.join(data_dir, "Managed", "Metadata", "global-metadata.dat")
    print("\n[ttg] Ta gra to build IL2CPP bez DLLi (global-metadata.dat"
          f" {'jest' if os.path.exists(meta) else 'brak'}, Managed/ bez *.dll).")
    print("[ttg] Zeby odczytac MonoBehaviour, podaj wersje Mono tej samej gry")
    print("[ttg] (np. instalke PC) - wystarczy folder gry albo sam Managed.")
    path = ask("[ttg] Sciezka do wersji PC (Enter = pomin): ").strip().strip('"')
    if not path:
        return None
    if os.path.isdir(os.path.join(path, "Managed")):
        return os.path.join(path, "Managed")
    if os.path.basename(path).lower() == "managed":
        return path
    try:
        ref_data, _ = find_data_dir(path)
    except SystemExit:
        print(f"[ttg] Nie znalazlem danych Unity w {path}")
        return None
    return find_dll_folder(ref_data)


def get_generator(game_root, data_dir, unity_version):
    global _GENERATOR, _GENERATOR_ERROR
    if _GENERATOR is not None:
        return _GENERATOR
    if _GENERATOR_ERROR is not None:
        raise RuntimeError(_GENERATOR_ERROR)
    # Bundle z wycietym numerem wersji nadal raportuje 0.0.0 w SerializedFile.
    # Generator musi dostac wersje gry, inaczej buduje zly layout MonoBehaviour
    # (np. 17 fontow w sharedassets0.assets w Bye Sweet Carole).
    if not unity_version or str(unity_version).startswith("0."):
        unity_version = UnityPy.config.FALLBACK_UNITY_VERSION
    if not unity_version or str(unity_version).startswith("0."):
        raise RuntimeError("Brak wersji Unity do wygenerowania typetree")
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    patch_typetree_generator()
    print(f"[ttg] TypeTreeGenerator dla Unity {unity_version}...")
    ttg = TypeTreeGenerator(unity_version)
    # Windows: GameAssembly.dll + il2cpp_data; Linux/Android: GameAssembly.so /
    # libil2cpp.so + il2cpp_data albo Managed/Metadata (assets/bin/Data z APK).
    il2cpp = next((p for p in (os.path.join(game_root, n) for n in (
        "GameAssembly.dll", "GameAssembly.so", "libil2cpp.so")) if os.path.exists(p)),
        os.path.join(game_root, "GameAssembly.dll"))
    metadata = next((p for p in (
        os.path.join(data_dir, "il2cpp_data", "Metadata", "global-metadata.dat"),
        os.path.join(data_dir, "Managed", "Metadata", "global-metadata.dat"))
        if os.path.exists(p)),
        os.path.join(data_dir, "il2cpp_data", "Metadata", "global-metadata.dat"))
    local_dlls = find_dll_folder(data_dir)
    if os.path.exists(il2cpp) and os.path.exists(metadata):
        print("[ttg] gra IL2CPP - laduje GameAssembly.dll + global-metadata.dat")
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
    elif local_dlls:
        print(f"[ttg] gra Mono - laduje DLLe z {local_dlls}")
        ttg.load_local_dll_folder(local_dlls)
    else:
        ref = ask_reference_dlls(data_dir)
        if ref:
            print(f"[ttg] laduje DLLe referencyjne z {ref}")
            ttg.load_local_dll_folder(ref)
        else:
            print("[ttg] BRAK DLLi - MonoBehaviour (fonty TMP) beda pomijane!")
    _GENERATOR = ttg
    return ttg


# ---------------------------------------------------------------------------
# Skanowanie
# ---------------------------------------------------------------------------

def serialized_files_of(env):
    """Wewnetrzne SerializedFile danego env.

    Plik .assets/levelN ma dokladnie jeden, bundle ma ich wiele (CAB-xxx,
    CAB-xxx.sharedAssets...). env.file bundla to BundleFile - kontener, ktory
    NIE ma ani obiektow, ani externali, wiec nigdy nie wolno go pytac wprost."""
    files = list(getattr(env, "assets", None) or [])
    if files:
        return files
    f = getattr(env, "file", None)
    return [f] if getattr(f, "externals", None) is not None else []


class GameFiles:
    """Cache zaladowanych plikow + sledzenie modyfikacji."""

    def __init__(self, data_dir, game_root):
        self.data_dir = data_dir
        self.game_root = game_root
        self.envs = {}      # abspath -> env
        self.modified = set()
        self.cab_index = {}         # nazwa SerializedFile -> plik na dysku
        self._cab_index_full = False
        self._disk_index = None     # nazwa pliku (lower) -> pelna sciezka

    def env(self, path):
        path = os.path.abspath(path)
        if path not in self.envs:
            e = UnityPy.load(path)
            try:
                uv = next(iter(e.assets)).unity_version
                e.typetree_generator = get_generator(self.game_root, self.data_dir, uv)
            except (StopIteration, RuntimeError):
                pass
            self.envs[path] = e
            self.register_cabs(path, e)
        return self.envs[path]

    # --- indeks CAB-ow (nazwa wewnetrznego SerializedFile -> plik na dysku) ---

    def register_cabs(self, path, env):
        self.register_cab_names(path, [getattr(sf, "name", None)
                                       for sf in serialized_files_of(env)])

    def register_cab_names(self, path, names):
        """Wariant dla skanu rownoleglego - z workera wracaja same nazwy
        (SerializedFile nie przechodzi przez pickle)."""
        for name in names:
            if name:
                self.cab_index.setdefault(name, os.path.abspath(path))

    def cab_file(self, name):
        path = self.cab_index.get(name)
        if path is None and not self._cab_index_full:
            self._build_cab_index()
            path = self.cab_index.get(name)
        return path

    def _build_cab_index(self):
        print("  (indeksuje pliki gry po nazwach CAB...)", file=sys.stderr)
        for fpath in iter_asset_files(self.data_dir):
            try:
                self.register_cabs(fpath, UnityPy.load(fpath))
            except Exception:
                continue
        self._cab_index_full = True

    def _find_on_disk(self, name):
        if self._disk_index is None:
            idx = {}
            for root, _dirs, files in os.walk(self.data_dir):
                for f in files:
                    idx.setdefault(f.lower(), os.path.join(root, f))
            self._disk_index = idx
        return self._disk_index.get(name.lower())

    # --- PPtr -> konkretny plik + konkretny SerializedFile w nim ---

    def resolve_ref(self, from_path, file_id, serialized_name=None):
        """PPtr -> (sciezka pliku na dysku, nazwa SerializedFile albo None).

        m_FileID == 0 znaczy "ten sam SerializedFile", wiec zwracamy zrodlo bez
        zadnego szukania. Dla m_FileID > 0 lista externali jest wlasnoscia
        KONKRETNEGO SerializedFile (nie calego bundla), a wpisy w bundlach maja
        postac 'archive:/CAB-xxx/CAB-yyy' - nazwa pliku na dysku w ogole tam nie
        wystepuje i trzeba jej szukac w indeksie CAB-ow."""
        if not file_id:
            return os.path.abspath(from_path), serialized_name
        files = serialized_files_of(self.env(from_path))
        sf = None
        if serialized_name:
            sf = next((f for f in files
                       if getattr(f, "name", None) == serialized_name), None)
        if sf is None:
            cands = [f for f in files if len(getattr(f, "externals", []) or []) >= file_id]
            if len(cands) == 1:
                sf = cands[0]
            elif not cands:
                raise LookupError(f"{os.path.basename(from_path)}: brak externala "
                                  f"#{file_id}")
            else:
                raise LookupError(
                    f"{os.path.basename(from_path)}: PPtr m_FileID={file_id} bez "
                    f"wskazania pliku wewnetrznego ({len(cands)} kandydatow)")
        ext = (sf.externals[file_id - 1].path or "").replace("\\", "/")
        if ext.startswith("archive:/"):
            cab = ext.rsplit("/", 1)[-1]
            path = self.cab_file(cab)
            if path is None:
                raise FileNotFoundError(f"Nie znaleziono pliku z {cab}")
            return path, cab
        name = os.path.basename(ext)
        path = self._find_on_disk(name)
        if path is None:
            raise FileNotFoundError(f"Nie znaleziono pliku zewnetrznego: {name}")
        return path, None

    def save_modified(self):
        for path in sorted(self.modified):
            backup = path + BACKUP_SUFFIX
            if not os.path.exists(backup):
                shutil.copy2(path, backup)
                print(f"Backup: {backup}")
            data = self.envs[path].file.save()
            with open(path, "wb") as f:
                f.write(data)
            print(f"Zapisano: {path}")


def serialized_file_name(obj):
    """Nazwa wewnetrznego SerializedFile; bundle moze miec powtarzajace sie path_id."""
    assets_file = getattr(obj, "assets_file", None)
    return getattr(assets_file, "name", None)


def _raw_read_string(raw, pos):
    if pos + 4 > len(raw):
        raise ValueError("string poza koncem obiektu")
    size = struct.unpack_from("<i", raw, pos)[0]
    if size < 0 or pos + 4 + size > len(raw):
        raise ValueError(f"nieprawidlowa dlugosc stringa: {size}")
    start = pos + 4
    end = start + size
    return raw[start:end].decode("utf-8", "replace"), end + (-end % 4)


def read_tmp_font_raw(obj):
    """Czyta pola potrzebne do naprawy TMP_FontAsset z Unity 6000.5."""
    raw = obj.get_raw_data()
    if len(raw) < 64:
        raise ValueError("za krotki TMP_FontAsset")
    pos = 28  # m_GameObject + m_Enabled/alignment + m_Script
    name, pos = _raw_read_string(raw, pos)
    version, pos = _raw_read_string(raw, pos)
    face_index = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    family, pos = _raw_read_string(raw, pos)
    style, pos = _raw_read_string(raw, pos)
    point_size = struct.unpack_from("<f", raw, pos)[0]
    pos += 4
    scale = struct.unpack_from("<f", raw, pos)[0]
    pos += 4
    units_per_em = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    pos += 15 * 4  # pozostale metryki FaceInfo
    mat_file_id, mat_path_id = struct.unpack_from("<iq", raw, pos)
    pos += 12
    _source_guid, pos = _raw_read_string(raw, pos)

    _source_name, pos = _raw_read_string(raw, pos)
    _creation_guid, pos = _raw_read_string(raw, pos)
    pos += 9 * 4
    _sequence, pos = _raw_read_string(raw, pos)
    _referenced_font, pos = _raw_read_string(raw, pos)
    _referenced_text, pos = _raw_read_string(raw, pos)
    pos += 4 + 4 + 4 + 4  # fontStyle, modifier, renderMode, font features

    src_file_id, src_path_id = struct.unpack_from("<iq", raw, pos)
    pos += 12
    _source_path, pos = _raw_read_string(raw, pos)
    population_mode = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    internal_dynamic_os = raw[pos]
    pos += 4

    glyph_count_offset = pos
    glyph_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    if glyph_count < 0 or pos + glyph_count * 52 > len(raw):
        raise ValueError(f"nieprawidlowa liczba glifow: {glyph_count}")
    glyphs = []
    for _ in range(glyph_count):
        v = struct.unpack_from("<I5f4ifii", raw, pos)
        pos += 52
        glyphs.append({
            "m_Index": v[0],
            "m_Metrics": {"m_Width": v[1], "m_Height": v[2],
                          "m_HorizontalBearingX": v[3],
                          "m_HorizontalBearingY": v[4],
                          "m_HorizontalAdvance": v[5]},
            "m_GlyphRect": {"m_X": v[6], "m_Y": v[7],
                            "m_Width": v[8], "m_Height": v[9]},
            "m_Scale": v[10], "m_AtlasIndex": v[11],
            "m_ClassDefinitionType": v[12],
        })

    char_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    if char_count < 0 or pos + char_count * 16 > len(raw):
        raise ValueError(f"nieprawidlowa liczba znakow: {char_count}")
    chars = []
    for _ in range(char_count):
        element_type, unicode_, glyph_index, char_scale = struct.unpack_from(
            "<IIIf", raw, pos)
        pos += 16
        chars.append({"m_ElementType": element_type, "m_Unicode": unicode_,
                      "m_GlyphIndex": glyph_index, "m_Scale": char_scale})

    middle_start = pos
    atlas_count = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    if atlas_count < 0 or pos + atlas_count * 12 + 24 > len(raw):
        raise ValueError(f"nieprawidlowa liczba atlasow: {atlas_count}")
    atlases = []
    for _ in range(atlas_count):
        file_id, path_id = struct.unpack_from("<iq", raw, pos)
        pos += 12
        atlases.append({"m_FileID": file_id, "m_PathID": path_id})
    atlas_index = struct.unpack_from("<i", raw, pos)[0]
    pos += 4
    # Unity 6000.5 ma tu dodatkowe flagi wzgledem starszego TMP. Szukamy
    # czworki width/height/padding/renderMode zamiast zgadywac ich liczbe.
    # Flagi przed nimi to zwykle 1,1,1 — same w sobie "potega dwojki", wiec
    # atlas musi miec rozsadny rozmiar (>= 32), inaczej trafiamy we flagi
    # (The Boys VR, Unity 6000.3: szerokosc 1, a 1024 brane za liczbe rect-ow).
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
    pos = atlas_values_offset
    atlas_width, atlas_height, atlas_padding, atlas_render_mode = struct.unpack_from(
        "<4i", raw, pos)
    pos += 16

    def read_rects():
        nonlocal pos
        count = struct.unpack_from("<i", raw, pos)[0]
        pos += 4
        if count < 0 or pos + count * 16 > len(raw):
            raise ValueError(f"nieprawidlowa liczba prostokatow: {count}")
        result = []
        for _ in range(count):
            x, y, w, h = struct.unpack_from("<4i", raw, pos)
            pos += 16
            result.append({"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h})
        return result

    used_rects = read_rects()
    free_rects = read_rects()
    suffix_offset = pos

    if version != "1.1.0" or not name or not family:
        raise ValueError("nieznany wariant TMP_FontAsset")
    if not (1 <= point_size <= 4096 and 0 <= units_per_em <= 65536):
        raise ValueError("nieprawdopodobne metryki TMP_FontAsset")
    if population_mode not in (0, 1, 2):
        raise ValueError(f"nieznany AtlasPopulationMode: {population_mode}")
    return {
        "m_Name": name,
        "m_Version": version,
        "m_FaceInfo": {
            "m_FaceIndex": face_index,
            "m_FamilyName": family,
            "m_StyleName": style,
            "m_PointSize": int(point_size),
            "m_Scale": scale,
            "m_UnitsPerEM": units_per_em,
        },
        "m_Material": {"m_FileID": mat_file_id, "m_PathID": mat_path_id},
        "m_SourceFontFile": {"m_FileID": src_file_id, "m_PathID": src_path_id},
        "m_AtlasPopulationMode": population_mode,
        "InternalDynamicOS": internal_dynamic_os,
        "m_GlyphTable": glyphs,
        "m_CharacterTable": chars,
        "m_AtlasTextures": atlases,
        "m_AtlasTextureIndex": atlas_index,
        "m_AtlasWidth": atlas_width,
        "m_AtlasHeight": atlas_height,
        "m_AtlasPadding": atlas_padding,
        "m_AtlasRenderMode": atlas_render_mode,
        "m_UsedGlyphRects": used_rects,
        "m_FreeGlyphRects": free_rects,
        "_raw_layout": {"prefix": raw[:glyph_count_offset],
                        "middle": raw[middle_start:atlas_values_offset],
                        "suffix": raw[suffix_offset:]},
    }


def write_tmp_font_raw(tree):
    """Zapisuje zmienne tabele, pozostawiajac nieznane pola bit w bit."""
    layout = tree["_raw_layout"]
    out = bytearray(layout["prefix"])
    glyphs = tree["m_GlyphTable"]
    out += struct.pack("<i", len(glyphs))
    for glyph in glyphs:
        metrics = glyph["m_Metrics"]
        rect = glyph["m_GlyphRect"]
        out += struct.pack(
            "<I5f4ifii", glyph["m_Index"], metrics["m_Width"],
            metrics["m_Height"], metrics["m_HorizontalBearingX"],
            metrics["m_HorizontalBearingY"], metrics["m_HorizontalAdvance"],
            rect["m_X"], rect["m_Y"], rect["m_Width"], rect["m_Height"],
            glyph["m_Scale"], glyph["m_AtlasIndex"],
            glyph.get("m_ClassDefinitionType", 0))
    chars = tree["m_CharacterTable"]
    out += struct.pack("<i", len(chars))
    for char in chars:
        out += struct.pack("<IIIf", char.get("m_ElementType", 1),
                           char["m_Unicode"], char["m_GlyphIndex"],
                           char.get("m_Scale", 1.0))
    out += layout["middle"]
    out += struct.pack("<4i", tree["m_AtlasWidth"], tree["m_AtlasHeight"],
                       tree["m_AtlasPadding"], tree["m_AtlasRenderMode"])
    for key in ("m_UsedGlyphRects", "m_FreeGlyphRects"):
        rects = tree[key]
        out += struct.pack("<i", len(rects))
        for rect in rects:
            out += struct.pack("<4i", rect["m_X"], rect["m_Y"],
                               rect["m_Width"], rect["m_Height"])
    out += layout["suffix"]
    return bytes(out)


def find_object(env, path_id, serialized_name=None):
    """Znajdz obiekt, rozrozniajac pliki wewnatrz bundle po ich nazwie.

    W bundlach (zwlaszcza scenowych) path_id sa male i POWTARZAJA sie miedzy
    kolejnymi CAB-ami, wiec branie pierwszego trafienia potrafi zwrocic
    kompletnie inny obiekt (np. MonoScript zamiast Texture2D). Gdy nie da sie
    rozstrzygnac, lepiej rzucic wyjatek i pominac font niz cicho zepsuc plik."""
    matches = [obj for obj in env.objects if obj.path_id == path_id]
    if serialized_name:
        for obj in matches:
            if serialized_file_name(obj) == serialized_name:
                return obj
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LookupError(f"Brak obiektu path_id={path_id}"
                          + (f" ({serialized_name})" if serialized_name else ""))
    names = sorted({str(serialized_file_name(o)) for o in matches})
    raise LookupError(f"path_id={path_id}: {len(matches)} obiektow w roznych plikach "
                      f"wewnatrz bundla ({', '.join(names)})"
                      + (f", brak w {serialized_name}" if serialized_name else ""))


def setup_fallback_unity_version(data_dir):
    """Bundle na Switchu maja wycieta wersje Unity - wykryj ja z glownych
    plikow gry i ustaw jako fallback, inaczej UnityPy nie otworzy bundli."""
    candidates = ["globalgamemanagers", "data.unity3d", "resources.assets",
                  "level0", "level1", "sharedassets0.assets"]
    for name in candidates:
        p = os.path.join(data_dir, name)
        if not os.path.isfile(p):
            continue
        try:
            env = UnityPy.load(p)
            for f in env.assets:
                uv = str(f.unity_version)
                if uv and not uv.startswith("0."):
                    UnityPy.config.FALLBACK_UNITY_VERSION = uv
                    try:
                        from UnityPy.exceptions import UnityVersionFallbackWarning
                        warnings.simplefilter("ignore", UnityVersionFallbackWarning)
                    except ImportError:
                        pass
                    print(f"Wersja Unity: {uv}")
                    return uv
        except Exception:
            continue
    return None


def iter_asset_files(data_dir, name_filter=""):
    for root, dirs, files in os.walk(data_dir):
        dirs[:] = [d for d in dirs
                   if d not in ("GI", "il2cpp_data", "Managed", "Plugins",
                                "APVStreamingAssets")]
        for fname in files:
            if fname.lower().endswith(SKIP_SUFFIX):
                continue
            if name_filter and name_filter.lower() not in fname.lower():
                continue
            yield os.path.join(root, fname)


# ---------------------------------------------------------------------------
# Nazwa klasy MonoBehaviour = m_ClassName MonoScriptu, na ktory wskazuje
# m_Script. Sam deref jest DROGI: MonoScripty siedza w innym pliku (przy
# Addressables w osobnym bundlu), wiec pierwsze pytanie o nie wymusza
# zaladowanie i rozpakowanie tego pliku (~0,5 s).
#
# Cache per plik nic tu nie daje - kazdy bundle scenowy pyta o te same
# MonoScripty, wiec ten sam bundle zaleznosci rozpakowuje sie od nowa dla
# kazdego z 600 plikow (w Chained Echoes: 119 s z 163 s calego skanu).
# Kluczem musi byc CEL wskaznika (plik + path_id), a nie (m_FileID, path_id),
# bo m_FileID jest numerem lokalnym dla konkretnego SerializedFile.
# ---------------------------------------------------------------------------

_script_class_cache = {}


def script_target_key(fpath, obj, script_ptr):
    """Globalnie unikalny klucz celu PPtr-a m_Script."""
    sf = getattr(obj, "assets_file", None)
    if script_ptr.m_FileID == 0:    # MonoScript w tym samym SerializedFile
        return (os.path.abspath(fpath), getattr(sf, "name", None),
                script_ptr.m_PathID)
    ext = sf.externals[script_ptr.m_FileID - 1]
    path = (ext.path or getattr(ext, "name", "") or "")
    if path.startswith("archive:/"):
        path = path[9:]
    return (path.rsplit("/")[-1].lower(), script_ptr.m_PathID)


def script_class_name(fpath, obj, script_ptr):
    """m_ClassName MonoScriptu (None, gdy nie da sie rozwiazac).

    Porazki tez sa cache'owane - nierozwiazywalny wskaznik potrafi za kazdym
    razem przeszukac wszystkie bundle gry, a w pliku scenowym powtarza sie
    dziesiatki tysiecy razy.
    """
    try:
        key = script_target_key(fpath, obj, script_ptr)
    except Exception:
        return None
    if key in _script_class_cache:
        return _script_class_cache[key]
    try:
        cls = script_ptr.deref_parse_as_object().m_ClassName
    except Exception:
        cls = None
    _script_class_cache[key] = cls
    return cls


def _forget_failed_scripts():
    for key in [k for k, v in _script_class_cache.items() if v is None]:
        del _script_class_cache[key]


# Czy ponowienie pliku z generatorem typetree cokolwiek daje: None = jeszcze
# nie wiemy, False = sprawdzone i nie pomaga (nie probuj wiecej, bo kazda proba
# to drugi przebieg po wszystkich obiektach pliku). Gry, w ktorych czesc bundli
# odwoluje sie do MonoScriptow spoza builda, maja takich plikow dziesiatki.
_generator_retry_useful = None


def scan_objects(fpath, env):
    """Obiekty jednego pliku -> (tmp_fonts, ttf_fonts, materials, mb_seen, mb_failed,
    bitmap_fonts).

    mb_seen/mb_failed sluza wykryciu sytuacji, w ktorej plik ma MonoBehaviour,
    ale ZADNEGO nie udalo sie rozpoznac - wtedy warto ponowic z generatorem
    typetree (patrz scan_game).
    """
    tmp_fonts, ttf_fonts, materials, bitmap_fonts = [], [], [], []
    mb_seen = mb_failed = 0
    for obj in env.objects:
        tname = obj.type.name
        if tname == "MonoBehaviour":
            mb_seen += 1
            try:
                head = obj.parse_monobehaviour_head()
                cls = script_class_name(fpath, obj, head.m_Script)
            except Exception:
                mb_failed += 1
                continue
            if cls is None:
                mb_failed += 1
                continue
            if cls == "TMP_FontAsset":
                tmp_fonts.append({"path": os.path.abspath(fpath),
                                  "path_id": obj.path_id,
                                  "serialized_name": serialized_file_name(obj),
                                  "name": head.m_Name})
        elif tname == "Font":
            try:
                d = obj.read()
                fd = d.m_FontData or b""
            except Exception:
                continue
            if len(fd) > 1000:
                ttf_fonts.append({"path": os.path.abspath(fpath),
                                  "path_id": obj.path_id,
                                  "serialized_name": serialized_file_name(obj),
                                  "name": d.m_Name, "size": len(fd)})
            elif getattr(d, "m_CharacterRects", None):
                # font bitmapowy: bez TTF-a, z gotowym atlasem (patrz
                # "Fonty BITMAPOWE")
                bitmap_fonts.append({"path": os.path.abspath(fpath),
                                     "path_id": obj.path_id,
                                     "serialized_name": serialized_file_name(obj),
                                     "name": d.m_Name})
        elif tname == "Material":
            try:
                m = obj.read_typetree()
            except Exception:
                continue
            for name, te in m.get("m_SavedProperties", {}).get("m_TexEnvs", []):
                if name == "_MainTex":
                    tex = te.get("m_Texture", {})
                    if tex.get("m_PathID"):
                        materials.append((os.path.abspath(fpath),
                                          serialized_file_name(obj), obj.path_id,
                                          tex.get("m_FileID", 0), tex["m_PathID"]))
    return tmp_fonts, ttf_fonts, materials, mb_seen, mb_failed, bitmap_fonts


# ---------------------------------------------------------------------------
# Skan rownolegly
#
# Po tym, jak deref MonoScriptow przestal dominowac, caly pozostaly czas siedzi
# w UnityPy: rozpakowaniu bundli i sparsowaniu naglowkow wszystkich obiektow
# (w Chained Echoes 2,2 mln obiektow w 645 plikach). Tego nie da sie przyspieszyc
# w jednym procesie, ale pliki sa od siebie niezalezne, a z workera wraca sama
# picklowalna metadana (sciezki, path_id, nazwy).
#
# Worker NIE buduje generatora typetree (nie jest do skanu potrzebny, a
# get_generator moze zapytac o sciezke do DLLi - w procesie potomnym nie ma
# komu odpowiedziec). Pliki, w ktorych rozpoznanie skryptow padlo w calosci,
# wracaja do rodzica i tam sa ponawiane z generatorem.
# ---------------------------------------------------------------------------


class MaterialIndex:
    """Materialy z _MainTex ulozone po docelowej teksturze - budowane LENIWIE.

    Rozwiazanie PPtr-a tekstury wymaga zaladowania pliku materialu (a przy
    Addressables jeszcze bundla z tekstura), wiec dla calej gry to kilkanascie
    sekund. Indeks jest potrzebny dopiero przy zapisie fontu (_GradientScale,
    _TextureWidth/Height w materialach), a spora czesc sesji konczy sie na
    obejrzeniu listy fontow i podgladow.
    """

    def __init__(self, gf, materials):
        self.gf = gf
        self.materials = materials      # (path, sf, path_id, tex_fileid, tex_pathid)
        self._index = None

    def build(self):
        if self._index is None:
            self._index = {}
            for mpath, msf, mpid, tfid, tpid in self.materials:
                try:
                    tex_path, tex_sf = self.gf.resolve_ref(mpath, tfid, msf)
                except Exception:
                    continue
                self._index.setdefault(
                    (os.path.abspath(tex_path), tex_sf, tpid), []).append(
                        (mpath, msf, mpid))
        return self._index

    def get(self, key, default=None):
        return self.build().get(key, default)

    def items(self):
        return self.build().items()

    def __len__(self):
        return len(self.build())


def default_scan_jobs():
    """Zostawiamy jeden rdzen systemowi i nie przesadzamy z liczba procesow -
    kazdy trzyma w pamieci rozpakowany bundle plus jego zaleznosci. Powyzej
    4 procesow i tak nie ma zysku (waskim gardlem jest dysk i alokator).

    W buildzie one-file PyInstallera domyslnie JEDEN proces: worker spawnuje
    sie przez ponowne uruchomienie exe, czyli kazdy rozpakowuje cale archiwum
    do %TEMP% od nowa - rownoleglosc wychodzi wtedy wolniejsza niz jej brak.
    Kto chce, wymusi --jobs N."""
    if getattr(sys, "frozen", False):
        return 1
    return max(1, min(4, (os.cpu_count() or 1) - 1))


def _scan_worker_init(fallback_version):
    if fallback_version:
        UnityPy.config.FALLBACK_UNITY_VERSION = fallback_version
        try:
            from UnityPy.exceptions import UnityVersionFallbackWarning
            warnings.simplefilter("ignore", UnityVersionFallbackWarning)
        except ImportError:
            pass


def _scan_one_file(fpath):
    """(fpath, nazwy CAB-ow, tmp_fonts, ttf_fonts, materials, mb_seen, mb_failed).

    Bez generatora typetree: nazwa klasy bierze sie z MonoScriptu, a to typ
    NATYWNY (wbudowany typetree), wiec generator nie jest do tego potrzebny -
    a jego zaladowanie to kilka sekund i setki MB RAM (IL2CPP: GameAssembly.dll
    + global-metadata.dat). Podpina sie dopiero przy czytaniu samego fontu
    (GameFiles.env).
    """
    try:
        env = UnityPy.load(fpath)
        # nazwy wewnetrznych SerializedFile -> ten plik. Bez tego indeksu
        # externale bundli ('archive:/CAB-xxx/...') sa nierozwiazywalne, bo nie
        # zawieraja nazwy pliku na dysku.
        cabs = [getattr(sf, "name", None) for sf in serialized_files_of(env)]
    except Exception:
        return None
    f_tmp, f_ttf, f_mat, mb_seen, mb_failed, f_bmp = scan_objects(fpath, env)
    return fpath, cabs, f_tmp, f_ttf, f_mat, mb_seen, mb_failed, f_bmp


def _scan_files(files, jobs):
    """Wyniki _scan_one_file dla wszystkich plikow, w kolejnosci `files`."""
    pool = None
    if jobs > 1 and len(files) > 4:
        try:
            import multiprocessing as mp
            pool = mp.get_context("spawn").Pool(
                jobs, initializer=_scan_worker_init,
                initargs=(UnityPy.config.FALLBACK_UNITY_VERSION,))
        except Exception as e:
            print(f"  ! nie udalo sie uruchomic {jobs} procesow ({e})"
                  f" - skanuje jednym", file=sys.stderr)
            pool = None
    if pool is None:
        for fpath in files:
            yield _scan_one_file(fpath)
        return
    try:
        # chunksize=1, bo koszt pliku jest skrajnie nierowny (bundle scenowy
        # kilka sekund, maly asset milisekundy) - wieksze paczki rozjezdzaja
        # workery. imap zachowuje kolejnosc, wiec wynik skanu jest powtarzalny.
        for res in pool.imap(_scan_one_file, files, chunksize=1):
            yield res
    finally:
        pool.terminate()
        pool.join()


def _rescan_with_generator(gf, fpath):
    """Ponowny skan pliku z generatorem typetree; None, gdy sie nie udalo."""
    try:
        env = UnityPy.load(fpath)
        asset = next(iter(env.assets))
        env.typetree_generator = get_generator(gf.game_root, gf.data_dir,
                                               asset.unity_version)
    except Exception:
        return None
    _forget_failed_scripts()
    return scan_objects(fpath, env)


def scan_game(gf, name_filter="", jobs=None):
    """Zwraca (tmp_fonts, ttf_fonts, materials_index).

    tmp_fonts: [{path, path_id, name}]
    ttf_fonts: [{path, path_id, name, size}]
    materials_index:
        {(tex_abs_path, tex_serialized_name, tex_path_id):
            [(mat_path, mat_serialized_name, mat_path_id)]}
    """
    global _generator_retry_useful
    tmp_fonts, ttf_fonts, bitmap_fonts = [], [], []
    materials = []  # (path, serialized_name, path_id, tex_fileid, tex_pathid)
    count = 0
    t0 = time.perf_counter()
    files = list(iter_asset_files(gf.data_dir, name_filter))
    jobs = default_scan_jobs() if jobs is None else max(1, int(jobs))
    print(f"  ({len(files)} plikow, procesow: {jobs})", file=sys.stderr)

    for res in _scan_files(files, jobs):
        if res is None:     # pliku nie da sie otworzyc jako asset Unity
            continue
        fpath, cabs, f_tmp, f_ttf, f_mat, mb_seen, mb_failed, f_bmp = res
        gf.register_cab_names(fpath, cabs)
        if mb_seen and mb_failed == mb_seen and _generator_retry_useful is not False:
            # cale rozpoznawanie skryptow w tym pliku padlo - moze jednak
            # potrzebny jest generator (nietypowy build / stara wersja Unity).
            # Zawsze w rodzicu: generator bywa interaktywny.
            retry = _rescan_with_generator(gf, fpath)
            if retry is not None:
                _generator_retry_useful = retry[4] < mb_failed
                if _generator_retry_useful:
                    print(f"  (generator typetree pomogl w {os.path.basename(fpath)})",
                          file=sys.stderr)
                    f_tmp, f_ttf, f_mat, f_bmp = retry[0], retry[1], retry[2], retry[5]
            else:
                # Nie ponawiaj kosztownej inicjalizacji TTG dla kazdego
                # kolejnego bundla, gdy generator nie obsluguje tej wersji.
                _generator_retry_useful = False
        tmp_fonts += f_tmp
        ttf_fonts += f_ttf
        bitmap_fonts += f_bmp
        materials += f_mat
        count += 1
        if count % 200 == 0:
            print(f"  ...przeskanowano {count}/{len(files)} plikow"
                  f" ({time.perf_counter() - t0:.0f}s)", file=sys.stderr)

    # Skan odwiedzil KAZDY plik i zarejestrowal jego CAB-y, wiec indeks jest
    # kompletny - bez tego pierwszy nierozwiazywalny CAB odpalalby
    # _build_cab_index(), czyli drugie przejscie po calej grze.
    if not name_filter:
        gf._cab_index_full = True

    print(f"Przeskanowano {count} plikow w {time.perf_counter() - t0:.0f}s: "
          f"{len(tmp_fonts)} TMP_FontAsset, {len(ttf_fonts)} Font (TTF), "
          f"{len(bitmap_fonts)} Font bitmapowych, {len(materials)} materialow")
    # osobny atrybut zamiast kolejnego elementu krotki - wolajacy, ktorzy nie
    # znaja fontow bitmapowych, dzialaja bez zmian
    gf.bitmap_fonts = bitmap_fonts
    return tmp_fonts, ttf_fonts, MaterialIndex(gf, materials)


# ---------------------------------------------------------------------------
# TTF
# ---------------------------------------------------------------------------

def ttf_polish_coverage(ttf_bytes, chars=None, quiet=False):
    """Zwraca (posiadane, brakujace) znaki z `chars` (domyslnie PL_CHARS)."""
    from fontTools.ttLib import TTFont
    chars = PL_CHARS if chars is None else chars
    try:
        with TTFont(io.BytesIO(ttf_bytes), fontNumber=0) as f:
            cmap = f.getBestCmap() or {}
            missing = (accent_composer.missing_characters(f, chars)
                       if accent_composer else
                       [ch for ch in chars if cmap.get(ord(ch), '.notdef') == '.notdef'])
    except Exception as e:
        if not quiet:
            print(f"  ! nie mozna odczytac fontu: {e}")
        return "", chars
    have = "".join(ch for ch in chars if ch not in missing)
    return have, "".join(missing)


def ttf_family_name(ttf_bytes):
    try:
        face = freetype.Face(io.BytesIO(ttf_bytes))
        return (face.family_name or b"").decode("utf-8", "replace")
    except Exception:
        return ""


def ttf_codepoints(ttf_bytes):
    """Zbior codepointow z cmap fontu (pusty, gdy nie da sie odczytac)."""
    from fontTools.ttLib import TTFont
    try:
        return set(TTFont(io.BytesIO(ttf_bytes), fontNumber=0).getBestCmap() or {})
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Odsiewanie fontow, ktorymi polskiego tekstu i tak nie widac
#
# Gra ma zwykle obok fontow UI kilka atlasow CJK (jp/ko/zh) i fontow
# ikon/symboli. Nie maja lacinskich liter bazowych, wiec nie ma z czego skladac
# ą/ć/ę, a tlumaczonego tekstu nikt nimi nie renderuje. Naprawianie ich to same
# koszty: atlas 4096x4096 z ideogramami wypieka sie minutami, PNG podgladu wazy
# kilkanascie MB, a wynik jest do niczego. Takie fonty odsiewamy PRZED
# podgladami i przed lista "ktore naprawic", ale zostaja widoczne na liscie
# z powodem - mozna je wskazac numerem recznie, jesli sie uprzemy.
# ---------------------------------------------------------------------------

LATIN_LOWER = "abcdefghijklmnopqrstuvwxyz"
LATIN_UPPER = LATIN_LOWER.upper()
# Minimalne pokrycie alfabetu lacinskiego, przy ktorym uznajemy, ze font sluzy
# do pisania po europejsku. Liczone osobno dla malych i duzych liter (liczy sie
# lepszy wynik) - fonty naglowkowe/all-caps maja czesto tylko jedna wielkosc.
LATIN_MIN_RATIO = 0.8
# Litery bazowe polskich znakow diakrytycznych (ą ć ę ł ń ó ś ź ż) plus 'i'/'j'
# (kropka). Font bez ktorejkolwiek z nich (w calosci malych albo w calosci
# duzych) to nie font do pisania po europejsku (ikony, symbole, obcy alfabet)
# - nie ma z czego skladac polskich liter, wiec go nie naprawiamy.
BASE_LETTERS = "acelnosz"
# Od jakiego udzialu znakow CJK w foncie nazywamy go wprost fontem azjatyckim
# (tylko dla komunikatu - odsianie i tak wynika z braku lacinskich liter).
CJK_MIN_RATIO = 0.5

CJK_RANGES = (
    (0x1100, 0x11FF),    # hangul jamo
    (0x2E80, 0x2FDF),    # radykaly CJK
    (0x3000, 0x303F),    # interpunkcja CJK
    (0x3040, 0x30FF),    # hiragana + katakana
    (0x3130, 0x318F),    # hangul compatibility jamo
    (0x31C0, 0x31EF),
    (0x3200, 0x4DBF),    # zamkniete formy + ideogramy ext A
    (0x4E00, 0x9FFF),    # ideogramy CJK
    (0xA960, 0xA97F),    # hangul jamo ext B
    (0xAC00, 0xD7FF),    # sylaby hangul
    (0xF900, 0xFAFF),    # zgodnosciowe ideogramy
    (0xFE30, 0xFE4F),    # formy do pisania w pionie
    (0xFF00, 0xFFEF),    # formy pelnej / polowkowej szerokosci
    (0x20000, 0x3FFFF),  # ideogramy ext B i dalsze
)


def is_cjk_cp(cp):
    return any(lo <= cp <= hi for lo, hi in CJK_RANGES)


def latin_ratio(cps):
    """Udzial pokrytego alfabetu lacinskiego (lepszy z: male / duze litery)."""
    return max(sum(1 for ch in alpha if ord(ch) in cps) / len(alpha)
               for alpha in (LATIN_LOWER, LATIN_UPPER))


def cjk_ratio(cps):
    return (sum(1 for cp in cps if is_cjk_cp(cp)) / len(cps)) if cps else 0.0


def unsupported_reason(cps):
    """Powod odsiania fontu albo None, gdy warto go naprawiac.

    `cps` to REALNE pokrycie fontu: m_CharacterTable dla fontu statycznego,
    cmap zrodlowego TTF dla dynamicznego."""
    cps = set(cps)
    if not cps:
        # nic nie wiemy o foncie (nieczytelny TTF, pusta tabela) - nie
        # odsiewamy na slepo, niech zdecyduje uzytkownik
        return None
    lat = latin_ratio(cps)
    has_base = any(all(ord(c) in cps for c in alpha)
                   for alpha in (BASE_LETTERS, BASE_LETTERS.upper()))
    if has_base and lat >= LATIN_MIN_RATIO:
        return None
    if not has_base and lat >= LATIN_MIN_RATIO:
        lost = "".join(c for c in BASE_LETTERS if ord(c) not in cps
                       and ord(c.upper()) not in cps)
        return (f"brak podstawowych liter ({lost or BASE_LETTERS}) - "
                f"font nie do pisania po europejsku")
    cjk = cjk_ratio(cps)
    if cjk >= CJK_MIN_RATIO:
        return (f"font azjatycki ({cjk * 100:.0f}% znakow CJK,"
                f" alfabet lacinski {lat * 100:.0f}%)")
    return f"brak liter lacinskich (alfabet {lat * 100:.0f}%)"


_font_data_cache = {}


def get_font_data(gf, font_ref):
    if font_ref.get("local_sf") is not None:       # font z folderu moje_fonty
        return font_ref["local_sf"].read_bytes()
    key = (os.path.abspath(font_ref["path"]), font_ref["path_id"],
           font_ref.get("serialized_name"))
    if key in _font_data_cache:
        return _font_data_cache[key]
    env = gf.env(font_ref["path"])
    obj = find_object(env, font_ref["path_id"], font_ref.get("serialized_name"))
    d = obj.read()
    data = d.m_FontData
    data = bytes(data) if not isinstance(data, bytes) else data
    _font_data_cache[key] = data
    return data


def font_coverage_note(gf, font_ref, need):
    """Adnotacja o pokryciu znakow `need` do listy wyboru fontu."""
    try:
        _have, missing = ttf_polish_coverage(get_font_data(gf, font_ref), need, quiet=True)
    except Exception:
        return "  [? nie da sie odczytac]"
    return "  [OK - ma wszystkie]" if not missing else f"  [brak: {missing}]"


TRANSLITERATION_MAP = {
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n",
    "ó": "o", "ś": "s", "ź": "z", "ż": "z",
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N",
    "Ó": "O", "Ś": "S", "Ź": "Z", "Ż": "Z",
}


def apply_transliteration(chars, missing):
    """Dla brakujacych znakow (ktorych font naprawde nie ma) dopisuje do
    `chars` wpis wskazujacy na GLIF JUZ OBECNY w `chars` - ten sam co jego
    odpowiednik bez ogonka (np. cp('a') dla 'a'). Nic sie nie renderuje,
    wiec dziala nawet bez zadnego fontu zrodlowego. Znaki, ktore font juz ma
    (nie ma ich w `missing`), nie sa ruszane - zostaje ich prawdziwy glif."""
    have_gi = {cp: gi for cp, gi in chars}
    still_missing = []
    added = []
    for cp in missing:
        base = TRANSLITERATION_MAP.get(chr(cp))
        base_gi = have_gi.get(ord(base)) if base else None
        if base_gi is None:
            still_missing.append(cp)
            continue
        chars.append((cp, base_gi))
        added.append(chr(cp))
    if added:
        print(f"  Transliteracja: {''.join(added)} -> odpowiedniki bez ogonkow")
    return chars, still_missing


# Litery do zmierzenia skali fallbacku: plaskie, bez wydluzen i diakrytykow,
# wiec ich wysokosc to czysty x-height (male) / cap-height (wielkie). Male
# i wielkie mierzymy OSOBNO, bo stosunek x-height do cap-height jest cecha
# kroju - jedna wspolna mediana nie pasuje wtedy do zadnej z grup.
SCALE_REF_LOWER = "xonesazcuvwmr"
SCALE_REF_UPPER = "XONESAZCUVWMRH"

# rozstaw pod-offsetow, gdy fallback renderujemy w kilku rozmiarach naraz:
# ten sam glyph_index przy dwoch pointSize to dwie rozne bitmapy
FALLBACK_GROUP_STRIDE = 100_000


def fallback_point_size(ref_heights, fb_face, point_size, ref_chars):
    """PointSize, przy ktorym litery fallbacku maja ta sama wysokosc co w
    foncie bazowym / atlasie.

    Ten sam pointSize w dwoch krojach NIE daje tych samych liter - kwadrat
    firmowy jest wspolny, ale x-height juz nie, wiec np. 'ę' z fallbacku
    potrafi byc wyraznie mniejsze od 'e' obok. Mierzymy wiec te same litery
    w obu fontach i bierzemy mediane stosunku wysokosci (mediana, bo
    pojedyncza litera moze miec nietypowy krojowy wyjatek).

    Zwraca (pointSize dla fallbacku, uzyty wspolczynnik).
    """
    fb_face.set_char_size(point_size * 64)
    load_flags = freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP
    ratios = []
    for ch in ref_chars:
        orig_h = ref_heights.get(ord(ch), 0)
        if orig_h <= 0:
            continue
        gi = fb_face.get_char_index(ord(ch))
        if gi == 0:
            continue
        try:
            fb_face.load_glyph(gi, load_flags)
        except Exception:
            continue
        fb_h = fb_face.glyph.metrics.height / 64.0
        if fb_h > 0:
            ratios.append(orig_h / fb_h)
    if not ratios:
        return point_size, 1.0
    ratios.sort()
    ratio = ratios[len(ratios) // 2]
    return max(1, int(round(point_size * ratio))), ratio


def scaled_fallback_glyphs(fb_face, missing, chars, glyphs, point_size, padding,
                           render_mode=None):
    """Renderuje `missing` z fallbacku, dopasowujac wielkosc liter do juz
    zebranych `glyphs` - osobno dla malych i wielkich.

    render_mode: m_AtlasRenderMode fontu docelowego, zeby dorobione litery byly
    tego samego rodzaju co atlas (SDF vs bitmapa).

    Zwraca (fb_chars, fb_glyphs, nadal_brakujace); indeksy glifow sa juz
    rozsuniete miedzy grupami, wiec nie koliduja ze soba.
    """
    gi_height = {gi: g["metrics"]["height"] for gi, g in glyphs.items()}
    ref_heights = {cp: gi_height.get(gi, 0) for cp, gi in chars}

    groups = [
        ("male", SCALE_REF_LOWER, [cp for cp in missing if chr(cp).islower()]),
        ("wielkie", SCALE_REF_UPPER, [cp for cp in missing if not chr(cp).islower()]),
    ]
    out_chars, out_glyphs, still = [], {}, []
    for i, (label, refs, cps) in enumerate(groups):
        if not cps:
            continue
        ps, ratio = fallback_point_size(ref_heights, fb_face, point_size, refs)
        if abs(ratio - 1.0) > 0.02:
            print(f"  Skala fallbacku ({label}): x{ratio:.2f} -> pointSize "
                  f"{point_size} -> {ps}")
        g_chars, g_glyphs, g_missing = gen.collect_glyphs(fb_face, cps, ps, padding,
                                                          render_mode=render_mode)
        sub = i * FALLBACK_GROUP_STRIDE
        out_chars += [(cp, gi + sub) for cp, gi in g_chars]
        out_glyphs.update({gi + sub: g for gi, g in g_glyphs.items()})
        still += g_missing
    return out_chars, out_glyphs, sorted(still)


# inny przedzial indeksow niz FALLBACK_GLYPH_OFFSET - font z systemu i ewentualny
# fallback moga byc roznymi plikami, a ten sam indeks to dwa rozne glify
SYSTEM_GLYPH_OFFSET = 3_000_000


def add_real_glyphs_from_ttf(ttf_bytes, missing, chars, glyphs, point_size, padding,
                             render_mode=None):
    """Brakujace litery z PRAWDZIWEGO fontu tego samego kroju (np. z systemu).

    Bierze tylko znaki, ktore font naprawde ma (bez kopii .notdef i ASCII), nic nie
    dorabia i nie sklada - to ma byc oryginalny glif. Wielkosc dopasowuje do glifow
    atlasu (scaled_fallback_glyphs). Modyfikuje `chars` i `glyphs` w miejscu.

    Zwraca (lista pobranych codepointow, nadal brakujace codepointy).
    """
    have, _ = ttf_polish_coverage(ttf_bytes, quiet=True)
    real = [cp for cp in missing if chr(cp) in have]
    if not real:
        return [], list(missing)
    fb_face = freetype.Face(io.BytesIO(ttf_bytes))
    got_chars, got_glyphs, still = scaled_fallback_glyphs(
        fb_face, real, chars, glyphs, point_size, padding, render_mode=render_mode)
    chars += [(cp, gi + SYSTEM_GLYPH_OFFSET) for cp, gi in got_chars]
    glyphs.update({gi + SYSTEM_GLYPH_OFFSET: g for gi, g in got_glyphs.items()})
    taken = [cp for cp, _ in got_chars]
    return taken, sorted((set(missing) - set(real)) | set(still))


def compose_missing_accents(fallback_ttf):
    """Uzupelnia braki w samym foncie FALLBACK technika font_fixer/fix_polish_fonts.py
    (litera bazowa + akcent wyciety z innego glifu TEGO fontu), zeby nie renderowac
    znaku calkowicie obcego krojowo. Zakres zalezy od trybu:
      SYNTH_FULL - wszystkie polskie litery (ogonek rysowany krzywa Beziera,
                   przekreslenie ł belka),
      tryb okrojony - tylko kreska (ć ń ó ś ź + wersaliki).

    Litery, ktorych fix_font nie umial zlozyc, sa z powrotem WYPINANE z cmap:
    inaczej fallback udawalby, ze ma znak, a mialby pod nim goly odpowiednik bez
    ogonka - o transliteracji decyduje osobny, jawny krok, nie ciche podstawienie.

    To nie jest krok, ktory ma cokolwiek zablokowac - przy bledzie zwracamy
    oryginalne bajty i lecimy dalej.

    Zwraca (ttf_bytes, dorobione_znaki).
    """
    wanted = set(PL_CHARS) if SYNTH_FULL else ACUTE_CHARS
    if accent_composer is None or not wanted:
        return fallback_ttf, []
    try:
        font = accent_composer.TTFont(io.BytesIO(fallback_ttf), lazy=False)
        cmap = font.getBestCmap()
        todo = accent_composer.missing_characters(font, sorted(wanted))
        if not todo:
            return fallback_ttf, []
        result = accent_composer.fix_font(font, cmap, todo, add_accents=True,
                                         full_set=SYNTH_FULL)
        made = list(result["composed"]) + list(result["synthesized"])
        if not made:
            return fallback_ttf, []
        for ch in result["plain"]:      # sama litera bez ogonka - to nie ten znak
            for st in font["cmap"].tables:
                if st.isUnicode():
                    st.cmap.pop(ord(ch), None)
        buf = io.BytesIO()
        font.save(buf)
        print(f"  Dorobiono w foncie fallback (jak w fix_polish_fonts.py): "
              f"{' '.join(sorted(made))}")
        return buf.getvalue(), made
    except Exception as e:
        print(f"  ! kompozycja akcentow w fallbacku nie powiodla sie ({e}) - lece dalej bez niej")
        return fallback_ttf, []


# ---------------------------------------------------------------------------
# Skladanie polskich liter z WLASNYCH glifow (bez obcego fontu)
#
# Kreske nad ć ń ś ź (i kropke nad ż) da sie wziac z kroju, ktory juz jest w
# atlasie: roznica miedzy 'ó' i 'o' to dokladnie kreska TEGO fontu, wiec zlozona
# litera nie odstaje niczym od sasiednich. To ta sama technika, co w
# font_fixer/fix_polish_fonts.py, tyle ze na pikselach zamiast na konturach.
#
# Pole SDF sklada sie idealnie przez maksimum: dla sumy dwoch ksztaltow wartosc
# w pikselu to zawsze ta z blizszego z nich. Ta sama wlasnosc dziala w druga
# strone - akcent to te piksele, w ktorych 'ó' jest "blizej wnetrza" niz 'o'.
# (Dla atlasow bitmapowych maksimum to zwykla suma pokrycia, wiec tez pasuje.)
#
# Ogonka (ą ę) ani przekreslenia (ł) nie ma z czego wyciac. W trybie SYNTH_FULL
# (domyslnym) rysujemy je wiec od zera - patrz sekcja nizej; w trybie okrojonym
# te litery biora sie z fontu fallback albo z transliteracji.
# ---------------------------------------------------------------------------

COMPOSED_GLYPH_OFFSET = 2_000_000   # indeksy glifow zlozonych z akcentu
INK_LEVEL = 128                     # >= tyle w polu SDF = wnetrze glifu
# litery, ktorych gorna krawedz wyznacza x-height (bez wydluzen i akcentow)
XHEIGHT_REFS = "xonezcsu"


def _glyph_origin(g):
    """(x kolumny 0, y wiersza 0) komorki glifu w przestrzeni fontu:
    x liczony od pozycji piora, y od linii bazowej. Tablica 'sdf' jest
    top-down, a 'inner' podaje y od DOLU komorki - stad ta konwersja."""
    ix, iy, iw, ih = g["inner"]
    m = g["metrics"]
    return (m["bearing_x"] - ix, m["bearing_y"] + (g["cell_h"] - iy - ih))


def _blit_max(dst, dst_origin, src, src_origin):
    """src w dst przez maksimum, z wyrownaniem po przestrzeni fontu."""
    col = int(round(src_origin[0] - dst_origin[0]))
    row = int(round(dst_origin[1] - src_origin[1]))
    dh, dw = dst.shape
    sh, sw = src.shape
    r0, c0 = max(0, row), max(0, col)
    r1, c1 = min(dh, row + sh), min(dw, col + sw)
    if r1 <= r0 or c1 <= c0:
        return
    np.maximum(dst[r0:r1, c0:c1], src[r0 - row:r1 - row, c0 - col:c1 - col],
               out=dst[r0:r1, c0:c1])


def _ink_bbox(arr, thr):
    """(c0, c1, r0, r1) obszaru o wartosciach >= thr; None gdy pusto."""
    hit = arr >= thr
    rows = np.nonzero(hit.any(axis=1))[0]
    if not rows.size:
        return None
    cols = np.nonzero(hit.any(axis=0))[0]
    return int(cols[0]), int(cols[-1]) + 1, int(rows[0]), int(rows[-1]) + 1


MARK_MAX_SIZE = 0.45    # znak diakrytyczny nie moze byc wiekszy niz tyle (x em)


def _pack_mark(field, origin, kind, base_top, base_bottom, base_cx,
               em_px=0.0, align="center"):
    """Wyciety znak diakrytyczny -> opis gotowy do doklejenia do innej litery.

    base_top / base_bottom / base_cx opisuja litere, PRZY ktorej znak stal
    u dawcy (gora i spod tuszu oraz srodek w poziomie albo - dla align="right" -
    jej prawa krawedz) - dzieki temu da sie go ustawic tak samo przy literze
    docelowej. Kreska i kropka wyrownuja sie do GORY litery, ogonek do jej SPODU
    (inaczej pod wersalikiem wjechalby w tusz), stad oba pola.

    Kandydat wiekszy niz MARK_MAX_SIZE em jest odrzucany - to samo sito, co
    fix_polish_fonts.mark_is_sane: znaczy, ze zamiast akcentu zlapalismy
    kawalek litery.
    """
    ink = _ink_bbox(field, INK_LEVEL)
    if ink is None:
        return None
    if em_px > 0 and (ink[1] - ink[0] > MARK_MAX_SIZE * em_px
                      or ink[3] - ink[2] > MARK_MAX_SIZE * em_px):
        return None
    if kind in ("acute", "dot") and em_px > 0:
        # A 1-2 px slice of a 200 px capital is not an accent. Keep real
        # one-pixel marks in small bitmap fonts (the threshold scales with em).
        if ink[3] - ink[2] < max(1, int(np.ceil(0.02 * em_px))):
            return None
    full = _ink_bbox(field, 1)      # cale pole, razem z rampa SDF
    c0, c1, r0, r1 = full
    ox, oy = origin
    return {
        "field": np.ascontiguousarray(field[r0:r1, c0:c1]),
        "origin": (ox + c0, oy - r0),
        "kind": kind,
        "base_top": base_top,
        "base_bottom": base_bottom,
        "base_cx": base_cx,
        "align": align,
    }


def _separated_top_mark(g, kind, em_px):
    """Extract a detached accent and measure the body of its OWN donor.

    Display fonts can compress the body of Oacute to fit O's cap height.
    The top of plain O would then cut through the accent itself. A gap
    between accent and body supplies the correct boundary and reference.
    Requiring a real gap also prevents an all-caps 'i' from donating the
    topmost row of its stem as a dot.
    """
    image = g["sdf"]
    occupied = (image >= INK_LEVEL).any(axis=1)
    rows = np.flatnonzero(occupied)
    if rows.size == 0:
        return None
    top, bottom = int(rows[0]), int(rows[-1]) + 1
    gaps = np.flatnonzero(np.diff(np.r_[False, ~occupied[top:bottom], False]
                                 .astype(np.int8)))
    ox, oy = _glyph_origin(g)
    for start, end in zip(gaps[::2] + top, gaps[1::2] + top):
        # The larger lower part must be the letter, not another accent.
        if bottom - end < (bottom - top) * 0.5:
            continue
        cut = (int(start) + int(end)) // 2
        body = _ink_bbox(image[end:bottom], INK_LEVEL)
        if body is None:
            continue
        field = image.copy()
        field[cut:, :] = 0
        mark = _pack_mark(field, (ox, oy), kind, oy - int(end),
                          oy - bottom, ox + (body[0] + body[1]) / 2.0, em_px)
        if mark is not None:
            return mark
    return None


def _isolate_mark(g_acc, g_base, kind, em_px):
    """Akcent jako roznica glifu zlozonego i jego litery bazowej (np. ó - o).

    Sama roznica pol NIE wystarcza. Glify 'ó' i 'o' sa wyrownane z dokladnoscia
    do piksela, wiec przy kazdej krawedzi litery zostaje slad grubosci ~1 px -
    a w polu SDF to piksele o wartosci "wnetrze", czyli tusz. Przy dawcy 'é'
    zostawal z tego caly poprzeczny sladzik litery i zlozone 'ć' wygladalo jak
    'é'. Dlatego dokladamy dwa sita, oba wprost z fix_polish_fonts:
      - pozycja: akcent lezy CALY nad litera (albo, dla ogonka, pod nia),
      - roznica liczy sie tylko tam, gdzie litery bazowej NIE MA.
    """
    if kind in ("acute", "dot"):
        mark = _separated_top_mark(g_acc, kind, em_px)
        if mark is not None:
            return mark
    acc = g_acc["sdf"]
    base = np.zeros(acc.shape, dtype=np.uint8)
    _blit_max(base, _glyph_origin(g_acc), g_base["sdf"], _glyph_origin(g_base))
    field = np.where((acc > base) & (base < INK_LEVEL), acc, 0).astype(np.uint8)
    m = g_base["metrics"]
    ox, oy = _glyph_origin(g_acc)
    if kind in ("acute", "dot"):
        cut = int(round(oy - m["bearing_y"]))                    # wiersz gory litery
        field[max(0, cut):, :] = 0
    else:
        cut = int(round(oy - (m["bearing_y"] - m["height"])))     # wiersz spodu litery
        field[:max(0, cut), :] = 0
    return _pack_mark(field, (ox, oy), kind, m["bearing_y"],
                      m["bearing_y"] - m["height"],
                      m["bearing_x"] + m["width"] / 2.0, em_px)


def _cut_mark_above(g, y_cut, em_px=0.0):
    """Kropka z i/j musi byc oddzielona od laski, nie tylko nad x-height."""
    return _separated_top_mark(g, "dot", em_px or _estimate_em_px(None, y_cut))


ATTACH_RIGHT_KINDS = ("ogonek",)   # znaki dosuwane do PRAWEJ krawedzi litery


def _standalone_mark(kind, have, glyphs, xheight, em_px):
    """Znak diakrytyczny jako OSOBNY glif fontu (´ ˙ ˛ oraz wersje skladajace).

    Ratunek, gdy w atlasie nie ma pary (znak zlozony, litera bazowa) - a ´
    trafia do atlasow czesto, bo siedzi w zakresie Latin-1. Kandydatow trzeba
    odsiac tak jak fix_polish_fonts.mark_is_sane: w fontach CJK ˙ bywa
    narysowane w polowie kratki i wyladowaloby w srodku litery.
    """
    for ch in accent_composer.MARK_STANDALONE.get(kind, []):
        gi = have.get(ord(ch))
        if gi is None or glyphs[gi].get("empty"):
            continue
        g = glyphs[gi]
        m = g["metrics"]
        w, h = m["width"], m["height"]
        if w <= 0 or h <= 0 or w > MARK_MAX_SIZE * em_px or h > MARK_MAX_SIZE * em_px:
            continue
        bottom = m["bearing_y"] - h
        if kind in ("acute", "dot"):
            rise = getattr(accent_composer, "MARK_MAX_RISE", 0.20)
            if bottom <= xheight * 0.85 or bottom > xheight + rise * em_px:
                continue
        elif bottom >= 0.15 * em_px:
            continue
        # samodzielny znak nie przynosi zadnej litery odniesienia: kreske
        # i kropke centrujemy nad litera, ogonek - jak fix_polish_fonts.place_mark
        # - dosuwamy do jej prawej krawedzi
        right = kind in ATTACH_RIGHT_KINDS
        mark = _pack_mark(g["sdf"].copy(), _glyph_origin(g), kind, xheight, 0.0,
                          m["bearing_x"] + (w if right else w / 2.0), em_px,
                          align="right" if right else "center")
        if mark is not None:
            return mark
    return None


def _get_mark(kind, upper, have, glyphs, xheight, em_px, cache):
    """Znak diakrytyczny danego rodzaju wyciety z glifow, ktore juz sa."""
    key = (kind, upper)
    if key in cache:
        return cache[key]
    mark = None
    pairs = accent_composer.MARK_PAIRS.get(kind, [])
    # najpierw dawca tej samej wielkosci liter - kreska nad wersalikiem bywa
    # inaczej wyskalowana i inaczej ustawiona niz nad mala litera
    for same_case in (True, False):
        for acc_ch, base_ch in pairs:
            if same_case and acc_ch.isupper() != upper:
                continue
            gi_a, gi_b = have.get(ord(acc_ch)), have.get(ord(base_ch))
            if gi_a is None or gi_b is None:
                continue
            if glyphs[gi_a].get("empty") or glyphs[gi_b].get("empty"):
                continue
            mark = _isolate_mark(glyphs[gi_a], glyphs[gi_b], kind, em_px)
            if mark is not None:
                break
        if mark is not None:
            break
    if mark is None:
        mark = _standalone_mark(kind, have, glyphs, xheight, em_px)
    if mark is None and kind == "dot" and xheight > 0:
        for ch in "ij":
            gi = have.get(ord(ch))
            if gi is not None and not glyphs[gi].get("empty"):
                mark = _cut_mark_above(glyphs[gi], xheight, em_px)
                if mark is not None:
                    break
    cache[key] = mark
    return mark


def _keep_sidebearings(base_m, bearing_x, width):
    """(bearing_x, advance) dorobionej litery z odstepami litery bazowej.

    Litera skladana dziedziczy advance po literze bazowej, ale jej tusz bywa
    SZERSZY: belka w ł wystaje o piksel w prawo poza laske, a ogonek wywija sie
    czubkiem w prawo poza obrys 'a'. Bez korekty prawy sidebearing schodzi do
    zera i litera skleja sie z nastepna (w Chained Echoes "łć" zlewalo sie
    w jeden znak). Pilnujemy wiec, zeby marginesy byly takie same jak w literze
    bazowej: tusz wystajacy w PRAWO powieksza advance, a wystajacy w LEWO
    przesuwa cala komorke w prawo (advance rosnie razem z nia).
    """
    adv, lsb = base_m["advance"], base_m["bearing_x"]
    rsb = max(adv - (lsb + base_m["width"]), 0.0)
    dx = max(min(lsb, 0.0) - bearing_x, 0.0)
    return bearing_x + dx, max(adv + dx, bearing_x + dx + width + rsb)


def _finish_composed_cell(canvas, origin, base_m, padding):
    """Kanwa z gotowa litera -> wpis do `glyphs` (przyciety do tuszu + padding).

    origin: (x, y) piksela [0, 0] kanwy w przestrzeni fontu (x od pozycji
    piora, y od linii bazowej).
    base_m: metryki litery bazowej - stad advance i odstepy boczne.
    """
    ink = _ink_bbox(canvas, INK_LEVEL)
    if ink is None:
        return None
    kc0, kc1, kr0, kr1 = ink
    # przyciecie z marginesem paddingu; kanwa ma zapas, ale gdyby go zabraklo,
    # lepiej obciac margines niz wyjsc poza tablice
    pr0, pc0 = max(0, kr0 - padding), max(0, kc0 - padding)
    pr1 = min(canvas.shape[0], kr1 + padding)
    pc1 = min(canvas.shape[1], kc1 + padding)
    cell = np.ascontiguousarray(canvas[pr0:pr1, pc0:pc1])
    ink_w, ink_h = kc1 - kc0, kr1 - kr0
    ox, oy = origin
    bearing_x, advance = _keep_sidebearings(base_m, float(ox + kc0), float(ink_w))
    return {
        "metrics": {"width": float(ink_w), "height": float(ink_h),
                    "bearing_x": bearing_x,
                    "bearing_y": float(oy - kr0),
                    "advance": advance},
        "empty": False,
        "cell_w": cell.shape[1], "cell_h": cell.shape[0],
        "sdf": cell,
        # iy liczone od DOLU komorki
        "inner": (kc0 - pc0, pr1 - kr1, ink_w, ink_h),
    }


def _compose_with_mark(g_base, mark, padding):
    """Litera bazowa + akcent w jednej komorce (suma pol przez maksimum)."""
    m = g_base["metrics"]
    ox, oy = _glyph_origin(g_base)
    ix, iy, iw, ih = g_base["inner"]
    base_top = oy - (g_base["cell_h"] - iy - ih)
    base_bottom = base_top - ih
    # akcent na srodku litery i na tej samej wysokosci co u dawcy; gdy litera
    # docelowa jest wyzsza (np. wersalik zamiast malej), podnosimy go tyle,
    # zeby nie wszedl w tusz. Ogonek liczy sie od SPODU litery - podniesiony
    # razem z gora wersalika wjechalby w jej srodek - i od jej PRAWEJ krawedzi.
    if mark.get("align") == "right":
        dx = (m["bearing_x"] + m["width"]) - mark["base_cx"]
    else:
        dx = (m["bearing_x"] + m["width"] / 2.0) - mark["base_cx"]
    if mark.get("kind") == "ogonek":
        dy = base_bottom - mark["base_bottom"]
    else:
        dy = max(0.0, base_top - mark["base_top"])

    mh, mw = mark["field"].shape
    col = int(round((mark["origin"][0] + dx) - ox))
    row = int(round(oy - (mark["origin"][1] + dy)))

    # kanwa z zapasem paddingu z kazdej strony - dzieki temu tusz nigdy nie
    # dotyka krawedzi i wycinek z marginesem zawsze sie miesci
    r0, c0 = min(0, row) - padding, min(0, col) - padding
    r1 = max(g_base["cell_h"], row + mh) + padding
    c1 = max(g_base["cell_w"], col + mw) + padding
    canvas = np.zeros((r1 - r0, c1 - c0), dtype=np.uint8)
    canvas[-r0:-r0 + g_base["cell_h"], -c0:-c0 + g_base["cell_w"]] = g_base["sdf"]
    np.maximum(canvas[row - r0:row - r0 + mh, col - c0:col - c0 + mw], mark["field"],
               out=canvas[row - r0:row - r0 + mh, col - c0:col - c0 + mw])

    return _finish_composed_cell(canvas, (ox + c0, oy - r0), m, padding)


# ---------------------------------------------------------------------------
# Znaki diakrytyczne DORYSOWANE na pikselach
#
# Ogonka (ą ę) i przekreslenia (ł) nie ma z czego wyciac: ogonka zwykle nie ma
# w foncie w ogole, a przekreslenie ł jest czescia litery, nie osobnym akcentem.
# Kreski (ć ń ó ś ź) i kropki (ż) NIE MA z czego wyciac w fontach zrobionych pod
# jedna gre - taki krój nie ma ani jednego glifu z akcentem, ani ´ / ˙, ani
# znaku skladajacego (VCR OSD Mono, dogica, Lusitana, Electronic Highway Sign).
# Dawniej takie litery szly do OBCEGO fontu fallback albo w transliteracje;
# fallback ma inny krój, inna szerokosc i inna wysokosc, wiec w napisie widac
# litery "w innym rozmiarze" (w monospace natychmiast - "WYJDŹ" w VCR OSD Mono).
#
# Dlatego wszystkie cztery rodzaje rysujemy od zera, tymi samymi proporcjami,
# ktorymi font_fixer/fix_polish_fonts.py rysuje je na konturach (make_ogonek /
# make_stroke / make_acute / make_dot). Tutaj mamy tylko gotowe pola z atlasu,
# wiec te SAME stale (OGONEK_*, ACUTE_*, DOT_SYNTH_*) odtwarzamy w pikselach.
#
# Ksztalty skladamy z okregow: pole odleglosci sumy okregow to dokladnie
# max(r_i - |p - c_i|), wiec dla punktow NA ZEWNATRZ wychodzi ta sama wartosc,
# ktora policzylby FreeType - nie trzeba zadnej rasteryzacji ani transformaty
# odleglosci. Wewnatrz cienkiej kreski pole i tak nie przekracza jej polgrubosci,
# tak samo jak w prawdziwym SDF.
# ---------------------------------------------------------------------------

SYNTH_KINDS = ("ogonek", "stroke", "acute", "dot")  # rysowane geometrycznie
# Kreska i kropka to znaki, ktore tryb okrojony (SYNTH_FULL = False) i tak
# obiecuje zrobic z wlasnych glifow fontu - tam rysowanie jest ostatnia
# deska ratunku przed obcym krojem, wiec nie zalezy od SYNTH_FULL.
SYNTH_ALWAYS_KINDS = ("acute", "dot")


def _field_to_bytes(dist, spread, sdf_mode, mono):
    """Odleglosc ze znakiem (px, dodatnia wewnatrz) -> bajty jak w atlasie."""
    if sdf_mode:
        value = 128.0 + 127.0 * dist / max(float(spread), 1.0)
    elif mono:
        value = np.where(dist >= 0.0, 255.0, 0.0)
    else:
        value = 255.0 * (dist + 0.5)     # bitmapa: rampa antyaliasingu 1 px
    return np.clip(value, 0, 255).astype(np.uint8)


def _circles_field(circles, shape, origin, spread, sdf_mode, mono):
    """Pole sumy okregow [(x, y, r), ...] w komorce o zadanym origin."""
    h, w = shape
    ox, oy = origin
    xs = ox + np.arange(w, dtype=np.float32)
    ys = oy - np.arange(h, dtype=np.float32)
    dist = np.full((h, w), -1e6, dtype=np.float32)
    for cx, cy, r in circles:
        d = r - np.hypot(xs[None, :] - cx, ys[:, None] - cy)
        np.maximum(dist, d, out=dist)
    return _field_to_bytes(dist, spread, sdf_mode, mono)


def _ink_runs(line):
    """Dlugosci pasm tuszu w jednym przekroju (wektor bool)."""
    edges = np.nonzero(np.diff(np.concatenate(
        ([0], line.astype(np.uint8), [0]))))[0]
    return [int(b - a) for a, b in zip(edges[::2], edges[1::2])]


def _pixel_stem_width(g):
    """Grubosc laski litery w pikselach - mediana pasm tuszu w 3 przekrojach
    (odpowiednik fix_polish_fonts.stem_width, tylko liczony na pikselach).
    Bez tego ogonek bylby nitka w kroju Black i kluska w Light."""
    ink = g["sdf"] >= INK_LEVEL
    rows = np.nonzero(ink.any(axis=1))[0]
    if not rows.size:
        return 0.0
    top, bottom = int(rows[0]), int(rows[-1])
    runs = []
    for frac in (0.30, 0.45, 0.60):     # liczone od DOLU litery, jak w font_fixer
        r = int(round(bottom - (bottom - top) * frac))
        runs += _ink_runs(ink[r])
    if not runs:
        return 0.0
    runs.sort()
    return float(runs[len(runs) // 2])


def _pixel_attach(g, em_px):
    """Punkt zaczepienia ogonka w przestrzeni fontu: najnizszy tusz w prawej
    czesci litery (przy remisie - najbardziej z prawej). Prawy dolny rog ramki
    nie wystarcza: pod 'e' prawy brzeg zakreca do gory i haczyk zawisalby
    w powietrzu."""
    ink = g["sdf"] >= INK_LEVEL
    ox, oy = _glyph_origin(g)
    cols = np.nonzero(ink.any(axis=0))[0]
    if not cols.size:
        return None
    c_lo, c_hi = int(cols[0]), int(cols[-1])
    rows = np.nonzero(ink.any(axis=1))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    probe = int(round(bottom - (bottom - top) * 0.05))
    edges = np.nonzero(np.diff(np.concatenate(([0], ink[probe], [0]))))[0]
    runs = list(zip(edges[::2], edges[1::2]))
    if runs:
        x = accent_composer.ogonek_anchor_x(
            runs, c_lo, c_hi + 1, _pixel_stem_width(g))
        c = min(int(x), ink.shape[1] - 1)
        occupied = np.nonzero(ink[:, c])[0]
        if occupied.size:
            return ox + x, oy - int(occupied[-1])
    width = c_hi - c_lo
    lo = c_lo + 0.45 * width
    hi = c_lo + accent_composer.OGONEK_ATTACH_MAX * width
    samples = []
    for i in range(21):
        c = int(round(lo + (hi - lo) * i / 20))
        if not (0 <= c < ink.shape[1]) or not ink[:, c].any():
            continue
        samples.append((c, int(np.nonzero(ink[:, c])[0][-1])))
    if not samples:
        return None
    lowest = max(r for _c, r in samples)          # najnizej = najwiekszy wiersz
    tol = max(1, int(round(0.02 * em_px)))
    flat = [s for s in samples if s[1] >= lowest - tol]
    c, r = max(flat, key=lambda s: s[0])
    return ox + c, oy - r


def _ogonek_circles(g, em_px):
    """Polski haczyk jako lancuch okregow - os to ta sama krzywa Beziera co
    w fix_polish_fonts.make_ogonek (w dol z odchyleniem w LEWO, czubkiem
    z powrotem w PRAWO i do gory), a grubosc zweza sie ku koncowi."""
    attach = _pixel_attach(g, em_px)
    if attach is None:
        return None
    ax, ay = attach
    a = accent_composer
    p0 = (ax, ay + a.OGONEK_MERGE * em_px)
    p1 = (ax - a.OGONEK_BULGE * em_px, ay - 0.09 * em_px)
    p2 = (ax - 0.01 * em_px, ay - a.OGONEK_DEPTH * em_px)
    p3 = (ax + a.OGONEK_BACK * em_px,
          ay - a.OGONEK_DEPTH * em_px * a.OGONEK_TIP_RISE)
    thick = min(max(_pixel_stem_width(g) * a.OGONEK_THICK,
                    a.OGONEK_THICK_MIN * em_px), a.OGONEK_THICK_MAX * em_px)
    steps = 28
    circles = []
    for i in range(steps + 1):
        t = i / steps
        u = 1.0 - t
        x = (u ** 3 * p0[0] + 3 * u * u * t * p1[0]
             + 3 * u * t * t * p2[0] + t ** 3 * p3[0])
        y = (u ** 3 * p0[1] + 3 * u * u * t * p1[1]
             + 3 * u * t * t * p2[1] + t ** 3 * p3[1])
        half = thick * (1 - t * (1 - a.OGONEK_TIP)) / 2
        circles.append((x, y, max(half, 0.6)))
    return circles


def _stroke_circles(g, em_px, upper):
    """Ukosna belka przekreslajaca ł/Ł - geometria z fix_polish_fonts.make_stroke,
    tylko z zaokraglonymi koncami (kilka pikseli na ukosie, nie do odróznienia)."""
    m = g["metrics"]
    x0, x1 = m["bearing_x"], m["bearing_x"] + m["width"]
    y_top = m["bearing_y"]
    if y_top <= 0:
        return None
    ox, oy = _glyph_origin(g)

    def ink_at_y(y):
        row = int(round(oy - y))
        if not 0 <= row < g["cell_h"]:
            return []
        edges = np.flatnonzero(np.diff(np.r_[0, g["sdf"][row] >= INK_LEVEL, 0]))
        return [(ox + int(a), ox + int(b)) for a, b in zip(edges[::2], edges[1::2])]

    cx, cy, hx, rise, half_v = accent_composer.stroke_geometry(
        (x0, y_top - m["height"], x1, y_top), em_px, upper,
        stem=_pixel_stem_width(g), ink_at_y=ink_at_y)
    return _slanted_bar_circles(cx, cy, hx, rise, half_v)


def _slanted_bar_circles(cx, cy, hx, rise, half_v, steps=12):
    """Ukosna belka o grubosci odkladanej PIONOWO (jak font_fixer.make_stroke /
    make_acute) jako lancuch okregow. Promien jest prostopadly do belki, wiec
    polgrubosc pionowa skalujemy cosinusem nachylenia."""
    radius = max(half_v * hx / (hx * hx + rise * rise) ** 0.5, 0.6)
    return [(cx - hx + 2 * hx * i / steps, cy - rise + 2 * rise * i / steps, radius)
            for i in range(steps + 1)]


def _font_stem_px(have, glyphs, upper):
    """Grubosc laski calego kroju w pikselach - mediana pomiarow na literach
    odniesienia (accent_composer.STEM_REFS). None, gdy zadnej nie ma.

    Kreska i kropka maja byc w calym foncie identyczne, wiec grubosci NIE liczymy
    z litery bazowej: zmierzona na 'Z' (sam ukos) wychodzila grubsza niz na 'O',
    i akcent w 'Ź' stal 2 px wyzej niz w 'Ó'."""
    widths = []
    for ch in accent_composer.STEM_REFS[upper]:
        gi = have.get(ord(ch))
        if gi is None or glyphs[gi].get("empty"):
            continue
        w = _pixel_stem_width(glyphs[gi])
        if w > 0:
            widths.append(w)
    if not widths:
        return None
    widths.sort()
    return widths[len(widths) // 2]


def _acute_circles(g, em_px, stem_px=None):
    """Kreska nad litera (ć ń ó ś ź) - geometria z fix_polish_fonts.make_acute:
    ukosna belka postawiona nad tuszem litery, przesunieta ździebko w prawo od
    jej srodka, o grubosci dobranej do grubosci laski kroju."""
    m = g["metrics"]
    y_top = m["bearing_y"]
    if y_top <= 0:
        return None
    a = accent_composer
    x0, x1 = m["bearing_x"], m["bearing_x"] + m["width"]
    stem = _pixel_stem_width(g) if stem_px is None else stem_px
    thick = min(max(stem * a.ACUTE_THICK,
                    a.ACUTE_THICK_MIN * em_px), a.ACUTE_THICK_MAX * em_px)
    hx = min(a.ACUTE_HALF_W * em_px, a.ACUTE_MAX_REL_W * (x1 - x0))
    rise = a.ACUTE_SLANT * hx
    half_v = thick / 2
    cx = (x0 + x1) / 2 + a.ACUTE_SHIFT * (x1 - x0)
    cy = y_top + a.ACUTE_GAP * em_px + rise + half_v
    return _slanted_bar_circles(cx, cy, hx, rise, half_v)


def _dot_circles(g, em_px, stem_px=None):
    """Kropka nad litera (ż Ż) - geometria z fix_polish_fonts.make_dot: kolo
    o srednicy dobranej do grubosci laski kroju, wysrodkowane nad tuszem litery.
    Tu wystarczy jeden okrag - w polu odleglosci to dokladnie kolo."""
    m = g["metrics"]
    y_top = m["bearing_y"]
    if y_top <= 0:
        return None
    a = accent_composer
    stem = _pixel_stem_width(g) if stem_px is None else stem_px
    r = min(min(max(stem * a.DOT_SYNTH_SIZE,
                    a.DOT_SYNTH_MIN * em_px), a.DOT_SYNTH_MAX * em_px),
            a.DOT_MAX_REL_W * m["width"]) / 2
    cx = m["bearing_x"] + m["width"] / 2
    cy = y_top + a.DOT_SYNTH_GAP * em_px + r
    return [(cx, cy, max(r, 0.6))]


def _compose_with_circles(g_base, circles, padding, sdf_mode, mono):
    """Litera bazowa + dorysowany ksztalt (haczyk / belka) w jednej komorce.

    padding jest tu jednoczesnie marginesem komorki i SPREADEM pola odleglosci -
    tak samo, jak w generate_tmp_sdf.collect_glyphs (set_sdf_spread(padding)),
    wiec dorysowany ksztalt ma dokladnie taka sama rampe jak reszta atlasu."""
    m = g_base["metrics"]
    ox, oy = _glyph_origin(g_base)
    r_max = max(c[2] for c in circles)
    x_lo = min(c[0] for c in circles) - r_max
    x_hi = max(c[0] for c in circles) + r_max
    y_lo = min(c[1] for c in circles) - r_max
    y_hi = max(c[1] for c in circles) + r_max
    # zasieg ksztaltu przeliczony na wiersze/kolumny komorki litery
    col_lo, col_hi = int(np.floor(x_lo - ox)), int(np.ceil(x_hi - ox))
    row_lo, row_hi = int(np.floor(oy - y_hi)), int(np.ceil(oy - y_lo))

    r0, c0 = min(0, row_lo) - padding, min(0, col_lo) - padding
    r1 = max(g_base["cell_h"], row_hi) + padding
    c1 = max(g_base["cell_w"], col_hi) + padding
    canvas = np.zeros((r1 - r0, c1 - c0), dtype=np.uint8)
    canvas[-r0:-r0 + g_base["cell_h"], -c0:-c0 + g_base["cell_w"]] = g_base["sdf"]
    origin = (ox + c0, oy - r0)
    np.maximum(canvas, _circles_field(circles, canvas.shape, origin, padding,
                                      sdf_mode, mono), out=canvas)
    return _finish_composed_cell(canvas, origin, m, padding)


def _synth_mark_glyph(kind, g_base, upper, padding, em_px, sdf_mode, mono,
                      stem_px=None):
    """Litera z dorysowanym znakiem diakrytycznym (albo None)."""
    if kind == "ogonek":
        circles = _ogonek_circles(g_base, em_px)
    elif kind == "stroke":
        circles = _stroke_circles(g_base, em_px, upper)
    elif kind == "acute":
        circles = _acute_circles(g_base, em_px, stem_px)
    elif kind == "dot":
        circles = _dot_circles(g_base, em_px, stem_px)
    else:
        return None
    if not circles:
        return None
    return _compose_with_circles(g_base, circles, padding, sdf_mode, mono)


def _estimate_em_px(point_size, xheight):
    """Kwadrat firmowy (em) w pikselach - font_fixer liczy wszystkie proporcje
    w jednostkach em, wiec trzeba je przelozyc na piksele atlasu. Normalnie to
    wprost pointSize; gdy pole w foncie klamie (stary TMP, przeskalowany atlas),
    zgadujemy z x-height (~0.5 em)."""
    ps = float(point_size or 0)
    if xheight > 0 and not (0.25 * ps <= xheight <= 0.9 * ps):
        return xheight / 0.5
    return ps if ps > 0 else 40.0


def compose_marks_from_glyphs(chars, glyphs, missing, padding, point_size=None,
                              render_mode=None, quiet=False):
    """Sklada brakujace polskie litery z glifow, ktore font JUZ ma: litera
    bazowa + akcent wyciety z innej jego litery (kreska z 'ó', kropka z 'i'),
    a gdy nie ma z czego wyciac - litera bazowa + znak DORYSOWANY geometrycznie
    (jak font_fixer/fix_polish_fonts.py). Kreska i kropka rysuja sie zawsze,
    ogonek i przekreslenie tylko w trybie SYNTH_FULL.

    Dziala tak samo na glifach wycietych z atlasu, jak i na swiezo
    wyrenderowanych z TTF - liczy sie tylko format `glyphs`. Modyfikuje
    `chars`/`glyphs` w miejscu.

    point_size / render_mode sa potrzebne tylko do rysowania: pierwsze daje
    skale (proporcje ogonka sa w jednostkach em), drugie decyduje, czy dorysowany
    ksztalt ma byc polem odleglosci czy zwykla bitmapa.

    Zwraca (chars, glyphs, nadal_brakujace, zlozone_znaki).
    """
    if accent_composer is None or not missing:
        return chars, glyphs, missing, []
    have = {}
    for cp, gi in chars:
        have.setdefault(cp, gi)
    xheight = max((glyphs[have[ord(c)]]["metrics"]["bearing_y"]
                   for c in XHEIGHT_REFS if ord(c) in have), default=0.0)
    em_px = _estimate_em_px(point_size, xheight)
    sdf_mode = gen.is_sdf_render_mode(render_mode)
    mono = gen.is_mono_render_mode(render_mode)

    cache, composed, drawn, still = {}, [], [], []
    stem_cache = {}          # grubosc laski kroju, liczona raz (na wersaliki
                             # i minuskuly osobno) - patrz _font_stem_px
    for cp in missing:
        ch = chr(cp)
        spec = accent_composer.ACCENTS.get(ch)
        base_gi = have.get(ord(spec[0])) if spec else None
        if base_gi is None or glyphs[base_gi].get("empty"):
            still.append(cp)
            continue
        kind = spec[1]
        # Ogonek musi byc zaczepiony o rzeczywisty spod konkretnej litery.
        # Przesuniecie gotowego ogonka wycietego np. z malego "a" pod wersalik
        # "A" zachowuje jego prawa krawedz, ale nie punkt styku i sporadycznie
        # zostawia widoczna przerwe. W pelnym trybie mamy pewniejsza geometrie:
        # _pixel_attach szuka dolu tuszu bezposrednio w glifie docelowym.
        force_synth = kind == "ogonek" and SYNTH_FULL
        mark = (None if force_synth else
                _get_mark(kind, ch.isupper(), have, glyphs, xheight, em_px, cache))
        g = _compose_with_mark(glyphs[base_gi], mark, padding) if mark else None
        method = "wyciety"
        # ogonka i przekreslenia zwykle nie ma z czego wyciac - w trybie
        # "wszystkie" rysujemy je od zera; kreske i kropke rysujemy zawsze,
        # bo alternatywa jest litera z obcego kroju (patrz SYNTH_ALWAYS_KINDS)
        if g is None and kind in SYNTH_KINDS and (SYNTH_FULL
                                                 or kind in SYNTH_ALWAYS_KINDS):
            upper = ch.isupper()
            if upper not in stem_cache:
                stem_cache[upper] = _font_stem_px(have, glyphs, upper)
            g = _synth_mark_glyph(kind, glyphs[base_gi], upper, padding,
                                  em_px, sdf_mode, mono, stem_cache[upper])
            method = "rysowany"
        if g is None:
            still.append(cp)
            continue
        gi = COMPOSED_GLYPH_OFFSET + cp
        glyphs[gi] = g
        chars.append((cp, gi))
        (composed if method == "wyciety" else drawn).append(ch)
    if not quiet:
        if composed:
            print(f"  Akcent wyciety z wlasnych glifow fontu: {''.join(composed)}")
        if drawn:
            print(f"  Dorysowane geometrycznie z proporcji fontu: {''.join(drawn)}")
    return chars, glyphs, still, composed + drawn


def ask_font_source(gf, ttf_fonts, prompt, need=None, partial_ok=False):
    """Pyta o font: numer z listy fontow gry albo sciezka z dysku.

    need: znaki, ktore font ma dostarczyc (domyslnie PL_CHARS). Lista fontow
    z gry jest adnotowana pokryciem i sortowana - kompletne na gorze.
    partial_ok: to wybor fontu BAZOWEGO, wiec pozycje z '[brak: ...]' sa jak
    najbardziej sensowne - braki mozna potem uzupelnic fallbackiem albo
    transliteracja. Bez tej podpowiedzi wyglada to na slepa uliczke.
    Zwraca (bytes, opis) lub (None, None)."""
    need = PL_CHARS if need is None else need
    # wlasne fonty z folderu moje_fonty sa na liscie obok fontow z gry
    try:
        ttf_fonts = list(ttf_fonts or []) + (system_fonts.user_font_refs()
                                             if USE_SYSTEM_FONTS else [])
    except Exception as e:
        print(f"  ! nie udalo sie wczytac folderu moje_fonty ({e})")
    print(f"  {prompt}")
    if partial_ok:
        print("  (font z '[brak: ...]' tez mozna wybrac - brakujace litery"
              " uzupelnisz potem fallbackiem lub transliteracja)")
    ranked = []
    if ttf_fonts:
        for fr in ttf_fonts:
            note = font_coverage_note(gf, fr, need)
            ranked.append((0 if "OK" in note else 1, fr, note))
        ranked.sort(key=lambda r: r[0])
        usable = sum(1 for r in ranked if r[0] == 0)
        print(f"  Fonty (TTF) dostepne w grze ({usable} z {len(ranked)} "
              f"ma komplet potrzebnych znakow: {need}):")
        for i, (_rank, fr, note) in enumerate(ranked, 1):
            print(f"    [{i}] {fr['name']}  ({fr['size']} B, "
                  f"{os.path.basename(fr['path'])}){note}")
        print("    ...albo wklej sciezke do pliku TTF/OTF z dysku (Enter = anuluj)")
    else:
        print("  Wklej sciezke do pliku TTF/OTF z dysku (Enter = anuluj)")
    while True:
        ans = ask("  Wybor: ").strip().strip('"')
        if not ans:
            return None, None
        if ans.isdigit() and ranked and 1 <= int(ans) <= len(ranked):
            fr = ranked[int(ans) - 1][1]
            return get_font_data(gf, fr), fr["name"]
        if os.path.isfile(ans):
            with open(ans, "rb") as f:
                return f.read(), os.path.basename(ans)
        print("  ! nie ma takiego pliku ani numeru")


class SystemTTF(bytes):
    """Bajty TTF/OTF znalezionego w systemie fontu TEGO SAMEGO kroju co font gry.
    Znacznik dla rebuild_font_asset_from_atlas: jego glify bierzemy PRZED skladaniem."""
    desc = ""


def pick_system_font(tmp_name, family, style=""):
    """Szuka fontu o nazwie fontu gry w folderze moje_fonty, a potem w systemie;
    zwraca SystemTTF albo None.

    Bierze tylko font, ktory ma jakiekolwiek polskie znaki - bez nich nic by nie dal.
    W trybie automatycznym uzywa go bez pytania, interaktywnie pyta (Enter = tak).
    """
    if not USE_SYSTEM_FONTS:
        return None
    try:
        cands = system_fonts.find(tmp_name, family, style)
    except Exception as e:
        print(f"  ! szukanie fontow systemowych nie powiodlo sie ({e})")
        return None
    for sf in cands:
        try:
            data = sf.read_bytes()
        except Exception as e:
            print(f"  ! nie mozna odczytac {sf.label}: {e}")
            continue
        have, missing = ttf_polish_coverage(data, quiet=True)
        if not have:
            print(f"  W systemie jest {sf.label}, ale bez polskich znakow - pomijam")
            continue
        print(f"  Znaleziono {'we WLASNYCH fontach' if sf.user else 'w SYSTEMIE'}"
              f" ten sam font: {sf.label}")
        print(f"    polskie znaki: {have}" +
              (f"  (brak: {missing})" if missing else "  (komplet)"))
        if not AUTO_SYNTH:
            ans = ask("  Uzyc jego prawdziwych polskich znakow? [T/n]: ", "t").strip().lower()
            if ans in ("n", "nie"):
                continue
        else:
            print("  (automat) biore z niego prawdziwe polskie znaki")
        out = SystemTTF(data)
        out.desc = sf.label
        return out
    return None


def choose_ttf(tmp_name, family, ttf_fonts, gf, style=""):
    """Wybiera TTF glowny + opcjonalny fallback dla brakujacych znakow.

    Zwraca (mode, base_ttf, fallback_ttf, translit):
      ("ttf", base, fallback|None, bool) - normalna sciezka: font zrodlowy
                                        (+ opc. fallback, + opc. transliteracja
                                        dla tego, czego i tak zabraknie)
      ("atlas", None, fallback|None, True) - glify beda wyciete z biezacego
                                        atlasu fontu; dopasowany TTF sluzy tylko
                                        jako fallback dla znakow, ktorych nie da
                                        sie zlozyc z istniejacych glifow
      ("skip", None, None, False)       - pomin ten font
    """
    global AUTO_SYNTH
    # 1. automatyczne dopasowanie po nazwie rodziny / nazwie assetu
    fam_l = family.lower()
    name_l = tmp_name.lower().replace(" sdf", "").replace(" - glow", "").strip()
    base = None
    base_desc = ""
    for fr in ttf_fonts:
        fn = fr["name"].lower()
        if (fam_l and (fam_l in fn or fn in fam_l)) or \
           (name_l and (name_l in fn or fn in name_l)):
            base = get_font_data(gf, fr)
            base_desc = fr["name"]
            print(f"  Znaleziono w grze pasujacy Font: {fr['name']!r} "
                  f"({os.path.basename(fr['path'])})")
            break

    if base is None:
        print(f"  ! Nie znaleziono w grze fontu TTF pasujacego do {tmp_name!r}.")
        # ten sam font zainstalowany w systemie: prawdziwe polskie glify w kroju oryginalu
        sys_ttf = pick_system_font(tmp_name, family, style)
        if sys_ttf is not None:
            return "atlas", None, sys_ttf, True
        if AUTO_SYNTH:
            # font fallback (jesli w ogole potrzebny) dobierzemy PO sprawdzeniu,
            # czego naprawde nie da sie zlozyc z wlasnych glifow atlasu - patrz
            # rebuild_font_asset_from_atlas
            print("  (automat) zostaje przy glifach z atlasu, dopisze tylko"
                  " brakujace litery")
            return "atlas", None, None, True
        print("    [1] ZOSTAW glify z biezacego atlasu, dopisz tylko brakujace"
              " litery  (zalecane - wyglad fontu nie zmienia sie)")
        print("    [2] wygeneruj CALY font od nowa z wybranego pliku TTF/OTF")
        print("    [3] pomin ten font")
        print("    [4] jak [1], ale DLA WSZYSTKICH pozostalych fontow - nie pytaj wiecej")
        ans = ask("  Wybor [1]: ", "1").strip() or "1"
        if ans == "4":
            AUTO_SYNTH = True
            print("  Tryb automatyczny: zachowuje istniejace glify wszystkich"
                  " kolejnych fontow")
            ans = "1"
        if ans == "1":
            # Fallback dla tego, czego napewno nie uda sie zlozyc z wlasnych
            # glifow, dobieramy PO sprawdzeniu (patrz rebuild_font_asset_from_atlas) -
            # w tym momencie nie wiadomo jeszcze, czy atlas ma litery bazowe
            # (a/e/l...) do zlozenia ogonka/kreski, wiec pytanie o fallback
            # tutaj byloby zgadywaniem na wyrost.
            return "atlas", None, None, True
        if ans != "2":
            return "skip", None, None, False
        base, base_desc = ask_font_source(
            gf, ttf_fonts, "Wybierz font zrodlowy (caly font od nowa):",
            partial_ok=True)
        if base is None:
            return "skip", None, None, False

    # Nie regenerujemy calego atlasu tylko dlatego, ze znalezlismy zrodlowy TTF.
    # Autorskie fonty miewaja nakladajace sie kontury, ktore renderer SDF FreeType
    # potrafi wypelnic inaczej niz Unity (dziury w A/M/D). Istniejace glify z gry
    # sa zrodlem prawdy; TTF jest potrzebny najwyzej dla brakujacych liter.
    have, missing = ttf_polish_coverage(base)
    if missing:
        print(f"  ! Font {base_desc!r} nie ma polskich znakow: {missing}")
        if have:
            print(f"    (ma juz: {have})")
    else:
        print(f"  Font {base_desc!r}: komplet polskich znakow")

    if AUTO_SYNTH:
        print("  (automat) zachowuje glify z atlasu i dopisuje tylko polskie litery")
        return "atlas", None, base, True

    print("    [1] ZACHOWAJ glify z atlasu, dopisz tylko polskie litery  [zalecane]")
    print("    [2] wygeneruj CALY atlas od nowa z dopasowanego TTF/OTF")
    print("    [3] wybierz INNY font dla brakujacych liter")
    print("    [4] pomin ten font")
    print("    [5] jak [1], ale DLA WSZYSTKICH pozostalych fontow - nie pytaj wiecej")
    while True:
        ans = ask("  Wybor [1 - zachowaj atlas]: ", "1").strip() or "1"
        if ans == "1":
            return "atlas", None, base, True
        if ans == "2":
            return "ttf", base, None, False
        if ans == "3":
            fb, fb_desc = ask_font_source(
                gf, ttf_fonts, "Wybierz font dla brakujacych liter:", need=PL_CHARS)
            if fb is not None:
                remember_fallback(fb, fb_desc)
                return "atlas", None, fb, True
        if ans == "4":
            return "skip", None, None, False
        if ans == "5":
            AUTO_SYNTH = True
            print("  Tryb automatyczny: zachowuje istniejace glify wszystkich"
                  " kolejnych fontow")
            return "atlas", None, base, True


# ---------------------------------------------------------------------------
# Regeneracja i wstrzykiwanie
# ---------------------------------------------------------------------------

FALLBACK_GLYPH_OFFSET = 1_000_000  # unika kolizji indeksow glifow obu fontow


def atlas_texture_ref(gf, tree, font_info):
    """(sciezka pliku, nazwa SerializedFile, path_id) pierwszej tekstury atlasu;
    (None, None, 0) gdy font nie ma zadnego atlasu."""
    tex_ptr = (tree.get("m_AtlasTextures") or [{}])[0]
    pid = tex_ptr.get("m_PathID", 0)
    if not pid:
        return None, None, 0
    path, sname = gf.resolve_ref(font_info["path"], tex_ptr.get("m_FileID", 0),
                                 font_info.get("serialized_name"))
    return path, sname, pid


def encode_texture_data(atlas, tex_tree, tex_obj):
    """Bajty tekstury gotowe do zapisu + opis trybu.

    Na Switchu tekstury sa zapisane w ukladzie block-linear (swizzle wg
    m_PlatformBlob) - wpisanie liniowych pikseli daje "szum" zamiast liter.
    Ostatnie 8 bajtow blobu to 2x uint32 z rozmiarem danych - przy zmianie
    rozmiaru atlasu trzeba je poprawic, inaczej gra czyta zla ilosc bajtow.
    Aktualizuje m_PlatformBlob w tex_tree w miejscu.
    """
    from UnityPy.enums import TextureFormat
    from UnityPy.helpers import TextureSwizzler

    blob = list(tex_tree.get("m_PlatformBlob") or [])
    platform = getattr(tex_obj, "platform", None)
    if platform is None:
        platform = getattr(getattr(tex_obj, "assets_file", None), "target_platform", None)
    if not TextureSwizzler.is_switch_swizzled(platform, blob):
        return atlas.tobytes(), ""

    gobs = TextureSwizzler.get_switch_gobs_per_block(blob)
    block = TextureSwizzler.TEXTURE_FORMAT_BLOCK_SIZE_MAP[TextureFormat.Alpha8]
    h, w = atlas.shape
    pw, ph = TextureSwizzler.get_padded_texture_size(w, h, *block, gobs)
    note = f", swizzle Switch (gobs={gobs})"
    if (pw, ph) != (w, h):
        padded = np.zeros((ph, pw), dtype=np.uint8)
        padded[:h, :w] = atlas
        atlas = padded
        note += f", padding do {pw}x{ph}"
    data = bytes(TextureSwizzler.swizzle(atlas.tobytes(), pw, ph, *block, gobs))

    old_size = struct.unpack("<I", bytes(blob[-4:]))[0]
    if old_size != len(data):
        tex_tree["m_PlatformBlob"] = list(bytes(blob[:-8]) + struct.pack("<II", len(data), len(data)))
        note += f", blob {old_size}B -> {len(data)}B"
    return data, note


def rebuild_font_asset(gf, font_info, tree, tmp_obj, ttf, mat_index,
                       fallback_ttf=None, export_dir=None, translit=False):
    point_size = int(tree["m_FaceInfo"]["m_PointSize"])
    padding = int(tree["m_AtlasPadding"])
    atlas_w = int(tree["m_AtlasWidth"])
    atlas_h = int(tree["m_AtlasHeight"])

    # atlas bitmapowy (SMOOTH/RASTER) vs SDF - decyduje o sposobie renderowania
    render_mode = tree.get("m_AtlasRenderMode")
    sdf_mode = gen.is_sdf_render_mode(render_mode)
    if not sdf_mode:
        print(f"  Tryb atlasu: {gen.render_mode_desc(render_mode)}"
              f" - font BITMAPOWY, renderuje rastrowo (bez SDF)")

    # limit FreeType: spread <= 32; skaluj pointSize zeby zachowac proporcje
    # (dotyczy tylko SDF - w bitmapie padding to zwykly pusty margines)
    if sdf_mode and padding > MAX_SPREAD:
        scale = MAX_SPREAD / padding
        new_ps = max(MIN_POINT_SIZE, int(round(point_size * scale)))
        print(f"  padding {padding} > {MAX_SPREAD} -> padding={MAX_SPREAD}, "
              f"pointSize {point_size} -> {new_ps}")
        padding = MAX_SPREAD
        point_size = new_ps

    codepoints = set(gen.parse_ranges(RANGES))
    codepoints |= {ord(ch) for ch in PL_CHARS}
    codepoints |= {c["m_Unicode"] for c in tree["m_CharacterTable"]}
    codepoints = sorted(codepoints)

    face = freetype.Face(io.BytesIO(ttf))
    if fallback_ttf:
        fallback_ttf, _composed = compose_missing_accents(fallback_ttf)
        fb_face = freetype.Face(io.BytesIO(fallback_ttf))
    else:
        fb_face = None

    said_composed = []

    def collect_all(ps):
        """Glify z fontu glownego, brakujace akcenty zlozone z jego wlasnych
        liter, a dopiero reszta z fallbacku (indeksy z offsetem).

        Fallback jest skalowany do x-height fontu glownego - inaczej litery
        z drugiego kroju bywaja wyraznie mniejsze/wieksze od sasiednich.
        """
        chars, glyphs, missing = gen.collect_glyphs(face, codepoints, ps, padding,
                                                   render_mode=render_mode)
        chars, glyphs, missing, composed = compose_marks_from_glyphs(
            chars, glyphs, missing, padding, point_size=ps,
            render_mode=render_mode, quiet=bool(said_composed))
        if composed:
            said_composed.append(True)
        if missing and fb_face is not None:
            fb_chars, fb_glyphs, missing = scaled_fallback_glyphs(
                fb_face, missing, chars, glyphs, ps, padding, render_mode=render_mode)
            chars += [(cp, gi + FALLBACK_GLYPH_OFFSET) for cp, gi in fb_chars]
            glyphs.update({gi + FALLBACK_GLYPH_OFFSET: g for gi, g in fb_glyphs.items()})
        return chars, glyphs, missing

    # najpierw probujemy powiekszyc atlas (do ATLAS_MAX) zachowujac pointSize
    # (jakosc SDF); dopiero gdy i to nie wystarczy, zmniejszamy pointSize
    orig_w, orig_h = atlas_w, atlas_h
    max_size = max(ATLAS_MAX, atlas_w, atlas_h)
    while True:
        chars, glyphs, missing = collect_all(point_size)
        try:
            atlas_w, atlas_h, placements, free_rects = gen.pack_atlas(
                glyphs, orig_w, orig_h, allow_grow=True, max_size=max_size)
            break
        except SystemExit:
            point_size -= 4
            if point_size < MIN_POINT_SIZE:
                print("  ! BLAD: glify nie mieszcza sie nawet przy minimalnym pointSize - pomijam")
                return False
            print(f"  ! atlas za maly nawet przy {max_size}, probuje pointSize={point_size}")
    if (atlas_w, atlas_h) != (orig_w, orig_h):
        print(f"  Atlas powiekszony: {orig_w}x{orig_h} -> {atlas_w}x{atlas_h}")

    # transliteracja tylko dla tego, czego nie dal ani font glowny, ani fallback;
    # nie dodaje glifow (aliasuje istniejace), wiec nie wplywa na pakowanie
    if translit and missing:
        chars, missing = apply_transliteration(chars, missing)

    if missing:
        shown = ", ".join(f"U+{cp:04X}" for cp in missing[:8])
        print(f"  ! brak {len(missing)} znakow (nawet w fallbacku): {shown}"
              f"{' ...' if len(missing) > 8 else ''}")
    print(f"  Glify: {len(glyphs)} dla {len(chars)} znakow, "
          f"pointSize={point_size}, padding={padding}")

    face_info = gen.build_face_info(face, point_size)
    return finalize_font_asset(gf, font_info, tree, tmp_obj, mat_index, glyphs,
                               placements, free_rects, chars, atlas_w, atlas_h, padding,
                               face_info, export_dir, sdf_mode=sdf_mode)


def finalize_font_asset(gf, font_info, tree, tmp_obj, mat_index, glyphs, placements,
                        free_rects, chars, atlas_w, atlas_h, padding, face_info,
                        export_dir=None, sdf_mode=True):
    """Wspolny ogon rebuild_font_asset / rebuild_font_asset_from_atlas: pakuje
    tabele glifow/znakow do typetree, komponuje atlas i zapisuje (PATCH/EKSPORT).

    face_info=None oznacza "nie ruszaj m_FaceInfo" (uzywane, gdy glify pochodza
    z biezacego atlasu, a nie ze swiezo wczytanego TTF).
    sdf_mode=False (atlas bitmapowy) wylacza _GradientScale - to pole ma sens
    tylko w materialach z shaderem SDF.
    """
    glyph_rows, used_rects = [], []
    for gi in sorted(glyphs.keys()):
        g = glyphs[gi]
        cx, cy = placements[gi]
        ix, iy, iw, ih = g["inner"]
        m = g["metrics"]
        if g.get("empty"):
            iw = ih = 0  # komorka pakera 1x1 nie jest tuszem spacji
        glyph_rows.append({"index": gi, "w": m["width"], "h": m["height"],
                           "bx": m["bearing_x"], "by": m["bearing_y"],
                           "adv": m["advance"],
                           "rx": cx + ix, "ry": cy + iy, "rw": iw, "rh": ih})
        used_rects.append((cx, cy, g["cell_w"], g["cell_h"]))

    atlas = gen.compose_atlas(glyphs, placements, atlas_w, atlas_h)

    # --- TMP_FontAsset ---
    if face_info is not None:
        fi = tree["m_FaceInfo"]
        for k, v in face_info.items():
            if k in fi:
                fi[k] = v if isinstance(v, (int, str)) else float(v)

    gproto = copy.deepcopy(tree["m_GlyphTable"][0]) if tree["m_GlyphTable"] \
        else copy.deepcopy(GLYPH_PROTO)
    garr = []
    for g in glyph_rows:
        e = copy.deepcopy(gproto)
        e["m_Index"] = g["index"]
        e["m_Metrics"].update({"m_Width": float(g["w"]), "m_Height": float(g["h"]),
                               "m_HorizontalBearingX": float(g["bx"]),
                               "m_HorizontalBearingY": float(g["by"]),
                               "m_HorizontalAdvance": float(g["adv"])})
        e["m_GlyphRect"].update({"m_X": g["rx"], "m_Y": g["ry"],
                                 "m_Width": g["rw"], "m_Height": g["rh"]})
        e["m_Scale"] = 1.0
        e["m_AtlasIndex"] = 0
        garr.append(e)
    tree["m_GlyphTable"] = garr

    cproto = copy.deepcopy(tree["m_CharacterTable"][0]) if tree["m_CharacterTable"] \
        else copy.deepcopy(CHAR_PROTO)
    carr = []
    for cp, gi in chars:
        e = copy.deepcopy(cproto)
        e.update({"m_ElementType": 1, "m_Unicode": cp, "m_GlyphIndex": gi, "m_Scale": 1.0})
        carr.append(e)
    tree["m_CharacterTable"] = carr

    def rect_arr(rects):
        return [{"m_X": x, "m_Y": y, "m_Width": w, "m_Height": h} for x, y, w, h in rects]

    tree["m_UsedGlyphRects"] = rect_arr(used_rects)
    tree["m_FreeGlyphRects"] = rect_arr(free_rects)
    tree["m_AtlasWidth"] = atlas_w
    tree["m_AtlasHeight"] = atlas_h
    tree["m_AtlasPadding"] = padding

    tex_path, tex_sf, tex_pid = atlas_texture_ref(gf, tree, font_info)

    # stary TMP: do gry (i do eksportu) idzie ORYGINALNY typetree, nie widok
    save_tree = tree
    if font_info.get("legacy_tree") is not None:
        save_tree = modern_to_legacy(font_info["legacy_tree"], tree)
        print(f"  Stary TMP (Unity 5.x): zapis jako m_glyphInfoList "
              f"({len(save_tree['m_glyphInfoList'])} wpisow)")

    # podglad napisu z gotowych glifow - jeszcze przed zapisem, wiec dziala
    # tak samo w EKSPORCIE i w PATCHU (i widac go nawet, gdy zapis padnie)
    dump_fixed_preview_static(font_info["name"], tree, atlas, padding, export_dir)

    # ============== TRYB EKSPORT ==============
    if export_dir is not None:
        os.makedirs(export_dir, exist_ok=True)
        key = export_key(font_info)
        from PIL import Image
        png_path = os.path.join(export_dir, key + ".png")
        Image.fromarray(np.flipud(atlas), "L").save(png_path)

        materials = []
        if tex_path:
            for mpath, msf, mpid in mat_index.get(
                    (os.path.abspath(tex_path), tex_sf, tex_pid), []):
                menv = gf.env(mpath)
                mobj = find_object(menv, mpid, msf)
                mtree = mobj.read_typetree()
                materials.append({
                    "assets_rel": os.path.relpath(mpath, gf.data_dir),
                    "serialized_name": msf,
                    "path_id": mpid,
                    "name": mtree.get("m_Name", ""),
                })

        meta = {
            "type": "static_atlas",
            "label": font_info["name"],
            "assets_rel": os.path.relpath(font_info["path"], gf.data_dir),
            "serialized_name": font_info.get("serialized_name"),
            "tmp_path_id": font_info["path_id"],
            "tex_assets_rel": os.path.relpath(tex_path, gf.data_dir) if tex_path else None,
            "tex_serialized_name": tex_sf,
            "tex_path_id": tex_pid,
            "atlas_w": atlas_w,
            "atlas_h": atlas_h,
            "padding": padding,
            # null dla atlasu bitmapowego - instalator ma wtedy NIE ruszac
            # _GradientScale (to pole dotyczy wylacznie shaderow SDF)
            "gradient_scale": (padding + 1) if sdf_mode else None,
            "materials": materials,
            "tmp_tree": {k: v for k, v in save_tree.items()
                         if not k.startswith("_raw_")},
            "tmp_raw_layout": ("unity_6000_5" if save_tree.get("_raw_mode")
                               else None),
        }
        json_path = os.path.join(export_dir, key + ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"  Wyeksportowano: {json_path}")
        print(f"                  {png_path}")
        return True

    # ============== TRYB PATCH ==============
    if save_tree.get("_raw_mode"):
        tmp_obj.set_raw_data(write_tmp_font_raw(save_tree))
    else:
        tmp_obj.save_typetree(save_tree)
    gf.modified.add(font_info["path"])

    # --- tekstura atlasu ---
    if not tex_pid:
        print("  ! brak m_AtlasTextures - pomijam teksture")
        return True
    tex_env = gf.env(tex_path)
    tex_obj = find_object(tex_env, tex_pid, tex_sf)
    tex_tree = tex_obj.read_typetree()
    data, swz = encode_texture_data(atlas, tex_tree, tex_obj)
    tex_tree["m_Width"] = atlas_w
    tex_tree["m_Height"] = atlas_h
    tex_tree["m_CompleteImageSize"] = len(data)
    tex_tree["image data"] = data
    if "m_StreamData" in tex_tree:
        tex_tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    if tex_tree.get("m_TextureFormat") != 1:
        print(f"  ! tekstura ma format {tex_tree.get('m_TextureFormat')} "
              f"(oczekiwano 1=Alpha8) - ustawiam Alpha8")
        tex_tree["m_TextureFormat"] = 1
    tex_tree["m_MipCount"] = 1
    tex_obj.save_typetree(tex_tree)
    gf.modified.add(os.path.abspath(tex_path))
    print(f"  Tekstura {tex_pid} ({os.path.basename(tex_path)}): osadzono "
          f"{atlas_w}x{atlas_h} Alpha8{swz}")

    # --- materialy (_GradientScale = padding+1 tylko dla SDF, wymiary atlasu) ---
    mat_float_targets = {"_TextureWidth": float(atlas_w),
                         "_TextureHeight": float(atlas_h)}
    if sdf_mode:
        mat_float_targets["_GradientScale"] = float(padding + 1)
    for mpath, msf, mpid in mat_index.get(
            (os.path.abspath(tex_path), tex_sf, tex_pid), []):
        menv = gf.env(mpath)
        mobj = find_object(menv, mpid, msf)
        mtree = mobj.read_typetree()
        floats = mtree.get("m_SavedProperties", {}).get("m_Floats", [])
        changed = False
        for i, (fname, fval) in enumerate(floats):
            target = mat_float_targets.get(fname)
            if target is not None and fval != target:
                print(f"  Material {mpid} ({mtree.get('m_Name')!r}): "
                      f"{fname} {fval} -> {target}")
                floats[i] = (fname, target)
                changed = True
        if changed:
            mobj.save_typetree(mtree)
            gf.modified.add(os.path.abspath(mpath))

    # podglad PNG
    try:
        from PIL import Image
        preview_dir = os.path.join(tempfile.gettempdir(), "tmp_font_fix")
        os.makedirs(preview_dir, exist_ok=True)
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in font_info["name"])
        png = os.path.join(preview_dir, safe + ".png")
        Image.fromarray(np.flipud(atlas), "L").save(png)
        print(f"  Podglad: {png}")
    except Exception:
        pass
    return True


def extract_existing_glyphs(atlas_img, tree, padding):
    """Wycina glify JUZ OBECNE w biezacym atlasie SDF fontu (bez zadnego TTF).

    atlas_img: numpy uint8 [h, w], top-down (wiersz 0 = gora), jak z PIL.
    Zwraca (chars, glyphs) w formacie zgodnym z gen.pack_atlas/compose_atlas -
    dokladnie tak, jakby ten sam obszar zostal przed chwila wyrenderowany
    przez FreeType (metryki biora sie wprost z m_GlyphTable, wiec nie trzeba
    niczego zgadywac).
    """
    atlas_h, atlas_w = atlas_img.shape
    glyphs = {}
    for g in tree["m_GlyphTable"]:
        gi = g["m_Index"]
        m = g["m_Metrics"]
        metrics = {"width": m["m_Width"], "height": m["m_Height"],
                   "bearing_x": m["m_HorizontalBearingX"],
                   "bearing_y": m["m_HorizontalBearingY"],
                   "advance": m["m_HorizontalAdvance"]}
        r = g["m_GlyphRect"]
        rw, rh = int(r["m_Width"]), int(r["m_Height"])
        if rw <= 0 or rh <= 0:
            glyphs[gi] = {"metrics": metrics, "empty": True, "cell_w": 1, "cell_h": 1,
                          "sdf": np.zeros((1, 1), dtype=np.uint8), "inner": (0, 0, 1, 1)}
            continue
        cell_w, cell_h = rw + 2 * padding, rh + 2 * padding
        # m_GlyphRect jest w ukladzie TMP (0,0 = lewy-dolny atlasu), atlas_img
        # jest top-down (PIL) - trzeba przeliczyc Y
        x0 = int(r["m_X"]) - padding
        y0_top = atlas_h - (int(r["m_Y"]) + rh) - padding
        sdf = np.zeros((cell_h, cell_w), dtype=np.uint8)
        sx0, sy0 = max(0, x0), max(0, y0_top)
        sx1, sy1 = min(atlas_w, x0 + cell_w), min(atlas_h, y0_top + cell_h)
        if sx1 > sx0 and sy1 > sy0:
            sdf[sy0 - y0_top:sy1 - y0_top, sx0 - x0:sx1 - x0] = atlas_img[sy0:sy1, sx0:sx1]
        glyphs[gi] = {"metrics": metrics, "empty": False, "cell_w": cell_w, "cell_h": cell_h,
                      "sdf": sdf, "inner": (padding, padding, rw, rh)}
    chars = [(c["m_Unicode"], c["m_GlyphIndex"]) for c in tree["m_CharacterTable"]]
    return chars, glyphs


def rebuild_font_asset_from_atlas(gf, font_info, tree, tmp_obj, mat_index,
                                  fallback_ttf=None, export_dir=None,
                                  ttf_fonts=None, replace_chars="", prefer_real=False):
    """Zamiast renderowac caly font od zera, wycina ISTNIEJACE glify wprost
    z biezacego atlasu
    i tylko dopelnia to, czego naprawde brakuje:
      1. najpierw wlasne glify fontu (kreska/kropka wyciete, w SYNTH_FULL takze
         dorysowany ogonek/przekreslenie) - patrz compose_marks_from_glyphs,
      2. dla tego, co i tak zostanie (bo atlas nie ma nawet litery bazowej do
         zlozenia akcentu): fontem FALLBACK - podanym z gory (fallback_ttf) albo
         dobranym interaktywnie/automatycznie z ttf_fonts, gdy faktycznie czegos
         brakuje (dopiero TU wiadomo, czego, wiec nie zgadujemy na wyrost),
      3. transliteracja (ą->a itd.) dla tego, co i tak zostanie - znaki, ktore
         font juz ma, nie sa ruszane, dostaja swoj prawdziwy glif z atlasu.

    Dorobione litery renderujemy w tym samym trybie, co atlas (m_AtlasRenderMode):
    dla fontow bitmapowych rastrowo, bo SDF wsrod twardych glifow wygladaloby
    jak rozmyta szara plama.
    """
    # padding MUSI byc oryginalny - to on definiuje geometrie komorek w
    # istniejacym atlasie; klamrowanie go do MAX_SPREAD ucinaloby glify
    padding = int(tree["m_AtlasPadding"])
    point_size = int(tree["m_FaceInfo"]["m_PointSize"])
    atlas_w, atlas_h = int(tree["m_AtlasWidth"]), int(tree["m_AtlasHeight"])
    render_mode = tree.get("m_AtlasRenderMode")
    sdf_mode = gen.is_sdf_render_mode(render_mode)
    print(f"  Tryb atlasu: {gen.render_mode_desc(render_mode)}"
          f" -> dorabiam litery {'jako SDF' if sdf_mode else 'rastrowo (bitmapa)'}")

    tex_path, tex_sf, tex_pid = atlas_texture_ref(gf, tree, font_info)
    if not tex_pid:
        print("  ! brak tekstury atlasu - nie da sie wyciagnac istniejacych glifow")
        return False
    tex_env = gf.env(tex_path)
    tex_obj = find_object(tex_env, tex_pid, tex_sf)
    atlas_img = np.array(to_gray_image(tex_obj.read().image))

    chars, glyphs = extract_existing_glyphs(atlas_img, tree, padding)
    if replace_chars:
        forced = {ord(ch) for ch in replace_chars}
        if not forced <= {ord(ch) for ch in PL_CHARS}:
            raise ValueError("replace_chars moze zawierac tylko polskie litery")
        # The glyph exists, but its drawing was explicitly reported as wrong.
        # Remove only the Unicode mappings; retain old glyphs in case another
        # character/kerning pair still references them. Composition uses base
        # letters from this atlas and does not copy the defective mark.
        chars = [(cp, gi) for cp, gi in chars if cp not in forced]
        print(f"  Odtwarzam wskazane glify: {''.join(chr(cp) for cp in sorted(forced))}")
    have_cp = {cp for cp, _ in chars}
    # uzupelniamy TYLKO polskie litery - reszty atlas ma tyle, ile gra
    # potrzebuje, a dorenderowanie jej z obcego fontu psuloby spojnosc kroju
    missing = sorted({ord(ch) for ch in PL_CHARS} - have_cp)
    print(f"  Z biezacego atlasu: {len(glyphs)} glifow, {len(chars)} znakow; "
          f"brakuje {''.join(chr(c) for c in missing) or '-'}")

    # prefer_real: TTF to ten sam font zainstalowany w systemie - jego prawdziwe
    # glify sa lepsze niz skladane z liter atlasu, wiec bierzemy je jako pierwsze
    # (tylko te znaki, ktore font naprawde ma); reszte dopelni skladanie nizej
    if prefer_real and fallback_ttf and missing:
        if sdf_mode and padding > MAX_SPREAD:
            print(f"  ! padding {padding} > {MAX_SPREAD} (limit spreadu FreeType) -"
                  f" nie da sie dorenderowac SDF z fontu systemowego")
        else:
            taken, missing = add_real_glyphs_from_ttf(
                fallback_ttf, missing, chars, glyphs, point_size, padding,
                render_mode=render_mode)
            if taken:
                print(f"  Z prawdziwego fontu: {''.join(chr(c) for c in sorted(taken))}"
                      f"{'; skladane z atlasu: ' + ''.join(chr(c) for c in missing) if missing else ''}")

    # najpierw to, co da sie zrobic z WLASNYCH glifow fontu: kreska i kropka
    # wyciete z jego liter, a w trybie SYNTH_FULL takze dorysowany ogonek
    # i przekreslenie; do fallbacku idzie dopiero to, co zostanie
    chars, glyphs, missing, _composed = compose_marks_from_glyphs(
        chars, glyphs, missing, padding, point_size=point_size,
        render_mode=render_mode)
    if _composed and missing:
        print(f"  Z fallbacku pojda tylko: {''.join(chr(c) for c in missing)}")

    # fallback dobieramy TERAZ, dopiero gdy wiadomo, czego naprawde nie da sie
    # zlozyc z wlasnych glifow atlasu (a nie na wyrost, dla calego PL_CHARS)
    if fallback_ttf is None and missing:
        if AUTO_SYNTH:
            fallback_ttf, _fb_desc = auto_fallback([chr(c) for c in missing])
        else:
            why = ("brak modulu font_fixer - skladanie z wlasnych glifow wylaczone"
                   if accent_composer is None else
                   "nie da sie zlozyc z wlasnych glifow atlasu")
            print(f"  {why}: {''.join(chr(c) for c in missing)}")
            print("    [1] wybierz font FALLBACK (prawdziwe litery z innego kroju)")
            print("    [2] transliteracja (ą->a, ę->e...)")
            sub = ask("  Wybor [1]: ", "1").strip() or "1"
            if sub == "1":
                fallback_ttf, fb_desc = ask_font_source(
                    gf, ttf_fonts or [], "Wybierz font fallback (dla brakujacych liter):",
                    need="".join(chr(c) for c in missing))
                if fallback_ttf is None:
                    print("  Bez fontu - zostaje transliteracja")
                else:
                    remember_fallback(fallback_ttf, fb_desc)

    if fallback_ttf and missing:
        # limit spreadu dotyczy tylko SDF - bitmape mozna dorobic przy kazdym paddingu
        if sdf_mode and padding > MAX_SPREAD:
            print(f"  ! padding {padding} > {MAX_SPREAD} (limit spreadu FreeType) -"
                  f" nie da sie dorenderowac SDF pasujacego do atlasu, uzyje transliteracji")
        else:
            fallback_ttf, _composed = compose_missing_accents(fallback_ttf)
            fb_face = freetype.Face(io.BytesIO(fallback_ttf))
            fb_chars, fb_glyphs, missing = scaled_fallback_glyphs(
                fb_face, missing, chars, glyphs, point_size, padding,
                render_mode=render_mode)
            chars += [(cp, gi + FALLBACK_GLYPH_OFFSET) for cp, gi in fb_chars]
            glyphs.update({gi + FALLBACK_GLYPH_OFFSET: g for gi, g in fb_glyphs.items()})
            print(f"  Fallback dorenderowal: {len(fb_chars)} znakow")

    if missing:
        chars, missing = apply_transliteration(chars, missing)

    if missing:
        shown = ", ".join(f"U+{cp:04X}" for cp in missing[:8])
        print(f"  ! nadal brak {len(missing)} znakow: {shown}"
              f"{' ...' if len(missing) > 8 else ''}")

    try:
        atlas_w, atlas_h, placements, free_rects = gen.pack_atlas(
            glyphs, atlas_w, atlas_h, allow_grow=True,
            max_size=max(ATLAS_MAX, atlas_w, atlas_h))
    except SystemExit as e:
        print(f"  ! {e}")
        return False
    print(f"  Glify: {len(glyphs)} dla {len(chars)} znakow, atlas {atlas_w}x{atlas_h}")

    return finalize_font_asset(gf, font_info, tree, tmp_obj, mat_index, glyphs,
                               placements, free_rects, chars, atlas_w, atlas_h, padding,
                               face_info=None, export_dir=export_dir, sdf_mode=sdf_mode)


# ---------------------------------------------------------------------------
# Fonty DYNAMICZNE: naprawa w samym pliku TTF
#
# Dynamiczny TMP_FontAsset nie ma nic do wypiekania - glify dorabia sobie sam
# w runtime, ale WYLACZNIE z tego, co jest w jego zrodlowym TTF
# (m_SourceFontFile). Naprawa musi wiec trafic do konturow fontu, nie do
# atlasu: albo dorabiamy brakujace litery wprost w TTF (technika z
# font_fixer/fix_polish_fonts.py), albo wklejamy je z innego fontu, albo
# podmieniamy caly plik.
# ---------------------------------------------------------------------------

def _ttf_glyph_height(glyph_set, cmap, ch):
    """Wysokosc konturu litery `ch` w jednostkach fontu (0 = brak/pusty)."""
    gname = cmap.get(ord(ch))
    if not gname:
        return 0
    try:
        bb = accent_composer.bbox(accent_composer.record_glyph(glyph_set, gname))
    except Exception:
        return 0
    return (bb[3] - bb[1]) if bb else 0


def _fallback_scale(base_gs, base_cmap, base_upm, fb_gs, fb_cmap, fb_upm, ref_chars):
    """Skala dla glifow wklejanych z fallbacku.

    Samo zrownanie unitsPerEm nie wystarcza - dwa kroje o tym samym upm maja
    rozny x-height, wiec wklejone 'ę' bywa wyraznie mniejsze od 'e' obok.
    Mierzymy te same litery w obu fontach i bierzemy mediane stosunku
    wysokosci (mediana, bo jedna litera moze miec krojowy wyjatek).
    """
    ratios = []
    for ch in ref_chars:
        bh = _ttf_glyph_height(base_gs, base_cmap, ch)
        fh = _ttf_glyph_height(fb_gs, fb_cmap, ch)
        if bh > 0 and fh > 0:
            ratios.append(bh / fh)
    if not ratios:
        return base_upm / fb_upm if fb_upm else 1.0
    ratios.sort()
    return ratios[len(ratios) // 2]


def _scale_ops(ops, scale, target_quadratic, upm):
    """Skaluje kontury i - gdy trzeba - zamienia krzywe szescienne (CFF) na
    kwadratowe, bo tablica 'glyf' innych nie przyjmie."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.pens.transformPen import TransformPen
    rec = RecordingPen()
    accent_composer.replay(ops, TransformPen(rec, (scale, 0, 0, scale, 0, 0)))
    ops = rec.value
    if target_quadratic and any(op == "curveTo" for op, _ in ops):
        from fontTools.pens.cu2quPen import Cu2QuPen
        rec2 = RecordingPen()
        accent_composer.replay(ops, Cu2QuPen(rec2, max_err=max(upm, 1000) / 1000.0))
        ops = rec2.value
    return ops


def _finalize_added_glyphs(font, ymax, ymin):
    """Porzadki po dopisaniu glifow (jak w fix_polish_fonts.fix_font)."""
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    for tag in ("hdmx", "LTSH"):  # cache'e per-glif, nie znaja nowych glifow
        if tag in font:
            del font[tag]
    if "post" in font and font["post"].formatType == 2.0:
        font["post"].formatType = 3.0
    hhea, os2 = font.get("hhea"), font.get("OS/2")
    if hhea:
        hhea.ascent = max(hhea.ascent, round(ymax))
        hhea.descent = min(hhea.descent, round(ymin))
    if os2:
        os2.usWinAscent = max(os2.usWinAscent, round(ymax))
        os2.usWinDescent = max(os2.usWinDescent, round(-ymin))


# open_faces / save_faces / merge_reports i sama naprawa bajtow TTF siedza w
# tools/font_fixer/fix_polish_fonts.py - wspolne z narzedziem dla Unreala
# (tools/font_fixer/unreal/fix_unreal_polish_fonts.py).
def _no_composer(*_a, **_k):
    raise RuntimeError("brak modulu font_fixer/fix_polish_fonts.py")


open_faces = getattr(accent_composer, "open_faces", _no_composer)
save_faces = getattr(accent_composer, "save_faces", _no_composer)
merge_reports = getattr(accent_composer, "merge_reports", _no_composer)


def _graft_into_font(base, chars, fb_bytes, quiet=False):
    """Wkleja glify `chars` z fontu fallback do jednego otwartego TTFont."""
    fb = accent_composer.TTFont(io.BytesIO(fb_bytes), fontNumber=0, lazy=False)
    base_cmap, fb_cmap = base.getBestCmap(), fb.getBestCmap()
    base_gs, fb_gs = base.getGlyphSet(), fb.getGlyphSet()
    base_upm = base["head"].unitsPerEm
    fb_upm = fb["head"].unitsPerEm
    quadratic = "glyf" in base
    subtables = [t for t in base["cmap"].tables if t.isUnicode()]

    slots = accent_composer.GlyphSlots(base)

    scales = {}
    for upper in (False, True):
        refs = SCALE_REF_UPPER if upper else SCALE_REF_LOWER
        scales[upper] = _fallback_scale(base_gs, base_cmap, base_upm,
                                        fb_gs, fb_cmap, fb_upm, refs)
    for upper, s in scales.items():
        if abs(s - 1.0) > 0.02 and not quiet:
            print(f"  Skala fallbacku ({'wielkie' if upper else 'male'}): x{s:.2f}")

    grafted, still = [], []
    ymax, ymin, n_added = 0, 0, 0
    for ch in chars:
        fb_gname = fb_cmap.get(ord(ch))
        if not fb_gname:
            still.append(ch)
            continue
        try:
            ops = accent_composer.record_glyph(fb_gs, fb_gname)
            ops = _scale_ops(ops, scales[not ch.islower()], quadratic, base_upm)
            bb = accent_composer.bbox(ops)
            if not bb:
                still.append(ch)
                continue
            advance = fb["hmtx"][fb_gname][0] * scales[not ch.islower()]
            base_ch = accent_composer.ACCENTS[ch][0]
            donor = base_cmap.get(ord(base_ch)) or base.getGlyphOrder()[0]
            name, reuse = slots.take(ch)
            if name is None:
                still.append(ch)  # font bez miejsca na nowe glify
                continue
            accent_composer.add_glyph(base, name, ops, round(advance),
                                      round(bb[0]), donor, reuse=reuse)
            for st in subtables:
                st.cmap[ord(ch)] = name
            grafted.append(ch)
            n_added += 1
            ymax, ymin = max(ymax, bb[3]), min(ymin, bb[1])
        except Exception as e:
            if not quiet:
                print(f"  ! {ch}: nie udalo sie wkleic z fallbacku ({e})")
            still.append(ch)

    if n_added:
        _finalize_added_glyphs(base, ymax, ymin)
    if slots.recycled and not quiet:
        print(f"  Font na limicie {accent_composer.GLYPH_MAX} glifow -"
              f" {slots.recycled} wklejonych weszlo na miejsce glifow"
              f" nieosiagalnych z cmap")
    return grafted, still


def graft_chars_from_fallback(ttf_bytes, chars, fb_bytes):
    """Wkleja prawdziwe glify `chars` z fontu fallback do `ttf_bytes`.

    Uzywane dla liter, ktorych nie da sie zlozyc z wlasnych glifow fontu
    (np. ą/ę w foncie bez zadnego ogonka). Glify sa skalowane do wysokosci
    liter fontu bazowego, zeby nie odstawaly rozmiarem.

    Zwraca (nowe_bajty, wklejone, nadal_brakujace).
    """
    try:
        coll, fonts = open_faces(ttf_bytes)
        # przy kolekcji znak liczymy jako wklejony tylko wtedy, gdy wszedl do
        # KAZDEGO kroju - gra siega po jeden z nich i nie wiadomo po ktory
        done = None
        still = []
        for i, f in enumerate(fonts):
            g, s = _graft_into_font(f, chars, fb_bytes, quiet=i > 0)
            done = set(g) if done is None else (done & set(g))
            still += [ch for ch in s if ch not in still]
        grafted = [ch for ch in chars if ch in (done or ())]
        if not grafted:
            return ttf_bytes, [], list(chars)
        return save_faces(coll, fonts), grafted, still
    except Exception as e:
        print(f"  ! wklejanie z fallbacku nie powiodlo sie ({e})")
        return ttf_bytes, [], list(chars)


def fix_polish_in_ttf(ttf_bytes, missing, add_accents=True, acute_only=None):
    """Dorabia brakujace polskie znaki wprost w pliku TTF - ta sama technika co
    font_fixer/fix_polish_fonts.py.

    acute_only=None bierze zakres z globalnego trybu (SYNTH_FULL):
      tryb "wszystkie" (domyslny) = full_set fix_polish_fonts, czyli takze
        ogonek (ą ę) rysowany krzywa Beziera i przekreslenie ł;
      tryb "tylko kreska i kropka" (acute_only=True) sklada wylacznie litery
        ze znakiem u gory (ć ń ó ś ź ż + wersaliki) - kreske i kropke da sie
        wyciac z wlasnego glifu fontu, a gdy nie ma z czego, sa dorysowane
        (make_acute / make_dot); ogonek i belka zostaja wtedy w 'plain'
        i lepiej wziac je z fontu fallback.

    add_accents=False => sama transliteracja: brakujace znaki dostaja kopie
    litery bez ogonka.

    Zwraca (nowe_bajty, raport) - raport to slownik jak z
    fix_polish_fonts.fix_font (composed / synthesized / plain / unfixable);
    przy bledzie (None, None).
    """
    if accent_composer is None:
        print("  ! brak modulu font_fixer/fix_polish_fonts.py - nie moge dorabiac glifow")
        return None, None
    if acute_only is None:
        acute_only = not SYNTH_FULL
    def _face_info(f, _i, total):
        if _i == 0 and total > 1:
            print(f"  Plik to kolekcja ({total} krojow) - naprawiam kazdy")
        n_glyphs = len(f.getGlyphOrder())
        if n_glyphs >= accent_composer.GLYPH_MAX:
            print(f"  Font ma {n_glyphs} glifow (limit formatu:"
                  f" {accent_composer.GLYPH_MAX}) - nowe glify pojda"
                  f" na miejsce tych nieosiagalnych z cmap")

    try:
        new_bytes, report = accent_composer.fix_font_bytes(
            ttf_bytes, chars=missing, add_accents=add_accents,
            full_set=not acute_only, on_face=_face_info)
        recycled = report.pop("_recycled", 0)
        if recycled:
            print(f"  Zrecyklowane martwe sloty glifow: {recycled}")
        return new_bytes, report
    except Exception as e:
        print(f"  ! naprawa fontu nie powiodla sie ({e})")
        return None, None


def print_ttf_report(report):
    if report["composed"]:
        print(f"  Akcent wyciety z wlasnych glifow: {' '.join(report['composed'])}")
    if report["synthesized"]:
        print(f"  Dorysowane wprost z proporcji fontu: "
              f"{' '.join(report['synthesized'])}")
    if report["plain"]:
        print(f"  Na razie wersja bez ogonka: {' '.join(report['plain'])}")
    if report["unfixable"]:
        print(f"  Brak litery bazowej, pominiete: {' '.join(report['unfixable'])}")


def fix_dynamic_font_ttf(gf, ttf_fonts, ttf, label, missing):
    """Interaktywna naprawa zrodlowego TTF fontu dynamicznego.

    Zwraca gotowe bajty TTF albo None (pomin ten font).
    """
    global AUTO_SYNTH
    synth_broken = False   # dorabianie glifow w TYM pliku juz raz padlo
    while True:
        print(f"  Font zrodlowy {label!r} nie ma: {''.join(missing)}")
        if AUTO_SYNTH and not synth_broken:
            print("  (automat) dorabiam brakujace litery z wlasnych glifow fontu")
            ans = "1"
        else:
            suffix = ("  [nie zadzialalo dla tego fontu]" if synth_broken
                      else "  [zalecane]")
            if SYNTH_FULL:
                print("    [1] DOROB WSZYSTKIE brakujace litery w foncie: kreska"
                      " i kropka z wlasnych")
                print(f"        glifow, ogonek i przekreslenie dorysowane"
                      f" (jak font_fixer){suffix}")
            else:
                print(f"    [1] DOROB kreske (ć ń ó ś ź) z wlasnych glifow fontu,"
                      f" a ą ę ł ż wez z fontu FALLBACK{suffix}")
            print("    [2] PODMIEN caly font na inny plik TTF/OTF"
                  + ("  [zalecane]" if synth_broken else ""))
            print("    [3] TRANSLITERACJA - brakujace znaki dostana glify bez ogonkow"
                  " (ą->a, ę->e...)")
            print("    [4] pomin ten font")
            print("    [5] pomin ten font i dorabiaj pozostale automatycznie"
                  if synth_broken else
                  "    [5] jak [1], ale DLA WSZYSTKICH pozostalych fontow"
                  " - nie pytaj wiecej")
            # po nieudanym dorabianiu domyslna staje sie podmiana fontu - inaczej
            # Enter zapetla sie na opcji, ktora dla tego pliku nie ma jak zadzialac
            dflt = "2" if synth_broken else "1"
            # w --auto po nieudanym dorabianiu nie ma kogo zapytac o inny plik
            # fontu - wtedy [4], czyli pomin ten font i lec dalej
            ans = ask(f"  Wybor [{dflt}]: ", "4" if AUTO else dflt).strip() or dflt

        if ans == "5":
            AUTO_SYNTH = True
            print("  Tryb automatyczny: kolejne fonty naprawiam z wlasnych glifow"
                  " bez pytania")
            if synth_broken:
                print("  Ten font pomijam po bledzie; automat obejmie kolejne fonty")
                return None
            ans = "1"

        if ans == "4":
            return None

        if ans == "2":
            new, new_desc = ask_font_source(gf, ttf_fonts,
                                           "Wybierz font zastepczy (caly font od nowa):",
                                           partial_ok=True)
            if new is None:
                continue
            _have, new_missing = ttf_polish_coverage(new)
            if not new_missing:
                print(f"  Font {new_desc!r}: komplet polskich znakow")
                return new
            ttf, label, missing = new, new_desc, new_missing
            synth_broken = False  # inny plik fontu - dorabianie moze sie udac
            continue

        if ans == "3":
            fixed, report = fix_polish_in_ttf(ttf, missing, add_accents=False)
            if fixed is None:
                synth_broken = True
                print("  Tego pliku fontu nie da sie przerobic - wybierz [2]"
                      " (inny font) albo [4] (pomin)")
                continue
            print_ttf_report(report)
            return fixed

        if ans != "1":
            continue
        if synth_broken:
            print("  Dorabianie juz nie powiodlo sie dla tych danych - wybierz"
                  " [2], [4] albo [5] (pomin i kontynuuj automatycznie)")
            continue

        # [1] dorabianie w konturach fontu; zakres z globalnego trybu:
        # "wszystkie" (domyslnie) rysuje takze ogonek i przekreslenie, a tryb
        # okrojony zostawia je w 'plain' i oddaje do fallbacku razem z ą/ę.
        fixed, report = fix_polish_in_ttf(ttf, missing, add_accents=True)
        if fixed is None:
            synth_broken = True
            print("  Tego pliku fontu nie da sie przerobic - wybierz [2]"
                  " (inny font) albo [4] (pomin)")
            continue
        print_ttf_report(report)
        leftover = report["plain"] + report["unfixable"]
        if not leftover:
            return fixed
        print(f"  Do wziecia z fontu fallback: {' '.join(leftover)}")
        if AUTO_SYNTH:
            # tryb automatyczny: bierzemy fallback wybrany wcześniej, a jeśli
            # zadnego nie bylo - zostaje transliteracja, bez pytania
            fb, fb_desc = auto_fallback(leftover)
            if fb is None:
                print("  (automat) bez fallbacku - zostaje transliteracja")
                return fixed
        else:
            print("    [1] wybierz font FALLBACK (prawdziwe ą/ę/ł/ż z innego kroju)")
            print("    [2] zostaw dla nich wersje bez ogonkow (transliteracja)")
            sub = ask("  Wybor [1]: ", "1").strip() or "1"
            if sub != "1":
                return fixed
            fb, fb_desc = ask_font_source(
                gf, ttf_fonts, "Wybierz font fallback (dla brakujacych liter):",
                need="".join(leftover))
            if fb is None:
                print("  Bez fallbacku - zostaje transliteracja")
                return fixed
            remember_fallback(fb, fb_desc)
        fixed2, grafted, still = graft_chars_from_fallback(fixed, leftover, fb)
        if grafted:
            print(f"  Wklejone z {fb_desc!r}: {' '.join(grafted)}")
        if still:
            print(f"  ! {fb_desc!r} tez nie ma: {' '.join(still)}"
                  f" - zostaja bez ogonkow")
        return fixed2


def fix_dynamic_font_interactive(gf, d, ttf_fonts, export_dir):
    """Cala sciezka dla jednego dynamicznego TMP_FontAsset."""
    try:
        src_ttf = get_dynamic_source_font_data(gf, d["tree"], d["path"],
                                               d.get("serialized_name"))
    except Exception as e:
        print(f"  ! nie mozna odczytac zrodlowego TTF ({e})")
        src_ttf = None

    if src_ttf is None:
        print("  ! font dynamiczny bez czytelnego zrodlowego TTF"
              " - zostaje podmiana calego pliku")
        if AUTO_SYNTH:
            print("  (automat) pominieto: nie ma konturow do dorobienia liter."
                  " Wskaz ten font recznie i wybierz plik TTF/OTF.")
            return False
        new, _desc = ask_font_source(gf, ttf_fonts,
                                     "Wybierz font zrodlowy:", partial_ok=True)
        if new is None:
            print("  pominieto")
            return False
        missing = ttf_polish_coverage(new, quiet=True)[1]
        if missing:
            new = fix_dynamic_font_ttf(gf, ttf_fonts, new, _desc, missing)
            if new is None:
                return False
        replace_dynamic_source_font(gf, d["tree"], d, new, export_dir)
        return True

    missing = d["src_missing"] or ttf_polish_coverage(src_ttf, quiet=True)[1]
    label = d.get("family") or d["name"]
    if not missing:
        print("  Zrodlowy TTF ma komplet polskich znakow - nie ma czego naprawiac")
        return True
    ttf = fix_dynamic_font_ttf(gf, ttf_fonts, src_ttf, label, missing)
    if ttf is None:
        print("  pominieto")
        return False
    _have, left = ttf_polish_coverage(ttf, quiet=True)
    if left:
        print(f"  ! w gotowym foncie nadal brakuje: {left}")
    replace_dynamic_source_font(gf, d["tree"], d, ttf, export_dir)
    return True


# Assety Font zapisane juz w tej sesji - zeby font naprawiony jako zrodlo
# TMP-a dynamicznego nie wrocil drugi raz na liste fontow UI.
_patched_font_refs = set()


def font_ref_ident(font_ref):
    return (os.path.abspath(font_ref["path"]), font_ref.get("serialized_name"),
            font_ref["path_id"])


def write_font_asset_ttf(gf, font_ref, ttf, label, export_dir=None,
                         key_info=None, font_name=None):
    """Wpisuje bajty TTF w m_FontData assetu Font - eksport albo patch.

    Dwa wywolania: zrodlowy font TMP-a dynamicznego (m_SourceFontFile) oraz
    zwykly asset Font, ktorym renderuje UI Text. `key_info` to wpis, po ktorym
    liczy sie nazwa plikow w fixed_fonts/ - dla TMP-a jest nim sam
    TMP_FontAsset (zeby eksport nazywal sie jak font na liscie), domyslnie sam
    `font_ref`. `font_name` to nazwa assetu Font dla instalatora (dopasowanie
    po nazwie, gdy path_id rozjedzie sie miedzy buildami gry).
    """
    fpath = font_ref["path"]
    fsf = font_ref.get("serialized_name")
    pid = font_ref["path_id"]

    dump_fixed_preview_dynamic(label, ttf, export_dir)
    _patched_font_refs.add(font_ref_ident(font_ref))

    if export_dir is not None:
        os.makedirs(export_dir, exist_ok=True)
        key = export_key(key_info or font_ref)
        ttf_path = os.path.join(export_dir, key + ".ttf")
        with open(ttf_path, "wb") as f:
            f.write(ttf)
        # m_Name samego assetu Font (a NIE nazwa TMP_FontAsset z `label`) -
        # instalator dopasowuje po nazwie, gdy path_id sie rozjedzie miedzy
        # buildami gry. Gdy nie da sie odczytac, zostaje samo path_id.
        if not font_name:
            try:
                for o in gf.env(fpath).objects:
                    if o.path_id == pid and o.type.name == "Font":
                        font_name = getattr(o.read(check_read=False), "m_Name", None)
                        break
            except Exception:
                pass

        meta = {
            "type": "dynamic_font_data",
            "label": label,
            "font_assets_rel": os.path.relpath(fpath, gf.data_dir),
            "font_serialized_name": fsf,
            "font_path_id": pid,
            "ttf_file": os.path.basename(ttf_path),
        }
        if font_name:
            meta["font_name"] = font_name
        json_path = os.path.join(export_dir, key + ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)
        print(f"  Wyeksportowano: {json_path}")
        print(f"                  {ttf_path}")
        return

    env = gf.env(fpath)
    obj = find_object(env, pid, fsf)
    ftree = obj.read_typetree()
    print(f"  Font {pid} ({ftree.get('m_Name')!r}): "
          f"{len(ftree.get('m_FontData', b''))} -> {len(ttf)} B")
    ftree["m_FontData"] = ttf
    obj.save_typetree(ftree)
    gf.modified.add(os.path.abspath(fpath))


def replace_dynamic_source_font(gf, tree, font_info, ttf, export_dir=None):
    """Dla fontow dynamicznych: podmienia dane TTF zrodlowego Fontu."""
    src = tree.get("m_SourceFontFile", {})
    pid = src.get("m_PathID", 0)
    if not pid:
        print("  ! font dynamiczny bez m_SourceFontFile - pomijam")
        return
    try:
        fpath, fsf = gf.resolve_ref(font_info["path"], src.get("m_FileID", 0),
                                    font_info.get("serialized_name"))
    except Exception as e:
        # bez wiedzy, w ktorym pliku gry siedzi zrodlowy Font, nie ma czego
        # patchowac ani co zapisac w metadanych dla instalatora
        print(f"  ! nie wiem, gdzie lezy zrodlowy Font ({e}) - pomijam")
        return
    write_font_asset_ttf(gf, {"path": fpath, "serialized_name": fsf,
                              "path_id": pid},
                         ttf, font_info["name"], export_dir, key_info=font_info)


# ---------------------------------------------------------------------------
# Zwykle assety Font (UI Text / stare GUI)
#
# Nie kazda gra jedzie na TextMesh Pro - UnityEngine.UI.Text i GUIStyle
# renderuja wprost z assetu Font, czyli z TTF-a osadzonego w m_FontData. Nie ma
# tu atlasu do wypiekania ani materialow do ruszania: brakujace litery dorabia
# sie w konturach pliku (ta sama sciezka i to samo menu, co dla zrodlowego TTF
# fontu dynamicznego) i wpisuje z powrotem w m_FontData.
#
# Do tej pory takie fonty byly zbierane tylko jako pula DAWCOW glifow dla
# fontow TMP - gra bez ani jednego TMP_FontAsset konczyla sie komunikatem "nie
# znaleziono" i nikt nie sprawdzil, czy jej wlasne TTF-y maja polskie znaki.
# ---------------------------------------------------------------------------

def describe_plain_fonts(gf, ttf_fonts):
    """Assety Font + to, czego im brakuje.

    Zwraca [{**font_ref, data, family, missing, chars, skip_reason, done}];
    `done` = font zapisany juz w tej sesji (jako zrodlo fontu TMP).
    """
    out = []
    for fr in ttf_fonts:
        try:
            data = get_font_data(gf, fr)
        except Exception as e:
            print(f"  ! {fr['name']}: nie mozna odczytac danych fontu ({e})")
            continue
        cps = ttf_codepoints(data)
        _have, missing = ttf_polish_coverage(data, quiet=True)
        out.append({**fr, "data": data, "family": ttf_family_name(data),
                    "missing": missing, "chars": len(cps),
                    "skip_reason": unsupported_reason(cps),
                    "done": font_ref_ident(fr) in _patched_font_refs})
    return out


def dump_plain_font_previews(fonts):
    """PNG z aktualnym wygladem kazdego assetu Font (probka tekstu z TTF).

    Osobny prefiks (ttf_), zeby te podglady nie mieszaly sie z numeracja fontow
    TMP w tym samym folderze."""
    out_dir = os.path.join(app_dir(), PREVIEW_DIR_NAME)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        print(f"! nie mozna utworzyc {out_dir}: {e}")
        return
    wanted = [f for f in fonts if not f["skip_reason"]]
    saved = 0
    for i, f in enumerate(fonts, 1):
        if f["skip_reason"]:
            continue
        try:
            render_ttf_sample(f["data"]).save(
                os.path.join(out_dir,
                             f"ttf_{i:02d}_{safe_name(f['name']) or 'font'}.png"))
            saved += 1
        except Exception as e:
            print(f"  ! [{i}] {f['name']}: nie udalo sie zrobic podgladu ({e})")
    print(f"Podglady fontow Font ({saved}/{len(wanted)}): {out_dir}")


def fix_plain_fonts(gf, ttf_fonts, export_dir, ask_first=False):
    """Interaktywna naprawa zwyklych assetow Font. True, gdy cos naprawiono.

    `ask_first` - gra ma tez fonty TMP i wlasnie je przerobilismy, wiec o fonty
    UI pytamy dopiero wtedy, gdy naprawde jest co naprawiac.
    """
    if not ttf_fonts:
        return False
    fonts = describe_plain_fonts(gf, ttf_fonts)
    todo = [f for f in fonts
            if f["missing"] and not f["skip_reason"] and not f["done"]]
    if ask_first:
        if not todo:
            return False
        print(f"\nW grze jest jeszcze {len(todo)} zwyklych fontow (asset Font,"
              f" UI Text) bez polskich znakow.")
        ans = ask("Naprawic takze je? [T/n]: ", "t").strip().lower() or "t"
        if ans not in ("t", "y", "1", "tak"):
            return False

    print("\nZnalezione fonty Font (TTF, UI Text / stare GUI):")
    for i, f in enumerate(fonts, 1):
        if f["done"]:
            status = "juz naprawiony (zrodlo fontu TMP)"
        elif f["skip_reason"]:
            status = "ODSIANY: " + f["skip_reason"]
        elif not f["missing"]:
            status = "polskie OK"
        else:
            status = f"BRAK: {f['missing']}"
        fam = f["family"]
        extra = f", {fam}" if fam and fam != f["name"] else ""
        print(f"  [{i}] {f['name']:45s} {f['chars']:5d} znakow  [{status}]  "
              f"({os.path.basename(f['path'])}{extra})")

    dropped = [f for f in fonts if f["skip_reason"]]
    if dropped:
        print(f"\nOdsiane ({len(dropped)}): fonty azjatyckie / bez liter"
              " lacinskich - nie ma czym renderowac polskiego tekstu.")
        print("  Pomijam je w podgladach i w naprawie; da sie je wskazac"
              " numerem recznie.")

    if not todo:
        print("\nNie ma czego naprawiac: zwykle fonty z lacinskim alfabetem"
              " maja polskie znaki.")
        return False

    print("\nZapisywanie podgladow (jak fonty wygladaja teraz)...")
    dump_plain_font_previews(fonts)

    ans = ask(f"\nKtore naprawic? (numery po przecinku / Enter = wszystkie"
              f" bez polskich [{len(todo)}]): ").strip()
    if ans:
        chosen = []
        for part in ans.split(","):
            try:
                f = fonts[int(part.strip()) - 1]
            except (ValueError, IndexError):
                continue
            if f["skip_reason"]:
                print(f"  ! {f['name']}: {f['skip_reason']} - naprawiam"
                      f" na zyczenie")
            chosen.append(f)
        todo = chosen
    if not todo:
        return False

    failed, done = [], 0
    for f in todo:
        print(f"\n=== {green(f['name'])} ({os.path.basename(f['path'])},"
              f" path_id {f['path_id']}) ===")
        # jak przy fontach TMP: jeden polamany plik nie moze zabrac ze soba
        # calej sesji
        try:
            missing = f["missing"] or ttf_polish_coverage(f["data"], quiet=True)[1]
            if not missing:
                print("  Font ma komplet polskich znakow - nie ma czego naprawiac")
                continue
            ttf = fix_dynamic_font_ttf(gf, ttf_fonts, f["data"],
                                       f.get("family") or f["name"], missing)
            if ttf is None:
                print("  pominieto")
                continue
            _have, left = ttf_polish_coverage(ttf, quiet=True)
            if left:
                print(f"  ! w gotowym foncie nadal brakuje: {left}")
            write_font_asset_ttf(gf, f, ttf, f["name"], export_dir,
                                 font_name=f["name"])
            done += 1
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            print(f"  ! BLAD: {type(e).__name__}: {e} - pomijam ten font")
            failed.append(f["name"])

    if failed:
        print(f"\n! Pominiete z bledem ({len(failed)}): {', '.join(failed)}")
    return done      # liczba naprawionych (0 = falsy, jak dawne False)


# ---------------------------------------------------------------------------
# Fonty BITMAPOWE (asset Font bez TTF: m_CharacterRects + atlas)
#
# Stary UI Text / TextMesh potrafi renderowac z fontu, ktory nie ma TTF-a
# (m_FontData puste), tylko gotowy atlas i tabele m_CharacterRects - typowo
# kopie "(Crisp)" fontow pikselowych z filtrem Point. Skan widzial dotad tylko
# Font z TTF-em, wiec takie fonty po cichu wypadaly z listy i w grze znikaly
# litery (Inscryption: "TEMPO WYŚWIETLANIA" bez Ś w menu na Marksman (Crisp)).
#
# Brakujace litery dorabiamy w dwoch krokach:
#   1. z BLIZNIACZEGO fontu bitmapowego tej gry (ten sam m_FontNames
#      i m_FontSize, wszystkie wspolne glify identyczne co do piksela) -
#      wtedy dostajemy oryginalny rysunek autora fontu,
#   2. reszte skladamy tym samym algorytmem, co dla atlasow TMP
#      (compose_marks_from_glyphs: kreska wycieta z 'ó', kropka z 'i',
#      ogonek i przekreslenie dorysowane), na koniec transliteracja.
# Nowe glify trafiaja w wolne miejsce atlasu (gdy go brak - atlas rosnie),
# a wpisy m_CharacterRects dostaja uv i vert. Operacje na pikselach:
# bitmap_font_atlas.py.
# ---------------------------------------------------------------------------

import bitmap_font_atlas as bmpa  # noqa: E402

BITMAP_RENDER_MONO = 0x101A   # BITMAP|MONO|HINTED - piksele 0/255
BITMAP_RENDER_AA = 0x1015     # BITMAP|NO_HINTING|8BIT - z antyaliasingiem
_TRANSLIT = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def bitmap_texture_ref(gf, font_ref, tree):
    """(sciezka, SerializedFile, path_id, skad) tekstury fontu bitmapowego.

    Font trzyma ja w m_Texture, a kopie "(Crisp)" bywaja z m_Texture pustym -
    wtedy atlas jest w _MainTex materialu m_DefaultMaterial."""
    fpath, fsf = font_ref["path"], font_ref.get("serialized_name")
    tex = tree.get("m_Texture") or {}
    if tex.get("m_PathID"):
        p, sf = gf.resolve_ref(fpath, tex.get("m_FileID", 0), fsf)
        return p, sf, tex["m_PathID"], "m_Texture"
    mat = tree.get("m_DefaultMaterial") or {}
    if not mat.get("m_PathID"):
        return None, None, 0, None
    mpath, msf = gf.resolve_ref(fpath, mat.get("m_FileID", 0), fsf)
    mtree = find_object(gf.env(mpath), mat["m_PathID"], msf).read_typetree()
    for name, te in mtree.get("m_SavedProperties", {}).get("m_TexEnvs", []):
        t = te.get("m_Texture", {})
        if name == "_MainTex" and t.get("m_PathID"):
            p, sf = gf.resolve_ref(mpath, t.get("m_FileID", 0), msf)
            return p, sf, t["m_PathID"], "material"
    return None, None, 0, None


def load_bitmap_font(gf, fr):
    """Font bitmapowy z gry: drzewo, obiekt, atlas (bottom-up) i tekstura."""
    obj = find_object(gf.env(fr["path"]), fr["path_id"], fr.get("serialized_name"))
    tree = obj.read_typetree()
    tex_path, tex_sf, tex_pid, via = bitmap_texture_ref(gf, fr, tree)
    if not tex_pid:
        raise LookupError("font bez tekstury atlasu")
    tex_obj = find_object(gf.env(tex_path), tex_pid, tex_sf)
    img = tex_obj.read().image
    alpha = img.getchannel("A") if "A" in img.getbands() else img.convert("L")
    atlas = np.ascontiguousarray(np.flipud(np.array(alpha, dtype=np.uint8)))
    return {**fr, "obj": obj, "tree": tree, "atlas": atlas, "tex_obj": tex_obj,
            "tex_path": tex_path, "tex_sf": tex_sf, "tex_pid": tex_pid, "tex_via": via}


def describe_bitmap_fonts(gf, bmp_fonts):
    out = []
    for fr in bmp_fonts:
        try:
            d = load_bitmap_font(gf, fr)
        except Exception as e:
            print(f"  ! {fr['name']}: nie mozna odczytac fontu bitmapowego ({e})")
            continue
        cps = {int(r["index"]) for r in d["tree"]["m_CharacterRects"]}
        d["missing"] = "".join(ch for ch in PL_CHARS if ord(ch) not in cps)
        d["chars"] = len(cps)
        d["skip_reason"] = unsupported_reason(cps)
        out.append(d)
    return out


def _bitmap_glyph_key(d, r):
    return (r["vert"]["x"], r["vert"]["y"], r["vert"]["width"], r["vert"]["height"],
            r["advance"], (bmpa.sample_glyph(d["atlas"], r) >= bmpa.INK).tobytes())


def bitmap_twin_glyphs(target, fonts, missing):
    """{kod: (komorka, (x0, y_top), advance)} z blizniaczego fontu bitmapowego.

    Blizniak = inny font bitmapowy gry z tym samym m_FontNames i m_FontSize,
    ktorego WSZYSTKIE wspolne glify maja identyczne piksele, vert i advance -
    np. "Marksman" dla "Marksman (Crisp)". Tylko wtedy kopia jest pewna."""
    t = target["tree"]
    mine = {int(r["index"]): r for r in t["m_CharacterRects"]}
    got = {}
    for d in fonts:
        if d is target or not missing:
            continue
        o = d["tree"]
        if (o.get("m_FontNames") != t.get("m_FontNames")
                or o.get("m_FontSize") != t.get("m_FontSize")):
            continue
        theirs = {int(r["index"]): r for r in o["m_CharacterRects"]}
        common = set(mine) & set(theirs)
        if len(common) < 0.8 * len(mine):
            continue
        if any(_bitmap_glyph_key(target, mine[cp]) != _bitmap_glyph_key(d, theirs[cp])
               for cp in common):
            continue
        for cp in list(missing):
            r = theirs.get(cp)
            if r is None:
                continue
            v = r["vert"]
            top = v["y"] if v["height"] < 0 else v["y"] + v["height"]
            got[cp] = (bmpa.sample_glyph(d["atlas"], r), (v["x"], top), r["advance"])
            missing.discard(cp)
        if got:
            print(f"  Z blizniaczego fontu {d['name']!r} (identyczne"
                  f" {len(common)} glify): {''.join(chr(c) for c in sorted(got))}")
    return got


def fix_bitmap_font(gf, d, fonts, export_dir):
    t = d["tree"]
    rects = t["m_CharacterRects"]
    atlas = d["atlas"]
    mono = set(np.unique(atlas).tolist()) <= {0, 255}
    missing = {ord(ch) for ch in d["missing"]}
    H, W = atlas.shape
    print(f"  Atlas {W}x{H} ({'piksele 0/255' if mono else 'z antyaliasingiem'}),"
          f" {len(rects)} znakow, brakuje {d['missing']}")

    new_cells = []
    for cp, (cell, origin, adv) in bitmap_twin_glyphs(d, fonts, missing).items():
        new_cells.append((cp, cell, origin, adv))

    if missing:
        padding = 1
        chars, glyphs = bmpa.extract_glyphs(atlas, rects, padding)
        before = set(glyphs)
        chars, glyphs, still, _done = compose_marks_from_glyphs(
            chars, glyphs, sorted(missing), padding,
            point_size=t.get("m_FontSize") or None,
            render_mode=BITMAP_RENDER_MONO if mono else BITMAP_RENDER_AA)
        for gi in set(glyphs) - before:
            g = glyphs[gi]
            cp = gi - COMPOSED_GLYPH_OFFSET
            cell = g["sdf"]
            if mono:
                cell = np.where(cell >= bmpa.INK, 255, 0).astype(np.uint8)
            new_cells.append((cp, cell, _glyph_origin(g), g["metrics"]["advance"]))
        missing = set(still)

    aliases = []
    if missing:
        by_cp = {int(r["index"]): r for r in rects}
        for cp in sorted(missing):
            base = by_cp.get(ord(chr(cp).translate(_TRANSLIT)))
            if base is not None:
                alias = json.loads(json.dumps(base))
                alias["index"] = cp
                aliases.append(alias)
        if aliases:
            print(f"  Transliteracja: {''.join(chr(a['index']) for a in aliases)}")
        missing -= {a["index"] for a in aliases}
    if missing:
        print(f"  ! nadal brak: {''.join(chr(c) for c in sorted(missing))}")
    if not new_cells and not aliases:
        print("  Nic do dodania")
        return False

    atlas2, rects2 = bmpa.place_glyphs(atlas, rects, new_cells)
    rects2 += aliases
    H2, W2 = atlas2.shape
    if (H2, W2) != (H, W):
        print(f"  Atlas urosl: {W}x{H} -> {W2}x{H2}")

    preview_dir = fixed_preview_dir(export_dir)
    try:
        os.makedirs(preview_dir, exist_ok=True)
        dst = os.path.join(preview_dir, f"bitmap_{safe_name(d['name']) or 'font'}.png")
        bmpa.render_text(atlas2, rects2, PREVIEW_TEXT + "\n" + PREVIEW_TEXT.upper()).save(dst)
        print(f"  Podglad: {dst}")
    except Exception as e:
        print(f"  ! podglad sie nie udal: {e}")

    if export_dir is not None:
        from PIL import Image
        os.makedirs(export_dir, exist_ok=True)
        key = export_key(d)
        png_path = os.path.join(export_dir, key + ".png")
        Image.fromarray(np.flipud(atlas2)).save(png_path)
        meta = {
            "type": "bitmap_font",
            "label": d["name"],
            "font_assets_rel": os.path.relpath(d["path"], gf.data_dir),
            "font_serialized_name": d.get("serialized_name"),
            "font_path_id": d["path_id"],
            "font_name": d["name"],
            "tex_assets_rel": os.path.relpath(d["tex_path"], gf.data_dir),
            "tex_serialized_name": d["tex_sf"],
            "tex_path_id": d["tex_pid"],
            "tex_via": d["tex_via"],
            "atlas_w": W2, "atlas_h": H2,
            "source_rects_sha": bmpa.rects_sha(rects),
            "added": "".join(chr(c) for c in sorted(
                {cp for cp, *_ in new_cells} | {a["index"] for a in aliases})),
            "rects": rects2,
        }
        json_path = os.path.join(export_dir, key + ".json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        print(f"  Wyeksportowano: {json_path}")
        print(f"                  {png_path}")
        return True

    # ============== TRYB PATCH ==============
    t["m_CharacterRects"] = rects2
    d["obj"].save_typetree(t)
    gf.modified.add(os.path.abspath(d["path"]))
    tex_tree = d["tex_obj"].read_typetree()
    data, swz = encode_texture_data(atlas2, tex_tree, d["tex_obj"])
    tex_tree["m_Width"], tex_tree["m_Height"] = W2, H2
    tex_tree["m_CompleteImageSize"] = len(data)
    tex_tree["image data"] = data
    if "m_StreamData" in tex_tree:
        tex_tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    if tex_tree.get("m_TextureFormat") != 1:
        print(f"  ! tekstura ma format {tex_tree.get('m_TextureFormat')} - ustawiam Alpha8")
        tex_tree["m_TextureFormat"] = 1
    tex_tree["m_MipCount"] = 1
    d["tex_obj"].save_typetree(tex_tree)
    gf.modified.add(os.path.abspath(d["tex_path"]))
    print(f"  Tekstura {d['tex_pid']} ({os.path.basename(d['tex_path'])}): osadzono"
          f" {W2}x{H2} Alpha8{swz}")
    return True


def fix_bitmap_fonts(gf, export_dir, ask_first=False):
    """Interaktywna naprawa fontow bitmapowych. Zwraca liczbe naprawionych."""
    bmp_fonts = getattr(gf, "bitmap_fonts", None) or []
    if not bmp_fonts:
        return 0
    fonts = describe_bitmap_fonts(gf, bmp_fonts)
    todo = [d for d in fonts if d["missing"] and not d["skip_reason"]]
    if ask_first:
        if not todo:
            return 0
        print(f"\nW grze jest {len(todo)} fontow BITMAPOWYCH (asset Font bez TTF,"
              f" UI Text) bez polskich znakow.")
        ans = ask("Naprawic takze je? [T/n]: ", "t").strip().lower() or "t"
        if ans not in ("t", "y", "1", "tak"):
            return 0

    print("\nZnalezione fonty bitmapowe (Font bez TTF):")
    for i, d in enumerate(fonts, 1):
        if d["skip_reason"]:
            status = "ODSIANY: " + d["skip_reason"]
        elif not d["missing"]:
            status = "polskie OK"
        else:
            status = f"BRAK: {d['missing']}"
        print(f"  [{i}] {d['name']:45s} {d['chars']:5d} znakow  [{status}]  "
              f"({os.path.basename(d['path'])})")
    if not todo:
        print("\nNie ma czego naprawiac w fontach bitmapowych.")
        return 0

    ans = ask(f"\nKtore naprawic? (numery po przecinku / Enter = wszystkie"
              f" bez polskich [{len(todo)}]): ").strip()
    if ans:
        chosen = []
        for part in ans.split(","):
            try:
                chosen.append(fonts[int(part.strip()) - 1])
            except (ValueError, IndexError):
                continue
        todo = chosen

    done, failed = 0, []
    for d in todo:
        print(f"\n=== {green(d['name'])} ({os.path.basename(d['path'])},"
              f" path_id {d['path_id']}) ===")
        try:
            if fix_bitmap_font(gf, d, fonts, export_dir):
                done += 1
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            print(f"  ! BLAD: {type(e).__name__}: {e} - pomijam ten font")
            failed.append(d["name"])
    if failed:
        print(f"\n! Pominiete z bledem ({len(failed)}): {', '.join(failed)}")
    return done


def fix_other_fonts(gf, ttf_fonts, export_dir, ask_first=False):
    """Fonty poza TMP: zwykle Font z TTF-em, potem bitmapowe."""
    done = int(fix_plain_fonts(gf, ttf_fonts, export_dir, ask_first=ask_first) or 0)
    return done + fix_bitmap_fonts(gf, export_dir, ask_first=ask_first)


# ---------------------------------------------------------------------------
# Podglady fontow PO naprawie (fixed_preview/ obok fixed_fonts/)
#
# font_preview/ pokazuje ATLAS przed naprawa - a to, czy naprawiony font
# naprawde wyglada dobrze, widac tylko w ZLOZONYM NAPISIE (litera z obcego
# fallbacku ma inna szerokosc i wysokosc, akcent bywa za wysoko, litery sie
# zlepiaja). Dlatego kazdy naprawiony font od razu dostaje podglad napisu
# i kontrole pochodzenia polskich liter - w OBU trybach, bo renderujemy
# z danych trzymanych w pamieci, jeszcze przed zapisem do gry.
# ---------------------------------------------------------------------------

FIXED_PREVIEW_DIR_NAME = "fixed_preview"


def fixed_preview_dir(export_dir=None):
    """Folder na podglady naprawionych fontow: obok fixed_fonts/ (tryb EKSPORT)
    albo obok skryptu (tryb PATCH, gdzie zadnego fixed_fonts nie ma)."""
    base = (os.path.dirname(os.path.abspath(export_dir)) if export_dir
            else app_dir())
    return os.path.join(base, FIXED_PREVIEW_DIR_NAME)


def _preview_module():
    """render_text_sample zaimportowany tak, zeby NIE zrobil drugiej kopii tego
    modulu: gdy lecimy jako __main__, rejestrujemy sie najpierw pod wlasna nazwa
    (inaczej `import fix_tmp_polish_fonts` w podgladzie wczytalby caly plik od
    nowa - osobne SYNTH_FULL, osobny cache _export_keys)."""
    sys.modules.setdefault("fix_tmp_polish_fonts", sys.modules[__name__])
    try:
        import render_text_sample
        return render_text_sample
    except Exception as e:
        print(f"  ! brak render_text_sample.py - bez podgladu napisu ({e})")
        return None


def _print_preview_result(dst, lines, missing, problems=0):
    for ln in lines:
        print(f"    {ln}")
    if missing:
        print(f"    ! w podgladzie brak znakow: {''.join(sorted(set(missing)))}")
    if not problems and lines:
        print("    (nic nie odstaje od reszty kroju)")
    if dst:
        print(f"  Podglad napisu: {dst}")


def dump_fixed_preview_static(name, tree, atlas_bottom_up, padding,
                              export_dir=None):
    """Podglad napisu z NAPRAWIONEGO atlasu (tree = widok nowoczesny, atlas
    w ukladzie TMP: wiersz 0 = SPOD atlasu, jak z gen.compose_atlas)."""
    preview = _preview_module()
    if preview is None:
        return
    try:
        img, missing, lines, problems = preview.preview_static(
            tree, np.flipud(atlas_bottom_up), padding)
        dst = preview.save_preview(img, fixed_preview_dir(export_dir), name)
        _print_preview_result(dst, lines, missing, problems)
    except Exception as e:
        print(f"  ! nie udalo sie zrobic podgladu napisu ({e})")


def dump_fixed_preview_dynamic(name, ttf, export_dir=None):
    """Podglad napisu z NAPRAWIONEGO pliku TTF (font dynamiczny)."""
    preview = _preview_module()
    if preview is None:
        return
    try:
        img, missing = preview.preview_dynamic(ttf)
        dst = preview.save_preview(img, fixed_preview_dir(export_dir), name)
        _print_preview_result(dst, [], missing)
    except Exception as e:
        print(f"  ! nie udalo sie zrobic podgladu napisu ({e})")


# ---------------------------------------------------------------------------
# Podglady fontow PRZED naprawa (font_preview/ obok skryptu)
# ---------------------------------------------------------------------------

PREVIEW_DIR_NAME = "font_preview"
PREVIEW_TEXT = "Zazolc gesla jazn ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż"


def to_gray_image(img):
    """PIL image -> 'L'; atlasy Alpha8 trzymaja glify w kanale alpha."""
    from PIL import ImageChops
    if "A" in img.getbands():
        return ImageChops.lighter(img.convert("RGB").convert("L"), img.getchannel("A"))
    return img.convert("L")


def render_ttf_sample(ttf, text=PREVIEW_TEXT, size=64):
    """Probka tekstu wyrenderowana z TTF (fonty dynamiczne nie maja atlasu)."""
    from PIL import Image
    face = freetype.Face(io.BytesIO(ttf))
    face.set_char_size(size * 64)
    asc = face.size.ascender >> 6
    desc = -(face.size.descender >> 6)
    height = asc + desc + 16
    canvas = np.zeros((height, 16), dtype=np.uint8)
    pen = 8
    for ch in text:
        face.load_char(ch, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        slot = face.glyph
        bmp = gen.bitmap_to_array(slot.bitmap)
        advance = slot.advance.x >> 6
        x = max(0, pen + slot.bitmap_left)
        y = max(0, asc + 8 - slot.bitmap_top)
        need = max(x + bmp.shape[1], pen + advance) + 8
        if need > canvas.shape[1]:
            canvas = np.pad(canvas, ((0, 0), (0, need - canvas.shape[1])))
        if bmp.size and y + bmp.shape[0] <= height:
            region = canvas[y:y + bmp.shape[0], x:x + bmp.shape[1]]
            np.maximum(region, bmp[:, :region.shape[1]], out=region)
        pen += advance
    return Image.fromarray(canvas, "L")


def preview_static_atlas(gf, d):
    tex_path, tex_sf, tex_pid = atlas_texture_ref(gf, d["tree"], d)
    if not tex_pid:
        return None
    obj = find_object(gf.env(tex_path), tex_pid, tex_sf)
    return to_gray_image(obj.read().image)


def get_dynamic_source_font_data(gf, tree, path, serialized_name=None):
    """Dla fontu dynamicznego: bajty jego zrodlowego TTF (m_SourceFontFile),
    albo None, gdy PPtr jest pusty/nie da sie go rozwiazac."""
    src = tree.get("m_SourceFontFile") or {}
    pid = src.get("m_PathID", 0)
    if not pid:
        return None
    fpath, fsf = gf.resolve_ref(path, src.get("m_FileID", 0), serialized_name)
    data = get_font_data(gf, {"path": fpath, "path_id": pid,
                              "serialized_name": fsf})
    if not data:
        raise ValueError("zrodlowy Font ma puste m_FontData (0 bajtow)")
    from fontTools.ttLib import TTFont
    try:
        with TTFont(io.BytesIO(data), fontNumber=0) as font:
            font.getBestCmap()
    except Exception as exc:
        raise ValueError(f"zrodlowy TTF/OTF jest nieczytelny: {exc}") from exc
    return data


def preview_dynamic_source(gf, d):
    data = get_dynamic_source_font_data(gf, d["tree"], d["path"],
                                        d.get("serialized_name"))
    if data is None:
        return None
    return render_ttf_sample(data)


def dump_font_previews(gf, details):
    """Zapisuje PNG z aktualnym wygladem kazdego fontu do font_preview/.

    Numer w nazwie pliku = numer na liscie fontow, wiec przy pytaniu "ktore
    naprawic?" widac, co dokladnie siedzi w kazdym wpisie. Fonty statyczne:
    biezacy atlas SDF; dynamiczne: probka tekstu z ich zrodlowego TTF.

    Fonty odsiane (azjatyckie / bez liter lacinskich) sa pomijane - numery na
    liscie zostaja te same, tylko nie marnujemy czasu i miejsca na PNG z
    atlasem 4096x4096 pelnym ideogramow.
    """
    out_dir = os.path.join(app_dir(), PREVIEW_DIR_NAME)
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        print(f"! nie mozna utworzyc {out_dir}: {e}")
        return
    wanted = [d for d in details if not d.get("skip_reason") and not d.get("source_error")]
    saved = 0
    for i, d in enumerate(details, 1):
        if d.get("skip_reason") or d.get("source_error"):
            continue
        try:
            img = preview_dynamic_source(gf, d) if d["dynamic"] else preview_static_atlas(gf, d)
            if img is None:
                continue
            img.save(os.path.join(out_dir, f"{i:02d}_{safe_name(d['name']) or 'font'}.png"))
            saved += 1
        except Exception as e:
            print(f"  ! [{i}] {d['name']}: nie udalo sie zrobic podgladu ({e})")
    print(f"Podglady fontow ({saved}/{len(wanted)}): {out_dir}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

DATA_DIR_MARKERS = ("resources.assets", "globalgamemanagers", "data.unity3d")


def looks_like_data_dir(path):
    # np. Switch: folder "Data" bez sufiksu _Data, ale z plikami Unity w srodku
    try:
        entries = os.listdir(path)
    except OSError:
        return False
    for e in entries:
        low = e.lower()
        if low in DATA_DIR_MARKERS or (low.startswith("sharedassets") and low.endswith(".assets")):
            return True
    return False


def find_data_dir(game_path):
    game_path = os.path.abspath(game_path)
    if os.path.isdir(game_path) and (game_path.endswith("_Data") or looks_like_data_dir(game_path)):
        return game_path, os.path.dirname(game_path)
    # Kilka katalogow *_Data (np. Empire of Sin: DLC_Data + EmpireOfSin_Data) -
    # wybierz ten z plikami glownej gry, a przy remisie ten o nazwie exe.
    data_dirs = [e for e in os.listdir(game_path)
                 if e.endswith("_Data") and os.path.isdir(os.path.join(game_path, e))]
    if data_dirs:
        exe_stems = {os.path.splitext(e)[0].lower() for e in os.listdir(game_path)
                     if e.lower().endswith(".exe")}

        def _rank(name):
            full = os.path.join(game_path, name)
            main = os.path.exists(os.path.join(full, "globalgamemanagers")) or \
                os.path.exists(os.path.join(full, "data.unity3d"))
            return (not main, not looks_like_data_dir(full),
                    name[:-5].lower() not in exe_stems, name.lower())

        data_dirs.sort(key=_rank)
        if len(data_dirs) > 1:
            print(f"Wiele katalogow *_Data {data_dirs} - wybrano: {data_dirs[0]}")
        return os.path.join(game_path, data_dirs[0]), game_path
    for entry in os.listdir(game_path):
        full = os.path.join(game_path, entry)
        if os.path.isdir(full) and looks_like_data_dir(full):
            return full, game_path
    # moze exe jest poziom nizej
    for entry in os.listdir(game_path):
        sub = os.path.join(game_path, entry)
        if os.path.isdir(sub):
            for e2 in os.listdir(sub):
                full = os.path.join(sub, e2)
                if os.path.isdir(full) and (e2.endswith("_Data") or looks_like_data_dir(full)):
                    return full, sub
    raise SystemExit(f"Nie znaleziono katalogu z danymi Unity (*_Data / resources.assets / data.unity3d) w: {game_path}")


USAGE = """\
Uzycie:
  fix_tmp_polish_fonts.py <katalog gry> [filtr nazwy pliku] [opcje]

Opcje:
  --auto, -y         bez zadnego pytania: wszedzie odpowiedz domyslna
                     (EKSPORT do fixed_fonts/, wszystkie fonty bez polskich
                     znakow, glify z wlasnego atlasu, fonty UI Text tez).
                     Do wolania z innych skryptow / CI.
  --patch            zamiast eksportu wstrzykuj od razu do plikow gry
  --export           wymus EKSPORT (domyslne; przydatne, zeby pominac pytanie)
  --export-dir DIR   katalog eksportu (domyslnie fixed_fonts/ obok skryptu)
  --fallback PLIK    TTF/OTF na litery, ktorych nie da sie zlozyc z wlasnych
                     glifow fontu (bez tego zostaje transliteracja)
  --marks-only       dorabiaj tylko kreske i kropke (ą ę ł z fallbacku)
  --no-system-fonts  nie szukaj w systemie (C:\\Windows\\Fonts, ~/.fonts...) tego samego
                     fontu co w grze; domyslnie statyczny atlas SDF bierze z niego
                     PRAWDZIWE polskie znaki, gdy font jest zainstalowany i je ma
  --replace-chars TEKST  zloz od nowa wskazane polskie glify statycznego TMP,
                        nawet gdy sa obecne (np. --replace-chars ąę)
  --jobs N, -j N     liczba procesow skanu (1 = bez rownoleglosci)
  --help, -h         ta pomoc

Kody wyjscia (dla skryptow): 0 = OK, 1 = czesci fontow nie naprawiono,
2 = nie bylo czego naprawiac / nie znaleziono fontow.
"""


class Options:
    """Argumenty linii polecen (pozycyjne jak dotad + flagi trybu --auto)."""

    def __init__(self):
        self.game_path = None
        self.name_filter = ""
        self.jobs = None
        self.auto = False
        self.mode = None          # "export" | "patch" | None (zapytaj)
        self.export_dir = None
        self.fallback = None
        self.synth_full = True
        self.system_fonts = True
        self.replace_chars = ""


def parse_args(argv):
    opts = Options()
    jobs = None
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a in ("-j", "--jobs") and nxt is not None:
            jobs = nxt
            i += 2
            continue
        if a.startswith("--jobs="):
            jobs = a.split("=", 1)[1]
            i += 1
            continue
        if a in ("-y", "--auto", "--yes"):
            opts.auto = True
            i += 1
            continue
        if a == "--patch":
            opts.mode = "patch"
            i += 1
            continue
        if a == "--export":
            opts.mode = "export"
            i += 1
            continue
        if a == "--export-dir" and nxt is not None:
            opts.export_dir = nxt
            i += 2
            continue
        if a.startswith("--export-dir="):
            opts.export_dir = a.split("=", 1)[1]
            i += 1
            continue
        if a == "--fallback" and nxt is not None:
            opts.fallback = nxt
            i += 2
            continue
        if a.startswith("--fallback="):
            opts.fallback = a.split("=", 1)[1]
            i += 1
            continue
        if a == "--marks-only":
            opts.synth_full = False
            i += 1
            continue
        if a == "--no-system-fonts":
            opts.system_fonts = False
            i += 1
            continue
        if a == "--replace-chars" and nxt is not None:
            opts.replace_chars = nxt
            i += 2
            continue
        if a.startswith("--replace-chars="):
            opts.replace_chars = a.split("=", 1)[1]
            i += 1
            continue
        if a in ("-h", "--help", "/?"):
            print(USAGE)
            raise SystemExit(0)
        if a.startswith("-"):
            raise SystemExit(f"! nieznana opcja {a}\n\n{USAGE}")
        rest.append(a)
        i += 1
    try:
        opts.jobs = None if jobs is None else max(1, int(jobs))
    except ValueError:
        print(f"! --jobs {jobs}: nie liczba, uzywam domyslnej")
        opts.jobs = None
    opts.game_path = rest[0] if rest else None
    if set(opts.replace_chars) - set(PL_CHARS):
        raise SystemExit("! --replace-chars: podaj wylacznie polskie litery")
    if opts.replace_chars and not opts.synth_full:
        raise SystemExit("! --replace-chars wymaga pelnego skladania (bez --marks-only)")
    opts.name_filter = rest[1] if len(rest) > 1 else ""
    if opts.export_dir:
        opts.export_dir = os.path.abspath(opts.export_dir)
        opts.mode = opts.mode or "export"
    return opts


def finish_session(gf, export_dir):
    """Wspolne zakonczenie obu sciezek: podglady + eksport albo zapis gry."""
    preview_dir = fixed_preview_dir(export_dir)
    if os.path.isdir(preview_dir):
        print(f"\nPodglady naprawionych fontow (napis + kontrola polskich"
              f" liter): {preview_dir}")

    if export_dir is not None:
        print(f"\nGotowe. Wyeksportowane fonty: {export_dir}")
    elif gf.modified:
        print(f"\nZapisywanie {len(gf.modified)} plikow...")
        gf.save_modified()
        print("\nGotowe. Przetestuj w grze.")
    else:
        print("\nNic nie zmieniono.")


def apply_options(opts):
    """Przenosi flagi CLI do globali trybu pracy. Zwraca export_dir albo None.

    Bez --auto nic sie nie zmienia: skrypt dalej pyta o wszystko tak jak dotad
    (tryb z wyborami jest domyslny, --auto to tylko skrot dla skryptow)."""
    global AUTO, AUTO_SYNTH, SYNTH_FULL, USE_SYSTEM_FONTS
    USE_SYSTEM_FONTS = opts.system_fonts
    SYNTH_FULL = opts.synth_full
    if opts.fallback:
        if not os.path.isfile(opts.fallback):
            raise SystemExit(f"! --fallback: nie ma pliku {opts.fallback}")
        with open(opts.fallback, "rb") as f:
            remember_fallback(f.read(), os.path.basename(opts.fallback))
        print(f"Font fallback z CLI: {os.path.basename(opts.fallback)}")
    if opts.auto:
        AUTO = True
        # "nie pytaj wiecej" wlaczone od razu: kazdy font idzie sciezka
        # "zachowaj glify z atlasu, dopisz tylko brakujace litery"
        AUTO_SYNTH = True
        print("Tryb AUTO: bez pytan, wszedzie odpowiedz domyslna.")
    mode = opts.mode or ("export" if opts.auto else None)
    if mode == "patch":
        return None
    if mode == "export":
        return opts.export_dir or os.path.join(app_dir(), "fixed_fonts")
    return "ASK"


def clean_previous_results(export_dir):
    """Pyta, czy skasowac wyniki poprzedniej pracy: fixed_fonts/ (tylko w trybie
    EKSPORT), fixed_preview/ i font_preview/. Domyslnie T. Kasuje ZAWARTOSC
    folderow, nie same foldery."""
    targets = [fixed_preview_dir(export_dir),
               os.path.join(app_dir(), PREVIEW_DIR_NAME)]
    if export_dir:
        targets.insert(0, export_dir)
    here = os.path.abspath(app_dir())
    found = []
    for d in targets:
        d = os.path.abspath(d)
        # nigdy folder skryptu ani jego przodek (np. zle podane --export-dir)
        if here == d or here.startswith(d + os.sep):
            continue
        if os.path.isdir(d) and os.listdir(d):
            found.append(d)
    if not found:
        return
    print("\nZnaleziono wyniki poprzedniej pracy:")
    for d in found:
        print(f"  - {d} ({len(os.listdir(d))} poz.)")
    ans = ask("Skasowac je przed rozpoczeciem? [T/n]: ", "T").strip().lower()
    if ans not in ("", "t", "tak", "y", "yes"):
        print("Zostawiam poprzednie wyniki.")
        return
    for d in found:
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
            except OSError as e:
                print(f"  ! nie udalo sie usunac {p}: {e}")
    print("Wyniki poprzedniej pracy skasowane.")


def main():
    print(bold("🛠️🛠️🛠️ UNITY PL FONT PATCHER 🛠️🛠️🛠️"))
    opts = parse_args(sys.argv[1:])
    export_dir = apply_options(opts)

    game_path = opts.game_path
    if not game_path:
        if AUTO:
            raise SystemExit("! --auto wymaga sciezki do gry w argumencie")
        game_path = input(ask_color("Podaj sciezke do gry: ")).strip().strip('"')

    data_dir, game_root = find_data_dir(game_path)
    print(f"Katalog danych: {data_dir}")

    if export_dir == "ASK":
        # domyslna sciezka dla czlowieka: pelne menu wyborow jak dotad
        print("\nTryb pracy:")
        print("  [1] EKSPORT - zapisuje naprawione fonty do folderu fixed_fonts/ (gra nietknieta)  [zalecane]")
        print("  [2] PATCH   - wstrzykuje naprawione fonty do plikow gry (z backupem)")
        export_dir = None
        while True:
            ans = input(ask_color("Wybor [1]: ")).strip()
            if ans in ("", "1"):
                export_dir = opts.export_dir or os.path.join(app_dir(), "fixed_fonts")
                break
            if ans == "2":
                break
    if export_dir:
        print(f"Eksport do: {export_dir}")
    else:
        print("Tryb PATCH: pliki gry beda nadpisane (backup .bak_plfont)")

    clean_previous_results(export_dir)

    ask_synth_mode()

    gf = GameFiles(data_dir, game_root)
    setup_fallback_unity_version(data_dir)

    print("\nSkanowanie plikow gry...")
    tmp_fonts, ttf_fonts, mat_index = scan_game(gf, opts.name_filter, opts.jobs)
    if not tmp_fonts:
        if not ttf_fonts and not getattr(gf, "bitmap_fonts", None):
            print("Nie znaleziono ani TMP_FontAsset, ani assetu Font (TTF / bitmapowego).")
            return 2
        # Gra bez TextMesh Pro: caly tekst leci przez UI Text, czyli przez
        # zwykle assety Font - i to w nich trzeba dorobic polskie litery.
        print("Nie znaleziono zadnego TMP_FontAsset - gra renderuje tekst"
              " zwyklymi fontami (UI Text).")
        done = fix_other_fonts(gf, ttf_fonts, export_dir)
        finish_session(gf, export_dir)
        return 0 if done else 2

    # wczytaj szczegoly kazdego TMP fontu
    print()
    details = []
    detail_errors = []
    for fi_ in tmp_fonts:
        try:
            env = gf.env(fi_["path"])
            obj = find_object(env, fi_["path_id"], fi_.get("serialized_name"))
            tree = obj.read_typetree()
        except Exception as e:
            try:
                tree = read_tmp_font_raw(obj)
                if write_tmp_font_raw(tree) != obj.get_raw_data():
                    raise ValueError("test round-trip surowego layoutu nie przeszedl")
                tree["_raw_mode"] = True
                print(f"  (surowy layout Unity 6000.5: {fi_['name']})")
            except Exception as raw_error:
                detail_errors.append((fi_["name"], f"{e}; fallback: {raw_error}"))
                continue
        # stary TMP (Unity 5.x/2017) ma inne nazwy pol - dalej pracujemy na
        # widoku nowoczesnym, a przy zapisie wracamy do oryginalu
        legacy_tree = None
        if is_legacy_tmp(tree):
            legacy_tree = tree
            tree = legacy_to_modern(tree)
        unicodes = {c["m_Unicode"] for c in tree.get("m_CharacterTable", [])}
        dynamic = tree.get("m_AtlasPopulationMode", 0) == 1
        src_missing = ""
        source_error = ""
        if dynamic:
            # Dynamiczny font sam dopisuje glify do atlasu w runtime, ale
            # tylko te, ktore ma jego zrodlowy TTF (m_SourceFontFile) - a nie
            # to, co juz jest w m_CharacterTable (ktora bywa prawie pusta).
            # Wiec sprawdzamy realne pokrycie w samym TTF, nie w atlasie.
            try:
                src_data = get_dynamic_source_font_data(gf, tree, fi_["path"],
                                                        fi_.get("serialized_name"))
            except Exception as exc:
                src_data = None
                source_error = str(exc)
            if src_data is None:
                have_pl = False
                src_missing = PL_CHARS
                source_error = source_error or "brak m_SourceFontFile"
            else:
                _have, src_missing = ttf_polish_coverage(src_data, quiet=True)
                have_pl = not src_missing
            cps = ttf_codepoints(src_data) if src_data else set()
        else:
            have_pl = all(ord(ch) in unicodes for ch in PL_CHARS)
            cps = unicodes
        details.append({**fi_, "obj": obj, "tree": tree, "have_pl": have_pl,
                        "legacy_tree": legacy_tree,
                        "dynamic": dynamic, "src_missing": src_missing,
                        "source_error": source_error,
                        "skip_reason": unsupported_reason(cps),
                         "family": tree.get("m_FaceInfo", {}).get("m_FamilyName", ""),
                         "style": tree.get("m_FaceInfo", {}).get("m_StyleName", ""),
                         "chars": len(unicodes)})

    if detail_errors:
        print(f"  ! Nie odczytano {len(detail_errors)}/{len(tmp_fonts)} fontow TMP.")
        for name, reason in detail_errors:
            print(f"    {name}: {reason}")
    if not details:
        print("  Brak fontow TMP, ktore mozna bezpiecznie przetworzyc.")
        return 2

    print("Znalezione fonty TMP:")
    for i, d in enumerate(details, 1):
        if d["skip_reason"]:
            status = "ODSIANY: " + d["skip_reason"]
        elif d["dynamic"]:
            status = (f"DYNAMICZNY, {d['source_error']}" if d["source_error"] else
                      "DYNAMICZNY, polskie w TTF OK" if d["have_pl"]
                       else f"DYNAMICZNY, BRAK w TTF: {d['src_missing']}")
        else:
            status = "polskie OK" if d["have_pl"] else "BRAK polskich"
        print(f"  [{i}] {d['name']:45s} {d['chars']:4d} znakow  [{status}]  "
              f"({os.path.basename(d['path'])})")

    dropped = [d for d in details if d["skip_reason"]]
    if dropped:
        print(f"\nOdsiane ({len(dropped)}): fonty azjatyckie / bez liter"
              " lacinskich - nie ma czym renderowac polskiego tekstu.")
        print("  Pomijam je w podgladach i w naprawie; da sie je wskazac"
              " numerem recznie.")

    print("\nZapisywanie podgladow (jak fonty wygladaja teraz)...")
    dump_font_previews(gf, details)

    to_fix = [d for d in details if not d["skip_reason"]
              and (not d["have_pl"] or (opts.replace_chars and not d["dynamic"]))]
    if not to_fix:
        print("\nNie ma czego naprawiac: fonty z lacinskim alfabetem maja"
              " polskie znaki.")
        done = fix_other_fonts(gf, ttf_fonts, export_dir, ask_first=True)
        finish_session(gf, export_dir)
        return 0 if done else 2
    ans = ask(f"\nKtore naprawic? (numery po przecinku / Enter = wszystkie wymagajace naprawy [{len(to_fix)}]): ").strip()
    if ans:
        chosen = []
        for part in ans.split(","):
            try:
                d = details[int(part.strip()) - 1]
            except (ValueError, IndexError):
                continue
            if d["skip_reason"]:
                print(f"  ! {d['name']}: {d['skip_reason']} - naprawiam"
                      f" na zyczenie")
            chosen.append(d)
        to_fix = chosen
    if not to_fix:
        # zadnego TMP-a do naprawy nie znaczy jeszcze, ze gra nie ma fontow
        # UI Text z brakami
        done = fix_other_fonts(gf, ttf_fonts, export_dir, ask_first=True)
        finish_session(gf, export_dir)
        return 0 if done else 2

    failed = []
    fixed_ok = 0
    for d in to_fix:
        print(f"\n=== {green(d['name'])} ({os.path.basename(d['path'])}, path_id {d['path_id']}) ===")
        # Jeden zepsuty font (nierozwiazywalny PPtr, kolizja path_id w bundlu,
        # polamany TTF) nie moze zabierac ze soba calej sesji - reszta fontow
        # jest niezalezna, wiec logujemy i lecimy dalej.
        try:
            if d["dynamic"]:
                # Dynamiczny font nie ma atlasu do wypiekania - naprawa idzie
                # wprost w kontury zrodlowego TTF (osobne menu).
                if fix_dynamic_font_interactive(gf, d, ttf_fonts, export_dir):
                    fixed_ok += 1
                else:
                    failed.append(d["name"])
                continue
            if opts.replace_chars:
                mode, ttf, fallback, translit = "atlas", None, None, False
            else:
                mode, ttf, fallback, translit = choose_ttf(d["name"], d["family"], ttf_fonts, gf,
                                                           d.get("style", ""))
            if mode == "skip":
                print("  pominieto")
                continue
            if mode == "atlas":
                ok = rebuild_font_asset_from_atlas(gf, d, d["tree"], d["obj"], mat_index,
                                                   fallback, export_dir, ttf_fonts=ttf_fonts,
                                                   replace_chars=opts.replace_chars,
                                                   prefer_real=isinstance(fallback, SystemTTF))
            else:
                ok = rebuild_font_asset(gf, d, d["tree"], d["obj"], ttf, mat_index,
                                        fallback, export_dir, translit)
            if ok:
                fixed_ok += 1
            else:
                failed.append(d["name"])
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            print(f"  ! BLAD: {type(e).__name__}: {e} - pomijam ten font")
            failed.append(d["name"])

    if failed:
        print(f"\n! Nie naprawiono ({len(failed)}): {', '.join(failed)}")

    # W jednej grze potrafi siedziec i TMP, i stare UI Text - fonty TMP juz
    # naprawione, wiec pytamy o reszte (zrodla fontow dynamicznych sa z tej
    # listy odsiewane, bo poszly juz razem z TMP-em).
    fixed_ok += fix_other_fonts(gf, ttf_fonts, export_dir, ask_first=True)

    finish_session(gf, export_dir)

    # kod wyjscia dla skryptu wolajacego (w trybie interaktywnym nikt na niego
    # nie patrzy, wiec nic to nie zmienia)
    print(f"\nPodsumowanie: naprawione {fixed_ok}, nieudane {len(failed)}")
    if failed:
        return 1
    return 0 if fixed_ok else 2


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()    # workery skanu w buildzie PyInstallera
    sys.exit(main() or 0)
