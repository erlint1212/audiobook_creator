import ast
import json
import math
import os
import re
import time

from constants import *
from logger import log_chapter_translation

try:
    import lmstudio as lms
except ImportError:
    print(
        "CRITICAL ERROR: The 'lmstudio' package is not installed. "
        "Please install it by running: pip install lmstudio"
    )
    exit()

# --- Configuration (GUI passes these via environment variables) ---
INPUT_DIR = os.getenv("PROJECT_TRANS_INPUT_DIR", "01_Raw_Text")
OUTPUT_DIR = os.getenv("PROJECT_TRANS_OUTPUT_DIR", "02_Translated")
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "localhost:1234")
LMSTUDIO_MODEL_NAME = os.getenv("LMSTUDIO_MODEL_NAME", "")
API_TIMEOUT_SECONDS = 600
GLOSSARY_JSON_FILE = "translation_glossary.json"

# Set SDK-wide timeout for sync operations
lms.set_sync_api_timeout(API_TIMEOUT_SECONDS)

DEFAULT_GLOSSARY = {
    "characters": {},
    "places": {},
    "organizations": {},
    "items": {},
    "skills": {},
    "species": {},
}


# ==============================================================
# Context Window Budget
# ==============================================================


def _max_input_tokens(glossary_json_str):
    """How many tokens of Chinese source text we can fit."""
    glossary_tokens = math.ceil(len(glossary_json_str) / AVG_CHARS_PER_TOKEN_EN)
    available = int(CONTEXT_LIMIT * SAFETY_MARGIN)
    # input_zh_tokens + output_en_tokens <= available - overhead - glossary
    # output_tokens ≈ input_zh_tokens * OUTPUT_RATIO * (ZH/EN) ≈ input_zh_tokens * 0.94
    # input_tokens * (1 + 0.94) <= budget  →  input_tokens <= budget / 1.94
    budget = available - PROMPT_OVERHEAD_TOKENS - glossary_tokens
    max_input = int(budget / 1.94)
    return max(200, max_input)


def _output_token_budget(glossary_json_str):
    """Max tokens to allow for generation output."""
    return int(_max_input_tokens(glossary_json_str) * 0.94 * 1.1)


def chunk_for_context(text, glossary_json_str):
    """Split Chinese source text into chunks that fit the context window."""
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

    print(
        f"  Split into {len(chunks)} chunks (max ~{max_chars} chars/chunk, ctx={CONTEXT_LIMIT})"
    )
    return chunks


# ==============================================================
# Thinking Dump Detection
# ==============================================================
def _is_thinking_dump(text):
    """Detect interleaved reasoning dumps vs clean translation."""
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
    # CJK chars in output = source text leaking through
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    if cjk_count > THINKING_DUMP_CJK_THRESHOLD:
        indicators += 3
    return indicators >= THINKING_DUMP_INDICATOR_THRESHOLD


# ==============================================================
# Robust JSON Repair
# ==============================================================
def _repair_json_string(raw):
    """
    Attempt to repair common JSON malformations from local LLMs.
    By this point, thinking dumps have already been detected and retried —
    this only handles legitimately malformed JSON.
    Returns (parsed_dict, success_bool).
    """
    if not raw or not raw.strip():
        return {}, False

    text = raw.strip()

    # 1. Strip markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"\s*```", "", text)
    text = text.strip()

    # 2. Strip short preamble before the first '{'
    #    (e.g. "Here is the JSON:\n{...")
    first_brace = text.find("{")
    if first_brace == -1:
        return {}, False
    text = text[first_brace:]

    # 3. Find the matching closing brace (string-aware)
    depth, end_pos = 0, -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_pos = i
                break

    if end_pos > 0:
        text = text[: end_pos + 1]
    elif depth > 0:
        # Truncated JSON — try to close it
        print(f"  [JSON Repair] Attempting to close truncated JSON (depth={depth})...")
        text = re.sub(r',\s*"[^"]*$', "", text)  # remove trailing partial key
        text = re.sub(r",\s*$", "", text)  # remove trailing comma
        text += "}" * depth

    # 4. Remove single-line comments (// ...)
    text = re.sub(r"//[^\n]*", "", text)

    # 5. Remove trailing commas before } or ]
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # 6. Replace Python-style True/False/None with true/false/null
    text = _replace_python_literals(text)

    # 7. Remove control characters that break JSON (except normal whitespace)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)

    # --- Attempt 1: Direct parse ---
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed, True
    except json.JSONDecodeError:
        pass

    # --- Attempt 2: Replace single quotes with double quotes ---
    try:
        fixed = _single_to_double_quotes(text)
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            return parsed, True
    except (json.JSONDecodeError, ValueError):
        pass

    # --- Attempt 3: Fix unquoted keys ---
    try:
        fixed = re.sub(
            r"(?<=[\{,])\s*([a-zA-Z_][\w]*)\s*:",
            r' "\1":',
            text,
        )
        parsed = json.loads(fixed)
        if isinstance(parsed, dict):
            return parsed, True
    except json.JSONDecodeError:
        pass

    # --- Attempt 4: ast.literal_eval for Python dict syntax ---
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, dict):
            return json.loads(json.dumps(parsed, ensure_ascii=False)), True
    except (ValueError, SyntaxError):
        pass

    # --- Attempt 5: Line-by-line rescue ---
    lines = text.split("\n")
    for trim in range(1, min(5, len(lines))):
        candidate = "\n".join(lines[:-trim])
        open_count = candidate.count("{") - candidate.count("}")
        if open_count > 0:
            candidate += "}" * open_count
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed, True
        except json.JSONDecodeError:
            continue

    return {}, False


