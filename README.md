# OgonekFix

**Dorabia brakujące polskie znaki (`ą ć ę ł ń ó ś ź ż` i wielkie) w fontach gier - w kroju
tego samego fontu, a nie przez podmianę na inny.**

Spolszczenie nic nie da, jeśli font gry nie ma polskich liter: zamiast `ą` widać kwadrat
albo goły `a`. OgonekFix znajduje takie fonty, dorysowuje brakujące glify i oddaje je w formie,
którą da się wgrać do gry.

## Co obsługuje

| Źródło fontu | Co robi narzędzie |
| --- | --- |
| **Unity** | `TMP_FontAsset` (statyczne i dynamiczne), zwykłe `Font`, fonty bitmapowe; także gry IL2CPP |
| **Unreal Engine 4/5** | `.ufont` / `.ttf` / `.otf` w pakach (`.pak`, IoStore) oraz fonty offline (atlas zaszyty w `.uasset`) |
| **Luźne pliki** | `.ttf` `.otf` `.ttc` `.otc` w dowolnych folderach - niezależnie od silnika |

## Jak to działa

Brakujące litery powstają w trzech krokach, od najlepszego:

1. **Złożenie z istniejących elementów** - litera bazowa plus kreska, kropka lub ogonek wycięte
   z liter, które font już ma (`ó` → kreska, `ż` → kropka, `ą` → ogonek).
2. **Dorysowanie** - gdy w foncie nie ma dawcy: przekreślenie `ł`, ogonek (krzywa Béziera),
   kreska i kropka, o grubości dobranej do laski litery.
3. **Awaryjnie** - wersja bez ogonka, jeśli font nie ma nawet litery bazowej.

Glify są scalane w jeden kontur, dzięki czemu wyglądają tak samo przy różnych regułach
wypełniania. Wykrywane są też fonty, w których kod `ó` wskazuje na pusty `.notdef` albo na zwykłą
literę ASCII - takie „mają” znak tylko na papierze.

## Instalacja

Wymaga Pythona 3.10+.

```bash
python -m pip install -r requirements.txt
python fix_game_fonts.py --check
```

`--check` sprawdza `config.json` i biblioteki - zacznij od niego na nowej maszynie.
Dla Unreala potrzebne są jeszcze [repak](https://github.com/trumank/repak/releases)
i (dla gier z IoStore) [retoc](https://github.com/trumank/retoc/releases); ścieżki wpisujesz
w `config.json`.

## Użycie

Dwuklik w `napraw_fonty.bat` (Windows) albo `sh napraw_fonty.sh` (Linux) - narzędzie zapyta
o katalog gry, rozpozna silnik i poprowadzi dalej. To samo z wiersza poleceń:

```bash
# interaktywnie
python fix_game_fonts.py "E:\Gry\Gra"

# bez pytań, gra nietknięta
python fix_game_fonts.py "E:\Gry\Gra" --auto

# tylko luźne pliki fontów, w kilku folderach
python fix_game_fonts.py "E:\Gry\Gra" --files-only --fonts-dir "E:\Fonty"

# tylko raport, nic nie zmieniaj
python fix_game_fonts.py "E:\Gry\Gra" --files-only --list
```

| Flaga | Działanie |
| --- | --- |
| `--auto` | bez pytań, wszędzie odpowiedź spod Entera |
| `--unity` / `--unreal` | wymusza silnik, gdy wykrywanie się myli |
| `--files` | po narzędziu silnika przeszukaj też luźne pliki fontów w folderze gry |
| `--files-only` | tylko luźne pliki, bez wykrywania silnika |
| `--fonts-dir DIR` | dodatkowy folder do przeszukania (można powtarzać) |
| `--patch` | zapisz wprost w plikach (oryginał jako `<plik>.bak_plfont`) |
| `--marks-only` | dorabiaj tylko kreskę i kropkę (`ć ń ó ś ź ż`) |
| `--include-cjk` | naprawiaj też fonty CJK (domyślnie pomijane) |
| `--list` | tylko raport |
| `--check` | sprawdź konfigurację i biblioteki |

### Tryby zapisu

- **Eksport (domyślny)** - poprawione kopie trafiają do osobnego katalogu w takim samym układzie
  jak źródło; gra zostaje nietknięta, a pliki kopiujesz na miejsce sam.
- **Patch** - pliki są nadpisywane w miejscu, z kopią zapasową obok.

### Kody wyjścia

`0` naprawione · `1` część fontów się nie udała · `2` nie było czego naprawiać ·
`3` nie rozpoznano silnika albo zły config.

## Konfiguracja

Wszystkie ścieżki są w `config.json` (względne liczone od jego folderu; pusty wpis = szukaj
w `PATH` albo użyj domyślnej wartości). Inny plik wskażesz zmienną `FONT_FIXER_CONFIG`.

## Ograniczenia

- „Wszystkie fonty OK” nie zawsze znaczy, że gra pokaże ogonki - część gier ma fonty w innych
  miejscach (np. wpisane w tekstury albo zaszyte w `.uasset` jako „Inline”). Zwracaj uwagę
  na ostrzeżenia na końcu raportu.
- Gry Unreala weryfikujące podpisy paków wymagają osobnego obejścia; sama kopia `.sig` nie wystarczy.
- Fonty offline w Unrealu o nietypowej budowie są odrzucane z podaniem powodu.
- Fonty wymagają testu w samej grze - narzędzie sprawdza obecność i kształt glifów,
  nie to, jak dany silnik je wyrenderuje.

## Struktura

```
fix_game_fonts.py      wejście: wykrywa silnik i uruchamia właściwe narzędzie
loose_fonts.py         luźne pliki .ttf/.otf/.ttc w folderach
fix_polish_fonts.py    silnik kroju: dorabianie liter w TTF/OTF/TTC (wspólny)
unity/                 Unity: TMP, Font, bitmapowe, instalacja w grze
unreal/                Unreal: .ufont w pakach, fonty offline
config.json            ścieżki do narzędzi i katalogów wyjściowych
```

## Licencja

Kod narzędzia: [MIT](LICENSE).

Licencja obejmuje tylko to narzędzie. Poprawione fonty są pochodną fontów z gry i dalej
podlegają ich licencji - nie rozpowszechniaj ich bez zgody właściciela fontu.
