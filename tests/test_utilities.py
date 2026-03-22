"""
Tests for utility functions across multiple modules:
- scraper_context_fetcher.py: extract_code_block
- metadata_fetcher.py: sanitize_generated_code, default_metadata_extraction
- tag_audiobook_files_opus_3.py: get_track_number, get_chapter_title_from_text
- convert_audio_to_opus_3.py: normalize_audio
"""
import os
import re
import tempfile
import unittest


# === extract_code_block (scraper_context_fetcher.py) ===

def extract_code_block(response_text):
    pattern = r"```python\s*(.*?)\s*```"
    match = re.search(pattern, response_text, re.DOTALL)
    if match:
        return match.group(1)
    return response_text


class TestExtractCodeBlock(unittest.TestCase):
    def test_extracts_python(self):
        self.assertEqual(extract_code_block('Intro\n```python\nprint("hi")\n```\nOutro'),
                         'print("hi")')

    def test_no_fence_returns_original(self):
        text = "Just plain text."
        self.assertEqual(extract_code_block(text), text)

    def test_first_block_only(self):
        self.assertEqual(extract_code_block('```python\nfirst\n```\n```python\nsecond\n```'), "first")

    def test_multiline(self):
        result = extract_code_block('```python\nimport os\nprint(os.getcwd())\n```')
        self.assertIn("import os", result)
        self.assertIn("print(os.getcwd())", result)

    def test_non_python_ignored(self):
        text = '```javascript\nconsole.log("hi")\n```'
        self.assertEqual(extract_code_block(text), text)


# === sanitize_generated_code (metadata_fetcher.py) ===

def sanitize_generated_code(code):
    lines = code.split("\n")
    cleaned = []
    for line in lines:
        if "sys.stdin" in line or "input(" in line:
            cleaned.append(f"    # [Auto-Removed Blocking Input]: {line.strip()}")
            cleaned.append("    pass")
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


class TestSanitizeCode(unittest.TestCase):
    def test_removes_input(self):
        result = sanitize_generated_code('x = input("val")\nprint(x)')
        # The original input line should only appear in the comment
        self.assertIn("pass", result)
        self.assertIn("print(x)", result)

    def test_removes_stdin(self):
        result = sanitize_generated_code('data = sys.stdin.read()\nprocess(data)')
        self.assertIn("pass", result)
        self.assertIn("process(data)", result)

    def test_clean_code_unchanged(self):
        code = 'import os\nprint("hello")'
        self.assertEqual(sanitize_generated_code(code), code)

    def test_multiple_blocking(self):
        code = 'a = input("a")\nb = input("b")\nprint(a, b)'
        self.assertEqual(sanitize_generated_code(code).count("pass"), 2)


# === default_metadata_extraction (metadata_fetcher.py) ===

try:
    from bs4 import BeautifulSoup
    BS4 = True
except ImportError:
    BS4 = False


def default_metadata_extraction(html, url):
    soup = BeautifulSoup(html, "html.parser")
    data = {"title": "Unknown Title", "author": "Unknown Author",
            "description": "", "cover_url": ""}
    og_title = soup.find("meta", property="og:title")
    if og_title:
        data["title"] = og_title.get("content", "").replace("– Dobytranslations", "").strip()
    else:
        h1 = soup.select_one("h1.entry-title")
        if h1:
            data["title"] = h1.get_text(strip=True)
    og_image = soup.find("meta", property="og:image")
    if og_image:
        data["cover_url"] = og_image.get("content", "")
    og_desc = soup.find("meta", property="og:description")
    if og_desc:
        data["description"] = og_desc.get("content", "")
    return data


