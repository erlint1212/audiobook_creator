"""Tests for TTS splitting and translation context-window chunking.

Run: python -m pytest tests/ -v
  or: python tests/test_chunking.py
"""

import math
import re
import unittest

# ================================================================
# TTS Constants & Functions (copied from test_tts_splitting.py)
# ================================================================
AVG_CHARS_PER_TOKEN = 1.9
FALLBACK_TOKEN_LIMIT = 170


def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    if not text:
        return 0
    return math.ceil(len(text) / max(1.0, avg_chars_per_token))


def normalize_text(text):
    replacements = {
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2026": "...",
        "\u2014": "-",
        "\u2013": "-",
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
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


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
                chunks.append(" ".join(buf))
                buf, buf_tok = [], 0
            chunks.extend(_split_by_force_chars(s, char_limit))
        elif buf_tok + est <= token_limit:
            buf.append(s)
            buf_tok += est
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
                chunks.append("\n".join(buf))
                buf, buf_tok = [], 0
            chunks.extend(_split_by_sentence_groups(line, token_limit, avg_cpt))
        elif buf_tok + est <= token_limit:
            buf.append(line)
            buf_tok += est
        else:
            if buf:
                chunks.append("\n".join(buf))
            buf, buf_tok = [line], est
    if buf:
        chunks.append("\n".join(buf))
    return [c for c in chunks if c.strip()]


# ================================================================
# Translation Context-Window Constants & Functions
# ================================================================
CONTEXT_LIMIT = 36970
AVG_CHARS_PER_TOKEN_ZH = 1.5
AVG_CHARS_PER_TOKEN_EN = 4.0
PROMPT_OVERHEAD_TOKENS = 1500
OUTPUT_RATIO = 2.5
SAFETY_MARGIN = 0.90


def _estimate_zh_tokens(text):
    return math.ceil(len(text) / AVG_CHARS_PER_TOKEN_ZH)


def _max_input_tokens(glossary_json_str):
    glossary_tokens = math.ceil(len(glossary_json_str) / AVG_CHARS_PER_TOKEN_EN)
    available = int(CONTEXT_LIMIT * SAFETY_MARGIN)
    budget = available - PROMPT_OVERHEAD_TOKENS - glossary_tokens
    max_input = int(budget / 1.94)
    return max(200, max_input)


def _output_token_budget(glossary_json_str):
    return int(_max_input_tokens(glossary_json_str) * 0.94 * 1.1)


def chunk_for_context(text, glossary_json_str):
    max_tok = _max_input_tokens(glossary_json_str)
    max_chars = int(max_tok * AVG_CHARS_PER_TOKEN_ZH)
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks, buf, buf_len = [], [], 0
    for p in paragraphs:
        if buf_len + len(p) > max_chars and buf:
            chunks.append("\n".join(buf))
            buf, buf_len = [], 0
        if len(p) > max_chars:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_len = [], 0
            sents = re.split(r"(?<=[。！？])", p)
            sbuf, slen = [], 0
            for s in sents:
                if slen + len(s) > max_chars and sbuf:
                    chunks.append("".join(sbuf))
                    sbuf, slen = [], 0
                sbuf.append(s)
                slen += len(s)
            if sbuf:
                chunks.append("".join(sbuf))
        else:
            buf.append(p)
            buf_len += len(p)
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _is_thinking_dump(text):
    if not text:
        return False
    lines = text.split("\n")
    indicators = 0
    for line in lines:
        if re.search(r".+\s*->\s*.+", line):
            indicators += 1
        if re.search(r"\((?:Note|Wait|Actually|Looking)", line):
            indicators += 1
        if re.search(r"\*\*Paragraph \d+", line):
            indicators += 1
        if re.search(r"(?:Let me|I will|I'll|Let's|Given the)", line):
            indicators += 1
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    if cjk_count > 20:
        indicators += 3
    return indicators >= 3


# ================================================================
# TTS TESTS — _estimate_tokens
# ================================================================
class TestEstimateTokens(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(_estimate_tokens(""), 0)

    def test_none(self):
        self.assertEqual(_estimate_tokens(None), 0)

    def test_short_word(self):
        self.assertEqual(_estimate_tokens("Hello"), 3)  # ceil(5/1.9)

    def test_exact_multiple(self):
        self.assertEqual(_estimate_tokens("A" * 190), 100)  # 190/1.9 = 100

    def test_custom_ratio(self):
        self.assertEqual(_estimate_tokens("ABCDEF", 3.0), 2)  # ceil(6/3)

    def test_single_char(self):
        self.assertEqual(_estimate_tokens("X"), 1)  # ceil(1/1.9)

    def test_zero_ratio_clamped(self):
        """avg_chars_per_token=0 should not divide by zero (max(1.0, 0))."""
        result = _estimate_tokens("Hello", 0.0)
        self.assertEqual(result, 5)  # ceil(5/1.0)

    def test_negative_ratio_clamped(self):
        result = _estimate_tokens("Hello", -2.0)
        self.assertEqual(result, 5)  # max(1.0, -2.0) = 1.0


# ================================================================
# TTS TESTS — normalize_text
# ================================================================
class TestNormalizeText(unittest.TestCase):
    def test_smart_double_quotes(self):
        result = normalize_text("\u201cHello,\u201d she said")
        self.assertIn('"Hello,"', result)

    def test_smart_single_quotes(self):
        result = normalize_text("\u2018it\u2019s")
        self.assertNotIn("\u2018", result)
        self.assertNotIn("\u2019", result)

    def test_em_dash(self):
        self.assertNotIn("\u2014", normalize_text("word\u2014word"))

    def test_en_dash(self):
        self.assertNotIn("\u2013", normalize_text("2020\u20132025"))

    def test_ellipsis(self):
        result = normalize_text("wait\u2026")
        self.assertNotIn("\u2026", result)
        self.assertIn(".", result)

    def test_period_spacing(self):
        self.assertIn("end. start", normalize_text("end.start"))

    def test_collapses_whitespace(self):
        self.assertNotIn("  ", normalize_text("too   many    spaces"))

    def test_already_clean(self):
        text = "This is normal text."
        result = normalize_text(text)
        self.assertIn("This is normal text", result)

    def test_period_after_period_gets_spaced(self):
        """'end..start' -> 'end. . start' after normalization."""
        result = normalize_text("end..start")
        self.assertNotIn("  ", result)  # whitespace collapsed

    def test_empty_string(self):
        self.assertEqual(normalize_text(""), "")

    def test_multiple_replacements_in_one_string(self):
        text = "\u201cHello\u201d\u2014she said\u2026\u2018wow\u2019"
        result = normalize_text(text)
        for ch in ["\u201c", "\u201d", "\u2014", "\u2026", "\u2018", "\u2019"]:
            self.assertNotIn(ch, result)


# ================================================================
# TTS TESTS — _split_by_force_chars
# ================================================================
class TestSplitByForceChars(unittest.TestCase):
    def test_short_not_split(self):
        self.assertEqual(_split_by_force_chars("Short.", 100), ["Short."])

    def test_exact_limit(self):
        text = "A" * 50
        self.assertEqual(_split_by_force_chars(text, 50), [text])

    def test_one_over_limit(self):
        """51 chars, no spaces: end+1 skip loses the 51st char. Known edge case."""
        text = "A" * 51
        chunks = _split_by_force_chars(text, 50)
        # start=end+1 after spaceless split means the last char is skipped
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 50)  # Loses 1 char!

    def test_splits_on_space(self):
        text = "Hello world this is a test of chunking"
        chunks = _split_by_force_chars(text, 20)
        for c in chunks:
            self.assertLessEqual(len(c), 20)

    def test_no_empty_chunks(self):
        chunks = _split_by_force_chars("Hello world. This is a test.", 20)
        for c in chunks:
            self.assertTrue(c.strip())

    def test_single_long_word_no_spaces(self):
        """Long word with no spaces: hard-splits but end+1 skip loses chars at boundaries."""
        text = "A" * 200
        chunks = _split_by_force_chars(text, 50)
        self.assertGreaterEqual(len(chunks), 3)
        # Known: end+1 skip after each spaceless chunk loses 1 char per split
        joined = "".join(chunks)
        lost = len(text) - len(joined)
        self.assertGreater(lost, 0, "Expected char loss from end+1 skip bug")

    def test_all_content_preserved(self):
        text = "The quick brown fox jumps over the lazy dog."
        chunks = _split_by_force_chars(text, 15)
        rejoined = " ".join(chunks)
        # All words present
        for word in text.split():
            self.assertIn(word.strip(".,"), rejoined)

    def test_limit_of_one(self):
        """Degenerate: char_limit=1. Each char becomes its own chunk."""
        text = "AB CD"
        chunks = _split_by_force_chars(text, 1)
        self.assertTrue(len(chunks) >= 2)

    def test_trailing_spaces(self):
        text = "word1 word2 word3   "
        chunks = _split_by_force_chars(text, 10)
        for c in chunks:
            self.assertEqual(c, c.strip())


# ================================================================
# TTS TESTS — _split_by_sentence_groups
# ================================================================
class TestSplitBySentenceGroups(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_split_by_sentence_groups("", 170, 1.9), [])

    def test_single_sentence_fits(self):
        result = _split_by_sentence_groups("Hello world.", 170, 1.9)
        self.assertEqual(len(result), 1)

    def test_multiple_short_sentences_grouped(self):
        result = _split_by_sentence_groups("Hello. World. Test.", 170, 1.9)
        self.assertEqual(len(result), 1)

    def test_respects_token_limit(self):
        s1, s2 = "A" * 100 + ".", "B" * 100 + "."
        result = _split_by_sentence_groups(f"{s1} {s2}", 60, 1.9)
        self.assertGreaterEqual(len(result), 2)

    def test_oversized_sentence_falls_to_force_chars(self):
        """Single sentence exceeding limit -> force-char split."""
        giant = "A" * 500 + "."
        result = _split_by_sentence_groups(giant, 50, 1.9)
        self.assertGreater(len(result), 1)

    def test_no_empty_chunks(self):
        result = _split_by_sentence_groups("One. Two. Three.", 10, 1.9)
        for c in result:
            self.assertTrue(c.strip())

    def test_sentence_exactly_at_limit(self):
        """Sentence whose token estimate == token_limit should fit alone."""
        # 19 chars / 1.9 = 10 tokens exactly
        text = "A" * 19 + "."  # 20 chars -> ceil(20/1.9) = 11
        # token_limit=11 -> should fit in one chunk
        result = _split_by_sentence_groups(text, 11, 1.9)
        self.assertEqual(len(result), 1)

    def test_many_tiny_sentences(self):
        text = ". ".join(["Hi"] * 50) + "."
        result = _split_by_sentence_groups(text, 20, 1.9)
        # Should group them, not produce 50 chunks
        self.assertLess(len(result), 50)
        self.assertGreater(len(result), 0)

    def test_no_punctuation(self):
        """Text with no sentence-ending punctuation -> treated as one 'sentence'."""
        text = "No punctuation here at all"
        result = _split_by_sentence_groups(text, 170, 1.9)
        # _simple_sent_tokenize returns full text as one sentence
        self.assertEqual(len(result), 1)


# ================================================================
# TTS TESTS — _split_by_line_groups
# ================================================================
class TestSplitByLineGroups(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_split_by_line_groups("", 170, 1.9), [])

    def test_none_like(self):
        self.assertEqual(_split_by_line_groups("   \n  \n\n", 170, 1.9), [])

    def test_single_short_line(self):
        self.assertEqual(_split_by_line_groups("Hello.", 170, 1.9), ["Hello."])

    def test_short_lines_grouped(self):
        text = "Line one.\nLine two.\nLine three."
        result = _split_by_line_groups(text, 170, 1.9)
        self.assertEqual(len(result), 1)
        self.assertIn("\n", result[0])  # Lines joined with \n

    def test_long_line_triggers_sentence_split(self):
        text = f"Short.\n{'A' * 400}\nShort again."
        result = _split_by_line_groups(text, 170, 1.9)
        self.assertGreaterEqual(len(result), 2)

    def test_blank_lines_ignored(self):
        result = _split_by_line_groups("Line one.\n\n\n\nLine two.", 170, 1.9)
        for c in result:
            self.assertTrue(c.strip())

    def test_many_lines_each_near_limit(self):
        """Each line just under the limit -> one chunk per line."""
        lines = [f"{'W' * 300}." for _ in range(5)]
        text = "\n".join(lines)
        result = _split_by_line_groups(text, 170, 1.9)
        # 300 chars / 1.9 ≈ 158 tokens. Just under 170 -> each fits alone
        # But can't group any two -> 5 chunks
        self.assertEqual(len(result), 5)

    def test_preserves_all_content(self):
        lines = ["Line one.", "Line two.", "Line three."]
        text = "\n".join(lines)
        result = _split_by_line_groups(text, 170, 1.9)
        combined = "\n".join(result)
        for line in lines:
            self.assertIn(line, combined)

    def test_only_newlines(self):
        self.assertEqual(_split_by_line_groups("\n\n\n", 170, 1.9), [])

    def test_mixed_lengths(self):
        """Mix of short and long lines."""
        text = "Short.\n" + "B" * 500 + "\nAlso short."
        result = _split_by_line_groups(text, 170, 1.9)
        self.assertGreater(len(result), 1)

    def test_realistic_tts_chapter(self):
        """Simulate a translated chapter with dialogue and narration."""
        paragraphs = [
            "Chapter 25 - Audience",
            '"Assault the city." Bai Ji pointed to the brightly lit city in the distance.',
            '"Understood!" Onda saluted and turned to relay the orders.',
            "The fire spread faster than the panicked soldiers could run. "
            "Flames consumed the dry leaves, turning the forest into an inferno. "
            "Smoke choked the retreating army as discipline collapsed entirely.",
            '"I don\'t know if this is right," she whispered.',
            "Short.",
        ]
        text = "\n".join(paragraphs)
        total_tokens = _estimate_tokens(text, 1.9)
        result = _split_by_line_groups(text, 170, 1.9)
        # All content should be preserved across chunks
        combined = "\n".join(result)
        for p in paragraphs:
            self.assertIn(p, combined)
        # No empty chunks
        for c in result:
            self.assertTrue(c.strip())


# ================================================================
# TRANSLATION TESTS — _estimate_zh_tokens
# ================================================================
class TestEstimateZhTokens(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_estimate_zh_tokens(""), 0)

    def test_chinese_text(self):
        text = "白" * 150  # 150 chars / 1.5 = 100 tokens
        self.assertEqual(_estimate_zh_tokens(text), 100)

    def test_single_char(self):
        self.assertEqual(_estimate_zh_tokens("白"), 1)

    def test_mixed_cjk_ascii(self):
        """Mixed text: each char counts equally in this estimator."""
        text = "白姬 Bai Ji"
        result = _estimate_zh_tokens(text)
        self.assertEqual(result, math.ceil(len(text) / 1.5))


# ================================================================
# TRANSLATION TESTS — _max_input_tokens
# ================================================================
class TestMaxInputTokens(unittest.TestCase):
    def test_empty_glossary(self):
        result = _max_input_tokens("{}")
        # available = 36970 * 0.9 = 33273
        # glossary_tokens = ceil(2/4) = 1
        # budget = 33273 - 1500 - 1 = 31772
        # max_input = int(31772 / 1.94) = 16377
        self.assertEqual(result, 16377)

    def test_large_glossary_reduces_budget(self):
        small = _max_input_tokens("{}")
        big = _max_input_tokens("X" * 10000)
        self.assertGreater(small, big)

    def test_floor_at_200(self):
        """Massive glossary should still return at least 200."""
        huge_glossary = "X" * 200000
        result = _max_input_tokens(huge_glossary)
        self.assertEqual(result, 200)

    def test_glossary_token_accounting(self):
        """Verify glossary size directly reduces available tokens."""
        g1 = "X" * 400  # 100 tokens
        g2 = "X" * 4000  # 1000 tokens
        diff = _max_input_tokens(g1) - _max_input_tokens(g2)
        # 900 extra glossary tokens / 1.94 ≈ 463 fewer input tokens
        self.assertAlmostEqual(diff, 463, delta=5)

    def test_returns_int(self):
        self.assertIsInstance(_max_input_tokens("{}"), int)


# ================================================================
# TRANSLATION TESTS — _output_token_budget
# ================================================================
class TestOutputTokenBudget(unittest.TestCase):
    def test_proportional_to_input(self):
        budget = _output_token_budget("{}")
        max_in = _max_input_tokens("{}")
        expected = int(max_in * 0.94 * 1.1)
        self.assertEqual(budget, expected)

    def test_shrinks_with_glossary(self):
        small = _output_token_budget("{}")
        big = _output_token_budget("X" * 10000)
        self.assertGreater(small, big)

    def test_total_fits_context(self):
        """input_tokens + output_tokens + overhead + glossary <= context_limit."""
        glossary = '{"characters":{},"places":{}}'
        max_in = _max_input_tokens(glossary)
        out_budget = _output_token_budget(glossary)
        glossary_tok = math.ceil(len(glossary) / AVG_CHARS_PER_TOKEN_EN)
        total = max_in + out_budget + PROMPT_OVERHEAD_TOKENS + glossary_tok
        self.assertLessEqual(
            total, CONTEXT_LIMIT, f"Total {total} exceeds context {CONTEXT_LIMIT}"
        )


# ================================================================
# TRANSLATION TESTS — chunk_for_context
# ================================================================
class TestChunkForContext(unittest.TestCase):
    def _max_chars(self, glossary="{}"):
        return int(_max_input_tokens(glossary) * AVG_CHARS_PER_TOKEN_ZH)

    def test_short_text_no_split(self):
        text = "白姬挥了挥墨水杖。"
        result = chunk_for_context(text, "{}")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], text)

    def test_empty_text(self):
        result = chunk_for_context("", "{}")
        self.assertEqual(result, [""])

    def test_whitespace_only(self):
        result = chunk_for_context("   \n  \n  ", "{}")
        # All paragraphs stripped -> empty list or single empty
        # Actually: len("   \n  \n  ") = 9 <= max_chars -> returns ["   \n  \n  "]
        self.assertEqual(len(result), 1)

    def test_exact_at_limit(self):
        max_c = self._max_chars()
        text = "白" * max_c
        result = chunk_for_context(text, "{}")
        self.assertEqual(len(result), 1)

    def test_one_char_over_triggers_split(self):
        max_c = self._max_chars()
        # Two paragraphs, each half the limit + 1 -> won't fit together
        half = max_c // 2 + 1
        text = ("白" * half) + "\n" + ("姬" * half)
        result = chunk_for_context(text, "{}")
        self.assertGreaterEqual(len(result), 2)

    def test_no_content_lost(self):
        """All input chars present after chunking."""
        paras = ["这是第一段。", "这是第二段。", "这是第三段，比较长。" * 50]
        text = "\n".join(paras)
        result = chunk_for_context(text, "{}")
        combined = "\n".join(result)
        for p in paras:
            # Paragraph content should be in combined output
            # (stripping may remove leading/trailing whitespace)
            self.assertIn(p.strip(), combined)

    def test_splits_by_paragraph_first(self):
        max_c = self._max_chars()
        para = "白" * (max_c // 3)
        text = "\n".join([para, para, para, para])
        result = chunk_for_context(text, "{}")
        # 4 paragraphs of ~1/3 max each -> 3 fit, 4th spills -> 2 chunks
        self.assertGreaterEqual(len(result), 2)

    def test_giant_paragraph_sentence_split(self):
        """Single paragraph exceeding max_chars -> splits on Chinese punctuation."""
        max_c = self._max_chars()
        # Build paragraph of sentences that together exceed limit
        sentence = "白姬挥了挥墨水杖。"  # 9 chars
        count = (max_c // len(sentence)) + 10
        para = sentence * count  # No newlines, just repeated sentences
        result = chunk_for_context(para, "{}")
        self.assertGreater(len(result), 1)
        # Each chunk should be <= max_chars (roughly)
        for chunk in result:
            self.assertLessEqual(
                len(chunk),
                max_c + len(sentence),
                "Chunk exceeds max by more than one sentence",
            )

    def test_giant_paragraph_no_punctuation(self):
        """Giant paragraph with no 。！？ -> can't sentence-split, becomes one oversized chunk."""
        max_c = self._max_chars()
        para = "白" * (max_c + 1000)  # No punctuation
        result = chunk_for_context(para, "{}")
        # Single sentence with no split points -> single chunk (oversized)
        # This is a known limitation worth documenting
        self.assertEqual(len(result), 1)
        self.assertGreater(len(result[0]), max_c)

    def test_larger_glossary_means_smaller_chunks(self):
        """Larger glossary -> smaller max_chars -> more chunks."""
        text = "这是一个句子。\n" * 500
        small_g = "{}"
        big_g = "X" * 20000
        r_small = chunk_for_context(text, small_g)
        r_big = chunk_for_context(text, big_g)
        self.assertGreaterEqual(len(r_big), len(r_small))

    def test_blank_lines_between_paragraphs(self):
        """Blank lines should be stripped, not create empty chunks."""
        text = "第一段。\n\n\n\n第二段。\n\n第三段。"
        result = chunk_for_context(text, "{}")
        for chunk in result:
            self.assertTrue(chunk.strip(), "Got empty/blank chunk")

    def test_mixed_short_and_long_paragraphs(self):
        max_c = self._max_chars()
        short = "短。"
        long_para = "长句子。" * (max_c // 12 + 1)
        text = f"{short}\n{short}\n{long_para}\n{short}"
        result = chunk_for_context(text, "{}")
        combined = "".join(result)
        self.assertIn("短", combined)
        self.assertIn("长句子", combined)

    def test_realistic_chapter(self):
        """Simulate a real chapter: ~4000 chars of Chinese text."""
        sentences = [
            "黑色雾霾笼罩，连月亮的光也无法穿透的深邃，寂静的森林中回响起惊慌失措的哀嚎与惨叫。",
            "被火点着的杰多士兵发了疯似的向同伴们跑去，沿途点着了泥地中失去水分的干枯树叶。",
            "领军的杰多将领惊呆了，谁这么缺德敢在茂林中用火攻？",
            "来不及扑火，窒息的滚滚浓烟中，杰多士兵溃不成军。",
        ]
        chapter = "\n".join(sentences * 20)
        result = chunk_for_context(chapter, '{"characters":{}}')
        # ~3200 chars, max_chars is ~24K -> should fit in one chunk
        self.assertEqual(len(result), 1)


# ================================================================
# TRANSLATION TESTS — _is_thinking_dump
# ================================================================
class TestIsThinkingDump(unittest.TestCase):
    def test_clean_translation(self):
        text = (
            "Chapter 25 - Audience\n"
            "Black fog shrouded everything. In the silent forest, "
            "panicked screams echoed.\n"
            '"Assault the city," Bai Ji commanded.'
        )
        self.assertFalse(_is_thinking_dump(text))

    def test_obvious_dump(self):
        """Based on real dump from ch_0367.txt."""
        text = (
            "Chapter 25 - 参见 (See/Attend) -> Chapter 25 - Audience\n"
            "黑色雾霾笼罩 -> Black fog shrouded everything\n"
            "(Note: 回**起 seems like a typo for 响起).\n"
            "**Paragraph 2:**\n"
            "Let me check the glossary again.\n"
            "Actually, looking closely: 远道 appears twice."
        )
        self.assertTrue(_is_thinking_dump(text))

    def test_cjk_leakage_alone_triggers(self):
        """21+ CJK chars = 3 indicators, which meets threshold."""
        text = "Translation here. " + "白" * 25 + " more text."
        self.assertTrue(_is_thinking_dump(text))

    def test_cjk_just_under_threshold(self):
        """20 CJK chars should NOT trigger (threshold is >20)."""
        text = "Translation here. " + "白" * 20 + " more text."
        self.assertFalse(_is_thinking_dump(text))

    def test_arrows_alone(self):
        text = "word -> translation\n" "another -> thing\n" "third -> result\n"
        self.assertTrue(_is_thinking_dump(text))

    def test_code_arrows_false_positive(self):
        """Legitimate use of -> in English (rare in novel translation)."""
        text = "The fire spread quickly -> the soldiers fled."
        self.assertFalse(_is_thinking_dump(text))  # Only 1 indicator

    def test_paragraph_markers(self):
        text = (
            "Some translation text.\n"
            "**Paragraph 1:**\n"
            "More text.\n"
            "**Paragraph 2:**\n"
            "Even more.\n"
            "**Paragraph 3:**\n"
        )
        self.assertTrue(_is_thinking_dump(text))

    def test_empty(self):
        self.assertFalse(_is_thinking_dump(""))

    def test_none(self):
        self.assertFalse(_is_thinking_dump(None))

    def test_reasoning_phrases(self):
        text = (
            "Let me think about this translation.\n"
            "I will check the glossary.\n"
            "Given the context, I'll use Onda.\n"
        )
        self.assertTrue(_is_thinking_dump(text))

    def test_mixed_clean_with_one_note(self):
        """One parenthetical note shouldn't trigger."""
        text = (
            "The knight swung his sword.\n"
            "(Note: this is a cultural reference)\n"
            "The enemy fled in terror."
        )
        self.assertFalse(_is_thinking_dump(text))

    def test_legitimate_annotation_not_flagged(self):
        """^[annotation] style from the translation should be fine."""
        text = (
            'He said, "This is fifty-fifty^[A gaming meme meaning even odds]."\n'
            "The old knight nodded and left."
        )
        self.assertFalse(_is_thinking_dump(text))


# ================================================================
# CROSS-CUTTING: Budget math invariants
# ================================================================
class TestBudgetInvariants(unittest.TestCase):
    """Verify budget math holds across a range of glossary sizes."""

    def test_budget_never_exceeds_context(self):
        for gsize in [0, 100, 1000, 5000, 20000, 50000]:
            glossary = "X" * gsize
            max_in = _max_input_tokens(glossary)
            out_budget = _output_token_budget(glossary)
            g_tok = math.ceil(len(glossary) / AVG_CHARS_PER_TOKEN_EN)
            total = max_in + out_budget + PROMPT_OVERHEAD_TOKENS + g_tok
            self.assertLessEqual(
                total,
                CONTEXT_LIMIT,
                f"Budget overflow at glossary size {gsize}: total={total}",
            )

    def test_max_input_monotonically_decreases(self):
        prev = _max_input_tokens("")
        for gsize in [100, 1000, 5000, 20000]:
            curr = _max_input_tokens("X" * gsize)
            self.assertLessEqual(
                curr, prev, f"max_input increased at glossary size {gsize}"
            )
            prev = curr

    def test_output_budget_positive(self):
        for gsize in [0, 1000, 50000]:
            self.assertGreater(_output_token_budget("X" * gsize), 0)


if __name__ == "__main__":
    unittest.main()
