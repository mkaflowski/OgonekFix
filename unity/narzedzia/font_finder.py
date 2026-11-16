import UnityPy
import os

# Rozszerzenia plików czcionek do wykrywania
FONT_EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2', '.fon', '.fnt'}


def get_object_name(data):
    """
    Try to get the name of an object from various possible attributes
    """
    if hasattr(data, 'm_Name') and data.m_Name:
        return data.m_Name
    elif hasattr(data, 'name') and data.name:
        return data.name
    elif hasattr(data, 'm_GameObject'):
        try:
            game_object = data.m_GameObject.read()
            if hasattr(game_object, 'm_Name'):
                return game_object.m_Name
        except:
            pass
    return None


def find_standalone_fonts(folder_path):
    """
    Find standalone font files (TTF, OTF, WOFF, etc.) in folder
    """
    font_files = []

    for root, dirs, files in os.walk(folder_path):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in FONT_EXTENSIONS:
                full_path = os.path.join(root, file)
                relative_path = os.path.relpath(full_path, folder_path)
                file_size = os.path.getsize(full_path)
                font_files.append({
                    'name': file,
                    'path': relative_path,
                    'full_path': full_path,
                    'extension': ext,
                    'size': file_size
                })

    return font_files


def format_size(size_bytes):
    """Format file size in human readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def analyze_unity_file(file_path):
    """
    Analyze a single Unity asset/bundle file
    Returns: (has_fonts, has_sdf, font_list, sdf_list, extractable_fonts)
    """
    font_objects = []
    sdf_objects = []
    extractable_fonts = []  # Fonts with embedded TTF data

    try:
        env = UnityPy.load(file_path)

        for obj in env.objects:
            try:
                data = obj.read()
                object_type = obj.type.name
                obj_name = get_object_name(data)

                # Check if it's a font
                if object_type == "Font":
                    font_info = obj_name if obj_name else "unnamed"
                    font_objects.append(font_info)

                    # Check if font has embedded TTF data
                    if hasattr(data, 'm_FontData') and data.m_FontData:
                        font_data = data.m_FontData
                        if isinstance(font_data, bytes) and len(font_data) > 0:
                            extractable_fonts.append({
                                'name': obj_name if obj_name else 'unnamed',
                                'object': obj,
                                'data': data,
                                'size': len(font_data)
                            })

                # Check if it's Texture2D with "sdf" or "atlas" in name (TMP font textures)
                if object_type == "Texture2D" and obj_name:
                    name_lower = obj_name.lower()
                    if "sdf" in name_lower or "atlas" in name_lower:
                        size_info = ""
                        if hasattr(data, 'm_Width') and hasattr(data, 'm_Height'):
                            size_info = f" [{data.m_Width}x{data.m_Height}]"
                        sdf_objects.append(f"{obj_name}{size_info}")

                # Check if it's MonoBehaviour with m_FaceInfo (TextMeshPro font asset)
                if object_type == "MonoBehaviour":
                    try:
                        raw = obj.read_typetree()
                        if raw and "m_FaceInfo" in raw:
                            face_info = raw["m_FaceInfo"]
                            family = face_info.get("m_FamilyName", "?")
                            style = face_info.get("m_StyleName", "?")
                            point_size = face_info.get("m_PointSize", "?")
                            version = raw.get("m_Version", "?")
                            mono_name = raw.get("m_Name", obj_name or "unnamed")
                            sdf_objects.append(
                                f"{mono_name} [TMP FontAsset: {family} {style}, {point_size}pt, v{version}]"
                            )
                    except:
                        pass

            except:
                continue

    except Exception as e:
        return False, False, [], [], []

    has_fonts = len(font_objects) > 0
    has_sdf = len(sdf_objects) > 0

    return has_fonts, has_sdf, font_objects, sdf_objects, extractable_fonts


def extract_font(font_info, output_folder):
    """
    Extract embedded font data to a TTF file
    """
    try:
        data = font_info['data']
        font_data = data.m_FontData

        if not font_data or len(font_data) == 0:
            return False, "No font data found"

        # Determine file extension based on magic bytes
        ext = '.ttf'
        if font_data[:4] == b'OTTO':
            ext = '.otf'
        elif font_data[:4] == b'wOFF':
            ext = '.woff'
        elif font_data[:4] == b'wOF2':
            ext = '.woff2'

        # Create safe filename
        safe_name = "".join(c for c in font_info['name'] if c.isalnum() or c in '._- ')
        if not safe_name:
            safe_name = 'extracted_font'

        output_path = os.path.join(output_folder, f"{safe_name}{ext}")

        # Handle duplicate filenames
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(output_folder, f"{safe_name}_{counter}{ext}")
            counter += 1

        with open(output_path, 'wb') as f:
            f.write(font_data)

        return True, output_path

    except Exception as e:
        return False, str(e)



def scan_single_file(file_path):
    """
    Analyze a single Unity asset file directly (not a folder scan)
    """
    print(f"\nScanning single file: {file_path}")
    print("=" * 80)

    ext = os.path.splitext(file_path)[1].lower()
    standalone_fonts = []

    if ext in FONT_EXTENSIONS:
        file_size = os.path.getsize(file_path)
        standalone_fonts.append({
            'name': os.path.basename(file_path),
            'path': file_path,
            'full_path': file_path,
            'extension': ext,
            'size': file_size
        })
        print(f"\n✓ File is a standalone font: {os.path.basename(file_path)} ({format_size(file_size)})")
        return {
            'standalone_fonts': standalone_fonts,
            'files_with_fonts': [],
            'files_with_sdf': [],
            'all_extractable': [],
            'folder_path': os.path.dirname(file_path)
        }

    print(f"\nAnalyzing as Unity asset...")
    has_fonts, has_sdf, font_list, sdf_list, extractable = analyze_unity_file(file_path)

    files_with_fonts = []
    files_with_sdf = []
    all_extractable = []

    if has_fonts:
        files_with_fonts.append((file_path, font_list))
        print(f"\n✓ Found {len(font_list)} Font object(s):")
        for font_name in font_list:
            print(f"   └─ {font_name}")
        if extractable:
            print(f"📦 {len(extractable)} font(s) with extractable TTF data:")
            for ext_font in extractable:
                print(f"   └─ {ext_font['name']} ({format_size(ext_font['size'])})")
                all_extractable.append({'file_path': file_path, 'font_info': ext_font})

    if has_sdf:
        files_with_sdf.append((file_path, sdf_list))
        print(f"\n✓ Found {len(sdf_list)} SDF / TMP FontAsset object(s):")
        for sdf_name in sdf_list:
            print(f"   └─ {sdf_name}")

    if not has_fonts and not has_sdf:
        print("✗ No fonts or SDF/TMP FontAsset objects found in this file.")

    print("\n" + "=" * 80)

    return {
        'standalone_fonts': standalone_fonts,
        'files_with_fonts': files_with_fonts,
        'files_with_sdf': files_with_sdf,
        'all_extractable': all_extractable,
        'folder_path': os.path.dirname(file_path)
    }


def scan_folder(folder_path):
    """
    Scan folder for all files and try to analyze them as Unity assets
    Returns scan results for potential extraction
    """
    if not os.path.exists(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        return None

    if not os.path.isdir(folder_path):
        if os.path.isfile(folder_path):
            return scan_single_file(folder_path)
        print(f"Error: Path is not a folder or file: {folder_path}")
        return None

    print(f"\nScanning folder: {folder_path}")
    print("=" * 80)

    # First, find standalone font files
    print("\n[Phase 1] Searching for standalone font files (TTF, OTF, WOFF, etc.)...")
    standalone_fonts = find_standalone_fonts(folder_path)

    if standalone_fonts:
        print(f"\n✓ Found {len(standalone_fonts)} standalone font file(s):")
        for font in standalone_fonts:
            print(f"   └─ {font['path']} ({font['extension']}, {format_size(font['size'])})")
    else:
        print("   No standalone font files found.")

    # Then scan Unity assets
    print("\n[Phase 2] Scanning Unity asset files...")
    print("-" * 80)

    all_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            # Skip standalone font files (already processed)
            ext = os.path.splitext(file)[1].lower()
            if ext not in FONT_EXTENSIONS:
                full_path = os.path.join(root, file)
                all_files.append(full_path)

    if not all_files:
        print("No other files found to check.")
        return {
            'standalone_fonts': standalone_fonts,
            'files_with_fonts': [],
            'files_with_sdf': [],
            'all_extractable': []
        }

    print(f"Found {len(all_files)} files to check.\n")

    files_with_fonts = []
    files_with_sdf = []
    all_extractable = []
    skipped_files = 0
    unity_files_count = 0

    for idx, file_path in enumerate(all_files, 1):
        relative_path = os.path.relpath(file_path, folder_path)
        print(f"[{idx}/{len(all_files)}] Checking: {relative_path}", end=" ")

        has_fonts, has_sdf, font_list, sdf_list, extractable = analyze_unity_file(file_path)

        if not has_fonts and not has_sdf:
            try:
                env = UnityPy.load(file_path)
                if not list(env.objects):
                    print("- Skipped (not a Unity asset)")
                    skipped_files += 1
                    continue
                else:
                    print("- No fonts or SDF textures")
                    unity_files_count += 1
            except:
                print("- Skipped (not a Unity asset)")
                skipped_files += 1
                continue
        else:
            unity_files_count += 1

        if has_fonts:
            files_with_fonts.append((relative_path, font_list))
            print(f"\n  ✓ Found {len(font_list)} Font object(s):")
            for font_name in font_list:
                print(f"     └─ {font_name}")

            if extractable:
                print(f"  📦 {len(extractable)} font(s) with extractable TTF data:")
                for ext_font in extractable:
                    print(f"     └─ {ext_font['name']} ({format_size(ext_font['size'])})")
                    all_extractable.append({
                        'file_path': relative_path,
                        'font_info': ext_font
                    })

        if has_sdf:
            files_with_sdf.append((relative_path, sdf_list))
            print(f"\n  ✓ Found {len(sdf_list)} SDF / TMP FontAsset object(s):")
            for sdf_name in sdf_list:
                print(f"     └─ {sdf_name}")

        if has_fonts or has_sdf:
            print()

    # Print final summary
    print("=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)

    print(f"\nStandalone font files: {len(standalone_fonts)}")
    print(f"Total files checked: {len(all_files)}")
    print(f"Files skipped (not Unity assets): {skipped_files}")
    print(f"Unity asset files analyzed: {unity_files_count}")
    print(f"Files with Font objects: {len(files_with_fonts)}")
    print(f"Files with SDF / TMP FontAsset objects: {len(files_with_sdf)}")
    print(f"Extractable embedded fonts: {len(all_extractable)}")

    # Standalone fonts list
    if standalone_fonts:
        print("\n" + "=" * 80)
        print("STANDALONE FONT FILES:")
        print("-" * 80)
        for font in standalone_fonts:
            print(f"   📄 {font['path']} ({font['extension']}, {format_size(font['size'])})")

    # Unity Font objects
    print("\n" + "=" * 80)
    print("UNITY FONT OBJECTS:")
    print("-" * 80)
    if files_with_fonts:
        for file_path, font_list in files_with_fonts:
            print(f"\n📁 {file_path}")
            for font_name in font_list:
                print(f"   └─ {font_name}")
    else:
        print("✗ No Unity Font objects found")

    # SDF textures + TMP FontAssets
    print("\n" + "=" * 80)
    print("SDF TEXTURE2D / TMP FONTASSET OBJECTS:")
    print("-" * 80)
    if files_with_sdf:
        for file_path, sdf_list in files_with_sdf:
            print(f"\n📁 {file_path}")
            for sdf_name in sdf_list:
                print(f"   └─ {sdf_name}")
    else:
        print("✗ No SDF Texture2D or TMP FontAsset objects found")

    print("\n" + "=" * 80)

    return {
        'standalone_fonts': standalone_fonts,
        'files_with_fonts': files_with_fonts,
        'files_with_sdf': files_with_sdf,
        'all_extractable': all_extractable,
        'folder_path': folder_path
    }


def perform_extraction(scan_results):
    """
    Extract all extractable fonts to a folder
    """
    if not scan_results or not scan_results.get('all_extractable'):
        print("No extractable fonts found.")
        return

    extractable = scan_results['all_extractable']
    base_folder = scan_results['folder_path']

    # Ask for output folder
    default_output = os.path.join(base_folder, "extracted_fonts")
    print(f"\nDefault output folder: {default_output}")
    output_folder = input("Enter output folder (or press Enter for default): ").strip()

    if not output_folder:
        output_folder = default_output

    output_folder = output_folder.strip('"').strip("'")

    # Create output folder
    os.makedirs(output_folder, exist_ok=True)

    print(f"\nExtracting {len(extractable)} font(s) to: {output_folder}")
    print("-" * 80)

    success_count = 0
    fail_count = 0

    for item in extractable:
        font_info = item['font_info']
        source_file = item['file_path']

        print(f"Extracting '{font_info['name']}' from {source_file}...", end=" ")

        success, result = extract_font(font_info, output_folder)

        if success:
            print(f"✓ Saved to: {os.path.basename(result)}")
            success_count += 1
        else:
            print(f"✗ Failed: {result}")
            fail_count += 1

    print("-" * 80)
    print(f"Extraction complete: {success_count} succeeded, {fail_count} failed")

    if success_count > 0:
        print(f"Fonts saved to: {output_folder}")


def main():
    print("=" * 80)
    print("Unity Asset Font Scanner")
    print("Scans for:")
    print("  • Standalone font files (TTF, OTF, WOFF, WOFF2)")
    print("  • Unity Font objects (with embedded TTF extraction)")
    print("  • SDF Texture2D objects (TextMeshPro)")
    print("  • MonoBehaviour with m_FaceInfo (TMP FontAsset)")
    print("=" * 80)

    while True:
        folder_path = input("\nEnter the path to folder or file (or 'quit' to exit): ").strip()

        if folder_path.lower() in ['quit', 'exit', 'q']:
            print("Exiting program. Goodbye!")
            break

        folder_path = folder_path.strip('"').strip("'")

        if not folder_path:
            print("No path entered. Please try again.")
            continue

        # Scan the folder
        scan_results = scan_folder(folder_path)

        if scan_results is None:
            continue

        # Ask about extraction if there are extractable fonts
        if scan_results.get('all_extractable'):
            print("\n" + "=" * 80)
            extractable_count = len(scan_results['all_extractable'])
            print(f"Found {extractable_count} font(s) with embedded TTF/OTF data that can be extracted.")

            extract_choice = input("Do you want to extract them? (y/n): ").strip().lower()

            if extract_choice in ['y', 'yes', 'tak', 't']:
                perform_extraction(scan_results)
            else:
                print("Extraction skipped.")

        print("\n" + "=" * 80)

        # Ask if user wants to scan another folder
        another = input("Scan another folder? (y/n): ").strip().lower()
        if another not in ['y', 'yes', 'tak', 't']:
            print("Exiting program. Goodbye!")
            break


if __name__ == "__main__":
    main()