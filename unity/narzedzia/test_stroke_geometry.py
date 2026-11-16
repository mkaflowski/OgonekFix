"""The ł/Ł stroke must cross the actual stem, including in rough/all-caps fonts."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fix_tmp_polish_fonts as fx


def box(x0, y0, x1, y1):
    return [("moveTo", ((x0, y0),)), ("lineTo", ((x1, y0),)),
            ("lineTo", ((x1, y1),)), ("lineTo", ((x0, y1),)),
            ("closePath", ())]


def l_shape():
    points = [(20, 0), (90, 0), (90, 12), (65, 12), (65, 120), (20, 120)]
    return [("moveTo", (points[0],))] + [("lineTo", (p,)) for p in points[1:]] + [("closePath", ())]


def bitmap_l(rough=False):
    image = np.zeros((128, 78), dtype=np.uint8)
    image[4:124, 4:49] = 255  # stem x=20..65, baseline y=0
    image[112:124, 4:74] = 255  # foot x=20..90
    if rough:
        image[4:108, 5:7] = 0  # a hole after a one-pixel sliver of the stem
    return {"sdf": image, "cell_w": 78, "cell_h": 128,
            "inner": (4, 4, 70, 120), "empty": False,
            "metrics": {"width": 70, "height": 120, "bearing_x": 20,
                        "bearing_y": 120, "advance": 100}}


class StrokeGeometryTest(unittest.TestCase):
    def assert_crosses_stem(self, left, right, stem_left=20, stem_right=65):
        self.assertLessEqual(left, stem_left - 7)
        self.assertGreaterEqual(right, stem_right + 7)

    def test_bitmap_stroke_extends_beyond_both_sides_of_heavy_stem(self):
        for upper in (True, False):
            with self.subTest(upper=upper):
                circles = fx._stroke_circles(bitmap_l(), 160, upper)
                self.assert_crosses_stem(circles[0][0], circles[-1][0])

    def test_rough_outline_uses_whole_stem_not_first_fleck(self):
        ops = l_shape() + box(21, 15, 23, 115)
        result = fx.accent_composer.make_stroke((20, 0, 90, 120), 160, True,
                                                stem=1, base_ops=ops)
        bb = fx.accent_composer.bbox(result)
        self.assert_crosses_stem(bb[0], bb[2])

    def test_narrow_lowercase_stem_can_fill_its_entire_bounds(self):
        result = fx.accent_composer.make_stroke((20, 0, 38, 120), 160, False,
                                                stem=1, base_ops=box(20, 0, 38, 120))
        bb = fx.accent_composer.bbox(result)
        self.assert_crosses_stem(bb[0], bb[2], 20, 38)

    def test_bitmap_and_outline_share_stroke_position_and_reach(self):
        for upper in (True, False):
            with self.subTest(upper=upper):
                circles = fx._stroke_circles(bitmap_l(rough=True), 160, upper)
                ops = fx.accent_composer.make_stroke((20, 0, 90, 120), 160, upper,
                    stem=1, base_ops=l_shape() + box(21, 15, 23, 115))
                pts = [args[0] for op, args in ops if op in ("moveTo", "lineTo")]
                self.assertAlmostEqual(circles[0][0], pts[0][0], delta=1)
                self.assertAlmostEqual(circles[-1][0], pts[1][0], delta=1)
                self.assertAlmostEqual(circles[0][1], (pts[0][1] + pts[3][1]) / 2, delta=1)
                self.assertAlmostEqual(circles[-1][1], (pts[1][1] + pts[2][1]) / 2, delta=1)

    @unittest.skipUnless(fx.accent_composer.pathops, "requires skia-pathops")
    def test_union_keeps_stroke_overlap_filled_for_even_odd_renderers(self):
        a = fx.accent_composer
        base = l_shape()
        stroke = a.make_stroke((20, 0, 90, 120), 160, True, base_ops=base)
        merged = a.union_ops(base + list(a.orient_like(stroke, base)), 160, True)
        runs = a.ink_runs_at_y([a.flatten_contour(c) for c in a.split_contours(merged)],
                              a.STROKE_Y_UPPER * 120)
        # A separate overlapping bar would cut a hole in the middle of the stem
        # with the even-odd fill rule used by some renderers.
        self.assertEqual(len(runs), 1)
        self.assertAlmostEqual(runs[0][0], 20, delta=1)
        self.assertAlmostEqual(runs[0][1], 65, delta=1)


if __name__ == "__main__":
    unittest.main()
