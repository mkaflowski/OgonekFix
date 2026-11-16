# Unreal Engine: polskie znaki w fontach (`fix_unreal_polish_fonts.py`)

Wspólne wejście dla obu silników: dwuklik `tools/font_fixer/napraw_fonty.bat`
(Linux: `sh napraw_fonty.sh`) albo `python tools/font_fixer/fix_game_fonts.py`
— pyta o katalog gry, rozpoznaje Unity/Unreal i odpala właściwe narzędzie
(argumenty przekazuje dalej, `--unity` / `--unreal` wymusza silnik).

Odpowiednik `tools/font_fixer/unity/fix_tmp_polish_fonts.py` dla Unreala 4 i 5.
Szuka fontów w pakach gry, dorabia brakujące polskie litery **w kroju tego samego
fontu** (silnik: `tools/font_fixer/fix_polish_fonts.py`, te same domyślne
ustawienia) i buduje mod `FONTY_PL_P.pak`.

```
python tools/font_fixer/unreal/fix_unreal_polish_fonts.py
python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\SteamLibrary\steamapps\common\Gra"
python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\...\Gra" --auto            # bez pytań, gra nietknięta
python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\...\Gra" --auto --install  # + kopia paka do gry
python tools/font_fixer/unreal/fix_unreal_polish_fonts.py "E:\...\Gra" --list            # sam raport
```

