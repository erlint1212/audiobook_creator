"""Tests for scraper_2.py — parse_chapter_title, clean_body_text"""
import re
import unittest


def parse_chapter_title(raw_title):
    raw_title = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", raw_title)
    stripped = re.sub(r"(?i)^volume\s+\d+\s*,\s*", "", raw_title).strip()
    m = re.match(r"(?i)^chapter\s+(\d+)\s*[–—\-:]\s*(.+)$", stripped)
    if m:
        return f"Chapter {m.group(1)} - {m.group(2).strip()}"
    m2 = re.match(r"(?i)^chapter\s+(\d+)\s*$", stripped)
    if m2:
        return f"Chapter {m2.group(1)}"
    return stripped


def clean_body_text(text):
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    text = re.sub(r"(?i)read\s+(at|on)\s+\w+\.com", "", text)
    text = re.sub(r"(?i)translated by.*?\n", "", text)
    lines = text.rstrip().split("\n")
    while lines:
        last = lines[-1].strip()
        if not last or (len(last) < 40 and not any(c in last for c in ".?!,;:")):
            lines.pop()
        else:
            break
    return "\n".join(lines).strip()


class TestParseChapterTitle(unittest.TestCase):
    def test_volume_and_subtitle(self):
        self.assertEqual(
            parse_chapter_title("Volume 1, Chapter 0 – Prologue: A Clumsy Transmigration"),
            "Chapter 0 - Prologue: A Clumsy Transmigration")

    def test_no_volume(self):
        self.assertEqual(parse_chapter_title("Chapter 42 – The Final Battle"),
                         "Chapter 42 - The Final Battle")

    def test_chapter_only(self):
        self.assertEqual(parse_chapter_title("Chapter 7"), "Chapter 7")

    def test_em_dash(self):
        self.assertEqual(parse_chapter_title("Chapter 100—Awakening"),
                         "Chapter 100 - Awakening")

    def test_colon(self):
        self.assertEqual(parse_chapter_title("Chapter 5: The Dream"),
                         "Chapter 5 - The Dream")

    def test_zero_width_stripped(self):
        self.assertEqual(parse_chapter_title("Chapter\u200b 3\u200d – Hidden"),
                         "Chapter 3 - Hidden")

    def test_case_insensitive_volume(self):
        self.assertEqual(parse_chapter_title("VOLUME 2, chapter 10 – Reunion"),
                         "Chapter 10 - Reunion")

    def test_fallback_non_chapter(self):
        self.assertEqual(parse_chapter_title("Epilogue: After the Storm"),
                         "Epilogue: After the Storm")

    def test_empty(self):
        self.assertEqual(parse_chapter_title(""), "")

    def test_whitespace(self):
        self.assertEqual(parse_chapter_title("   "), "")

    def test_volume_no_chapter(self):
        self.assertEqual(parse_chapter_title("Volume 3, Prologue"), "Prologue")


class TestCleanBodyText(unittest.TestCase):
    def test_zero_width_removed(self):
        self.assertEqual(clean_body_text("Hello\u200bWorld\ufeff!"), "HelloWorld!")

    def test_read_at_watermark(self):
        result = clean_body_text("Some story text.\nRead at example.com\nMore text.")
        self.assertNotIn("Read at", result)
        self.assertIn("More text.", result)

    def test_read_on_watermark(self):
        self.assertNotIn("read on", clean_body_text("Story.\nread on novelsite.com\nEnd."))

    def test_translated_by_watermark(self):
        self.assertNotIn("Translated by",
                         clean_body_text("Story text.\nTranslated by SomeTeam\nMore story."))

    def test_trailing_credit_stripped(self):
        self.assertEqual(clean_body_text("Last real sentence.\nRedZTL\nTL handle"),
                         "Last real sentence.")

    def test_keeps_punctuated_trailing(self):
        self.assertIn("This is also real",
                      clean_body_text("Last real sentence.\nThis is also real, with commas."))

    def test_empty(self):
        self.assertEqual(clean_body_text(""), "")

    def test_all_short_trailing_removed(self):
        self.assertEqual(clean_body_text("Real content here.\nfoo\nbar\nbaz"),
                         "Real content here.")

    def test_short_with_sentence_ending_kept(self):
        self.assertIn("Yes!", clean_body_text("Real content.\nYes!"))


if __name__ == "__main__":
    unittest.main()
