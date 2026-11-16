"""Regression tests for accents in all-caps and compressed display fonts."""
import copy
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fix_tmp_polish_fonts as fx


def glyph(image, bearing_y, padding=4):
    h, w = image.shape
    return {
        "sdf": image,
        "cell_w": w,
        "cell_h": h,
        "empty": False,
        "inner": (padding, padding, w - 2 * padding, h - 2 * padding),
        "metrics": {"width": w - 2 * padding, "height": h - 2 * padding,
                    "bearing_x": 0, "bearing_y": bearing_y, "advance": w},
    }


class AtlasMarksTest(unittest.TestCase):
    def test_full_acute_is_copied_when_donor_body_is_compressed(self):
        # Like HEAVYWEIGHT: accent + compressed O barely exceeds plain O.
        # Cutting at the plain letter's top preserves only two accent rows.
        base = np.zeros((104, 80), dtype=np.uint8)
        base[4:100, 4:76] = 255
        donor = np.zeros_like(base)
        donor[24:100, 4:76] = 255
        donor[4:20, 36:44] = 255
        glyphs = {1: glyph(base, 100), 2: glyph(donor, 102)}
        chars = [(ord("o"), 1), (ord("ó"), 2), (ord("c"), 1)]
        _, composed, missing, _ = fx.compose_marks_from_glyphs(
            chars, glyphs, [ord("ć")], 4, point_size=120,
            render_mode=4122, quiet=True)
        self.assertEqual(missing, [])
        result = composed[fx.COMPOSED_GLYPH_OFFSET + ord("ć")]
        top = fx._glyph_origin(result)[1]
        rows_above_base = int(round(top - 100))
        mark_ink = fx._ink_bbox(result["sdf"][:rows_above_base], fx.INK_LEVEL)
        self.assertIsNotNone(mark_ink)
        self.assertEqual(mark_ink[3] - mark_ink[2], 16)

    def test_capital_I_is_not_a_dot_donor(self):
        image = np.zeros((104, 30), dtype=np.uint8)
        image[4:100, 4:26] = 255
        self.assertIsNone(fx._cut_mark_above(glyph(image, 100), 99))

    def test_one_pixel_dot_in_small_bitmap_is_kept(self):
        image = np.zeros((14, 8), dtype=np.uint8)
        image[3, 4] = 255
        image[7:13, 4] = 255
        mark = fx._cut_mark_above(glyph(image, 11, padding=1), 6)
        self.assertIsNotNone(mark)
        bbox = fx._ink_bbox(mark["field"], fx.INK_LEVEL)
        self.assertEqual((bbox[1] - bbox[0], bbox[3] - bbox[2]), (1, 1))

    def test_dot_is_synthesized_when_lowercase_i_is_a_capital(self):
        image = np.zeros((104, 40), dtype=np.uint8)
        image[4:100, 4:36] = 255
        base = glyph(image, 99)
        capital_i = copy.deepcopy(base)
        capital_i["metrics"]["bearing_y"] = 100
        chars = [(ord("z"), 1), (ord("i"), 2)]
        _, glyphs, missing, _ = fx.compose_marks_from_glyphs(
            chars, {1: base, 2: capital_i}, [ord("ż")], 4,
            point_size=120, render_mode=4122, quiet=True)
        self.assertEqual(missing, [])
        result = glyphs[fx.COMPOSED_GLYPH_OFFSET + ord("ż")]
        rows_above_base = int(round(fx._glyph_origin(result)[1] - 99))
        bbox = fx._ink_bbox(result["sdf"][:rows_above_base], fx.INK_LEVEL)
        self.assertIsNotNone(bbox)
        self.assertGreater(bbox[3] - bbox[2], 2)


def box_ops(x0, y0, x1, y1):
    return [("moveTo", ((x0, y0),)), ("lineTo", ((x1, y0),)),
            ("lineTo", ((x1, y1),)), ("lineTo", ((x0, y1),)),
            ("closePath", ())]


class OutlineGlyph:
    def __init__(self, ops):
        self.ops = ops

    def draw(self, pen):
        fx.accent_composer.replay(self.ops, pen)


class OutlineMarksTest(unittest.TestCase):
    def test_compressed_outline_donor_uses_full_accent_not_roughness(self):
        gs = {"o": OutlineGlyph(box_ops(0, 0, 100, 800)),
              "oacute": OutlineGlyph(box_ops(0, 0, 100, 700)
                                      + box_ops(25, 720, 55, 810)
                                      + box_ops(48, 799, 52, 808))}
        cmap = {ord("o"): "o", ord("ó"): "oacute"}
        ops, reference = fx.accent_composer.find_mark(gs, cmap, "acute", 1000, 800)
        bounds = fx.accent_composer.bbox(ops)
        self.assertEqual(bounds[3] - bounds[1], 90)
        self.assertEqual(reference, 700)

    def test_rough_capital_outline_is_not_a_dot_donor(self):
        gs = {"i": OutlineGlyph(box_ops(0, 0, 100, 810)
                                 + box_ops(40, 780, 45, 795))}
        self.assertIsNone(fx.accent_composer.find_mark(
            gs, {ord("i"): "i"}, "dot", 1000, 800))

    def test_real_outline_dot_is_kept(self):
        gs = {"i": OutlineGlyph(box_ops(0, 0, 100, 500)
                                 + box_ops(30, 560, 80, 610))}
        mark = fx.accent_composer.find_mark(gs, {ord("i"): "i"}, "dot", 1000, 500)
        self.assertIsNotNone(mark)
        bounds = fx.accent_composer.bbox(mark[0])
        self.assertEqual((bounds[2] - bounds[0], bounds[3] - bounds[1]), (50, 50))


if __name__ == "__main__":
    unittest.main()
