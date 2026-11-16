import re


def replace_sections(file1_path, file2_path, output_path):
    """
    Replace multiple sections in file1 with those from file2:
    - FaceInfo section
    - UsedGlyphRects section
    - pointSizeSamplingMode section
    - FaceInfo_Legacy section
    - characterSequence value
    - m_PathID value

    Args:
        file1_path: Path to the first file (main content)
        file2_path: Path to the second file (source of replacements)
        output_path: Path where the result will be saved
    """

    # Read both files
    with open(file1_path, 'r', encoding='utf-8') as f:
        file1_content = f.read()

    with open(file2_path, 'r', encoding='utf-8') as f:
        file2_content = f.read()

    new_content = file1_content

    # ===== PART 1: Replace FaceInfo section =====
    start_marker1 = " 0 FaceInfo m_FaceInfo"
    end_marker1 = " 0 vector m_AtlasTextures"

    file1_start = new_content.find(start_marker1)
    file1_end = new_content.find(end_marker1)

    file2_start = file2_content.find(start_marker1)
    file2_end = file2_content.find(end_marker1)

    if file1_start == -1 or file1_end == -1:
        raise ValueError("Could not find FaceInfo section markers in file1")
    if file2_start == -1 or file2_end == -1:
        raise ValueError("Could not find FaceInfo section markers in file2")

    # Extract the section from file2 (including start marker, excluding end marker)
    file2_section1 = file2_content[file2_start:file2_end]

    # Replace in new_content
    new_content = (
            new_content[:file1_start] +
            file2_section1 +
            new_content[file1_end:]
    )

    print(f"✓ Replaced FaceInfo section ({len(file2_section1)} characters)")

    # ===== PART 2: Replace UsedGlyphRects section =====
    start_marker2 = " 0 GlyphRect m_UsedGlyphRects"
    end_marker2 = " 0 FaceInfo_Legacy m_fontInfo"

    file1_start = new_content.find(start_marker2)
    file1_end = new_content.find(end_marker2)

    file2_start = file2_content.find(start_marker2)
    file2_end = file2_content.find(end_marker2)

    if file1_start == -1 or file1_end == -1:
        raise ValueError("Could not find UsedGlyphRects section markers in file1")
    if file2_start == -1 or file2_end == -1:
        raise ValueError("Could not find UsedGlyphRects section markers in file2")

    # Extract the section from file2
    file2_section2 = file2_content[file2_start:file2_end]

    # Replace in new_content
    new_content = (
            new_content[:file1_start] +
            file2_section2 +
            new_content[file1_end:]
    )

    print(f"✓ Replaced UsedGlyphRects section ({len(file2_section2)} characters)")

    # ===== PART 3: Replace pointSizeSamplingMode section =====
    # Note: These fields are inside FontAssetCreationSettings with specific indentation
    start_marker3 = "\n  0 int pointSizeSamplingMode"
    end_marker3 = "\n  1 string referencedFontAssetGUID"

    file1_start = new_content.find(start_marker3)
    file1_end = new_content.find(end_marker3)

    file2_start = file2_content.find(start_marker3)
    file2_end = file2_content.find(end_marker3)

    if file1_start == -1 or file1_end == -1:
        raise ValueError("Could not find pointSizeSamplingMode section markers in file1")
    if file2_start == -1 or file2_end == -1:
        raise ValueError("Could not find pointSizeSamplingMode section markers in file2")

    # Extract the section from file2 (skip the leading newline we used for matching)
    file2_section3 = file2_content[file2_start:file2_end]

    # Replace in new_content
    new_content = (
            new_content[:file1_start] +
            file2_section3 +
            new_content[file1_end:]
    )

    print(f"✓ Replaced pointSizeSamplingMode section ({len(file2_section3)} characters)")

    # ===== PART 4: Replace FaceInfo_Legacy section =====
    start_marker4 = " 0 FaceInfo_Legacy m_fontInfo"
    end_marker4 = " 0 FontAssetCreationSettings m_CreationSettings"

    file1_start = new_content.find(start_marker4)
    file1_end = new_content.find(end_marker4)

    file2_start = file2_content.find(start_marker4)
    file2_end = file2_content.find(end_marker4)

    if file1_start == -1 or file1_end == -1:
        raise ValueError("Could not find FaceInfo_Legacy section markers in file1")
    if file2_start == -1 or file2_end == -1:
        raise ValueError("Could not find FaceInfo_Legacy section markers in file2")

    # Extract the section from file2
    file2_section4 = file2_content[file2_start:file2_end]

    # Replace in new_content
    new_content = (
            new_content[:file1_start] +
            file2_section4 +
            new_content[file1_end:]
    )

    print(f"✓ Replaced FaceInfo_Legacy section ({len(file2_section4)} characters)")

    # ===== PART 5: Replace characterSequence value =====
    pattern_charseq = r'(  1 string characterSequence = )"[^"]*"'

    match_file2 = re.search(pattern_charseq, file2_content)
    if not match_file2:
        raise ValueError("Could not find characterSequence in file2")

    file2_charseq_line = match_file2.group(0)

    match_file1 = re.search(pattern_charseq, new_content)
    if not match_file1:
        raise ValueError("Could not find characterSequence in file1")

    new_content = new_content.replace(match_file1.group(0), file2_charseq_line)

    file2_charseq_value = match_file2.group(0).split('"')[1]
    print(f"✓ Replaced characterSequence: {file2_charseq_value[:50]}...")

    # Write the result
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"\n✓ Success! Output written to: {output_path}")


# Usage example:
if __name__ == "__main__":
    replace_sections(
        file1_path="file1.txt",  # Your first file
        file2_path="file2.txt",  # Your second file
        output_path="output.txt"  # Where to save the result
    )