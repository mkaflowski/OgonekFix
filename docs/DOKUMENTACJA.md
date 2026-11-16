# font_fixer — polskie znaki w fontach gier (Unity / Unreal)

Jedno wejście dla obu silników: podajesz katalog gry, narzędzie rozpoznaje silnik
i odpala właściwy skrypt. Brakujące litery (`ą ć ę ł ń ó ś ź ż` + wielkie) są
dorabiane **w kroju tego samego fontu**, a nie podmieniane innym.

## Uruchomienie

| jak | co |
| --- | --- |
| dwuklik `napraw_fonty.bat` | Windows — pyta o katalog gry |
| `sh napraw_fonty.sh` | Linux |
| `python fix_game_fonts.py "E:\Gry\Gra"` | to samo z wiersza poleceń |
| `python fix_game_fonts.py "E:\Gry\Gra" --auto` | bez pytań, wszędzie odpowiedź spod Entera, gra nietknięta |
| `python fix_game_fonts.py --check` | **sprawdza `config.json` i biblioteki** — zacznij od tego na nowej maszynie |

### Luźne pliki fontów (`.ttf` / `.otf` / `.ttc` / `.otc`)

Narzędzia silnikowe czytają fonty tylko z assetów i paków. Fonty leżące w grze jako
zwykłe pliki (StreamingAssets, Godot, silniki własne, mody) albo w dowolnym innym
folderze obsługuje `loose_fonts.py` — nie wymaga rozpoznania silnika.

| jak | co |
| --- | --- |
| `fix_game_fonts.py "E:\Gry\Gra"` | po narzędziu silnika pyta: *Przeszukać też luźne pliki fontów? [t/N]* |
| `... --files` | po narzędziu silnika przeszukuje też luźne pliki w folderze gry |
| `... --files-only` | tylko luźne pliki, bez wykrywania silnika (`--auto`, `--list`, `--patch`, `--out` działają) |
| `... --fonts-dir "E:\Fonty"` | dodatkowy folder (można powtarzać; włącza `--files`; z `--files-only` katalog gry nie jest potrzebny) |
| `python loose_fonts.py "E:\Gry\Gra" "E:\Fonty"` | samo narzędzie, bez launchera |

Skan jest rekurencyjny, pomija katalogi wyjściowe (`fixed`, `fixed_fonts`, `font_preview`,
`loose_fonts_out`, …) i rozpoznaje font po nagłówku, nie po rozszerzeniu (uszkodzone pliki
lądują w raporcie jako „nieznana forma”). Kolekcje `.ttc` naprawiane są razem, wszystkie kroje;
fonty ikonowe i CJK są pomijane (`--include-cjk` je włącza); identyczne pliki naprawiane są raz.

- **EKSPORT** (domyślny): poprawione kopie w `loose_fonts_out/<gra>/` (klucz `loose_fonts_out`
  w `config.json`, albo `--files-out` / `--out`) w tym samym układzie katalogów co źródło —
  wystarczy skopiować na miejsce oryginałów. Gra nietknięta.
- **PATCH** (`--patch`): nadpisuje w miejscu, oryginał zostaje jako `<plik>.bak_plfont`.
- Po naprawie wynik jest czytany z powrotem i sprawdzany — jeśli czegoś nadal brakuje,
  plik oznaczony jest jako `CZĘŚCIOWO` (kod wyjścia `1`).
- Kod wyjścia launchera = połączenie wyniku narzędzia silnika i plików (`1`, jeśli cokolwiek
  się nie udało).

`--unity` / `--unreal` wymusza silnik, gdy wykrywanie się myli. Pozostałe argumenty
idą bez zmian do narzędzia silnika (np. `--install`, `--list`, `--patch`).

Kody wyjścia: `0` naprawione · `1` część fontów się nie udała · `2` nie było czego
naprawiać · `3` nie rozpoznano silnika / zły config.

## `config.json` — wszystkie ścieżki w jednym miejscu

Ścieżki **względne liczą się od folderu z `config.json`**, bezwzględne zostają jak są.
Pusty napis = „szukaj w `PATH`” (programy) albo „wartość domyślna narzędzia” (katalogi).
Zmienna `FONT_FIXER_CONFIG` wskazuje inny plik konfiguracji.

| klucz | co to | gdy puste / brak pliku |
| --- | --- | --- |
| `unity_tool` | skrypt naprawy fontów Unity (`fix_tmp_polish_fonts.py`) | `unity/fix_tmp_polish_fonts.py` |
| `unreal_tool` | skrypt naprawy fontów Unreala | `unreal/fix_unreal_polish_fonts.py` |
| `repak` | `repak.exe` — czytanie i budowanie `.pak` (Unreal, **wymagany**) | `repak` z `PATH` |
| `retoc` | `retoc.exe` — IoStore `.utoc/.ucas` (Unreal: wykrywanie i naprawa fontów offline) | `retoc` z `PATH`; bez niego ten krok jest pomijany |
| `unreal_output_dir` | gdzie lądują paki, podglądy i oryginały (podfolder na grę) | `unreal_fonts_out/` w bieżącym katalogu |
| `unity_export_dir` | katalog `fixed_fonts` dla Unity (przekazywany jako `--export-dir`) | `fixed_fonts/` obok skryptu Unity |
| `loose_fonts_out` | gdzie lądują poprawione luźne pliki fontów (podfolder na grę) | `loose_fonts_out/` w bieżącym katalogu |

