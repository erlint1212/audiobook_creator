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
# Strict Validation & Fallback Chunking
# ==============================================================
def validate_clean_output(text, is_json=False):
    """
    Strictly checks the output. Throws ValueError if a thinking dump is detected.
    """
    text = text.strip()

    # 1. JSON Strict Check
    if is_json:
        if not text.startswith(("{", "[")):
            raise ValueError(
                "Thinking dump detected: Output does not start with JSON brackets."
            )

    # 2. Conversational Filler Check
    lower_text = text.lower()
    thinking_triggers = [
        "thinking process:",
        "the user wants",
        "i need to",
        "here is the",
        "certainly",
        "sure,",
        "let me",
        "i will",
        "i'll",
        "analysis:",
        "step-by-step:",
    ]

    for trigger in thinking_triggers:
        if text.startswith(trigger) or (is_json and trigger in lower_text[:200]):
            raise ValueError(
                f"Thinking dump detected: Found trigger phrase '{trigger}'."
            )

    return text


def chunk_text(text, max_chars=1500):
    """Splits text into smaller chunks by paragraphs for fallback processing."""
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if len(current_chunk) + len(p) > max_chars:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = p + "\n"
        else:
            current_chunk += p + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def call_lmstudio_api(
    model,
    system_prompt,
    user_prompt,
    temperature=0.2,
    max_tokens=-1,
    expect_json=False,
    few_shot_user=None,
    few_shot_assistant=None,
):
    """Base API caller."""
    chat = lms.Chat(system_prompt)
    if few_shot_user and few_shot_assistant:
        chat.add_user_message(few_shot_user)
        chat.add_assistant_response(few_shot_assistant)
    chat.add_user_message(user_prompt)

    config = {"temperature": temperature}
    if max_tokens and max_tokens > 0:
        config["maxTokens"] = max_tokens

    # Attempt to force structured JSON output if server supports it
    if expect_json:
        try:
            config["responseFormat"] = {"type": "json_object"}
        except Exception:
            pass  # fallback if unsupported

    result = model.respond(chat, config=config)
    return str(result) if result else ""


def process_with_retries(
    model,
    system_prompt,
    user_prompt_template,
    text_input,
    is_json,
    max_retries=1,
    temperature=0.2,
    max_tokens=-1,
    few_shot_user=None,
    few_shot_assistant=None,
):
    """Attempts to process text, retrying aggressively on failure. Returns None if all retries fail."""
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            # Format the dynamic text into the prompt
            user_prompt = user_prompt_template.format(text=text_input)

            # Escalate pressure on subsequent attempts
            if attempt > 0 and is_json:
                user_prompt = (
                    "/no_think\n"
                    + user_prompt
                    + "\n\nCRITICAL: Respond with ONLY valid JSON. Start with { immediately. No markdown."
                )
            elif attempt > 0:
                user_prompt = (
                    "/no_think\n"
                    + user_prompt
                    + "\n\nCRITICAL: Respond with ONLY the target text. No commentary."
                )

            raw_response = call_lmstudio_api(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=min(temperature + 0.1 * attempt, 0.5),
                max_tokens=max_tokens,
                expect_json=is_json,
                few_shot_user=few_shot_user,
                few_shot_assistant=few_shot_assistant,
            )

            # Fail fast if there's a thinking dump
            validate_clean_output(raw_response, is_json=is_json)

            if is_json:
                return json.loads(raw_response)  # Will raise JSONDecodeError if invalid
            return raw_response

        except (ValueError, json.JSONDecodeError) as e:
            print(
                f"    ❌ FAILED: {e}. Discarding and restarting (Attempt {attempt+1}/{max_retries})."
            )
        except Exception as e:
            print(f"    ❌ API Error: {e} (Attempt {attempt+1}/{max_retries}).")

        if attempt < max_retries - 1:
            time.sleep(retry_delay)
            retry_delay *= 2

    return None  # Failed after all retries


