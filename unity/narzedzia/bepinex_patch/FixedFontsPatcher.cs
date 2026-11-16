// Szkielet BepInEx (IL2CPP) - laduje fixed_fonts/ (ten sam format co
// patch_fixed_fonts.py) w runtime, zamiast patchowac binarnie resources.assets.
//
// STATUS: NIEPRZETESTOWANE. Patrz README.md w tym folderze - w szczegolnosci
// sekcja "Otwarty problem: dynamic_font_data" (tego typu fontow ten kod NIE
// patchuje, tylko loguje ostrzezenie) i "Namespace interop" (dokladne typy
// zaleza od tego, jak BepInEx wygenerowal interop-assemblies dla danej gry).
//
// Co robi:
//   1. Przy starcie gry czyta fixed_fonts/*.json obok wlasnego .dll.
//   2. Dla kazdego "static_atlas": znajduje zaladowany TMP_FontAsset o
//      pasujacej nazwie (Resources.FindObjectsOfTypeAll), podmienia atlas
//      (Texture2D z PNG) i tabele znakow/glifow z tmp_tree w JSON-ie.
//   3. Dla "dynamic_font_data": tylko ostrzega - patrz README.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using BepInEx;
using BepInEx.Logging;
using Newtonsoft.Json.Linq;
using UnityEngine;
using TMPro;

namespace FixedFontsPatcher
{
    [BepInPlugin("unitytranslator.fixedfontspatcher", "FixedFonts Runtime Patcher", "0.1.0")]
    public class FixedFontsPlugin : BasePlugin
    {
        internal static ManualLogSource Log;

        public override void Load()
        {
            Log = base.Log;
            string pluginDir = Path.GetDirectoryName(typeof(FixedFontsPlugin).Assembly.Location);
            string fixedFontsDir = Path.Combine(pluginDir, "fixed_fonts");

            if (!Directory.Exists(fixedFontsDir))
            {
                Log.LogWarning($"Brak folderu {fixedFontsDir} - nic do zrobienia.");
                return;
            }

            // Fonty w typowym Unity sa juz zaladowane, zanim wystartuje
            // pierwsza scena gry - ale zeby miec pewnosc, ze docelowy
            // TMP_FontAsset juz istnieje w pamieci, najprosciej odpalic to
            // po zaladowaniu pierwszej sceny, nie w Load() pluginu.
            // BepInEx IL2CPP: podepnij sie pod SceneManager.sceneLoaded albo
            // - najprosciej do testu - pod Update() pierwszej klatki.
            // Tu, dla przejrzystosci szkieletu, wolamy synchronicznie od razu;
            // jesli fonty jeszcze nie sa zaladowane, ZNAJDZ_I_PATCHUJ nic nie
            // zrobi (0 dopasowan) - do zweryfikowania w konkretnej grze.
            ApplyFixedFonts(fixedFontsDir);
        }

        static void ApplyFixedFonts(string fixedFontsDir)
        {
            var jsonFiles = Directory.GetFiles(fixedFontsDir, "*.json");
            Log.LogInfo($"Znaleziono {jsonFiles.Length} plikow meta w {fixedFontsDir}");

            foreach (var jsonPath in jsonFiles)
            {
                JObject meta;
                try
                {
                    meta = JObject.Parse(File.ReadAllText(jsonPath));
                }
                catch (Exception e)
                {
                    Log.LogError($"Nie udalo sie sparsowac {jsonPath}: {e}");
                    continue;
                }

                string type = (string)meta["type"] ?? "static_atlas";
                string label = (string)meta["label"] ?? Path.GetFileNameWithoutExtension(jsonPath);

                try
                {
                    if (type == "static_atlas")
                    {
                        string pngPath = Path.ChangeExtension(jsonPath, ".png");
                        if (!File.Exists(pngPath))
                        {
                            Log.LogWarning($"Brak {pngPath} - pomijam {label}");
                            continue;
                        }
                        ApplyStaticAtlas(label, meta, pngPath);
                    }
                    else if (type == "dynamic_font_data")
                    {
                        // Patrz README.md - brak potwierdzonej sciezki API,
                        // zeby podmienic surowe bajty TTF dynamicznego fontu
                        // w runtime bez dotykania plikow gry.
                        Log.LogWarning(
                            $"{label}: typ dynamic_font_data nie jest jeszcze " +
                            "obslugiwany w runtime (patrz README.md) - pomijam.");
                    }
                    else
                    {
                        Log.LogWarning($"{label}: nieznany typ {type} - pomijam");
                    }
                }
                catch (Exception e)
                {
                    Log.LogError($"{label}: patch nie powiodl sie: {e}");
                }
            }
        }

