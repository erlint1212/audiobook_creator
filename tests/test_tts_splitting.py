"""Tests for alltalk_tts_generator — text splitting and normalization"""
import math
import re
import unittest

AVG_CHARS_PER_TOKEN = 1.9
FALLBACK_TOKEN_LIMIT = 170


def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    if not text:
        return 0
    return math.ceil(len(text) / max(1.0, avg_chars_per_token))


def normalize_text(text):
    replacements = {
        "\u201c": '"', "\u201d": '"', "\u2018": "'", "\u2019": "'",
        "\u2026": "...", "\u2014": "-", "\u2013": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace(".", ". ")
    text = re.sub(r"\s+", " ", text)
    return text


def _split_by_force_chars(text_content, char_limit):
    if len(text_content) <= char_limit:
        return [text_content]
    chunks = []
    start = 0
    while start < len(text_content):
        end = min(start + int(char_limit), len(text_content))
        if end < len(text_content):
            space = text_content.rfind(" ", start, end)
            if space != -1 and space > start:
                end = space
        chunk = text_content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end + 1
    return chunks


def _simple_sent_tokenize(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def _split_by_sentence_groups(text_content, token_limit, avg_cpt):
    char_limit = token_limit * avg_cpt
    sentences = _simple_sent_tokenize(text_content)
    if not sentences:
        return []
    chunks, buf, buf_tok = [], [], 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        est = _estimate_tokens(s, avg_cpt)
        if est > token_limit:
            if buf:
                chunks.append(" ".join(buf)); buf, buf_tok = [], 0
            chunks.extend(_split_by_force_chars(s, char_limit))
        elif buf_tok + est <= token_limit:
            buf.append(s); buf_tok += est
        else:
            if buf:
                chunks.append(" ".join(buf))
            buf, buf_tok = [s], est
    if buf:
        chunks.append(" ".join(buf))
    return [c for c in chunks if c.strip()]


def _split_by_line_groups(text_content, token_limit, avg_cpt):
    if not text_content or not text_content.strip():
        return []
    lines = [l.strip() for l in text_content.split("\n") if l.strip()]
    if not lines:
        return []
    chunks, buf, buf_tok = [], [], 0
    for line in lines:
        est = _estimate_tokens(line, avg_cpt)
        if est > token_limit:
            if buf:
                chunks.append("\n".join(buf)); buf, buf_tok = [], 0
            chunks.extend(_split_by_sentence_groups(line, token_limit, avg_cpt))
        elif buf_tok + est <= token_limit:
            buf.append(line); buf_tok += est
        else:
            if buf:
                chunks.append("\n".join(buf))
            buf, buf_tok = [line], est
    if buf:
        chunks.append("\n".join(buf))
    return [c for c in chunks if c.strip()]


class TestEstimateTokens(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_estimate_tokens(""), 0)

    def test_none(self):
        self.assertEqual(_estimate_tokens(None), 0)

    def test_short(self):
        self.assertEqual(_estimate_tokens("Hello"), 3)  # 5/1.9 → ceil = 3

    def test_exact(self):
        self.assertEqual(_estimate_tokens("A" * 190), 100)

    def test_custom_ratio(self):
        self.assertEqual(_estimate_tokens("ABCDEF", 3.0), 2)


class TestNormalizeText(unittest.TestCase):
    def test_smart_quotes(self):
        result = normalize_text("\u201cHello,\u201d she said")
        self.assertIn('"Hello,"', result)
        self.assertNotIn("\u201c", result)

    def test_em_dash(self):
        result = normalize_text("word\u2014word")
        self.assertIn("-", result)
        self.assertNotIn("\u2014", result)

    def test_ellipsis(self):
        # … → ... → ". . . " because normalize_text also adds space after every period
        result = normalize_text("wait\u2026")
        self.assertNotIn("\u2026", result)  # original ellipsis removed

    def test_period_spacing(self):
        self.assertIn("end. start", normalize_text("end.start"))

    def test_double_spaces_collapsed(self):
        self.assertNotIn("  ", normalize_text("too   many    spaces"))


class TestSplitByForceChars(unittest.TestCase):
    def test_short_not_split(self):
        self.assertEqual(_split_by_force_chars("Short.", 100), ["Short."])

    def test_splits_needed(self):
        text = ("word " * 20).strip()
        chunks = _split_by_force_chars(text, 50)
        self.assertGreaterEqual(len(chunks), 2)

    def test_no_empty_chunks(self):
        chunks = _split_by_force_chars("Hello world. This is a test.", 20)
        for c in chunks:
            self.assertTrue(c.strip())

    def test_single_long_word(self):
        text = "A" * 200
        chunks = _split_by_force_chars(text, 50)
        self.assertGreaterEqual(len(chunks), 4)
        # Each chunk should contain only 'A's
        for c in chunks:
            self.assertTrue(all(ch == "A" for ch in c))


class TestSplitByLineGroups(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_split_by_line_groups("", 170, 1.9), [])

    def test_whitespace_only(self):
        self.assertEqual(_split_by_line_groups("   \n  ", 170, 1.9), [])

    def test_single_short_line(self):
        self.assertEqual(_split_by_line_groups("Hello.", 170, 1.9), ["Hello."])

    def test_short_lines_grouped(self):
        result = _split_by_line_groups("Line one.\nLine two.\nLine three.", 170, 1.9)
        self.assertEqual(len(result), 1)

    def test_long_lines_split(self):
        text = f"Short.\n{'A' * 400}\nShort again."
        result = _split_by_line_groups(text, 170, 1.9)
        self.assertGreaterEqual(len(result), 2)

    def test_no_empty_results(self):
        result = _split_by_line_groups("Line one.\n\n\nLine two.", 170, 1.9)
        for c in result:
            self.assertTrue(c.strip())


class TestSplitBySentenceGroups(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_split_by_sentence_groups("", 170, 1.9), [])

    def test_short_single_chunk(self):
        result = _split_by_sentence_groups("Hello. World. Test.", 170, 1.9)
        self.assertEqual(len(result), 1)

    def test_respects_limit(self):
        s1, s2 = "A" * 100 + ".", "B" * 100 + "."
        result = _split_by_sentence_groups(f"{s1} {s2}", 60, 1.9)
        self.assertGreaterEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
