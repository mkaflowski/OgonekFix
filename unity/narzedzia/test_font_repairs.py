"""Regresje zapisu TTF, zaczepu Ą i limitów pakowania atlasu.

Uruchom: python -m unittest discover -s tools/font_fixer/unity/narzedzia -p test_font_repairs.py
"""
import copy
import io
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fix_tmp_polish_fonts as fx
import patch_fixed_fonts as installer


class FontRepairsTest(unittest.TestCase):
    def test_explicit_replacement_option_does_not_accept_plain_letters(self):
        opts = fx.parse_args(['game', '--auto', '--replace-chars', 'ąę'])
        self.assertEqual(opts.replace_chars, 'ąę')
        with self.assertRaises(SystemExit):
            fx.parse_args(['game', '--replace-chars', 'a'])
        with self.assertRaises(SystemExit):
            fx.parse_args(['game', '--replace-chars', 'ą', '--marks-only'])

    def test_ogonek_curves_left_then_finishes_to_the_right(self):
        image = np.zeros((60, 50), dtype=np.uint8)
        image[5:55, 30:40] = 255
        glyph = {'sdf': image, 'cell_w': 50, 'cell_h': 60, 'inner': (0, 0, 50, 60),
                 'metrics': {'bearing_x': 0, 'bearing_y': 55}}
        circles = fx._ogonek_circles(glyph, 100)
        self.assertLess(min(x for x, _, _ in circles), circles[0][0])
        self.assertGreater(circles[-1][0], circles[0][0])
        self.assertLess(circles[-1][1], circles[0][1])

    def test_installer_updates_material_dimensions_after_atlas_growth(self):
        assets = SimpleNamespace(name='test.bundle', objects={})
        class Obj:
            def __init__(self, tree, path_id=1, type_name='MonoBehaviour'):
                self.tree, self.path_id = tree, path_id
                self.assets_file = assets
                self.type = SimpleNamespace(name=type_name)
                assets.objects[path_id] = self
            def read_typetree(self):
                return copy.deepcopy(self.tree)
            def save_typetree(self, tree):
                self.tree = tree
        font = Obj({'m_Name': 'Test', 'm_GlyphTable': [],
                    'm_AtlasTextures': [{'m_FileID': 0, 'm_PathID': 2}],
                    'm_Script': {'m_FileID': 1, 'm_PathID': 77}})
        Obj({}, 2, 'Texture2D')
        material = Obj({'m_Name': 'Test Material', 'm_SavedProperties': {
            'm_TexEnvs': [('_MainTex', {'m_Texture': {'m_FileID': 0, 'm_PathID': 2}})],
            'm_Floats': [('_TextureWidth', 512.0), ('_TextureHeight', 512.0),
                         ('_GradientScale', 9.0)]}}, 3, 'Material')
        gf = SimpleNamespace(find=lambda path, name, kind, *args: font if kind == 'MonoBehaviour' else material,
                             named_objects=lambda path, name, kind: [material],
                             mark=lambda _: None)
        meta = {'label': 'Test', 'tmp_tree': {'m_Name': 'Test', 'm_GlyphTable': []},
                'assets_rel': 'test.bundle', 'tmp_path_id': 1, 'atlas_w': 1024, 'atlas_h': 512,
                'padding': 8, 'tex_path_id': 0, 'gradient_scale': 9,
                'materials': [{'assets_rel': 'test.bundle', 'name': 'Test Material', 'path_id': 3}]}
        installer.install_static(gf, meta, 'unused.png')
        values = dict(material.tree['m_SavedProperties']['m_Floats'])
        self.assertEqual(values['_TextureWidth'], 1024.0)
        self.assertEqual(values['_TextureHeight'], 512.0)
        self.assertEqual(font.tree['m_Script']['m_PathID'], 77)

    def test_float_advance_survives_ttf_save_and_reload(self):
        builder = FontBuilder(1000, isTTF=True)
        builder.setupGlyphOrder(['.notdef', 'A', 'Oacute'])
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((500, 0))
        pen.lineTo((250, 700))
        pen.closePath()
        box = TTGlyphPen(None)
        box.moveTo((0, 0))
        box.lineTo((400, 0))
        box.lineTo((400, 600))
        box.lineTo((0, 600))
        box.closePath()
        box_glyph = box.glyph()
        builder.setupGlyf({'.notdef': box_glyph, 'A': pen.glyph(),
                          'Oacute': copy.deepcopy(box_glyph)})
        builder.setupHorizontalMetrics({'.notdef': (600, 0), 'A': (600, 0), 'Oacute': (600, 0)})
        builder.setupHorizontalHeader(ascent=800, descent=-200)
        builder.setupCharacterMap({65: 'A', ord('O'): 'A', ord('Ó'): 'Oacute'})
        builder.setupNameTable({'familyName': 'Regression', 'styleName': 'Regular'})
        builder.setupOS2()
        builder.setupPost()
        font = builder.font
        ops = fx.accent_composer.record_glyph(font.getGlyphSet(), 'A')
        fx.accent_composer.add_glyph(font, 'Aogonek', ops, 902.0, 0.0, 'A')
        data = io.BytesIO()
        font.save(data)
        with TTFont(io.BytesIO(data.getvalue())) as restored:
            self.assertEqual(restored['hmtx']['Aogonek'], (902, 0))
            self.assertEqual(restored['hhea'].advanceWidthMax, 902)
        have, missing = fx.ttf_polish_coverage(data.getvalue(), 'OÓ')
        self.assertEqual((have, missing), ('O', 'Ó'))
        fixed, report = fx.fix_polish_in_ttf(data.getvalue(), missing)
        self.assertIsNotNone(fixed)
        self.assertFalse(report['plain'] or report['unfixable'])
        self.assertEqual(fx.ttf_polish_coverage(fixed, 'OÓ'), ('OÓ', ''))

    def test_ogonek_attaches_to_foot_not_sloping_side_of_A(self):
        # Prawa nóżka A leży poza starym limitem 80% szerokości.
        polys = [[(0, 0), (45, 100), (55, 100), (100, 0),
                  (90, 0), (50, 80), (10, 0)]]
        x, y = fx.accent_composer.find_attach(polys, (0, 0, 100, 100), 140)
        self.assertGreater(x, 80)
        self.assertLessEqual(y, 3)
        image = np.zeros((101, 101), dtype=np.uint8)
        for row in range(101):
            for left, right in fx.accent_composer.ink_runs_at_y(polys, 100 - row + 0.01):
                image[row, int(np.ceil(left)):int(np.ceil(right))] = 255
        g = {'sdf': image, 'cell_w': 101, 'cell_h': 101,
             'inner': (0, 0, 101, 101),
             'metrics': {'bearing_x': 0, 'bearing_y': 100}}
        px, py = fx._pixel_attach(g, 140)
        self.assertGreater(px, 80)
        self.assertLessEqual(py, 3)
        self.assertAlmostEqual(x, px, delta=2)

    def test_atlas_grows_other_axis_and_reports_actual_limit(self):
        glyphs = {i: {'cell_w': 8, 'cell_h': 8} for i in range(3)}
        w, h, positions, _ = fx.gen.pack_atlas(glyphs, 16, 8, True, max_size=16)
        self.assertEqual((w, h), (16, 16))
        rects = [(x, y, x + 8, y + 8) for x, y in positions.values()]
        for i, a in enumerate(rects):
            for b in rects[i + 1:]:
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0]
                                or a[3] <= b[1] or b[3] <= a[1])
        with self.assertRaisesRegex(SystemExit, 'maksymalny wymiar to 32'):
            fx.gen.pack_atlas({0: {'cell_w': 33, 'cell_h': 1}}, 32, 32, True, 32)

    def test_option_five_does_not_repeat_failed_repair(self):
        with patch.object(fx, 'AUTO_SYNTH', False), \
                patch.object(fx, 'fix_polish_in_ttf', return_value=(None, None)) as repair, \
                patch('builtins.input', side_effect=['5', '5']):
            self.assertIsNone(fx.fix_dynamic_font_ttf(None, [], b'broken', 'broken', 'ą'))
            self.assertEqual(repair.call_count, 1)
            self.assertTrue(fx.AUTO_SYNTH)

    def test_generator_uses_game_version_for_stripped_bundle(self):
        with patch.object(fx, '_GENERATOR', None), \
                patch.object(fx, '_GENERATOR_ERROR', None), \
                patch.object(fx.UnityPy.config, 'FALLBACK_UNITY_VERSION', '2021.3.45f1'), \
                patch.object(fx, 'patch_typetree_generator'), \
                patch.object(fx, 'find_dll_folder', return_value='Managed'), \
                patch('os.path.exists', return_value=False), \
                patch('UnityPy.helpers.TypeTreeGenerator.TypeTreeGenerator') as generator:
            fx.get_generator('game', 'data', '0.0.0')
            generator.assert_called_once_with('2021.3.45f1')


if __name__ == '__main__':
    unittest.main()
