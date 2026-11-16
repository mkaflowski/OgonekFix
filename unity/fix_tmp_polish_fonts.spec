# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = []
binaries = []
# fix_polish_fonts (font_fixer) i render_text_sample sa importowane po nazwie
# przez sys.path / leniwie w funkcji - statyczna analiza ich nie widzi
hiddenimports = ['fix_polish_fonts', 'render_text_sample', 'generate_tmp_sdf']

datas += collect_data_files('fontTools')
tmp_ret = collect_all('UnityPy')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_ret = collect_all('TypeTreeGeneratorAPI')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

tmp_ret = collect_all('freetype')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    ['fix_tmp_polish_fonts.py'],
    pathex=['..', 'narzedzia'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'tensorflow', 'scipy', 'pandas',
        'sklearn', 'transformers', 'onnxruntime', 'numba', 'llvmlite',
        'openpyxl', 'matplotlib',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='fix_tmp_polish_fonts',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
