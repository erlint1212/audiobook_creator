"""Tests for glossary and title reformatting (gemini/grok translate modules)"""
import json
import os
import re
import tempfile
import unittest


def load_glossary_from_json(filepath):
    default = {"characters": {}, "places": {}}
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("characters", {})
            data.setdefault("places", {})
            return data
    except (json.JSONDecodeError, IOError):
        return default


def save_glossary_to_json(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def reformat_chapter_title_in_text(text_content):
    if not text_content or not text_content.strip():
        return text_content
    lines = text_content.split("\n", 1)
    first_line = lines[0]
    rest = lines[1] if len(lines) > 1 else ""
    match = re.match(r"^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)", first_line, re.IGNORECASE)
    if match:
        ch, title = match.group(1).strip(), match.group(2).strip()
        header = f"{ch} - {title}" if title else ch
        return f"{header}\n{rest}"
    num = re.match(r"^(\d+)\s+(.*)", first_line)
    if num:
        try:
            return f"Chapter {int(num.group(1))} - {num.group(2).strip()}\n{rest}"
        except ValueError:
            pass
    return text_content


class TestLoadGlossary(unittest.TestCase):
    def test_missing_file(self):
        self.assertEqual(load_glossary_from_json("/tmp/nonexistent_abc123.json"),
                         {"characters": {}, "places": {}})

    def test_valid_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"characters": {"兰波": {"pinyin": "Lan Bo"}}, "places": {}}, f)
            path = f.name
        try:
            result = load_glossary_from_json(path)
            self.assertIn("兰波", result["characters"])
        finally:
            os.unlink(path)

    def test_missing_characters_key(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"places": {}}, f)
            path = f.name
        try:
            result = load_glossary_from_json(path)
            self.assertIn("characters", result)
        finally:
            os.unlink(path)

    def test_corrupt_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{bad json")
            path = f.name
        try:
            self.assertEqual(load_glossary_from_json(path),
                             {"characters": {}, "places": {}})
        finally:
            os.unlink(path)


class TestSaveGlossary(unittest.TestCase):
    def test_round_trip(self):
        data = {"characters": {"张三": {"pinyin": "Zhang San"}}, "places": {}}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_glossary_to_json(path, data)
            loaded = load_glossary_from_json(path)
            self.assertEqual(loaded["characters"]["张三"]["pinyin"], "Zhang San")
        finally:
            os.unlink(path)

    def test_unicode_preserved(self):
        data = {"characters": {"白蛇": {"name": "White Snake"}}, "places": {}}
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save_glossary_to_json(path, data)
            with open(path, encoding="utf-8") as fh:
                raw = fh.read()
            self.assertIn("白蛇", raw)
        finally:
            os.unlink(path)


class TestReformatChapterTitle(unittest.TestCase):
    def test_colon(self):
        self.assertTrue(
            reformat_chapter_title_in_text("Chapter 5: The Dream\nBody.").startswith("Chapter 5 - The Dream"))

    def test_dash(self):
        self.assertTrue(
            reformat_chapter_title_in_text("Chapter 10 - Awakening\nBody.").startswith("Chapter 10 - Awakening"))

    def test_em_dash(self):
        self.assertTrue(
            reformat_chapter_title_in_text("Chapter 3—Escape\nBody.").startswith("Chapter 3 - Escape"))

    def test_numeric_first_line(self):
        self.assertTrue(
            reformat_chapter_title_in_text("42 The Answer\nBody.").startswith("Chapter 42 - The Answer"))

    def test_no_subtitle(self):
        self.assertTrue(
            reformat_chapter_title_in_text("Chapter 7\nBody.").startswith("Chapter 7"))

    def test_unrecognized_unchanged(self):
        text = "Epilogue\nBody text."
        self.assertEqual(reformat_chapter_title_in_text(text), text)

    def test_empty(self):
        self.assertEqual(reformat_chapter_title_in_text(""), "")

    def test_body_preserved(self):
        result = reformat_chapter_title_in_text("Chapter 1: Start\nParagraph one.\nParagraph two.")
        self.assertIn("Paragraph one.", result)
        self.assertIn("Paragraph two.", result)


if __name__ == "__main__":
    unittest.main()