@unittest.skipUnless(BS4, "beautifulsoup4 not installed")
class TestMetadataExtraction(unittest.TestCase):
    def test_og_title(self):
        html = '<html><head><meta property="og:title" content="My Novel" /></head></html>'
        self.assertEqual(default_metadata_extraction(html, "")["title"], "My Novel")

    def test_strips_doby(self):
        html = '<html><head><meta property="og:title" content="Novel – Dobytranslations" /></head></html>'
        self.assertEqual(default_metadata_extraction(html, "")["title"], "Novel")

    def test_h1_fallback(self):
        html = '<html><body><h1 class="entry-title">Fallback</h1></body></html>'
        self.assertEqual(default_metadata_extraction(html, "")["title"], "Fallback")

    def test_cover_url(self):
        html = '<html><head><meta property="og:image" content="http://img.com/c.jpg" /></head></html>'
        self.assertEqual(default_metadata_extraction(html, "")["cover_url"], "http://img.com/c.jpg")

    def test_description(self):
        html = '<html><head><meta property="og:description" content="Great story." /></head></html>'
        self.assertEqual(default_metadata_extraction(html, "")["description"], "Great story.")

    def test_defaults(self):
        result = default_metadata_extraction("<html><body></body></html>", "")
        self.assertEqual(result["title"], "Unknown Title")
        self.assertEqual(result["author"], "Unknown Author")


# === get_track_number (tag_audiobook_files_opus_3.py) ===

def get_track_number(filename):
    matches = re.findall(r"(\d+)", filename)
    return int(matches[-1]) if matches else None


class TestGetTrackNumber(unittest.TestCase):
    def test_standard(self):
        self.assertEqual(get_track_number("ch_0042.opus"), 42)

    def test_multiple_numbers(self):
        self.assertEqual(get_track_number("vol_02_ch_0015.opus"), 15)

    def test_no_numbers(self):
        self.assertIsNone(get_track_number("prologue.opus"))

    def test_simple(self):
        self.assertEqual(get_track_number("track7.opus"), 7)


# === get_chapter_title_from_text (tag_audiobook_files_opus_3.py) ===

def get_chapter_title_from_text(track_num, text_dir):
    if not text_dir or not os.path.exists(text_dir):
        return None
    txt_path = os.path.join(text_dir, f"ch_{track_num:04d}.txt")
    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                return first_line if first_line else None
        except Exception:
            pass
    return None


class TestGetChapterTitle(unittest.TestCase):
    def test_reads_first_line(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "ch_0001.txt"), "w") as f:
                f.write("Chapter 1 - Start\n\nBody.")
            self.assertEqual(get_chapter_title_from_text(1, d), "Chapter 1 - Start")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(get_chapter_title_from_text(999, d))

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "ch_0002.txt"), "w") as f:
                f.write("")
            self.assertIsNone(get_chapter_title_from_text(2, d))

    def test_bad_dir(self):
        self.assertIsNone(get_chapter_title_from_text(1, "/nonexistent"))


# === normalize_audio (convert_audio_to_opus_3.py) ===

class MockAudio:
    def __init__(self, dbfs):
        self._dbfs = dbfs
        self.gain_applied = 0

    @property
    def dBFS(self):
        return self._dbfs

    def apply_gain(self, gain):
        new = MockAudio(self._dbfs + gain)
        new.gain_applied = gain
        return new


def normalize_audio(sound, target_dbfs):
    if sound.dBFS == float("-inf"):
        return sound
    return sound.apply_gain(target_dbfs - sound.dBFS)


class TestNormalizeAudio(unittest.TestCase):
    def test_quiet_boosted(self):
        self.assertAlmostEqual(normalize_audio(MockAudio(-30.0), -20.0).gain_applied, 10.0)

    def test_loud_reduced(self):
        self.assertAlmostEqual(normalize_audio(MockAudio(-10.0), -20.0).gain_applied, -10.0)

    def test_at_target(self):
        self.assertAlmostEqual(normalize_audio(MockAudio(-20.0), -20.0).gain_applied, 0.0)

    def test_silent_unchanged(self):
        audio = MockAudio(float("-inf"))
        self.assertIs(normalize_audio(audio, -20.0), audio)


if __name__ == "__main__":
    unittest.main()
