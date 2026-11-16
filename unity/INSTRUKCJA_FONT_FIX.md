# INSTRUKCJA: naprawa polskich znaków w fontach TMP (gry Unity)

Narzędzia z tego folderu naprawiają fonty TextMeshPro (atlasy SDF) oraz zwykłe
assety `Font` (stare `UI Text` / `GUIStyle`), w których brakuje polskich znaków
(ąćęłńóśźż). Działają na grach Unity (Mono i IL2CPP), na plikach `.assets`
i bundlach.

## Skrypty

| Skrypt | Do czego | Wymaga |
|---|---|---|
| `fix_tmp_polish_fonts.py` | znajduje i naprawia fonty (tryb PATCH lub EKSPORT) | UnityPy, TypeTreeGeneratorAPI, freetype-py, fontTools, skia-pathops, numpy, PIL |
| `patch_fixed_fonts.py` | instaluje gotowe fonty z `fixed_fonts/` do gry | UnityPy, TypeTreeGeneratorAPI, numpy, PIL (bez FreeType) |
| `narzedzia/generate_tmp_sdf.py` | silnik generowania atlasów SDF (używany przez powyższe; można też ręcznie z dumpami UABEA) | freetype-py, numpy, PIL |
| `narzedzia/export_game_fonts.py` | eksportuje wszystkie pliki fontów (TTF/OTF/TTC) z gry do `exported_fonts/` — np. żeby obejrzeć, czego gra używa, albo użyć ich jako źródła/fallbacku | UnityPy |
| `narzedzia/render_text_sample.py` | składa napis z naprawionego fontu (`fixed_preview/`) i wypisuje, skąd wzięta jest każda polska litera; woła go sam `fix_tmp_polish_fonts.py`, ale działa też z linii poleceń na gotowym `fixed_fonts/` | numpy, PIL, freetype-py (tylko fonty dynamiczne) |

Pozostałe pomocnicze skrypty (testy, `font_finder`, `fix_wrong_pl_glyphs`, `monoreplacer*`, szkielet BepInEx) leżą w `narzedzia/`.
Przy każdym uruchomieniu `fix_tmp_polish_fonts.py` pyta, czy skasować wyniki poprzedniej pracy
(`fixed_fonts/`, `fixed_preview/`, `font_preview/`) — domyślnie **T**.

Skrypt `fix_tmp_polish_fonts.py` robi **jedno i drugie**: sam **szuka** fontów
w plikach gry (`.assets`, `data.unity3d`, bundle — także w grach IL2CPP) i sam je
**naprawia**. Nie trzeba mu podawać nazw fontów, nazw plików ani pliku TTF —
wystarczy ścieżka do katalogu gry.

## Opcje linii poleceń

| Opcja | Znaczenie |
|---|---|
| `<katalog gry>` | pozycyjny, wymagany (bez niego skrypt zapyta) |
| `<filtr>` | drugi pozycyjny — zawęża skan do plików z tym fragmentem w nazwie |
| `--auto`, `-y` | bez żadnego pytania: wszędzie odpowiedź domyślna (patrz wariant C) |
| `--patch` | wstrzykuj wynik do plików gry (domyślnie: eksport) |
| `--export` | wymuś EKSPORT bez pytania o tryb |
| `--export-dir DIR` | katalog eksportu (domyślnie `fixed_fonts/` obok skryptu) |
| `--fallback PLIK` | TTF/OTF na litery, których nie da się złożyć z własnych glifów |
| `--marks-only` | dorabiaj tylko kreskę i kropkę (`ą ę ł` z fallbacku) |
| `--replace-chars ąę` | odtwórz wskazane polskie glify statycznego TMP, nawet jeśli są w atlasie, lecz mają błędny rysunek; resztę glifów zachowaj |
| `--jobs N`, `-j N` | liczba procesów skanu (1 = bez równoległości) |
| `--help`, `-h` | pełna pomoc |

---

## Wariant A: szybka naprawa własnej gry (tryb PATCH)

