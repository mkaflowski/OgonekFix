"""Regresje wyszukiwania zasobow fontow: bez generatora i bez zgadywania path_id."""

import copy
from types import SimpleNamespace
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import patch_fixed_fonts as F


def obj(file, pid, type_name, name, tree=None):
    value = SimpleNamespace(assets_file=file, path_id=pid,
                            type=SimpleNamespace(name=type_name))
    value.parse_monobehaviour_head = Mock(return_value=SimpleNamespace(m_Name=name))
    value.read = Mock(return_value=SimpleNamespace(m_Name=name))
    value.tree = tree or {}
    value.read_typetree = Mock(side_effect=lambda: copy.deepcopy(value.tree))

    def save(tree):
        value.tree = copy.deepcopy(tree)

    value.save_typetree = Mock(side_effect=save)
    file.objects[pid] = value
    return value


def ptr(pid, file_id=0):
    return {'m_FileID': file_id, 'm_PathID': pid}


def material_tree(texture, file_id=0):
    return {'m_SavedProperties': {
        'm_TexEnvs': [('_MainTex', {'m_Texture': ptr(texture, file_id)})],
        'm_Floats': [('_TextureWidth', 512.0), ('_TextureHeight', 512.0),
                     ('_GradientScale', 6.0), ('_FaceDilate', 0.2)]}}


