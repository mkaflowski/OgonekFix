# fixed_fonts/ przez BepInEx (runtime), zamiast binarnego patcha

Szkielet pluginu BepInEx (IL2CPP), ktory czyta te same `fixed_fonts/*.json`
(+`.png`/`.ttf`) co `patch_fixed_fonts.py`, ale zamiast dopisywac dane binarnie
do `resources.assets`, podmienia je **w pamieci** przy starcie gry.

**Status: nieprzetestowane.** Nikt tego jeszcze nie odpalil na zadnej grze -
nie ma tu srodowiska BepInEx do weryfikacji. Traktuj to jako punkt startowy,
nie gotowe rozwiazanie. Ponizej jest jasno rozdzielone co jest pewne (to samo
robi juz dzialajacy `patch_fixed_fonts.py`, tylko czytane inaczej), a co jest
zgadywanka wymagajaca sprawdzenia w konkretnej grze.

## Dlaczego to w ogole ma sens

- **Odwracalne bez ryzyka**: BepInEx nie dotyka plikow gry - wszystko siedzi
  w `BepInEx/plugins/`. Usuniecie folderu = gra wraca do oryginalu. Zaden
  `resources.assets` nigdy nie jest nadpisywany, wiec znika caly temat z tej
  rozmowy o `PermissionError`/`os.replace`/wolnym `write_value` w UnityPy -
  to sa problemy WYLACZNIE binarnego patchowania na dysku.
- Koszt: dodatkowa instalacja (BepInEx + ten plugin) zamiast samego pliku
  `Polish.csv` + spatchowanych assetow.

## Co jest reuzywalne z fixed_fonts/ 1:1, a co nie

| typ w JSON            | dane wejsciowe        | reuzywalne przy BepInEx?                                  |
|------------------------|------------------------|-------------------------------------------------------------|
| `dynamic_font_data`    | `.ttf`                 | Dane tak, ale **brak potwierdzonej sciezki API** zeby podmienic `m_FontData` dynamicznego fontu w runtime (patrz sekcja "Otwarty problem" nizej). |
| `static_atlas`         | `.png` + `tmp_tree` w JSON | Dane tak - `tmp_tree["m_CharacterTable"]`/`m_GlyphTable"]` to surowy zrzut pol `TMP_FontAsset`, ktore w nowszych TMPro sa publiczne (`characterTable`, `glyphTable`). Ten kod ponizej implementuje wlasnie ta sciezke. |

`path_id`/`assets_rel` z JSON-a (uzywane przez UnityPy do namierzenia obiektu
w pliku `.assets`) **nie maja tu zastosowania** - w runtime szukamy obiektu po
`label`/nazwie (`TMP_FontAsset.name`), nie po offsetach w pliku.

## Otwarty problem: dynamic_font_data (.ttf) w runtime

Statyczny patch podmienia `m_FontData` (surowe bajty TTF) na obiekcie `Font`,
z ktorego TMPro dynamicznie generuje atlas SDF w locie w silniku (natywny
kod C++, nie C#). To pole nie jest wystawione w publicznym API `UnityEngine.Font`
- nie widac go przez zwykla refleksje, bo serializacja/import fontu dzieje sie
w silniku, nie w zarzadzanym kodzie. Nie znalazlem potwierdzonej, czystej
sciezki zeby to zrobic w runtime bez dotykania plikow gry.

Realne opcje do sprawdzenia (zadna nie jest tu zaimplementowana):
1. `Font.CreateDynamicFontFromOSFont` - wymaga zainstalowanej czcionki w
   systemie (nie surowych bajtow TTF), wiec trzeba by ja najpierw
   zainstalowac w OS-ie przy starcie gry (mozliwe, ale brudne).
2. Zbudowanie WLASNEGO `TMP_FontAsset` od zera z pliku `.ttf` przez
   `TMP_FontAsset.CreateFontAsset(Font, ...)` i podmiana WSZYSTKICH miejsc,
   ktore odwoluja sie do oryginalnego fontu (nie tylko jednego obiektu) -
   duzo wiecej roboty i ryzyka niespojnosci niz przy static_atlas.
3. Fallback pozostajemy przy static_atlas: mozna wygenerowac bitmapowy/SDF
   atlas Pythonem (tak jak dzis) i zaladowac go w runtime jak nizej, zamiast
   robic prawdziwy dynamiczny font.

W tym szkielecie **dynamic_font_data jest pomijany z ostrzezeniem** - patrz
`FixedFontsPatcher.cs`.

## Wymagania / setup

1. Zainstalowany BepInEx (IL2CPP) dla docelowej gry - pierwsze uruchomienie
   gry z BepInEx generuje interop-assemblies w
   `BepInEx/interop/*.dll` (m.in. `Il2Cppmscorlib.dll`,
   `Il2CppUnityEngine.CoreModule.dll`, `Il2CppTextMeshPro.dll` albo podobnie
   nazwany - dokladna nazwa zalezy od wersji Unity/TMPro w grze).
2. .NET SDK (do budowania pluginu) - `dotnet build`.
3. W `FixedFontsPatcher.csproj` ustaw `GameInteropDir` na folder z tymi
   wygenerowanymi DLL-kami (patrz komentarz w pliku .csproj) - referencje sa
   per-gra, wiec **plugin trzeba przebudowac dla kazdej gry** (tak samo jak
   `patch_fixed_fonts.py` per-gra generuje typetree z jej `GameAssembly.dll`,
   tylko tu robi to kompilator zamiast robic to w locie).
4. Skopiuj `fixed_fonts/` (z `tools/font_fixer/unity/fixed_fonts/` albo z folderu
   gry z `game_specific/unity/<gra>/fixed_fonts/`) obok skompilowanego
   `FixedFontsPatcher.dll` w `BepInEx/plugins/`.

## Namespace interop

Ponizszy kod zaklada namespace `TMPro`/`UnityEngine` tak jak po
wygenerowaniu przez **Il2CppInterop** (nowszy standard, uzywany przez
BepInEx 6 IL2CPP). Starsze `Il2CppAssemblyUnhollower` tez zwykle zachowuje
oryginalny namespace, ale typy kolekcji (`List<T>` vs
`Il2CppSystem.Collections.Generic.List<T>`) i sygnatury moga sie roznic -
**do zweryfikowania na konkretnym BepInEx po wygenerowaniu interop**.