1. Uruchom:
   ```
   python fix_tmp_polish_fonts.py "E:\Games\NazwaGry"
   ```
   (drugi argument opcjonalnie zawęża skan do plików z daną nazwą, np.
   `sharedassets0` — przydatne w dużych grach).
2. Wybierz tryb **[2] PATCH**.
2a. Skrypt zapyta o **zakres dorabiania brakujących liter z własnych glifów
   fontu** (dotyczy wszystkich fontów w tej sesji):
   - **[1] WSZYSTKIE** (domyślne, tak jak `font_fixer/fix_polish_fonts.py`
     z pełnym zestawem) — kreska i kropka są wycinane z glifów fontu
     (różnica `ó`−`o`, górka z `i`), a **ogonek (ą ę) i przekreślenie (ł)
     dorysowywane geometrycznie**; font FALLBACK jest potrzebny tylko na to,
     czego naprawdę nie da się złożyć (np. brak litery bazowej),
   - **[2] TYLKO kreska i kropka** (ć ń ó ś ź ż) — `ą ę ł` biorą się wtedy
     z fontu FALLBACK albo z transliteracji (dawne zachowanie skryptu).

   W obu trybach kreska i kropka, gdy **nie ma ich z czego wyciąć** (krój bez
   ani jednego akcentu i bez `´ ˙`), są **dorysowywane** — inaczej `ć ń ó ś ź ż`
   musiałyby przyjść z obcego kroju i odstawałyby rozmiarem od reszty napisu.
3. Skrypt przeskanuje pliki gry i wypisze wszystkie fonty TMP z oznaczeniem:
   `polskie OK` / `BRAK polskich` (statyczne — sprawdzana `m_CharacterTable`)
   albo `DYNAMICZNY, polskie w TTF OK` / `DYNAMICZNY, BRAK w TTF: <znaki>`
   (dynamiczne — sprawdzany cmap źródłowego TTF, bo `m_CharacterTable` bywa
   prawie pusta i nic nie mówi o realnych możliwościach fontu).
4. Zanim skrypt zapyta, które naprawić, zrzuca podglądy do folderu
   **`font_preview/`** obok skryptu — `NN_<nazwa>.png`, gdzie `NN` to numer
   z listy (statyczne: obecny atlas SDF, dynamiczne: próbka tekstu z ich TTF).
   Obejrzyj je, żeby wiedzieć, który wpis to naprawdę ten font, o który chodzi.
5. Wybierz numery fontów do naprawy (Enter = wszystkie bez polskich znaków —
   statyczne i dynamiczne).
6. Dla fontów **statycznych** skrypt szuka pasującego TTF w grze (po nazwie
   rodziny). Jeśli nie znajdzie, do wyboru: **[1]** zostaw glify z bieżącego
   atlasu i dopisz tylko brakujące litery (zalecane — wygląd fontu się nie
   zmienia; brakujące litery są składane/dorysowywane wprost na pikselach
   atlasu), **[2]** wygeneruj cały font od nowa z wybranego TTF/OTF,
   **[3]** pomiń, **[4]** jak [1], ale dla wszystkich kolejnych fontów bez
   pytania (tryb „nie pytaj więcej" — litery, których nie da się złożyć,
   biorą ostatnio wybrany fallback albo idą w transliterację).
7. Jeśli wybrany TTF **nie ma polskich znaków**, dostaniesz menu:
   - **[1]** podmień na INNY font (całkowita podmiana wyglądu),
   - **[2]** dodaj font FALLBACK — oryginalny font zostaje, tylko brakujące
     litery (ą, ę, ś...) są dorabiane z drugiego fontu,
   - **[3]** transliteruj brakujące litery (ą→a itd.),
   - **[4]** dorób brakujące litery z własnych glifów tego fontu — bez obcego
     kroju (domyślne, gdy w kroku 2a wybrano WSZYSTKIE),
   - **[5]** pomiń ten font.
