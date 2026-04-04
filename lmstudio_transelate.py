import json
import os
import re
import sys
import time

# LM Studio exposes an OpenAI-compatible API, so we reuse the openai package.
try:
    from openai import APIError, APITimeoutError, OpenAI
except ImportError:
    print(
        "CRITICAL ERROR: The 'openai' package is not installed. Please install it by running: pip install openai"
    )
    exit()

# --- Configuration (GUI passes these via environment variables) ---
INPUT_DIR = os.getenv("PROJECT_TRANS_INPUT_DIR", "01_Raw_Text")
OUTPUT_DIR = os.getenv("PROJECT_TRANS_OUTPUT_DIR", "02_Translated")
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
LMSTUDIO_MODEL_NAME = os.getenv("LMSTUDIO_MODEL_NAME", "")
API_TIMEOUT_SECONDS = 600.0
GLOSSARY_JSON_FILE = "translation_glossary.json"


# --- Glossary Helper Functions ---
def load_glossary_from_json(filepath: str) -> dict:
    """
    Loads a glossary dictionary (for characters and places) from a JSON file.
    If the file doesn't exist or is invalid, it returns a new dictionary structure.
    """
    default_glossary = {"characters": {}, "places": {}}
    if not os.path.exists(filepath):
        print(
            f"Glossary JSON file not found at '{filepath}'. A new one will be created."
        )
        return default_glossary
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "characters" not in data:
                data["characters"] = {}
            if "places" not in data:
                data["places"] = {}
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading or parsing JSON file '{filepath}': {e}. Starting fresh.")
        return default_glossary