        static void ApplyStaticAtlas(string label, JObject meta, string pngPath)
        {
            // Namierzanie po nazwie obiektu - odpowiednik "assets_rel" +
            // "tmp_path_id" z JSON-a (offsety w pliku .assets), ktore w
            // runtime nie maja zastosowania.
            var candidates = Resources.FindObjectsOfTypeAll<TMP_FontAsset>()
                .Where(f => f.name == label || f.name.StartsWith(label))
                .ToList();

            if (candidates.Count == 0)
            {
                Log.LogWarning(
                    $"{label}: nie znaleziono zaladowanego TMP_FontAsset o tej nazwie " +
                    "- font jeszcze nie zaladowany, albo nazwa w fixed_fonts/ " +
                    "nie zgadza sie z m_Name w tej wersji gry.");
                return;
            }

            var fontAsset = candidates[0];
            JObject tree = (JObject)meta["tmp_tree"];

            // 1. Atlas: PNG (grayscale, jak przy eksporcie Pythonem) -> Texture2D.
            byte[] png = File.ReadAllBytes(pngPath);
            int atlasW = (int)meta["atlas_w"];
            int atlasH = (int)meta["atlas_h"];
            var tex = new Texture2D(atlasW, atlasH, TextureFormat.Alpha8, false);
            if (!ImageConversion.LoadImage(tex, png))
            {
                Log.LogError($"{label}: ImageConversion.LoadImage nie powiodlo sie");
                return;
            }
            // Eksport Pythonem zapisuje PNG top-down (Image.fromarray), ale
            // patch_fixed_fonts.py przy binarnym patchu robi np.flipud() przed
            // zapisem "image data" (Unity trzyma tekstury bottom-up) - tu
            // ladujemy przez ImageConversion, ktore samo obsluguje orientacje
            // PNG, WIEC TO FLIPOWANIE MOZE BYC ZBEDNE ALBO ODWROTNE.
            // DO ZWERYFIKOWANIA WIZUALNIE W GRZE.

            // TMP_FontAsset trzyma tablice atlasow (SDF moze miec wiecej niz
            // jeden przy przepelnieniu) - tu zakladamy pojedynczy atlas [0],
            // tak jak przy eksporcie/patchu Pythonem.
            if (fontAsset.atlasTextures != null && fontAsset.atlasTextures.Length > 0)
            {
                fontAsset.atlasTextures[0] = tex;
            }
            else
            {
                Log.LogError($"{label}: fontAsset.atlasTextures jest puste - nie mam gdzie wstawic atlasu");
                return;
            }

            if (fontAsset.material != null)
            {
                fontAsset.material.mainTexture = tex;
                var gradientScale = meta["gradient_scale"];
                if (gradientScale != null && gradientScale.Type != JTokenType.Null)
                {
                    fontAsset.material.SetFloat("_GradientScale", (float)gradientScale);
                }
            }

            // 2. Character/Glyph table - z m_CharacterTable/m_GlyphTable w
            //    tmp_tree (surowy zrzut UnityPy read_typetree, patrz
            //    tools/font_fixer/unity/fix_tmp_polish_fonts.py).
            //    TMP_Glyph/TMP_Character to publiczne klasy w nowszych TMPro
            //    - DOKLADNE nazwy pol/konstruktorow SPRAWDZ w
            //    Il2CppTextMeshPro.dll (moga sie roznic miedzy wersjami TMPro).
            var glyphTable = new List<TMP_Glyph>();
            foreach (var g in (JArray)tree["m_GlyphTable"])
            {
                var glyph = new TMP_Glyph
                {
                    index = (uint)g["m_GlyphIndex"],
                    // m_GlyphRect w typetree to zazwyczaj {m_X, m_Y, m_Width, m_Height}
                };
                // TODO: przepisac pelna geometrie (rect, metrics, scale) z g["m_GlyphRect"]
                // i g["m_Metrics"] - pominiete w tym szkielecie, bo dokladny
                // ksztalt zalezy od wersji TMPro (TMP_Glyph vs Glyph w nowszych).
                glyphTable.Add(glyph);
            }

            Log.LogWarning(
                $"{label}: podmiana atlasu/materialu zrobiona, ALE przepisanie " +
                "pelnej character/glyph table z tmp_tree NIE jest tu dokonczone " +
                "(patrz TODO w kodzie) - potrzebne dopisanie mapowania na " +
                "typ Glyph/TMP_Character z konkretnej wersji TMPro tej gry.");

            fontAsset.ReadFontAssetDefinition();
            Log.LogInfo($"{label}: atlas podmieniony ({atlasW}x{atlasH})");
        }
    }
}