def _replace_python_literals(s):
    """Replace True/False/None with true/false/null outside quoted strings."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '"':
            j = i + 1
            while j < len(s):
                if s[j] == "\\":
                    j += 2
                    continue
                if s[j] == '"':
                    j += 1
                    break
                j += 1
            result.append(s[i:j])
            i = j
        else:
            for py_val, js_val in [
                ("True", "true"),
                ("False", "false"),
                ("None", "null"),
            ]:
                if s[i : i + len(py_val)] == py_val:
                    before_ok = i == 0 or not s[i - 1].isalnum()
                    after_ok = (
                        i + len(py_val) >= len(s) or not s[i + len(py_val)].isalnum()
                    )
                    if before_ok and after_ok:
                        result.append(js_val)
                        i += len(py_val)
                        break
            else:
                result.append(s[i])
                i += 1
    return "".join(result)


def _single_to_double_quotes(text):
    """
    Replace single-quoted strings with double-quoted strings in JSON-like text.
    Handles escaped quotes and mixed quoting.
    """
    result = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            # Already a double-quoted string — skip it
            result.append('"')
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    result.append(text[i : i + 2])
                    i += 2
                    continue
                result.append(text[i])
                if text[i] == '"':
                    i += 1
                    break
                i += 1
        elif text[i] == "'":
            # Single-quoted string — convert to double
            result.append('"')
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    result.append(text[i : i + 2])
                    i += 2
                    continue
                if text[i] == "'":
                    result.append('"')
                    i += 1
                    break
                # Escape any unescaped double quotes inside
                if text[i] == '"':
                    result.append('\\"')
                else:
                    result.append(text[i])
                i += 1
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


# ==============================================================
# Glossary / File I/O
# ==============================================================
def load_glossary_from_json(filepath):
    if not os.path.exists(filepath):
        print(
            f"Glossary JSON file not found at '{filepath}'. A new one will be created."
        )
        return dict(DEFAULT_GLOSSARY)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key in DEFAULT_GLOSSARY:
                if key not in data:
                    data[key] = {}
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading glossary '{filepath}': {e}. Starting fresh.")
        return dict(DEFAULT_GLOSSARY)


def save_glossary_to_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved glossary to '{filepath}'.")
    except IOError as e:
        print(f"Error writing glossary '{filepath}': {e}")


def reformat_chapter_title_in_text(text_content):
    if not text_content or not text_content.strip():
        return text_content
    lines = text_content.split("\n", 1)
    first_line = lines[0]
    rest = lines[1] if len(lines) > 1 else ""
    match = re.match(
        r"^(Chapter\s*\d+)\s*[:\-\u2013\u2014]?\s*(.*)", first_line, re.IGNORECASE
    )
    if match:
        ch, title = match.group(1).strip(), match.group(2).strip()
        return f"{ch} - {title}\n{rest}" if title else f"{ch}\n{rest}"
    numeric = re.match(r"^(\d+)\s+(.*)", first_line)
    if numeric:
        try:
            return (
                f"Chapter {int(numeric.group(1))} - {numeric.group(2).strip()}\n{rest}"
            )
        except ValueError:
            pass
    return text_content


def list_available_models(host=None):
    """Returns loaded LLM model identifiers. Used by the GUI."""
    try:
        if host:
            clean = host.replace("http://", "").replace("https://", "").rstrip("/")
            if clean.endswith("/v1"):
                clean = clean[:-3]
            with lms.Client(clean) as client:
                return [m.model_key for m in client.list_loaded_models("llm")]
        else:
            return [m.model_key for m in lms.list_loaded_models("llm")]
    except Exception as e:
        print(f"Error fetching models: {type(e).__name__}: {e}")
        return []


# ==============================================================
# Extraction / Cleaning
# ==============================================================
def _extract_translation_content(text):
    if not text:
        return text
    original_len = len(text)
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>\s*", "", text, flags=re.DOTALL)
    thinking_headers = [
        r"Thinking Process\s*:",
        r"Analysis\s*:",
        r"Let me (?:think|analyze|break)",
        r"Step-by-step\s*:",
        r"\d+\.\s+\*\*Analyze",
        r"I'll (?:start|begin) by",
        r"I need to (?:translate|analyze|consider)",
        r"First,? (?:let me|I'll|I need)",
        r"The user wants",
        r"I need to follow",
        r"\*\*Text Analysis",
    ]
    if re.match(rf"^\s*(?:{'|'.join(thinking_headers)})", text, re.IGNORECASE):
        content_markers = [
            r"\n---+\s*\n",
            r"\nTranslation\s*:\s*\n",
            r"\nFinal (?:Translation|Output)\s*:\s*\n",
            r"\nChapter\s+\d+",
            r"\n\u7b2c\s*\d+\s*\u7ae0",
            r"\nHere is the translation:\s*\n",
        ]
        best_pos = -1
        for marker in content_markers:
            m = re.search(marker, text, re.IGNORECASE)
            if m:
                pos = (
                    m.start() + 1
                    if marker.startswith(r"\nChapter") or marker.startswith(r"\n\u7b2c")
                    else m.end()
                )
                if best_pos == -1 or pos < best_pos:
                    best_pos = pos
        if best_pos > 0:
            text = text[best_pos:]
        else:
            parts = text.split("\n\n", 1)
            if len(parts) > 1:
                print(f"  [DEBUG] Dropping first paragraph as assumed reasoning.")
                text = parts[1]
    text = text.strip()
    stripped = original_len - len(text)
    if stripped > 50:
        print(f"  Extracted translation (stripped {stripped} chars of reasoning).")
    return text


# ==============================================================
# Thinking-Dump Detection for JSON Responses
# ==============================================================
def _is_json_thinking_dump(raw):
    """
    Detect if a response that should be JSON is actually a thinking dump.
    Returns True if the model dumped its reasoning instead of outputting JSON.
    """
    if not raw or not raw.strip():
        return True  # empty = failed

    text = raw.strip()

    # Strip tagged thinking (these are expected and fine — check what's left)
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>\s*", "", text, flags=re.DOTALL)
    text = text.strip()

    # If after stripping tags we have something starting with '{', it's not a dump
    if text.startswith("{"):
        return False

    # If there's no '{' at all, it's definitely a dump
    if "{" not in text:
        return True

    # There's a '{' somewhere but the response leads with reasoning text.
    # Check how much preamble there is before the first '{'
    first_brace = text.index("{")
    preamble = text[:first_brace].strip()

    # A short preamble like "Here is the JSON:" is tolerable
    if len(preamble) < 80:
        return False

    # Long preamble = thinking dump
    return True


# ==============================================================
# LM Studio API Call (with thinking dump retry)
# ==============================================================
def _call_lmstudio(
    model,
    system_prompt,
    user_prompt,
    temperature=0.2,
    max_tokens=-1,
    expect_json=False,
    few_shot_user=None,
    few_shot_assistant=None,
):
    max_retries = 3
    retry_delay = 10
    for attempt in range(max_retries):
        try:
            chat = lms.Chat(system_prompt)
            if few_shot_user and few_shot_assistant:
                chat.add_user_message(few_shot_user)
                chat.add_assistant_response(few_shot_assistant)
            chat.add_user_message(user_prompt)
            config = {"temperature": temperature}
            if max_tokens and max_tokens > 0:
                config["maxTokens"] = max_tokens

            # Force structured JSON output when we expect JSON.
            # LM Studio applies grammar-level constraints so the model
            # can only emit valid JSON tokens.
            if expect_json:
                config["responseFormat"] = {"type": "json_object"}

            result = model.respond(chat, config=config)
            raw = str(result) if result else ""
            if expect_json:
                # Strip tagged thinking blocks (legitimate format)
                raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL)
                raw = re.sub(r"<reasoning>.*?</reasoning>\s*", "", raw, flags=re.DOTALL)
                raw = raw.strip()

                # Thinking dump detection → retry
                if _is_json_thinking_dump(raw):
                    if attempt < max_retries - 1:
                        print(
                            f"  ⚠ JSON thinking dump detected. "
                            f"Retrying {attempt+1}/{max_retries} in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(
                            f"  ⚠ JSON thinking dump on final attempt. Returning as-is."
                        )
                return raw
            else:
                cleaned = _extract_translation_content(raw)
                # Thinking dump detection → retry
                if _is_thinking_dump(cleaned):
                    if attempt < max_retries - 1:
                        print(
                            f"  ⚠ Thinking dump detected. "
                            f"Retrying {attempt+1}/{max_retries} in {retry_delay}s..."
                        )
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"  ⚠ Thinking dump on final attempt. Returning as-is.")
                return cleaned
        except TimeoutError:
            print(f"  Timeout. Retrying {attempt+1}/{max_retries} in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
            if attempt == max_retries - 1:
                return None
        except Exception as e:
            err_msg = str(e).lower()
            # If the model/server doesn't support responseFormat, fall back
            if expect_json and (
                "responseformat" in err_msg
                or "response_format" in err_msg
                or "unsupported" in err_msg
                or "not supported" in err_msg
            ):
                print(
                    f"  [INFO] JSON mode not supported by this model, retrying without it..."
                )
                config.pop("responseFormat", None)
                try:
                    result = model.respond(chat, config=config)
                    raw = str(result) if result else ""
                    raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL)
                    raw = re.sub(
                        r"<reasoning>.*?</reasoning>\s*", "", raw, flags=re.DOTALL
                    )
                    raw = raw.strip()
                    if not _is_json_thinking_dump(raw):
                        return raw
                    # Thinking dump — fall through to retry
                    print(f"  ⚠ JSON thinking dump on fallback. Will retry...")
                except Exception as e2:
                    print(f"  Error on fallback ({type(e2).__name__}): {e2}")
            else:
                print(f"  Error ({type(e).__name__}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return None
    return None


# ==============================================================
# Pass 1: Glossary Extraction
# ==============================================================
def _glossary_pass(model, original_chinese):
    few_shot_user = (
        "Extract entities from: "
        "\u5170\u6ce2\u5e26\u7740\u7834\u5984\u5251\u53bb\u4e86"
        "\u6e05\u6cb3\u5e02\u7684\u5929\u8f89\u9a91\u58eb\u56e2\u3002"
    )
    few_shot_assistant = json.dumps(
        {
            "characters": {
                "\u5170\u6ce2": {
                    "pinyin": "Lan Bo",
                    "english_name": "Lan Bo",
                    "pronoun": "he/him",
                }
            },
            "places": {
                "\u6e05\u6cb3\u5e02": {
                    "pinyin": "Qinghe Shi",
                    "english_name": "Qinghe City",
                }
            },
            "organizations": {
                "\u5929\u8f89\u9a91\u58eb\u56e2": {
                    "pinyin": "Tianhui Qishi Tuan",
                    "english_name": "Radiant Knights",
                }
            },
            "items": {
                "\u7834\u5984\u5251": {
                    "pinyin": "Po Wang Jian",
                    "english_name": "Delusion Breaker",
                }
            },
            "skills": {},
            "species": {},
        },
        ensure_ascii=False,
    )
    prompt = (
        "You are a named entity extraction assistant for Chinese fantasy/web novels.\n"
        "Given the Chinese text below, extract ALL named entities and provide English translations.\n\n"
        "CATEGORIES:\n"
        '- "characters": People/beings. Needs "pinyin", "english_name", "pronoun".\n'
        '- "places": Cities, buildings, towers, dungeons. Needs "pinyin", "english_name".\n'
        '- "organizations": Orders, sects, guilds, factions, clans. Needs "pinyin", "english_name".\n'
        '- "items": Weapons, artifacts, tools, potions, books. Needs "pinyin", "english_name".\n'
        '- "skills": Techniques, spells, formations. Needs "pinyin", "english_name".\n'
        '- "species": Races, creature types, bloodlines. Needs "pinyin", "english_name".\n\n'
        "DISAMBIGUATION:\n"
        "- \u9a91\u58eb\u56e2 (knight order) \u2192 ORGANIZATION, not place.\n"
        "- \u57ce (city) / \u5854 (tower) \u2192 PLACE, not organization.\n"
        "- \u5251/\u6756/named weapon \u2192 ITEM, not character or skill.\n"
        "- \u672f (technique) / \u9635 (formation) \u2192 SKILL, not item.\n"
        "- \u65cf (race) / \u79cd (species) \u2192 SPECIES. But \u65cf as family/clan \u2192 ORGANIZATION.\n\n"
        "Return JSON with all six keys. Empty objects for empty categories.\n"
        "ONLY the JSON. No markdown, no explanation.\n\n"
        f"--- CHINESE TEXT ---\n{original_chinese}\n--- END ---"
    )
    system = (
        "You are a data extractor. Output ONLY valid JSON. "
        "No markdown, no explanation, no code fences. "
        "Start your response with { and end with }."
    )
    print(f"  [Pass 1/2] Extracting glossary...")
    raw = _call_lmstudio(
        model,
        system,
        prompt,
        temperature=0.1,
        expect_json=True,
        few_shot_user=few_shot_user,
        few_shot_assistant=few_shot_assistant,
    )
    if raw is None:
        print(f"  [Pass 1/2] Glossary extraction failed (no response).")
        return {}

    # Use the robust JSON repair pipeline
    items, success = _repair_json_string(raw)

    if not success:
        # Log the raw output so the user can diagnose which model is misbehaving
        preview = raw[:300].replace("\n", "\\n")
        print(f"  [Pass 1/2] JSON parse failed after all repair attempts.")
        print(f"  [Pass 1/2] Raw preview: {preview}")
        return {}

    if not isinstance(items, dict):
        print(f"  [Pass 1/2] Parsed result is not a dict (got {type(items).__name__}).")
        return {}

    # Ensure all category keys exist
    for key in DEFAULT_GLOSSARY:
        if key not in items:
            items[key] = {}

    # Validate structure: each category should be a dict of dicts
    for key in DEFAULT_GLOSSARY:
        if not isinstance(items.get(key), dict):
            print(f"  [Pass 1/2] Category '{key}' is not a dict, clearing it.")
            items[key] = {}
        else:
            # Remove any entries that aren't dicts themselves
            bad_keys = [k for k, v in items[key].items() if not isinstance(v, dict)]
            for bk in bad_keys:
                print(f"  [Pass 1/2] Removing malformed entry '{bk}' in '{key}'.")
                del items[key][bk]

    counts = [f"{len(items[k])} {k}" for k in DEFAULT_GLOSSARY if items.get(k)]
    print(f"  [Pass 1/2] Extracted: {', '.join(counts) if counts else 'nothing'}.")
    return items


# ==============================================================
# Pass 2: Translation
# ==============================================================
def _translate_pass(model, text_to_translate, glossary_json_str, target_language):
    few_shot_user = (
        "Translate into English. Output ONLY the translation.\n\n"
        "--- CHINESE TEXT ---\n"
        "\u90a3\u4e2a\u53eb\u59ec\u767d\u7684\u9a91\u58eb\u6325\u821e\u7740"
        "\u7834\u5984\u5251\uff0c\u8bf4\u9053\uff1a\u201c\u8fd9\u6ce2\u662f"
        "\u4e94\u4e94\u5f00\uff0c\u4f60\u4eec\u5148\u6492\u3002\u201d\n"
        "\u8001\u9a91\u58eb\u70b9\u4e86\u70b9\u5934\uff0c\u8f6c\u8eab\u79bb\u5f00\u3002\n"
        "--- END ---"
    )
    few_shot_assistant = (
        "The knight named Ji Bai swung the Delusion Breaker and said, "
        '"This is a fifty-fifty^[A gaming meme from Chinese esports meaning an even '
        "split, often used sarcastically when the odds are clearly not equal.], "
        'you all retreat first."\n'
        "The old knight nodded and turned to leave."
    )
    prompt = (
        f"You are an expert Chinese-to-English translator.\n"
        f"Translate the Chinese text below into high-quality, natural-sounding {target_language}.\n\n"
        f"RULES:\n"
        f"- Use 'english_name' from the glossary below for all known names.\n"
        f"- Pronouns: Chinese often omits them. Infer from context.\n"
        f"- Titles: Translate \u8001\u7237\u5b50, \u5e08\u5144, \u5144\u5f1f etc. contextually, not literally.\n\n"
        f"ANNOTATION RULES \u2014 BE EXTREMELY SELECTIVE:\n"
        f"Only annotate with ^[explanation] for things genuinely obscure to non-Chinese readers.\n\n"
        f"DO annotate:\n"
        f"- Internet memes/slang with no English equivalent (\u4e94\u4e94\u5f00, \u67e0\u6aac\u7cbe, 996, \u8eba\u5e73)\n"
        f"- Homophonic puns where the joke is lost in translation\n"
        f"- References to specific Chinese pop culture, history, or social media\n"
        f"- Idioms kept literal for style where meaning is non-obvious\n\n"
        f"DO NOT annotate:\n"
        f"- Standard idioms already translated into natural English\n"
        f"- Words clear from context ('demon race', 'knight order', 'magic array')\n"
        f"- Character names, place names, or titles\n"
        f"- Common expressions, greetings, emotional reactions\n"
        f"- Self-explanatory fantasy/cultivation terms\n"
        f"- Anything where the English already conveys the meaning\n\n"
        f"When in doubt, DO NOT annotate. Zero annotations per chapter is fine.\n\n"
        f"GLOSSARY:\n{glossary_json_str}\n\n"
        f"--- CHINESE TEXT ---\n{text_to_translate}\n--- END ---\n\n"
        f"Output ONLY the translated text. No reasoning, no commentary."
    )
    system = (
        "You are a professional translation engine. Output ONLY the final English translation. "
        "No reasoning, no chain of thought, no meta-commentary. Start immediately with the translation."
    )
    output_budget = _output_token_budget(glossary_json_str)
    print(f"  [Pass 2/2] Translating (max_tokens={output_budget})...")
    raw = _call_lmstudio(
        model,
        system,
        prompt,
        temperature=0.2,
        max_tokens=output_budget,
        few_shot_user=few_shot_user,
        few_shot_assistant=few_shot_assistant,
    )
    if raw is None:
        return None
    if raw == "":
        return None
    translation = re.sub(
        r"^(Here is|Here's|Below is|The translation)[^\n]*\n+",
        "",
        raw.strip(),
        flags=re.IGNORECASE,
    ).strip()
    print(f"  [Pass 2/2] Translation complete ({len(translation)} chars).")
    return translation


# ==============================================================
# Main Translation Orchestrator
# ==============================================================
def translate_text_with_lmstudio(
    text_to_translate, known_glossary_data, target_language="English"
):
    model_name = LMSTUDIO_MODEL_NAME
    if not model_name:
        return "[Translation Error: No LM Studio model selected.]", {}
    try:
        model = lms.llm(model_name)
    except Exception as e:
        return f"[Translation Error: {type(e).__name__}: {e}]", {}

    filtered_glossary = {key: {} for key in DEFAULT_GLOSSARY}
    for cat in DEFAULT_GLOSSARY:
        for k, v in known_glossary_data.get(cat, {}).items():
            if k in text_to_translate:
                filtered_glossary[cat][k] = v

    print(f"Translating with '{model_name}' ({len(text_to_translate)} chars)...")

    # Single glossary pass on full text
    new_glossary_items = _glossary_pass(model, text_to_translate)
    filtered_new = {key: {} for key in DEFAULT_GLOSSARY}
    for cat in DEFAULT_GLOSSARY:
        for name, details in new_glossary_items.get(cat, {}).items():
            if name not in known_glossary_data.get(cat, {}):
                filtered_new[cat][name] = details
                filtered_glossary[cat][name] = details

    combined = json.dumps(filtered_glossary, ensure_ascii=False, separators=(",", ":"))

    # Chunk for context window, translate each
    chunks = chunk_for_context(text_to_translate, combined)
    translations = []
    for j, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  Chunk {j+1}/{len(chunks)} ({len(chunk)} chars)...")
        t = _translate_pass(model, chunk, combined, target_language)
        if t is None:
            return f"[Translation Error - chunk {j+1} failed]", {}
        translations.append(t)

    return "\n\n".join(translations), filtered_new


# ==============================================================
# File Processing Loop
# ==============================================================
def process_files_for_translation():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = (
        INPUT_DIR if os.path.isabs(INPUT_DIR) else os.path.join(script_dir, INPUT_DIR)
    )
    output_dir = (
        OUTPUT_DIR
        if os.path.isabs(OUTPUT_DIR)
        else os.path.join(script_dir, OUTPUT_DIR)
    )
    project_root = os.path.dirname(input_dir)
    glossary_path = os.path.join(project_root, GLOSSARY_JSON_FILE)
    glossary_data = load_glossary_from_json(glossary_path)

    if not os.path.exists(input_dir):
        print(f"Error: Input directory '{input_dir}' not found.")
        return
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    files = sorted([f for f in os.listdir(input_dir) if f.endswith(".txt")])
    if not files:
        print(f"No .txt files found in '{input_dir}'.")
        return

    print(f"Found {len(files)} file(s). Model: {LMSTUDIO_MODEL_NAME}")
    print(f"Mode: Two-pass (Glossary Extraction \u2192 Translation)")
    print(f"Context limit: {CONTEXT_LIMIT} tokens (safety margin: {SAFETY_MARGIN})")

    for i, filename in enumerate(files):
        in_path = os.path.join(input_dir, filename)
        out_path = os.path.join(output_dir, filename)
        print(f"\n[{i+1}/{len(files)}] Checking: {filename}...")

        if os.path.exists(out_path):
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    check = f.read(200)
                    if (
                        "[Translation Error" not in check
                        and "[ERROR PROCESSING FILE" not in check
                    ):
                        print(f"Output exists and is valid. Skipping.")
                        continue
                    else:
                        print(f"Output contains error marker. Re-translating.")
            except Exception:
                pass

        print(f"Processing: {filename}")
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                source = f.read()
            clean = "\n".join(
                l
                for l in source.splitlines()
                if l.strip() and re.search(r"[\u4e00-\u9fff]", l)
            ).strip()

            if not clean:
                translated = "[No Chinese content found in source]"
            else:
                translated, new_items = translate_text_with_lmstudio(
                    clean, glossary_data
                )
                if new_items:
                    for cat in DEFAULT_GLOSSARY:
                        for name, details in new_items.get(cat, {}).items():
                            if name not in glossary_data.get(cat, {}):
                                if cat not in glossary_data:
                                    glossary_data[cat] = {}
                                glossary_data[cat][name] = details
                                print(f"    + [{cat}] {name} -> {details}")

            final = (
                translated
                if translated.startswith("[")
                else reformat_chapter_title_in_text(translated)
            )
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(final)
            print(f"Saved: {out_path}")
            save_glossary_to_json(glossary_path, glossary_data)

            log_chapter_translation(filename, LMSTUDIO_MODEL_NAME)

            if i < len(files) - 1:
                time.sleep(1.0)
        except Exception as e:
            print(f"FATAL Error: {e}")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"[ERROR PROCESSING FILE: {e}]")

            log_chapter_translation(filename, LMSTUDIO_MODEL_NAME, f"Error: {e}")

    print(f"\n--- Translation Run Summary ---")
    print(f"Total: {len(files)} files checked")


if __name__ == "__main__":
    print("Starting translation (LM Studio SDK)...")
    if not LMSTUDIO_MODEL_NAME:
        print("CRITICAL: LMSTUDIO_MODEL_NAME not set.")
        exit()
    print(f"Model: {LMSTUDIO_MODEL_NAME}")
    models = list_available_models()
    if models:
        print(f"Loaded models: {models}")
    else:
        print("WARNING: No models found. Is LM Studio running?")
    process_files_for_translation()
    print("Done.")
