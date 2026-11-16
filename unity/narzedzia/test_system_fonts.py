"""Dopasowanie fontu gry do fontu zainstalowanego w systemie (system_fonts.find)
i pobieranie prawdziwych polskich glifow (add_real_glyphs_from_ttf)."""
import io
import os
import sys
import unittest
from pathlib import Path

UNITY_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, UNITY_DIR)
import system_fonts as sf  # noqa: E402


def fake(family, style, full=None, ps="", user=False, stem=None):
    return sf.SystemFont(Path(f"{stem or family + '-' + style}.ttf"), 0, family, style,
                         full or (family if style == "Regular" else f"{family} {style}"), ps, user)


class FindTests(unittest.TestCase):
    def setUp(self):
        self._old = sf._INDEX
        sf._INDEX = [fake("Arial", "Regular"), fake("Arial", "Bold", ps="Arial-BoldMT"),
                     fake("Arial Black", "Regular"), fake("Arial Narrow", "Regular"),
                     fake("Liberation Sans", "Regular")]

    def tearDown(self):
        sf._INDEX = self._old

    def names(self, *args, **kw):
        return [c.full_name for c in sf.find(*args, **kw)]

    def test_noise_words_are_ignored(self):
        self.assertEqual(self.names("Arial SDF", "Arial", "Regular"), ["Arial"])
        self.assertEqual(self.names("LiberationSans SDF - Fallback"), ["Liberation Sans"])

    def test_style_selects_the_right_face(self):
        self.assertEqual(self.names("Arial Bold SDF", "Arial", "Bold"), ["Arial Bold"])

    def test_no_substring_matches(self):
        self.assertEqual(self.names("Arial SDF", "Arial", "Regular"), ["Arial"])
        self.assertEqual(self.names("Ari SDF", "Ari"), [])
        self.assertEqual(self.names("Arial Black SDF", "Arial Black", "Regular"), ["Arial Black"])

    def test_unknown_font_has_no_candidates(self):
        self.assertEqual(self.names("FOT-RodinNTLGPro-DB SDF", "FOT-RodinNTLGPro-DB"), [])


class UserFontsTests(unittest.TestCase):
    def setUp(self):
        self._old = sf._INDEX
        sf._INDEX = [fake("Arial", "Regular"),
                     fake("Arial", "Regular", full="Arial (moj)", user=True, stem="ArialMoj"),
                     fake("Super Font", "Regular", user=True, stem="Inter")]

    def tearDown(self):
        sf._INDEX = self._old

    def test_user_font_comes_first(self):
        hits = sf.find("Arial SDF", "Arial", "Regular")
        self.assertEqual([h.full_name for h in hits], ["Arial (moj)", "Arial"])
        self.assertTrue(hits[0].user)

    def test_user_file_name_counts_as_font_name(self):
        self.assertEqual([h.full_name for h in sf.find("Inter SDF")], ["Super Font"])

    def test_system_file_name_does_not(self):
        sf._INDEX = [fake("Super Font", "Regular", stem="Inter")]
        self.assertEqual(sf.find("Inter SDF"), [])

    def test_menu_refs_only_contain_user_fonts(self):
        refs = sf.user_font_refs()
        self.assertEqual(sorted(r["name"] for r in refs), ["Arial (moj)", "Super Font"])
        self.assertTrue(all(r["local_sf"].user for r in refs))


class RealGlyphTests(unittest.TestCase):
    """Syntetyczny atlas bez polskich liter + font z polskimi literami."""

    @classmethod
    def setUpClass(cls):
        import fix_tmp_polish_fonts as fx
        cls.fx = fx
        win = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
        cands = [win, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                 Path("/usr/share/fonts/TTF/DejaVuSans.ttf")]
        cls.polish = next((p for p in cands if p.is_file()), None)

    def test_takes_only_chars_the_font_really_has(self):
        if self.polish is None:
            self.skipTest("brak systemowego fontu z polskimi znakami")
        fx = self.fx
        import freetype
        from fontTools.ttLib import TTFont
        from fontTools import subset
        font = TTFont(str(self.polish))
        opts = subset.Options()
        opts.notdef_outline = True
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=range(0x20, 0x7F))
        sub.subset(font)
        buf = io.BytesIO()
        font.save(buf)
        base = freetype.Face(io.BytesIO(buf.getvalue()))
        chars, glyphs, _ = fx.gen.collect_glyphs(base, list(range(0x20, 0x7F)), 48, 6)
        before = len(glyphs)
        missing = sorted(ord(c) for c in fx.PL_CHARS)

        taken, still = fx.add_real_glyphs_from_ttf(
            self.polish.read_bytes(), missing, chars, glyphs, 48, 6)
        self.assertEqual(sorted(taken), missing)
        self.assertEqual(still, [])
        self.assertGreater(len(glyphs), before)
        by_cp = dict(chars)
        for cp in missing:
            self.assertFalse(glyphs[by_cp[cp]].get("empty"), chr(cp))

        # font bez polskich znakow nic nie daje i nic nie psuje
        n = len(chars)
        taken, still = fx.add_real_glyphs_from_ttf(buf.getvalue(), missing, chars, glyphs, 48, 6)
        self.assertEqual(taken, [])
        self.assertEqual(still, missing)
        self.assertEqual(len(chars), n)


if __name__ == "__main__":
    unittest.main()