Wymaga `repak.exe` (`E:\Programy\UnrealEngineModding\repak\`, albo w `PATH`;
katalog narzędzi można zmienić zmienną `UNREAL_MODDING_DIR`) oraz
`pip install fonttools skia-pathops pillow`.

## Co robi po kolei

1. Znajduje `Content/Paks`, nazwę projektu, wersję silnika (z zasobów
   `*-Shipping.exe`) i **wersję formatu pak** (z samych paków — to ona idzie do moda).
2. Czyta indeksy wszystkich `.pak` (`repak list`); patche `_P` nadpisują paki
   bazowe, własny wcześniejszy `FONTY_PL_P.pak` jest pomijany (ponowne
   uruchomienie startuje zawsze z oryginałów).
3. Wyciąga fonty gry — `*.ufont` oraz luźne `*.ttf/*.otf/*.ttc` — do `oryginalne/`.
   **Fonty silnika z `Engine/` są pomijane** (`--include-engine` je włącza)
   (obok każdego `.ufont` ląduje też rozpakowany `.ttf`/`.otf` do podejrzenia).
4. Lista: `polskie OK` / `BRAK polskich` / `pominięty` (CJK, fonty bez łaciny).
5. Naprawa: Enter = wszystkie fonty z brakami, tryb „wszystkie litery”.
6. Podgląd PNG każdego naprawionego fontu w `podglad/` — **obejrzyj przed wgraniem**.
7. `repak pack` → `FONTY_PL_P.pak`, kontrola zawartości, pytanie o kopię do gry
   (domyślnie **nie**).
8. Gdy gra ma pliki `.sig`: obok paka powstaje `FONTY_PL_P.sig` — kopia podpisu
   z gry pod nazwą moda (`--no-sig` wyłącza). Pak i `.sig` idą do gry razem.

Wynik: `E:\Programy\UnrealEngineModding\Output\Fonts\<Gra>\` (`--out` zmienia).

## Formy pliku `.ufont`

| forma | budowa | rozpoznanie |
| --- | --- | --- |
| surowy | zwykły TTF/OTF | plik zaczyna się od `00 01 00 00` / `OTTO` |
| z nagłówkiem | `[uint32 LE = długość fontu − 4][TTF/OTF]` | sygnatura fontu dopiero od 4. bajtu |

Dlatego „zmiana rozszerzenia na `.otf`” raz działa, a raz nie. Skrypt zdejmuje
nagłówek, naprawia font i zakłada nagłówek z przeliczoną długością. Reguła
`długość − 4` zmierzona na 59 plikach z 4 gier (Samson, Elliot, Amsterdam 1666...)
bez wyjątku; tabele fontu sięgają do końca pliku, więc **payload to cała reszta
pliku**, nie „tyle bajtów, ile mówi licznik”. Przy zapisie font jest dopełniany
zerami, żeby był kompletny przy obu interpretacjach licznika.

## Dlaczego sam `.pak`, także w UE5 z IoStore

W grach z `.utoc/.ucas` do IoStore trafiają tylko **pakiety** (`.uasset`, `.umap`,
`.ubulk`). Pliki „nie-assetowe” — `.ufont`, `.locres`, `.ini` — zostają w zwykłym
`.pak` nawet w UE 5.5 (Crisol: 12 `.ufont` w `CRToiPrototype-Windows.pak`, zero
w `.utoc`). Mod z fontami to więc **zawsze jeden plik `.pak`**, bez `.utoc/.ucas`
i bez kopiowania czegokolwiek z `global.*`.

Trójka `X_P.pak + X_P.utoc + X_P.ucas` jest potrzebna dopiero wtedy, gdy mod
podmienia `.uasset` (wtedy `retoc to-zen`): silnik szuka plików `.pak`, a `.utoc`
montuje tylko jako „towarzysza” paka o tej samej nazwie — stąd pusty pak obok
kontenera. Fontów to nie dotyczy.

## Fonty offline (atlas liter w `.uasset`)

TextRender i część HUD-ów nie używa `.ufont`, tylko fontu **offline**: tablica
`Characters` + strony atlasu `Texture2D` w jednym pakiecie, stały zestaw znaków
(zwykle Latin-1). Dlatego gra potrafi gubić ogonki przy „wszystkie `.ufont` OK”
(Crisol: sklepik). Skrypt po analizie plików fontów:

1. wykrywa takie assety (IoStore: `retoc to-legacy`; klasyczny pak: `repak get`),
2. sprawdza, których polskich liter brakuje w `Characters`,
3. bierze font źródłowy z gry (najpierw o podobnej nazwie; `--offline-ttf <plik>`
   wskazuje go ręcznie) i **dopasowuje render do istniejących liter atlasu** —
   rozmiar, linię bazową i technikę (pole odległości SDF albo zwykłe krycie).
   Błąd dopasowania powyżej 6 poziomów szarości = odmowa (to nie ten krój),
4. dorysowuje litery w wolnym miejscu atlasu, wydłuża `Characters`, poprawia
   rozmiary i offsety eksportów,
5. buduje osobny mod `FONTY_PL_OFFLINE_P`: `.utoc/.ucas/.pak` dla IoStore (z kontrolą
   zwrotną bajt w bajt), sam `.pak` dla gier klasycznych. Podgląd: `podglad/*_offline.png`.

`--no-offline` wyłącza ten krok. Kod: `offline_font.py` (wymaga `numpy`, `scipy`).

Założenia, przy których działa: strony `PF_G8`, `Characters` indeksowane wprost kodem
znaku (`IsRemapped = false`), wolne miejsce w atlasie. Sprawdzone tylko na Crisolu
(SDF, 4 strony 256×256); ścieżka klasycznego paka — na spreparowanym paku z tym
samym assetem. **W grze nietestowane.**

## Czego narzędzie nie obsługuje

- **Font zaszyty w `.uasset`** (FontFace z `LoadingPolicy = Inline`, bez `.ufont`).
  Skrypt tylko wypisuje podejrzane assety. Wymagałoby to `retoc to-legacy` →
  podmiana danych w `.uexp` z poprawką rozmiarów → `retoc to-zen`.
- **Fonty offline o nietypowej budowie** — patrz sekcja „Fonty offline” niżej; skrypt
  odmawia z podanym powodem zamiast zgadywać.
- **Gry naprawdę weryfikujące podpisy.** Kopia `.sig` wystarcza tam, gdzie silnik
  wymaga tylko obecności pliku (tak są zrobione mody w Trover Saves the Universe).
  Gdy skróty bloków są egzekwowane, potrzebny bypass (`dsound.dll` +
  `UniversalSigBypasser.asi`).
- Paki zaszyfrowane wymagają `--aes` (skrypt zapyta, gdy nic nie da się odczytać).

## Status weryfikacji

Sprawdzone: wykrywanie i odczyt na Crisol (UE 5.5.4, IoStore, pak V11 + Oodle),
naprawa i pakowanie na spreparowanym paku z fontami obu form (TTF i OTF/CFF),
odczyt zwrotny z gotowego paka, drugi przebieg, kopia `.sig` na atrapie podpisu,
naprawa fontu offline Crisola (kontener zgodny bajt w bajt po konwersji zwrotnej). **Nie sprawdzone w grze** — na
Crisolu nie było czego naprawiać (wszystkie fonty łacińskie mają polskie znaki).
