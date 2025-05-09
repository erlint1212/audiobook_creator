import unittest
import math # For direct comparison with math.ceil if needed in tests
# Assuming your script is named alltalk_tts_generator_chunky_3.py
# and these functions are directly importable or you adjust the import path
import sys # <--- ADD THIS
import os  # <--- ADD THIS

# --- ADD THESE LINES TO ADJUST SYS.PATH ---
# Get the directory of the current test file (e.g., .../tests/)
_current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (e.g., .../web_scraping/)
_project_root = os.path.abspath(os.path.join(_current_dir, '..'))
# Add the project root to the start of the Python path
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
# --- END OF SYS.PATH ADJUSTMENT ---

# Ensure this matches your actual script filename
from alltalk_tts_generator_chunky_4 import (
    _estimate_tokens,
    _split_into_sentences,
    _split_long_text_by_char_est,
    split_text_into_chunks,
    # Also import any global constants from alltalk_tts_generator_chunky_4.py
    # that your test functions might implicitly rely on or that you want to use
    # as a reference for your TEST_... constants in this file. For example:
    # AVG_CHARS_PER_TOKEN as SCRIPT_AVG_CHARS_PER_TOKEN,
    # TOKEN_LIMIT as SCRIPT_TOKEN_LIMIT,
    # CHUNK_CHAR_LIMIT as SCRIPT_CHUNK_CHAR_LIMIT
)