8. Dla fontów **dynamicznych** naprawa idzie w kontury źródłowego TTF i menu
   jest inne:
   - **[1]** dorób brakujące litery w samym foncie — techniką z
     `font_fixer/fix_polish_fonts.py`, w zakresie wybranym w kroku 2a
     (domyślnie WSZYSTKIE: kreska i kropka wycięte z glifów fontu — a gdy nie ma
     z czego, dorysowane; ogonek i przekreślenie zawsze dorysowane). To, czego
     nie udało się złożyć (brak litery bazowej), możesz jeszcze wkleić
     **z fontu FALLBACK**; bez fallbacku te litery zostaną bez ogonków,
   - **[2]** podmień cały plik TTF/OTF,
   - **[3]** transliteracja — brakujące znaki dostają glify bez ogonków,
   - **[4]** pomiń ten font.

   Pliki `.ttc` (kolekcja kilku krojów w jednym pliku, np. warianty
   latin/zh/ja/ko) są naprawiane w całości — każdy krój osobno, bo nie wiadomo,
   po który sięga gra.
9. Skrypt zapisze pliki gry (backupy: `<plik>.bak_plfont`).
10. Każdy naprawiony font dostaje po drodze podgląd złożonego napisu w
    **`fixed_preview/`** obok skryptu (w trybie EKSPORT — obok `fixed_fonts/`)
    plus raport pochodzenia polskich liter na konsoli. Zerknij tam, zanim
    odpalisz grę: `FALLBACK` przy jakiejkolwiek literze znaczy, że wyjdzie
    innym krojem i rozmiarem.
11. Przetestuj w grze. Rollback: przywróć pliki `.bak_plfont`.

### Glif istnieje, ale ma zły kształt

Sam wpis w `m_CharacterTable` nie dowodzi, że litera jest poprawnie narysowana.
Przykład Nexus VR: oryginalny DINOT ma pod `ą/ę` odłączone ukośne kreski zamiast
ogonków. Po potwierdzeniu na podglądzie użyj `--replace-chars ąę` i wybierz fonty
jak zwykle. Narzędzie odtwarza te znaki z bazowych `a/e` i własnego algorytmu
ogona; pozostałe glify zachowuje. Dla wywołań z kodu służy parametr
`replace_chars="ąę"` w `rebuild_font_asset_from_atlas()`. To jawna operacja na
wskazanych znakach, nie automatyczne przebudowywanie istniejących polskich liter.

## Wariant B: przygotowanie paczki dla użytkowników (EKSPORT + instalator)

Krok 1 — na swoim komputerze (wymaga FreeType):

1. Uruchom `python fix_tmp_polish_fonts.py "E:\Games\NazwaGry"`.
2. Wybierz tryb **[1] EKSPORT** (domyślny).
3. Dalej jak w wariancie A (wybór fontów, TTF, fallback) — ale gra NIE jest
   modyfikowana; naprawione fonty trafiają do folderu **`fixed_fonts/`**
   obok skryptu:
   - `<nazwa>.json` + `<nazwa>.png` — fonty statyczne (typetree TMP + atlas),
   - `<nazwa>.json` + `<nazwa>.ttf` — fonty dynamiczne (podmiana danych TTF).