class FontResourceTests(unittest.TestCase):
    def setUp(self):
        self.file = SimpleNamespace(name='main.assets', objects={})
        self.gf = F.GameFiles('.', '.')
        self.env = SimpleNamespace(objects=[])
        self.gf.env = Mock(return_value=self.env)

    def test_monobehaviour_name_never_generates_script_tree(self):
        font = obj(self.file, 1, 'MonoBehaviour', 'Known font')
        font.read.side_effect = AssertionError('Full MonoBehaviour read invoked')
        self.assertEqual(F.object_name(font), 'Known font')
        font.read.assert_not_called()
        font.read_typetree.assert_not_called()

    def test_name_index_reused_and_serialized_file_precedes_old_id(self):
        other = SimpleNamespace(name='other.assets', objects={})
        wrong = obj(other, 7, 'MonoBehaviour', 'Font')
        right = obj(self.file, 99, 'MonoBehaviour', 'Font')
        self.env.objects = [wrong, right]
        for _ in range(2):
            self.assertIs(self.gf.find('data.unity3d', 'Font', 'MonoBehaviour', 7, 'main.assets'), right)
        wrong.parse_monobehaviour_head.assert_called_once()
        right.parse_monobehaviour_head.assert_called_once()

    def test_same_name_materials_selected_by_live_atlas_not_stale_id(self):
        font = obj(self.file, 10, 'MonoBehaviour', 'Font')
        obj(self.file, 20, 'Texture2D', 'Atlas')
        obj(self.file, 21, 'Texture2D', 'Other atlas')
        target = obj(self.file, 30, 'Material', 'Duplicate', material_tree(20))
        wrong = obj(self.file, 31, 'Material', 'Duplicate', material_tree(21))
        self.env.objects = list(self.file.objects.values())
        meta = {'atlas_w': 1024, 'atlas_h': 512, 'padding': 5, 'materials': [
            {'assets_rel': 'data.unity3d', 'name': 'Duplicate', 'path_id': 31}]}
        tree = {'m_AtlasTextures': [ptr(20)]}
        self.assertTrue(F.patch_static_materials(self.gf, meta, font, tree))
        self.assertEqual(dict(target.tree['m_SavedProperties']['m_Floats'])['_TextureWidth'], 1024)
        self.assertEqual(dict(target.tree['m_SavedProperties']['m_Floats'])['_FaceDilate'], 0.2)
        wrong.save_typetree.assert_not_called()
        self.assertFalse(F.patch_static_materials(self.gf, meta, font, tree))
        target.save_typetree.assert_called_once()

    def test_external_atlas_and_bitmap_preserve_gradient(self):
        external = SimpleNamespace(name='atlas.assets', objects={})
        self.file.externals = [SimpleNamespace(path='archive:/atlas.assets')]
        self.file.parent = SimpleNamespace(files={'atlas.assets': external})
        font = obj(self.file, 10, 'MonoBehaviour', 'Font')
        obj(external, 20, 'Texture2D', 'Atlas')
        mat = obj(self.file, 30, 'Material', 'Material', material_tree(20, 1))
        self.env.objects = list(self.file.objects.values()) + list(external.objects.values())
        meta = {'atlas_w': 1024, 'atlas_h': 1024, 'padding': 1, 'gradient_scale': None,
                'materials': [{'assets_rel': 'data.unity3d', 'name': 'Material'}]}
        self.assertTrue(F.patch_static_materials(self.gf, meta, font, {'atlas': ptr(20, 1)}))
        floats = dict(mat.tree['m_SavedProperties']['m_Floats'])
        self.assertEqual(floats['_TextureHeight'], 1024)
        self.assertEqual(floats['_GradientScale'], 6)

    def test_unrelated_material_is_not_patched(self):
        font = obj(self.file, 10, 'MonoBehaviour', 'Font')
        obj(self.file, 20, 'Texture2D', 'Atlas')
        obj(self.file, 21, 'Texture2D', 'Other atlas')
        mat = obj(self.file, 30, 'Material', 'Material', material_tree(21))
        self.env.objects = list(self.file.objects.values())
        meta = {'atlas_w': 1024, 'atlas_h': 512, 'padding': 5,
                'materials': [{'assets_rel': 'data.unity3d', 'name': 'Material'}]}
        with self.assertRaisesRegex(RuntimeError, 'powiazanego z atlasem'):
            F.patch_static_materials(self.gf, meta, font, {'m_AtlasTextures': [ptr(20)]})
        mat.save_typetree.assert_not_called()
        self.assertFalse(self.gf.modified)

    def dynamic_fixture(self):
        source = obj(self.file, 1, 'Font', 'Source',
                     {'m_Name': 'Source', 'm_FontData': b'current-ttf'})
        font = obj(self.file, 10, 'MonoBehaviour', 'Dynamic', {
            'm_Name': 'Dynamic', 'm_AtlasPopulationMode': 1,
            'm_SourceFontFile': ptr(1), 'm_Script': ptr(999),
            'm_AtlasTextures': [ptr(20)], 'material': ptr(30),
            'm_AtlasTextureIndex': 0, 'm_AtlasWidth': 16, 'm_AtlasHeight': 16,
            'm_AtlasRenderMode': 4165, 'm_FaceInfo': {'m_PointSize': 42},
            'm_GlyphTable': [{'m_Index': 8}],
            'm_CharacterTable': [{'m_Unicode': ord('z'), 'm_GlyphIndex': 8}],
            'm_UsedGlyphRects': [{'m_X': 1, 'm_Y': 1, 'm_Width': 8, 'm_Height': 8}],
            'm_FreeGlyphRects': [],
            'm_FontFeatureTable': {'m_GlyphPairAdjustmentRecords': [{'old': 1}]},
            'm_KerningTable': {'kerningPairs': []},
        })
        atlas = obj(self.file, 20, 'Texture2D', 'Atlas', {
            'm_IsReadable': True, 'm_TextureFormat': 1, 'm_MipCount': 1,
            'm_Width': 16, 'm_Height': 16, 'm_CompleteImageSize': 256,
            'image data': b'', 'm_StreamData': {'offset': 100, 'size': 256, 'path': 'old.resS'},
        })
        material = obj(self.file, 30, 'Material', 'Material', material_tree(20))
        self.env.objects = list(self.file.objects.values())
        meta = {'label': 'Dynamic', 'font_name': 'Source', 'font_path_id': 1,
                'font_assets_rel': 'data.unity3d', 'clear_tmp_caches': [
                    {'name': 'Dynamic', 'assets_rel': 'data.unity3d', 'path_id': 999}]}
        return source, font, atlas, material, meta

    def test_same_ttf_still_clears_stale_cache_and_second_install_is_noop(self):
        source, font, atlas, material, meta = self.dynamic_fixture()
        original_tree = copy.deepcopy(font.tree)
        with tempfile.TemporaryDirectory() as folder:
            ttf_path = os.path.join(folder, 'font.ttf')
            with open(ttf_path, 'wb') as stream:
                stream.write(b'current-ttf')
            F.install_dynamic(self.gf, meta, ttf_path)
            self.assertEqual(font.tree['m_CharacterTable'], [])
            self.assertEqual(font.tree['m_GlyphTable'], [])
            self.assertEqual(font.tree['m_UsedGlyphRects'], [])
            self.assertEqual(font.tree['m_FreeGlyphRects'], [
                {'m_X': 0, 'm_Y': 0, 'm_Width': 15, 'm_Height': 15}])
            self.assertEqual(font.tree['m_FontFeatureTable']['m_GlyphPairAdjustmentRecords'], [])
            for key in ('m_SourceFontFile', 'm_AtlasTextures', 'material', 'm_Script',
                        'm_AtlasPopulationMode', 'm_FaceInfo'):
                self.assertEqual(font.tree[key], original_tree[key])
            self.assertEqual(atlas.tree['image data'], bytes(256))
            self.assertEqual(atlas.tree['m_StreamData'], {'offset': 0, 'size': 0, 'path': ''})
            self.gf.modified.clear()
            F.install_dynamic(self.gf, meta, ttf_path)
        font.save_typetree.assert_called_once()
        atlas.save_typetree.assert_called_once()
        source.save_typetree.assert_not_called()
        material.save_typetree.assert_not_called()
        self.assertFalse(self.gf.modified)

    def test_cache_must_reference_actual_source_font_not_just_same_path_id(self):
        source, font, atlas, material, meta = self.dynamic_fixture()
        other = SimpleNamespace(name='other.assets', objects={})
        obj(other, 1, 'Font', 'Other source')
        self.file.externals = [SimpleNamespace(path='archive:/other.assets')]
        self.file.parent = SimpleNamespace(files={'other.assets': other})
        font.tree['m_SourceFontFile'] = ptr(1, 1)
        with self.assertRaisesRegex(RuntimeError, 'innego zrodlowego TTF'):
            F.clear_dynamic_tmp_caches(self.gf, meta, source)
        font.save_typetree.assert_not_called()
        atlas.save_typetree.assert_not_called()

    def test_static_or_unreadable_font_is_never_converted_to_dynamic(self):
        source, font, atlas, material, meta = self.dynamic_fixture()
        font.tree['m_AtlasPopulationMode'] = 0
        with self.assertRaisesRegex(RuntimeError, 'tylko w dynamicznym TMP'):
            F.clear_dynamic_tmp_caches(self.gf, meta, source)
        font.tree['m_AtlasPopulationMode'] = 1
        atlas.tree['m_IsReadable'] = False
        with self.assertRaisesRegex(RuntimeError, 'czytelnego atlasu Alpha8'):
            F.clear_dynamic_tmp_caches(self.gf, meta, source)
        font.save_typetree.assert_not_called()
        atlas.save_typetree.assert_not_called()

    def test_plain_ui_font_does_not_touch_tmp_assets(self):
        source, font, atlas, material, meta = self.dynamic_fixture()
        del meta['clear_tmp_caches']
        self.assertEqual(F.clear_dynamic_tmp_caches(self.gf, meta, source), 0)
        font.read_typetree.assert_not_called()
        atlas.read_typetree.assert_not_called()


if __name__ == '__main__':
    unittest.main()