def save_glossary_to_json(filepath: str, data: dict):
    """Saves a glossary dictionary to a JSON file with pretty printing."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved updated glossary to '{filepath}'.")
    except IOError as e:
        print(f"Error writing to JSON file '{filepath}': {e}")


# --- Helper Function to Reformat Title ---
def reformat_chapter_title_in_text(text_content: str) -> str:
    if not text_content or not text_content.strip():
        return text_content

    lines = text_content.split("\n", 1)
    first_line = lines[0]
    rest_of_content = lines[1] if len(lines) > 1 else ""

    match = re.match(
        r"^(Chapter\s*\d+)\s*[:\-\u2013\u2014]?\s*(.*)", first_line, re.IGNORECASE
    )
    if match:
        chapter_part = match.group(1).strip()
        title_part = match.group(2).strip()
        reformatted_first_line = (
            f"{chapter_part} - {title_part}" if title_part else chapter_part
        )
        return f"{reformatted_first_line}\n{rest_of_content}"

    numeric_match = re.match(r"^(\d+)\s+(.*)", first_line)
    if numeric_match:
        try:
            chapter_number_int = int(numeric_match.group(1))
            title_part = numeric_match.group(2).strip()
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            return f"{reformatted_first_line}\n{rest_of_content}"
        except ValueError:
            pass
    return text_content


# --- Utility: List available models from LM Studio ---
def list_available_models(base_url: str) -> list:
    """
    Queries the LM Studio /v1/models endpoint and returns a list of model IDs.
    This is used by the GUI to populate the model dropdown.
    """
    import urllib.error
    import urllib.request

    models_url = base_url.rstrip("/")
    if models_url.endswith("/v1"):
        models_url += "/models"
    elif not models_url.endswith("/models"):
        models_url += "/v1/models"

    try:
        req = urllib.request.Request(models_url)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            model_ids = [m["id"] for m in data.get("data", []) if "id" in m]
            return model_ids
    except urllib.error.URLError as e:
        print(f"Error connecting to LM Studio at '{models_url}': {e}")
        return []
    except Exception as e:
        print(f"Error fetching models: {type(e).__name__}: {e}")
        return []


# --- Extract actual content from thinking-model output ---
def _extract_translation_content(text):
    """
    When a thinking model leaks its reasoning, this extracts the translation.
    If no clear marker is found, it falls back to dropping the first paragraph
    instead of throwing away the entire response.
    """
    if not text:
        return text

    original_len = len(text)

    # 1. Strip standard thinking tags
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    text = re.sub(r"<reasoning>.*?</reasoning>\s*", "", text, flags=re.DOTALL)

    # 2. Handle freeform thinking preamble
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
    header_pattern = "|".join(thinking_headers)

    if re.match(rf"^\s*(?:{header_pattern})", text, re.IGNORECASE):
        # Look for transition markers
        content_markers = [
            r"\n---+\s*\n",
            r"\nTranslation\s*:\s*\n",
            r"\nFinal (?:Translation|Output)\s*:\s*\n",
            r"\nChapter\s+\d+",
            r"\n第\s*\d+\s*章",
            r"\nHere is the translation:\s*\n",
        ]
        best_pos = -1
        for marker in content_markers:
            m = re.search(marker, text, re.IGNORECASE)
            if m:
                if marker.startswith(r"\nChapter") or marker.startswith(r"\n第"):
                    pos = m.start() + 1
                else:
                    pos = m.end()
                if best_pos == -1 or pos < best_pos:
                    best_pos = pos

        if best_pos > 0:
            text = text[best_pos:]
        else:
            # NEW FALLBACK: Instead of failing, drop the first paragraph and continue.
            preview = text[:150].replace("\n", " ")
            print(f"  [DEBUG] Reasoning detected, but no clear transition marker.")
            print(f"  [DEBUG] Preview: '{preview}...'")

            parts = text.split("\n\n", 1)
            if len(parts) > 1:
                print(f"  [DEBUG] Dropping first paragraph as assumed reasoning.")
                text = parts[1]
            else:
                print(f"  [DEBUG] Returning raw text to avoid pipeline crash.")

    text = text.strip()

    stripped = original_len - len(text)
    if stripped > 50:
        print(
            f"  Extracted translation from thinking output (stripped {stripped} chars)."
        )

    return text


# --- Shared: LLM call with retry logic ---
# --- Shared: LLM call with retry logic ---
def _call_lmstudio(
    client,
    model_name,
    system_prompt,
    user_prompt,
    temperature=0.2,
    max_tokens=None,
    expect_json=False,
):
    """
    Makes a single LLM call to LM Studio with retry logic.
    Uses Few-Shot Injection to force the model to obey the format.
    """
    max_retries = 3
    retry_delay = 10

    # --- FEW-SHOT INJECTION ---
    # We inject a fake conversation history to show the model exactly how to behave.
    # This completely breaks its habit of writing "1. Analyze the text..."
    if expect_json:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Extract characters and places from: 兰波去了清河市。",
            },
            {
                "role": "assistant",
                "content": '{"characters": {"兰波": {"pinyin": "Lan Bo", "english_name": "Lan Bo", "pronoun": "he/him"}}, "places": {"清河市": {"pinyin": "Qinghe Shi", "english_name": "Qinghe City"}}}',
            },
            {"role": "user", "content": user_prompt},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Translate the following text into English. Output ONLY the translation. \n\n--- CHINESE TEXT ---\n那个叫姬白的骑士挥舞着破妄剑。这波是五五开。\n--- END ---",
            },
            {
                "role": "assistant",
                "content": "The knight named Ji Bai swung the sword of illusion breaking. This was a fifty-fifty^[A gaming meme from Chinese esports meaning something is an even split, often used sarcastically when the odds are clearly not equal.].",
            },
            {"role": "user", "content": user_prompt},
        ]

    kwargs = {
        "messages": messages,
        "model": model_name,
        "temperature": temperature,
    }

    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    for attempt in range(max_retries):
        try:
            chat_completion = client.chat.completions.create(**kwargs)

            choice = chat_completion.choices[0] if chat_completion.choices else None
            if not choice or not choice.message:
                return None

            raw_content = choice.message.content or ""

            # Check if the backend provided separated reasoning (DeepSeek R1 style)
            has_reasoning_field = (
                hasattr(choice.message, "reasoning_content")
                and choice.message.reasoning_content
            )
            if has_reasoning_field:
                thinking_len = len(choice.message.reasoning_content)
                print(
                    f"  Model reasoned ({thinking_len} chars) internally before responding."
                )
                return raw_content.strip()

            # Process the standard content
            if expect_json:
                cleaned = re.sub(
                    r"<think>.*?</think>\s*", "", raw_content, flags=re.DOTALL
                )
                cleaned = re.sub(
                    r"<reasoning>.*?</reasoning>\s*", "", cleaned, flags=re.DOTALL
                )
                return cleaned.strip()
            else:
                cleaned = _extract_translation_content(raw_content)
                return cleaned

        except APITimeoutError:
            print(
                f"  Warning: API Timeout. Retrying {attempt + 1}/{max_retries} in {retry_delay}s..."
            )
            time.sleep(retry_delay)
            retry_delay *= 2
            if attempt == max_retries - 1:
                print(f"  ERROR: Timeout after {max_retries} attempts.")
                return None
        except APIError as e:
            print(f"  API Error ({type(e).__name__}): {e}")
            return None
        except Exception as e:
            error_type = type(e).__name__
            print(f"  Unexpected Error ({error_type}): {e}")
            if "Connection refused" in str(e) or "ConnectionError" in error_type:
                print(
                    f"  HINT: Is LM Studio running and serving at {LMSTUDIO_BASE_URL}?"
                )
            return None

    return None


# ============================================================
# PASS 1: Translation + Cultural Annotations
# ============================================================
def _translate_pass(
    client, model_name, text_to_translate, glossary_json_str, target_language
):
    """
    First LLM call: Translate the Chinese text and annotate cultural references.
    The model only needs to output the English translation — no JSON, no separators.
    If the model burns its output budget on thinking, retries with higher max_tokens.
    """
    prompt = (
        f"You are an expert Chinese-to-English translator.\n"
        f"Translate the Chinese text below into high-quality, natural-sounding {target_language}.\n\n"
        f"RULES:\n"
        f"- For character names and place names, you MUST use the 'english_name' from the glossary below if present.\n"
        f"- Annotate cultural references, idioms, wordplay, internet slang, memes, inside jokes, or any phrase whose humor or meaning would be lost on a non-Chinese reader.\n"
        f"- Place annotations IMMEDIATELY after the translated phrase using this exact syntax: translated phrase^[Brief explanation]\n"
        f"- Keep explanations concise (one or two sentences). Only annotate when the meaning would genuinely be unclear. Do NOT annotate straightforward text.\n\n"
        f"ANNOTATION EXAMPLES:\n"
        f"- 他真是个柠檬精 → He was such a lemon spirit^[Chinese internet slang for someone who is extremely jealous or envious of others.]\n"
        f"- 这波是五五开 → This was a fifty-fifty^[A gaming meme from Chinese esports meaning something is an even split, often used sarcastically when the odds are clearly not equal.]\n"
        f'- 我太南了 → I\'m just too south^[A homophonic pun - "south" (南 nán) sounds like "hard/difficult" (难 nán), expressing that life is too hard.]\n\n'
        f"GLOSSARY (use these translations for known names):\n"
        f"{glossary_json_str}\n\n"
        f"--- CHINESE TEXT ---\n"
        f"{text_to_translate}\n"
        f"--- END ---\n\n"
        f"CRITICAL REMINDER: Output ONLY the final translated English text. Start immediately with the first translated sentence. DO NOT output any reasoning, text analysis, introductions, or 'Here is the translation'. Your response must be pure translation."
    )

    # UPDATED: Strictly forbid reasoning and analysis in the system prompt
    system = (
        "You are a professional translation engine. Output ONLY the final English translation. "
        "CRITICAL: Do NOT output any reasoning, chain of thought, text analysis, or meta-commentary. "
        "Start your response immediately with the translated text."
    )

    # Try with default max_tokens first. If the model spends all its tokens
    # on thinking and produces no translation, retry with a larger budget.
    max_tokens_attempts = [33096, 33096, 33096]

    for i, max_tok in enumerate(max_tokens_attempts):
        tok_label = str(max_tok) if max_tok else "default"
        print(f"  [Pass 1/2] Translating (max_tokens={tok_label})...")

        raw = _call_lmstudio(
            client, model_name, system, prompt, temperature=0.2, max_tokens=max_tok
        )

        if raw is None:
            return None  # Hard failure (connection, API error)

        if raw == "":
            # Model used its entire output on reasoning, never got to translation.
            if i < len(max_tokens_attempts) - 1:
                next_tok = max_tokens_attempts[i + 1]
                print(
                    f"  [Pass 1/2] Model spent all tokens on reasoning. "
                    f"Retrying with max_tokens={next_tok}..."
                )
                continue
            else:
                print(
                    f"  [Pass 1/2] Model failed to produce translation even with max_tokens={tok_label}."
                )
                return None

        # Got actual translation content
        break

    # Clean up any leftover preamble
    translation = re.sub(
        r"^(Here is|Here's|Below is|The translation)[^\n]*\n+",
        "",
        raw.strip(),
        flags=re.IGNORECASE,
    ).strip()

    print(f"  [Pass 1/2] Translation complete ({len(translation)} chars).")
    return translation


# ============================================================
# PASS 2: Glossary Extraction (new characters & places)
# ============================================================
def _glossary_pass(client, model_name, original_chinese, translation):
    """
    Second LLM call: Given the original Chinese and the English translation,
    extract any NEW character names and place names as structured JSON.
    """
    prompt = (
        f"You are a data extraction assistant. Given a Chinese text and its English translation below, "
        f"identify ALL character names and place names that appear in the text.\n\n"
        f"Return a JSON object with two keys:\n"
        f'- "characters": an object where each key is the Chinese name, with values containing "pinyin", "english_name", and "pronoun" (he/him, she/her, or they/them).\n'
        f'- "places": an object where each key is the Chinese place name, with values containing "pinyin" and "english_name".\n\n'
        f"If no characters or places are found, use empty objects.\n\n"
        f"EXAMPLE OUTPUT:\n"
        f'{{"characters": {{"兰波": {{"pinyin": "Lan Bo", "english_name": "Lan Bo", "pronoun": "he/him"}}}}, "places": {{"清河市": {{"pinyin": "Qinghe Shi", "english_name": "Qinghe City"}}}}}}\n\n'
        f"IMPORTANT: Respond with ONLY the JSON object. No markdown fences, no explanation, no preamble.\n\n"
        f"--- CHINESE TEXT ---\n"
        f"{original_chinese}\n\n"
        f"--- ENGLISH TRANSLATION ---\n"
        f"{translation}\n"
        f"--- END ---"
    )

    system = "You are a data extractor. Output ONLY valid JSON. No markdown fences, no explanation — just the JSON object."

    print(f"  [Pass 2/2] Extracting glossary...")
    raw = _call_lmstudio(
        client, model_name, system, prompt, temperature=0.1, expect_json=True
    )

    if raw is None:
        print(
            f"  [Pass 2/2] Glossary extraction failed. Continuing without new entries."
        )
        return {}

    # Try to parse JSON from the response
    try:
        # Strip markdown fences if present
        cleaned = re.sub(r"```json\s*|\s*```", "", raw.strip(), flags=re.DOTALL).strip()

        # Sometimes the model wraps it in extra text — try to find the JSON object
        if not cleaned.startswith("{"):
            json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if json_match:
                cleaned = json_match.group(0)

        glossary_items = json.loads(cleaned)

        # Validate structure
        if not isinstance(glossary_items, dict):
            print(f"  [Pass 2/2] Warning: Response is not a JSON object. Skipping.")
            return {}

        # Ensure expected keys exist
        if "characters" not in glossary_items:
            glossary_items["characters"] = {}
        if "places" not in glossary_items:
            glossary_items["places"] = {}

        char_count = len(glossary_items.get("characters", {}))
        place_count = len(glossary_items.get("places", {}))
        print(
            f"  [Pass 2/2] Extracted {char_count} character(s), {place_count} place(s)."
        )
        return glossary_items

    except json.JSONDecodeError as e:
        print(f"  [Pass 2/2] Warning: Failed to parse JSON: {e}")
        print(f"  [Pass 2/2] Raw response (first 200 chars): {raw[:200]}")
        return {}


# ============================================================
# Main Translation Orchestrator
# ============================================================
def translate_text_with_lmstudio(
    text_to_translate: str, known_glossary_data: dict, target_language: str = "English"
) -> (str, dict):
    """
    Translates text using two separate LLM calls for reliability:
      Pass 1: Translation + cultural annotations
      Pass 2: Glossary extraction (new characters & places)
    """
    model_name = LMSTUDIO_MODEL_NAME
    base_url = LMSTUDIO_BASE_URL

    if not model_name:
        return (
            "[Translation Error: No LM Studio model selected. Set LMSTUDIO_MODEL_NAME.]",
            {},
        )

    try:
        client = OpenAI(
            api_key="lm-studio",
            base_url=base_url,
            timeout=API_TIMEOUT_SECONDS,
        )
    except Exception as e:
        return (
            f"[Translation Error: Could not initialize client for LM Studio - {type(e).__name__}: {e}]",
            {},
        )

    # --- Dynamic Glossary Filtering ---
    filtered_glossary = {"characters": {}, "places": {}}

    for name_key, details in known_glossary_data.get("characters", {}).items():
        if name_key in text_to_translate:
            filtered_glossary["characters"][name_key] = details

    for place_key, details in known_glossary_data.get("places", {}).items():
        if place_key in text_to_translate:
            filtered_glossary["places"][place_key] = details

    known_glossary_json_str = json.dumps(
        filtered_glossary, ensure_ascii=False, separators=(",", ":")
    )

    total_chars = len(known_glossary_data.get("characters", {}))
    relevant_chars = len(filtered_glossary["characters"])
    print(
        f"  Glossary Optimization: Sending {relevant_chars}/{total_chars} characters relevant to this chapter."
    )

    print(
        f"Translating with LM Studio model '{model_name}' (length: {len(text_to_translate)} chars)..."
    )

    # --- PASS 1: Translation + Annotations ---
    translation = _translate_pass(
        client, model_name, text_to_translate, known_glossary_json_str, target_language
    )

    if translation is None:
        return f"[Translation Error ({model_name} - Pass 1 Failed)]", {}

    # --- PASS 2: Glossary Extraction ---
    new_glossary_items = _glossary_pass(
        client, model_name, text_to_translate, translation
    )

    # Filter out entities we already know about
    filtered_new = {"characters": {}, "places": {}}
    for name, details in new_glossary_items.get("characters", {}).items():
        if name not in known_glossary_data.get("characters", {}):
            filtered_new["characters"][name] = details
    for name, details in new_glossary_items.get("places", {}).items():
        if name not in known_glossary_data.get("places", {}):
            filtered_new["places"][name] = details

    return translation, filtered_new


# --- Main Processing Logic ---
def process_files_for_translation():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir_full_path = os.path.join(script_dir, INPUT_DIR)
    output_dir_full_path = os.path.join(script_dir, OUTPUT_DIR)
    glossary_json_full_path = os.path.join(script_dir, GLOSSARY_JSON_FILE)
    glossary_data = load_glossary_from_json(glossary_json_full_path)

    if not os.path.exists(input_dir_full_path):
        print(f"Error: Input directory '{input_dir_full_path}' not found.")
        return
    if not os.path.exists(output_dir_full_path):
        os.makedirs(output_dir_full_path)
        print(f"Created output directory: {output_dir_full_path}")

    files_to_process = sorted(
        [f for f in os.listdir(input_dir_full_path) if f.endswith(".txt")]
    )
    if not files_to_process:
        print(f"No .txt files found in '{input_dir_full_path}'.")
        return

    print(
        f"Found {len(files_to_process)} file(s) to process from '{input_dir_full_path}'."
    )
    print(f"Using LM Studio model: {LMSTUDIO_MODEL_NAME}")
    print(f"LM Studio endpoint: {LMSTUDIO_BASE_URL}")
    print(f"Mode: Two-pass (Translation → Glossary Extraction)")

    for i, filename in enumerate(files_to_process):
        input_filepath = os.path.join(input_dir_full_path, filename)
        output_filepath = os.path.join(output_dir_full_path, filename)
        print(f"\n[{i+1}/{len(files_to_process)}] Checking: {filename}...")

        if os.path.exists(output_filepath):
            try:
                with open(output_filepath, "r", encoding="utf-8") as f_check:
                    content_check = f_check.read(200)
                    if (
                        "[Translation Error" not in content_check
                        and "[ERROR PROCESSING FILE" not in content_check
                    ):
                        print(
                            f"Output file '{output_filepath}' exists and is valid. Skipping."
                        )
                        continue
                    else:
                        print(
                            f"Output file contains an error marker. Will re-translate."
                        )
            except Exception:
                pass

        print(f"Processing for translation: {filename}")

        try:
            with open(input_filepath, "r", encoding="utf-8") as f:
                source_content = f.read()
            clean_source_for_api = "\n".join(
                [
                    line
                    for line in source_content.splitlines()
                    if line.strip() and re.search(r"[\u4e00-\u9fff]", line)
                ]
            ).strip()

            if not clean_source_for_api:
                translated_content = "[No Chinese content found in source]"
            else:
                translated_content, new_glossary_items = translate_text_with_lmstudio(
                    clean_source_for_api, glossary_data, target_language="English"
                )

                if new_glossary_items:
                    new_chars = new_glossary_items.get("characters", {})
                    if new_chars:
                        print(
                            f"  Updating master list with {len(new_chars)} new character(s)."
                        )
                        for name, details in new_chars.items():
                            if name not in glossary_data["characters"]:
                                glossary_data["characters"][name] = details
                                print(f"    + Added Character: {name} -> {details}")

                    new_places = new_glossary_items.get("places", {})
                    if new_places:
                        print(
                            f"  Updating master list with {len(new_places)} new place(s)."
                        )
                        for name, details in new_places.items():
                            if name not in glossary_data["places"]:
                                glossary_data["places"][name] = details
                                print(f"    + Added Place: {name} -> {details}")

            final_content_to_write = (
                translated_content
                if translated_content.startswith("[")
                else reformat_chapter_title_in_text(translated_content)
            )
            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            # Save glossary after each file
            save_glossary_to_json(glossary_json_full_path, glossary_data)

            # No sleep needed for local models, but a tiny pause to be safe
            if i < len(files_to_process) - 1:
                print(f"Pausing for 1.0 seconds...")
                time.sleep(1.0)

        except Exception as e:
            print(f"FATAL Error processing file {filename}: {e}")
            with open(output_filepath, "w", encoding="utf-8") as f_err:
                f_err.write(f"[ERROR PROCESSING FILE: {e}]")

    print(f"\n--- Translation Run Summary ---")
    print(f"Total source files checked: {len(files_to_process)}")
    print(f"-----------------------------")


if __name__ == "__main__":
    print(f"Starting Chinese to English translation process (LM Studio)...")
    if not LMSTUDIO_MODEL_NAME:
        print("\nCRITICAL ERROR: 'LMSTUDIO_MODEL_NAME' environment variable not set.")
        print("Please select a model in the GUI or set the variable manually.")
        exit()

    print(f"LM Studio URL: {LMSTUDIO_BASE_URL}")
    print(f"Model: {LMSTUDIO_MODEL_NAME}")

    # Quick connectivity check
    models = list_available_models(LMSTUDIO_BASE_URL)
    if models:
        print(f"Connected! Available models: {models}")
        if LMSTUDIO_MODEL_NAME not in models:
            print(
                f"WARNING: Selected model '{LMSTUDIO_MODEL_NAME}' not in available models."
            )
            print(f"Available: {models}")
    else:
        print("WARNING: Could not connect to LM Studio. Is it running?")

    process_files_for_translation()
    print("Translation process finished.")