# Define constants for testing, these can override or complement script defaults for test isolation
TEST_AVG_CHARS_PER_TOKEN = 3 # Or whatever value you want for these specific tests
TEST_TOKEN_LIMIT = 250
TEST_CHAR_COMBINATION_LIMIT = 800
class TestTTSTextProcessing(unittest.TestCase):

    def test_estimate_tokens(self):
        self.assertEqual(_estimate_tokens("", avg_chars_per_token=TEST_AVG_CHARS_PER_TOKEN), 0)
        self.assertEqual(_estimate_tokens("abc", avg_chars_per_token=TEST_AVG_CHARS_PER_TOKEN), 1) # 3/3 = 1
        self.assertEqual(_estimate_tokens("abcd", avg_chars_per_token=TEST_AVG_CHARS_PER_TOKEN), math.ceil(4/TEST_AVG_CHARS_PER_TOKEN)) # 4/3 = 1.33 -> 2
        self.assertEqual(_estimate_tokens("This is a test.", avg_chars_per_token=TEST_AVG_CHARS_PER_TOKEN), math.ceil(len("This is a test.")/TEST_AVG_CHARS_PER_TOKEN))
        # Test with a different avg_chars_per_token
        self.assertEqual(_estimate_tokens("abcdefgh", avg_chars_per_token=4), 2) # 8/4 = 2

    def test_split_into_sentences(self):
        text1 = "Hello world. This is a test. Is it?"
        expected1 = ["Hello world.", "This is a test.", "Is it?"]
        self.assertEqual(_split_into_sentences(text1), expected1)

        text2 = "Mr. Smith went to Washington. He said \"Hello!\" then left."
        # Basic regex might struggle with "Mr." but should split others
        # Current _split_into_sentences regex might produce: ["Mr. Smith went to Washington.", 'He said "Hello!"', 'then left.']
        # Depending on the regex, you'll need to adjust expected output.
        # The provided regex r'(?<=[.!?\"\'\)])(?=\s|\Z)' might result in:
        # ['Mr. Smith went to Washington.', 'He said "Hello!"', 'then left.']
        # Let's assume the improved regex handles common cases well.
        # For the regex provided in my last correct answer for alltalk_tts_generator:
        # r'(?<=[.!?\"\'\)])(?=\s|\Z)' would roughly do this:
        # "Mr. Smith went to Washington." -> "Mr. Smith went to Washington."
        # "He said \"Hello!\" then left." -> "He said \"Hello!\"", "then left."
        # Expected based on current script's likely _split_into_sentences
        expected2 = ["Mr.", "Smith went to Washington.", 'He said "Hello!"', "then left." ] # Or however your regex actually splits it
        self.assertEqual(_split_into_sentences(text2), expected2)
        text3 = "One sentence only."
        self.assertEqual(_split_into_sentences(text3), ["One sentence only."])
        self.assertEqual(_split_into_sentences(""), [])
        self.assertEqual(_split_into_sentences("   "), [])


    def test_split_long_text_by_char_est(self):
        long_text = "This is a very long string that needs to be split into smaller pieces based on character estimation for tokens."
        # token_limit=10, avg_chars=3 => hard_char_limit = 30
        token_limit = 10
        avg_chars = 3
        hard_char_limit = max(1, int(token_limit * avg_chars)) # 30

        chunks = _split_long_text_by_char_est(long_text, token_limit, avg_chars)
        self.assertTrue(len(chunks) > 1)
        for chunk in chunks:
            self.assertTrue(len(chunk) <= hard_char_limit + len(" ")) # Allow for stripping effects, roughly

        # Test empty
        self.assertEqual(_split_long_text_by_char_est("", token_limit, avg_chars), [])


    def test_split_text_into_chunks_phase1_combining(self):
        # Test only the character combination phase
        text = "Segment one.\n\nSegment two, short too.\n\nThis is a much longer third segment that will likely exceed the char_combination_limit if combined with the first two, or even stand alone if very long."
        char_limit = 100 # For combining
        token_limit = 500 # High enough not to trigger token splitting for this test
        avg_chars = TEST_AVG_CHARS_PER_TOKEN

        # Expected: "Segment one.\n\nSegment two, short too." and the long segment separate
        # Length of S1 = 12, S2 = 22. S1+sep+S2 = 12+2+22 = 36. Fits < 100.
        # S3 is long.
        chunks = split_text_into_chunks(text, char_limit, token_limit, avg_chars)
        self.assertTrue(len(chunks) >= 2)
        self.assertEqual(chunks[0], "Segment one.\n\nSegment two, short too.")
        self.assertTrue("This is a much longer third segment" in chunks[1])

    def test_split_text_into_chunks_phase2_token_splitting_by_sentence(self):
        # char_combination_limit is high, force focus on token splitting
        char_limit = 2000
        token_limit_for_test = 20 # Very low to force sentence splitting
        avg_chars = TEST_AVG_CHARS_PER_TOKEN # 3

        # Text where one combined chunk would exceed token_limit_for_test
        # "Sentence one. Sentence two." (len 28, est_tokens ~28/3 = 10 per sentence) -> total est ~20, should fit
        # "Sentence one is a bit longer. Sentence two follows."
        # S1: "Sentence one is a bit longer." (len 30, est_tokens = 10)
        # S2: "Sentence two follows." (len 21, est_tokens = 7)
        # S1 + " " + S2: len 52, est_tokens = ceil(52/3) = 18. This should fit if combined.
        
        text = "This is sentence one. This is sentence two. This is sentence three, which is also short. This is sentence four. This is sentence five. This is sentence six."
        # Total chars: ~150. Est tokens with avg_chars=3: ~50.
        # If token_limit_for_test = 20, it must split by sentences.
        # "This is sentence one." (len 21, est 7 tokens)
        # "This is sentence two." (len 21, est 7 tokens) -> S1+S2 = 14 tokens. Fits.
        # "This is sentence three, which is also short." (len 42, est 14 tokens) -> S1+S2+S3 (14+14=28) > 20. So S1+S2 is one chunk.
        
        chunks = split_text_into_chunks(text, char_limit, token_limit_for_test, avg_chars)
        
        # Expected output:
        # Chunk 1: "This is sentence one. This is sentence two." (est. 14 tokens for "This is sentence one. This is sentence two." (len=43 -> 15 tokens))
        # Chunk 2: "This is sentence three, which is also short." (est. 14 tokens)
        # Chunk 3: "This is sentence four. This is sentence five." (est. 15 tokens)
        # Chunk 4: "This is sentence six." (est. 7 tokens)
        # This depends heavily on the exact sentence splitting and accumulation logic.

        # For simplicity, let's check that sub-splitting occurred and chunks are shorter.
        initial_est_tokens = _estimate_tokens(text, avg_chars)
        if initial_est_tokens > token_limit_for_test:
            self.assertTrue(len(chunks) > 1, "Text should have been split by token limit")
        for chunk in chunks:
            self.assertTrue(_estimate_tokens(chunk, avg_chars) <= token_limit_for_test + 5, # Allow some leeway due to sentence joining / estimation
                            f"Chunk '{chunk}' estimated tokens {_estimate_tokens(chunk, avg_chars)} exceeds limit {token_limit_for_test}")

    def test_split_text_into_chunks_single_long_sentence_fallback(self):
        # Test the fallback for a single sentence that exceeds token_limit
        char_limit = 2000
        token_limit_for_test = 10 # Very low
        avg_chars = 3 # So, hard char limit target per piece for fallback is ~30 chars

        # A single sentence longer than 10 * 3 = 30 characters.
        long_sentence = "This single sentence is deliberately made very long to test the fallback character splitting mechanism because it will exceed the token limit."
        # Estimated tokens for long_sentence: ceil(len(long_sentence)/3) which will be > 10.

        # Ensure the initial text forms one intermediate_char_chunk
        text = long_sentence 
        chunks = split_text_into_chunks(text, char_limit, token_limit_for_test, avg_chars)

        self.assertTrue(len(chunks) > 1, "Long sentence should have been sub-split by character estimation")
        # Verify each chunk is roughly within char_limit (token_limit * avg_chars)
        expected_char_per_sub_chunk = max(1, int(token_limit_for_test * avg_chars))
        for chunk in chunks:
             self.assertTrue(len(chunk) <= expected_char_per_sub_chunk + 5) # Allow for spaces/stripping

if __name__ == '__main__':
    unittest.main()