def process_chapter_robustly(
    model,
    system_prompt,
    user_prompt_template,
    chapter_text,
    is_json=False,
    temperature=0.2,
    max_tokens=-1,
    few_shot_user=None,
    few_shot_assistant=None,
):
    """
    Main entry point for tasks. Tries full text, falls back to chunking if it keeps failing.
    """
    result = process_with_retries(
        model=model,
        system_prompt=system_prompt,
        user_prompt_template=user_prompt_template,
        text_input=chapter_text,
        is_json=is_json,
        max_retries=3,
        temperature=temperature,
        max_tokens=max_tokens,
        few_shot_user=few_shot_user,
        few_shot_assistant=few_shot_assistant,
    )

    if result is not None:
        return result

    print("  ⚠️ Continuous failures on full text. Falling back to chunking strategy...")
    chunks = chunk_text(chapter_text, max_chars=1500)

    if is_json:
        combined_json = {k: {} for k in DEFAULT_GLOSSARY}
    else:
        combined_text = ""

    for i, chunk in enumerate(chunks):
        print(f"  -> Processing sub-chunk {i+1}/{len(chunks)}...")
        chunk_result = process_with_retries(
            model=model,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            text_input=chunk,
            is_json=is_json,
            max_retries=4,  # Give sub-chunks slightly more retries
            temperature=temperature,
            max_tokens=max_tokens,
            few_shot_user=few_shot_user,
            few_shot_assistant=few_shot_assistant,
        )

        if chunk_result is None:
            print(f"  [Fatal Error] Even sub-chunk {i+1} failed completely.")
            return None

        # Stitch results together
        if is_json:
            for key in combined_json.keys():
                if key in chunk_result and isinstance(chunk_result[key], dict):
                    combined_json[key].update(chunk_result[key])
        else:
            combined_text += chunk_result + "\n\n"

    print("  ✅ Successfully stitched all sub-chunks!")
    return combined_json if is_json else combined_text.strip()


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
    prompt_template = (
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
        "--- CHINESE TEXT ---\n{text}\n--- END ---"
    )
    system = (
        "You are a data extractor. Output ONLY valid JSON. "
        "No markdown, no explanation, no code fences. "
        "Start your response with { and end with }."
    )

    print(f"  [Pass 1/2] Extracting glossary...")

    items = process_chapter_robustly(
        model=model,
        system_prompt=system,
        user_prompt_template=prompt_template,
        chapter_text=original_chinese,
        is_json=True,
        temperature=0.1,
        few_shot_user=few_shot_user,
        few_shot_assistant=few_shot_assistant,
    )

    if not items:
        print(f"  [Pass 1/2] Glossary extraction completely failed.")
        return {}

    # Ensure all category keys exist and are dicts
    for key in DEFAULT_GLOSSARY:
        if key not in items or not isinstance(items.get(key), dict):
            items[key] = {}
        else:
            # Remove any entries that aren't dicts themselves
            bad_keys = [k for k, v in items[key].items() if not isinstance(v, dict)]
            for bk in bad_keys:
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
    prompt_template = (
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
        f"--- CHINESE TEXT ---\n{{text}}\n--- END ---\n\n"
        f"Output ONLY the translated text. No reasoning, no commentary."
    )
    system = (
        "You are a professional translation engine. Output ONLY the final English translation. "
        "No reasoning, no chain of thought, no meta-commentary. Start immediately with the translation."
    )
    output_budget = _output_token_budget(glossary_json_str)
    print(f"  [Pass 2/2] Translating (max_tokens={output_budget})...")

    translation = process_chapter_robustly(
        model=model,
        system_prompt=system,
        user_prompt_template=prompt_template,
        chapter_text=text_to_translate,
        is_json=False,
        temperature=0.2,
        max_tokens=output_budget,
        few_shot_user=few_shot_user,
        few_shot_assistant=few_shot_assistant,
    )

    if not translation:
        return None

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

    # Single glossary pass on full text (which now falls back to chunking if it fails)
    new_glossary_items = _glossary_pass(model, text_to_translate)

    filtered_new = {key: {} for key in DEFAULT_GLOSSARY}
    for cat in DEFAULT_GLOSSARY:
        for name, details in new_glossary_items.get(cat, {}).items():
            if name not in known_glossary_data.get(cat, {}):
                filtered_new[cat][name] = details
                filtered_glossary[cat][name] = details

    combined = json.dumps(filtered_glossary, ensure_ascii=False, separators=(",", ":"))

    # Chunk for context window (Token Budget), translate each
    chunks = chunk_for_context(text_to_translate, combined)
    translations = []

    for j, chunk in enumerate(chunks):
        if len(chunks) > 1:
            print(f"  Context Chunk {j+1}/{len(chunks)} ({len(chunk)} chars)...")

        t = _translate_pass(model, chunk, combined, target_language)

        if t is None:
            return f"[Translation Error - chunk {j+1} failed completely]", {}
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
