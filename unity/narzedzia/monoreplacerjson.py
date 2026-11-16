import json
import os


def replace_sections_json(file1_path, file2_path, output_path):
    """
    Replace multiple sections in file1 (JSON) with those from file2 (JSON),
    BUT preserve m_Scale in m_FaceInfo from file1.
    """

    # Sprawdzenie czy pliki istnieją
    if not os.path.exists(file1_path) or not os.path.exists(file2_path):
        print("⚠ Error: One or both input files do not exist.")
        return

    # Read both JSON files
    with open(file1_path, 'r', encoding='utf-8') as f:
        file1_data = json.load(f)

    with open(file2_path, 'r', encoding='utf-8') as f:
        file2_data = json.load(f)

    # ===== PART 1: Replace m_FaceInfo (with m_Scale preservation) =====
    if 'm_FaceInfo' in file2_data:
        # KROK 1: Zapamiętaj m_Scale z file1, jeśli istnieje
        preserved_scale = None
        if 'm_FaceInfo' in file1_data and 'm_Scale' in file1_data['m_FaceInfo']:
            preserved_scale = file1_data['m_FaceInfo']['m_Scale']

        # KROK 2: Nadpisz całą sekcję danymi z file2
        file1_data['m_FaceInfo'] = file2_data['m_FaceInfo']

        # KROK 3: Przywróć m_Scale z file1 do nowej sekcji
        if preserved_scale is not None:
            file1_data['m_FaceInfo']['m_Scale'] = preserved_scale
            print(f"✓ Replaced m_FaceInfo (Preserved m_Scale: {preserved_scale})")
        else:
            print("✓ Replaced m_FaceInfo (No m_Scale found in target to preserve)")

    else:
        print("⚠ m_FaceInfo not found in source file")

    # ===== PART 2: Replace m_GlyphTable =====
    if 'm_GlyphTable' in file2_data:
        file1_data['m_GlyphTable'] = file2_data['m_GlyphTable']
        print("✓ Replaced m_GlyphTable")
    else:
        print("⚠ m_GlyphTable not found in source file")

    # ===== PART 3: Replace m_CharacterTable =====
    if 'm_CharacterTable' in file2_data:
        file1_data['m_CharacterTable'] = file2_data['m_CharacterTable']
        print("✓ Replaced m_CharacterTable")
    else:
        print("⚠ m_CharacterTable not found in source file")

    # ===== PART 4: Replace m_UsedGlyphRects =====
    if 'm_UsedGlyphRects' in file2_data:
        file1_data['m_UsedGlyphRects'] = file2_data['m_UsedGlyphRects']
        print("✓ Replaced m_UsedGlyphRects")
    else:
        print("⚠ m_UsedGlyphRects not found in source file")

    # ===== PART 5: Replace m_FreeGlyphRects =====
    if 'm_FreeGlyphRects' in file2_data:
        file1_data['m_FreeGlyphRects'] = file2_data['m_FreeGlyphRects']
        print("✓ Replaced m_FreeGlyphRects")
    else:
        print("⚠ m_FreeGlyphRects not found in source file")

    # ===== PART 6: Replace m_CreationSettings fields =====
    creation_settings_fields = [
        'pointSizeSamplingMode',
        'pointSize',
        'padding',
        'paddingMode',
        'packingMode',
        'atlasWidth',
        'atlasHeight',
        'characterSetSelectionMode',
        'characterSequence',
    ]

    if 'm_CreationSettings' in file1_data and 'm_CreationSettings' in file2_data:
        for field in creation_settings_fields:
            if field in file2_data['m_CreationSettings']:
                file1_data['m_CreationSettings'][field] = file2_data['m_CreationSettings'][field]
        print(f"✓ Replaced m_CreationSettings fields")
    else:
        print("⚠ m_CreationSettings not found in one or both files")

    # ===== PART 7: Replace m_fontInfo (legacy) =====
    if 'm_fontInfo' in file2_data:
        file1_data['m_fontInfo'] = file2_data['m_fontInfo']
        print("✓ Replaced m_fontInfo (legacy)")
    else:
        print("⚠ m_fontInfo not found in source file")

    # ===== PART 8: Replace m_AtlasWidth and m_AtlasHeight =====
    if 'm_AtlasWidth' in file2_data:
        file1_data['m_AtlasWidth'] = file2_data['m_AtlasWidth']
        print("✓ Replaced m_AtlasWidth")

    if 'm_AtlasHeight' in file2_data:
        file1_data['m_AtlasHeight'] = file2_data['m_AtlasHeight']
        print("✓ Replaced m_AtlasHeight")

    # Write the result
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(file1_data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Success! Output written to: {output_path}")


# Usage example:
if __name__ == "__main__":
    # Upewnij się, że nazwy plików są poprawne
    replace_sections_json(
        file1_path="file1.json",
        file2_path="file2.json",
        output_path="output.json"
    )