Skąd wziąć programy: [repak](https://github.com/trumank/repak/releases),
[retoc](https://github.com/trumank/retoc/releases).

## Co jest w folderze, a czego nie ma

```
tools/font_fixer/
  napraw_fonty.bat / .sh        uruchamiacze
  fix_game_fonts.py             wykrywanie silnika + przekazanie dalej
  config.json, ff_config.py     ścieżki
  loose_fonts.py                luźne pliki .ttf/.otf/.ttc w folderach: skan, raport, naprawa
  fix_polish_fonts.py           SILNIK KROJU: dorabianie liter w TTF/OTF/TTC (wspólny)
  ttf_polish_glyphs.py          starszy wariant dorabiania (używany przez inne moduły repo)
  requirements.txt              biblioteki Pythona
  unity/
    fix_tmp_polish_fonts.py     Unity: TMP / Font / bitmapowe -> fixed_fonts/ albo patch gry
    patch_fixed_fonts.py        Unity: instalacja fixed_fonts/ w grze (używają jej instalatory gier)
    bitmap_font_atlas.py, unitypy_format23.py
    narzedzia/                  generator SDF, testy, szkielet BepInEx
    instalator/                 uniwersalny instalator fontów dla graczy
    INSTRUKCJA_FONT_FIX.md
  unreal/
    fix_unreal_polish_fonts.py  Unreal: .ufont / .ttf w pakach -> FONTY_PL_P.pak
    offline_font.py             Unreal: fonty offline (atlas w .uasset) -> FONTY_PL_OFFLINE_P
    INSTRUKCJA_FONT_FIX_UNREAL.md
```

Moduł Unity (dawniej `unity_tools/fonts/`) jest teraz **w tym folderze**, razem
z `unitypy_format23.py`, więc oba silniki można przenieść jednym katalogiem.
Poza nim zostają:

- **`repak.exe` / `retoc.exe`** (Unreal) — ścieżki w configu,
- **biblioteki Pythona** — `pip install -r requirements.txt` (Python 3.10+),
- **`unity_tools/fix_addressables_crc.py`** — tylko przy instalacji fontów w grach
  z Addressables (`patch_fixed_fonts.py` szuka go pod `<repo>/unity_tools/`; bez niego
  eksport i zwykły patch działają, a instalator ostrzega, że nie przeliczy `catalog.json`).

Układ katalogu musi zostać taki, jak w repo — `patch_fixed_fonts.py` liczy ścieżkę do
`unity_tools/` od własnego położenia (`tools/font_fixer/unity/` → korzeń repo).

## Co robi każdy silnik

**Unity** — skanuje assety i bundle, znajduje `TMP_FontAsset`, zwykłe `Font` i fonty
bitmapowe, dorabia litery na atlasie albo w konturach TTF. Domyślnie EKSPORT do
`fixed_fonts/` (gra nietknięta), `--patch` zapisuje w grze z kopią `.bak_plfont`.
Uwaga: przy starcie pyta, czy skasować podglądy z poprzedniej gry (`font_preview/`);
w `--auto` kasuje je bez pytania.

**Unreal** — czyta paki przez `repak`, wyciąga `*.ufont` / `*.ttf` / `*.otf` (bez
`Engine/`), obsługuje obie formy `.ufont` (surowy font oraz z 4-bajtowym nagłówkiem),
buduje `FONTY_PL_P.pak` i — gdy gra ma pliki `.sig` — dokłada kopię podpisu pod nazwą
moda. Pak trafia do katalogu wyjściowego; do gry kopiuje go dopiero `--install` albo
odpowiedź „t” na pytanie.

**Unreal, fonty offline** — atlas liter zaszyty w `.uasset` (TextRender, część HUD-ów),
bez pliku `.ufont`; to one gubią ogonki, gdy wszystkie pliki fontów są w porządku.
Skrypt wykrywa je, dorysowuje brakujące litery w stylu dopasowanym do istniejących
i buduje osobny mod `FONTY_PL_OFFLINE_P` (gra z IoStore: trzy pliki `.utoc/.ucas/.pak`,
wszystkie muszą trafić do `Paks`). Wymaga `retoc` dla gier z IoStore.

## Pytania i pliki robocze

Każdy tekst, na który trzeba odpowiedzieć, jest **błękitny** (launcher, Unreal i Unity).
Enter zawsze wybiera odpowiedź domyślną — wielka litera w `[T/n]` / `[t/N]`.

Narzędzie Unreala na końcu pyta **„Skasować pliki robocze? [T/n]”** (domyślnie tak):
usuwa `oryginalne/`, `assety_fontow/` i katalogi przygotowane do spakowania, a zostawia
gotowe mody, `podglad/` i raporty. W `--auto` sprząta bez pytania; `--keep-work`
wyłącza sprzątanie (np. gdy chcesz obejrzeć wyciągnięte fonty w edytorze).

## Czego narzędzie nie naprawia

- Fonty offline w Unrealu o nietypowej budowie (strony inne niż `PF_G8`, `Characters`
  z przemapowaniem, brak miejsca w atlasie) — skrypt odmawia z podanym powodem.
- Fonty zaszyte w `.uasset` jako FontFace „Inline” — tylko wypisywane.
- Gry weryfikujące podpisy paków naprawdę — kopia `.sig` nie wystarczy, potrzebny bypass.

„Wszystkie pliki fontów OK” nie gwarantuje więc ogonków w grze — zawsze sprawdź
ostrzeżenia na końcu raportu.

## Dodanie kolejnego silnika

Nowy skrypt (zajmuje się tylko opakowaniem fontu, samą naprawę woła przez
`fix_polish_fonts.fix_font_bytes`) + klucz `<silnik>_tool` w `config.json` + wpis
w `TOOLS` i `detect_engine()` w `fix_game_fonts.py`.