4. Obejrzyj wygenerowane `.png` — od razu widać, czy w atlasie są polskie znaki.
4a. Obejrzyj **`fixed_preview/`** (obok `fixed_fonts/`) — skrypt zapisuje tam
   automatycznie, dla każdego naprawionego fontu, **złożony napis** z polskimi
   literami. Atlas pokazuje litery w kratce, więc nie widać na nim ani metryk,
   ani tego, że litera przyszła z obcego kroju; napis pokazuje jedno i drugie.
   Do napisu dochodzi raport na konsoli — pochodzenie każdej polskiej litery:
   `zlozone z wlasnych glifow fontu` (dobrze), `bez akcentu (transliteracja)`
   albo **`z OBCEGO fontu (FALLBACK)`**. Ostatni wariant to jedyny, który
   zmienia krój i rozmiar litery — w grze będzie odstawać od reszty napisu
   (patrz „Litery w innym rozmiarze" niżej).
4b. Ten sam podgląd można zrobić w każdej chwili na gotowej paczce, także po
   miesiącach, bez gry pod ręką:
   ```
   python narzedzia/render_text_sample.py fixed_fonts --text "DZIĘKI [WYJDŹ]"
   ```

Krok 2 — instalacja u użytkownika (bez FreeType):

5. Przekaż użytkownikowi: `patch_fixed_fonts.py` (albo zbudowany
   `patch_fixed_fonts.exe`) + folder `fixed_fonts/` obok.
6. Użytkownik uruchamia i podaje ścieżkę do gry:
   ```
   python patch_fixed_fonts.py "E:\Games\NazwaGry"
   ```
7. Skrypt instaluje wszystkie fonty z `fixed_fonts/` (backupy `.bak_plfont`).

## Wariant C: tryb `--auto` (bez pytań, do wołania z innych skryptów)

Interaktywne menu z wariantów A i B **zostaje domyślne** — `--auto` to tylko skrót
dla automatu (inny skrypt, CI, brak konsoli do odpowiadania). W tym trybie skrypt
nie zadaje ani jednego pytania: każde dostaje **tę samą odpowiedź, którą daje
Enter**, i wypisuje ją w logu z dopiskiem `(automat)`.

```
python fix_tmp_polish_fonts.py "E:\Games\NazwaGry" --auto
python fix_tmp_polish_fonts.py "E:\Games\NazwaGry" --auto --patch
python fix_tmp_polish_fonts.py "E:\Games\NazwaGry" --auto \
    --fallback Inter.ttf --export-dir ..\..\game_specific\unity\gra\fixed_fonts
```

Co automat wybiera:

| Pytanie | Odpowiedź w `--auto` |
|---|---|
| tryb pracy | EKSPORT do `fixed_fonts/` (`--patch` = zapis do gry, `--export-dir` = inny katalog) |
| zakres dorabiania | WSZYSTKIE litery z własnych glifów (`--marks-only` = tylko kreska i kropka) |
| które fonty naprawić | wszystkie bez polskich znaków; odsiane CJK/ikonowe pomijane |
| brak dopasowanego TTF | zostaw glify z atlasu, dopisz tylko brakujące litery |
| font FALLBACK | plik z `--fallback`, a bez niego transliteracja (nie ma kogo pytać o krój) |
| font dynamiczny bez czytelnego TTF | pomijany — do dokończenia ręcznie |
| nieudane dorabianie w TTF | pomiń ten font i leć dalej |
| fonty `UI Text` obok TMP | naprawiane też |

Kody wyjścia (dla skryptu wołającego):

| Kod | Znaczenie |
|---|---|
| `0` | fonty naprawione |
| `1` | część fontów się nie udała — zostaje ręczne dokończenie (lista w logu) |
| `2` | nie było czego naprawiać albo w grze nie ma fontów |

Podglądy (`font_preview/`, `fixed_preview/`) powstają tak samo jak w trybie
interaktywnym — po przebiegu automatu i tak warto je obejrzeć, zanim wynik wejdzie
do paczki. Uwaga dla dopisujących kod: **każde pytanie musi iść przez wspólne
`ask(prompt, default)`**, inaczej `--auto` zawiesi się na `input()`.

## Budowanie exe (PyInstaller)

Uniwersalny naprawiacz (ze wszystkim, ~62 MB):
```
pyinstaller --onefile --console --name fix_tmp_polish_fonts ^
  --collect-all UnityPy --collect-all TypeTreeGeneratorAPI ^
  --collect-all freetype --collect-data fontTools ^
  fix_tmp_polish_fonts.py
```

Lekki instalator (bez FreeType; `fixed_fonts/` leży OBOK exe):
```
pyinstaller --onefile --console --name patch_fixed_fonts ^
  --collect-all UnityPy --collect-all TypeTreeGeneratorAPI ^
  --exclude-module fontTools --exclude-module freetype ^
  patch_fixed_fonts.py
```

## Uwagi techniczne / pułapki

- **Nie zmieniaj fontów TMP na dynamiczne** (popMode=1 + readable na
  streamowanej teksturze atlasu) — to crashuje grę przy ładowaniu.
  Te skrypty generują wyłącznie statyczne atlasy.
- **Padding > 32** (fonty z efektem glow): FreeType ma limit spread=32,
  więc skrypt automatycznie zmniejsza padding do 32 i proporcjonalnie
  pointSize, a materiałom ustawia `_GradientScale = padding + 1`.
- **Za mały atlas**: powiększamy najpierw jedną oś tekstury, do maksymalnie
  16384 pikseli, aktualizując `_TextureWidth/Height` materiałów. Przy naprawie
  z atlasu oryginalne piksele i metryki glifów zostają zachowane. Przykład:
  Gladista/PTSerif SDF z Bye Sweet Carole mieszczą się w `8192×4096`, a bitmapowy
  PTSerif potrzebuje `16384×8192` (128 MiB Alpha8). Dopiero przy regenerowaniu
  z TTF i wyczerpaniu limitu obniżamy pointSize. Komunikat błędu podaje realny
  limit, zamiast dawnego, wpisanego na sztywno `8192`.
- **IL2CPP**: typetree jest generowany z `GameAssembly.dll` +
  `global-metadata.dat` gry — te pliki muszą być na miejscu.
  Jeśli bundle zgłasza wersję `0.0.0`, generator używa wersji wykrytej z plików
  głównych gry. Zły numer wersji powodował `read_str out of bounds` przy
  poprawnych fontach w `sharedassets0.assets`.
- **Zablokowany plik gry** (`PermissionError`): zamknij grę i UABEA.
- Gra IL2CPP z zestrippowanym TMP może nie mieć typetree — wtedy skrypt
  wypisze błąd odczytu przy danym foncie i go pominie.
- Fonty **DYNAMICZNE** nie mają atlasu do wypiekania — naprawa idzie w kontury
  źródłowego TTF (dorobienie liter + fallback / podmiana pliku /
  transliteracja) i tak samo trafia do assetu Font w obu trybach.
  Puste `m_FontData` (0 bajtów, np. „times new roman” w Bye Sweet Carole) to
  brak źródła, a nie brak samych polskich znaków. W automacie font jest pomijany
  z wyjaśnieniem; po ręcznym wybraniu można wskazać TTF/OTF do podmiany.
- **`advanceWidthMax`, np. `Value 902.0 does not fit in format H`**: metryki
  dodawanych glifów są teraz zaokrąglane do liczb całkowitych przed zapisem
  przez wspólny `tools/font_fixer/fix_polish_fonts.py`.
- **Prostokąt zamiast `ó/Ó` mimo obecności w cmap**: wykrywamy także glify
  identyczne z `.notdef` (Electronic Highway Sign), żeby dorobić prawdziwe litery.
- **Ogonek `Ą` zaczepiony za wysoko**: zaczep mierzymy na prawym odcinku tuszu
  przy spodzie litery, wykorzystując regułę z `tools/font_fixer/ttf_polish_glyphs.py`.
  Limit 80% szerokości nie może wypchnąć zaczepu poza prawą nóżkę `A`.
  Wspólna funkcja `ogonek_anchor_x` obsługuje zarówno kontury TTF, jak i atlas TMP.
- **Gry bez TextMeshPro** (stare `UI Text` / `GUIStyle`) renderują wprost
  z assetów `Font`, czyli z TTF-a osadzonego w `m_FontData`. Takie fonty idą tą
  samą ścieżką co źródłowy TTF fontu dynamicznego: osobna lista
  `Font (TTF, UI Text / stare GUI)` z oznaczeniem braków, podglądy
  `ttf_NN_<nazwa>.png` w `font_preview/`, to samo menu naprawy, a wynik wraca
  do `m_FontData`. W trybie EKSPORT dostajesz `<nazwa>.ttf` + `<nazwa>.json`
  typu `dynamic_font_data` — instaluje je `patch_fixed_fonts.py` bez żadnych
  zmian. Gdy gra ma i fonty TMP, i zwykłe, skrypt pyta o te drugie po naprawie
  TMP-ów; źródła fontów dynamicznych są z tej listy odsiewane, bo poszły już
  razem ze swoim TMP-em.
- **Dorabianie liter z własnych glifów** (krok 2a) działa w dwóch przestrzeniach,
  ale z tymi samymi proporcjami co `font_fixer/fix_polish_fonts.py`: w plikach
  TTF (fonty dynamiczne, font fallback) na konturach, a w atlasach statycznych
  wprost na pikselach — kreska i kropka są wycinane z gotowych glifów (różnica
  `ó`−`o`, górka z `i`, albo samodzielne `´ ˙ ˛`), a ogonek i przekreślenie
  rysowane jako łańcuch okręgów, dzięki czemu wychodzą w tym samym trybie co
  atlas (pole SDF albo twarda bitmapa) i z tą samą rampą (spread = padding).
- **„Litery w innym rozmiarze" = font FALLBACK, nie błąd generatora.** Objaw:
  w napisie część polskich liter jest innego kroju, wyższa albo szersza od
  sąsiadów (w monospace widać to natychmiast — `[WYJDŹ]` w VCR OSD Mono, gdzie
  `Ź` przyszło z Intera: `advance` +33 % i wierzchołek 20 % wyżej). Dokładnie
  tak samo zachowuje się gra, gdy litery w foncie NIE MA — TextMeshPro sięga
  wtedy po `m_FallbackFontAssetTable` (a dalej po globalny fallback z TMP
  Settings), więc jedna litera renderuje się zupełnie innym fontem.
  Skąd się to brało u nas: kreska (`ć ń ó ś ź`) i kropka (`ż`) były wyłącznie
  **wycinane** z gotowych glifów, a krój zrobiony pod jedną grę (VCR OSD Mono,
  dogica, Lusitana, Electronic Highway Sign) nie ma ani jednego glifu
  z akcentem, ani `´`, ani znaku składającego — nie było z czego wyciąć, więc
  litera szła do obcego fallbacku albo w transliterację. Od teraz kreska
  i kropka są, jak ogonek i przekreślenie, **dorysowywane** z proporcji fontu
  (`make_acute` / `make_dot`, stałe `ACUTE_*` / `DOT_SYNTH_*` zmierzone na 343
  fontach systemowych), i to niezależnie od trybu z kroku 2a. Font fallback
  zostaje wyłącznie na przypadki bez litery bazowej.
  Sprawdzenie: `render_text_sample.py` wypisuje `FALLBACK` przy każdej takiej
  literze — jeśli raport go nie pokazuje, w grze nic nie będzie odstawać.
- **Tryb „nie pytaj więcej"** (`[5]` w menu naprawy) nie zapamiętuje fontu
  fallback, którego nigdy nie wybrałeś — wcześniej oznaczało to ciche zejście
  do transliteracji dla wszystkich kolejnych fontów. Po zmianie wyżej ma to
  znaczenie tylko dla liter bez litery bazowej w foncie.
  Po błędzie dorabiania `[5]` pomija bieżący font i włącza automat dla następnych,
  zamiast bez końca ponawiać tę samą nieudaną operację.
- **Biała szpara w belce `ł` albo wygryziony róg przy ogonku** = renderer
  wypełnia glif regułą **even-odd**, a litera i dorobiony znak to dwa nachodzące
  na siebie kontury (belka musi przeciąć laskę, ogonek wejść w spód litery, żeby
  się skleiły). Przy regule nonzero taki glif wygląda dobrze, przy even-odd
  część wspólna wypada jako dziura. Dlatego `font_fixer` scala oba kontury
  w jeden zarys (`union_ops`, biblioteka **skia-pathops**) — wynik jest
  identyczny w obu regułach. Bez `skia-pathops` skrypt wypisuje ostrzeżenie
  i zostawia stare, nachodzące kontury: `pip install skia-pathops`.
- **Nie oceniaj fontu dynamicznego po `m_CharacterTable`** — trzyma tylko to,
  co gra już kiedyś wyrenderowała, więc bywa prawie pusta. O tym, czy da się
  napisać po polsku, decyduje cmap źródłowego TTF.
- **Poprawiony TTF, ale stary kształt liter w grze:** dynamiczny TMP może mieć
  atlas wypieczony w buildzie (Fall of Porcupine: Lets Play, 99/82 zapisane znaki).
  Podmiana `m_FontData` zmienia tylko znaki generowane później. Do metadanych
  `dynamic_font_data` można dodać `clear_tmp_caches`: listę obiektów z `name`,
  `assets_rel`, opcjonalnie `serialized_name` i `path_id` jako podpowiedzią.
  `patch_fixed_fonts.install_dynamic()` weryfikuje powiązanie z TTF, czyści
  tablice znaków/glifów, kerning, stan pakowania i piksele czytelnego atlasu
  Alpha8. Zachowuje tryb dynamiczny, wskaźniki i materiały. Obsługuje pojedynczy
  atlas; inne warianty zgłaszają błąd fontu zamiast zgadywania. Czyszczenie działa
  również wtedy, gdy TTF już jest zgodny (naprawa po starszym importerze).
  Zwykłe `Font` dla UI Text nie wymagają tej opcji. Nie odtwarzaj atlasu przez
  przełączanie fontu statycznego na dynamiczny.
- Fonty CJK w formacie **CFF CID-keyed** (np. Source Han Sans) sięgają CID-em
  blisko limitu 65535 — nowe glify dostają numery z luk w numeracji, inaczej
  charset nie daje się skompilować.

### HEAVYWEIGHT i inne kroje wersalikowe: akcent obecny, lecz niewidoczny

W Inscryption font `HEAVYWEIGHT` ma dwa szczegóły, których nie wolno pomijać:

- **Korpus `Ó` jest niższy niż korpus `O`**, aby zmieścić kreskę w tej samej
  wysokości pisma. Cięcie atlasu na wysokości wierzchołka zwykłego `O`
  zostawiało tylko **2 z 24 pikseli wysokości kreski**. Odtworzone `ćńśź`
  miały więc ledwie widoczny pasek zamiast akcentu.
- **Małe `i` wygląda jak `I` i nie ma kropki.** Cięcie nad x-height brało
  jednopikselową górę laski za kropkę. W TTF analogicznym fałszywym dawcą
  były małe kontury tworzące chropowatą fakturę litery.

Naprawa we wspólnych narzędziach:

- `fix_tmp_polish_fonts.py` szuka rzeczywistej przerwy między akcentem
  a korpusem **tej samej litery dawcy**; zachowuje pełną kreskę i ustawia
  jej wysokość względem korpusu, który rzeczywiście był pod nią;
- kropka z `i/j` musi być oddzielona od laski; gdy jej nie ma, jest
  dorysowywana ze wspólnych proporcji kroju;
- `tools/font_fixer/fix_polish_fonts.py` stosuje analogiczną kontrolę
  oddzielnych pasm konturów dla TTF;
- odrzucane są odpryski o wysokości poniżej 2% em; w atlasie próg wynosi
  co najmniej 1 piksel, więc prawdziwa jednopikselowa kropka małego fontu
  bitmapowego pozostaje prawidłowym dawcą.

**Sama etykieta „złożona z własnych glifów” nie ocenia kształtu akcentu.**
Oglądaj złożony napis. Stary eksport, który ma już wadliwe glify w tabeli,
nie stanie się poprawny od samej aktualizacji generatora. Dla statycznego
TMP użyj `--replace-chars ćńśźżĆŃŚŹŻ`, wybierz właściwy font i wyeksportuj
go ponownie. TTF można odtworzyć z oryginalnego źródła; w już naprawionym
TTF jawne odtworzenie wymaga usunięcia mapowań tylko wskazanych znaków przed
wywołaniem `fix_polish_in_ttf()`. Nie usuwać dobrych `ó/Ó` — są dawcami kreski.

Regresje: `narzedzia/test_atlas_marks.py` obejmuje skompresowany korpus,
fałszywą kropkę z wersalika, szum konturów TTF i prawdziwą małą kropkę.

### Przekreślenie Ł ginie w grubej lasce albo wystaje tylko z jednej strony

W HEAVYWEIGHT atlas używał stałego zasięgu kreski `0.09 em` i zgadywał
środek laski z szerokości całego `L`. Kreska kończyła się niemal wewnątrz
pionowej części litery. TTF mierzył pierwszy odcinek tuszu, ale chropowata
faktura dzieliła prawdziwą laskę na drobne fragmenty — pierwszy z nich
nie był jej pełną grubością.

Obie ścieżki korzystają teraz ze wspólnego `stroke_geometry()` w
`tools/font_fixer/fix_polish_fonts.py`:

- pomiar pełnej laski na trzech pobliskich wysokościach;
- łączenie drobnych ubytków faktury do `0.015 em` i odrzucanie odległych
  odprysków przy wyborze głównego odcinka tuszu;
- środek kreski leży w zmierzonej lasce, a zasięg obejmuje połowę jej
  grubości **plus wystawkę z obu stron**;
- wąskie `l` może mieć laskę zajmującą całą szerokość glifu — dawny próg
  60% szerokości błędnie odrzucał taki prawidłowy pomiar;
- grubość, nachylenie i położenie wynikają ze wspólnych stałych `STROKE_*`.

Istniejące wadliwe `Ł/ł` w atlasie odtwórz jawnie przez
`--replace-chars Łł`. Przy naprawie TTF potrzebny jest `skia-pathops`,
aby scalić kreskę z laską bez dziury w miejscu przecięcia (patrz wyżej).
Po zmianie sprawdzaj napis również przy 24–32 px, nie tylko duży atlas.
Regresje są w `narzedzia/test_stroke_geometry.py`.

### Fonty bitmapowe (asset `Font` bez TTF-a)

UI Text / TextMesh potrafi renderować z fontu, który nie ma TTF-a (`m_FontData` puste),
tylko gotowy atlas i tabelę `m_CharacterRects` — typowo kopie „(Crisp)” fontów
pikselowych z filtrem Point. Skrypt listuje je osobno („Znalezione fonty bitmapowe”)
i naprawia po fontach TMP i TTF:

1. brakujące litery kopiuje z **bliźniaczego** fontu bitmapowego tej samej gry
   (ten sam `m_FontNames` i `m_FontSize`, a wszystkie wspólne glify identyczne co do
   piksela, `vert` i `advance`) — to oryginalny rysunek autora fontu,
2. resztę składa jak w atlasach TMP (kreska wycięta z `ó`, kropka z `i`, ogonek
   i przekreślenie dorysowane; przy atlasie 0/255 w trybie MONO), na końcu transliteracja,
3. nowe glify wstawia w wolne miejsce atlasu (gdy brak — podwaja wysokość
   i przelicza uv istniejących wpisów).

Atlas bywa podpięty przez `m_Texture` albo — przy kopiach „(Crisp)” — przez `_MainTex`
materiału `m_DefaultMaterial`. Glify z flagą `flipped` są w atlasie obrócone o 90°;
wycinanie (`bitmap_font_atlas.sample_glyph`) liczy narożniki tak jak
`UnityEngine.CharacterInfo`, więc obsługuje oba warianty. Podgląd napisu:
`fixed_preview/bitmap_<font>.png`.

Eksport: `<font>.json` typu `bitmap_font` (pełna nowa tabela `rects`, odcisk tabeli
sprzed naprawy `source_rects_sha`) + `<font>.png` (atlas top-down). Instalator
(`patch_fixed_fonts.install_bitmap`) wgrywa go tylko wtedy, gdy font w grze ma
dokładnie tę tabelę, z której robiony był eksport (albo już naszą — wtedy „już
zainstalowany”), a teksturę znajduje przez wskaźniki z drzewa W GRZE.
