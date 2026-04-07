import json
import os
import re
import sys
import time

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
            result = model.respond(chat, config=config)
            raw = str(result) if result else ""
            if expect_json:
                raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.DOTALL)
                raw = re.sub(r"<reasoning>.*?</reasoning>\s*", "", raw, flags=re.DOTALL)
                return raw.strip()
            else:
                return _extract_translation_content(raw)
        except TimeoutError:
            print(f"  Timeout. Retrying {attempt+1}/{max_retries} in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay *= 2
            if attempt == max_retries - 1:
                return None
        except Exception as e:
            print(f"  Error ({type(e).__name__}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                return None
    return None


def _glossary_pass(model, original_chinese):
    few_shot_user = "Extract entities from: \u5170\u6ce2\u5e26\u7740\u7834\u5984\u5251\u53bb\u4e86\u6e05\u6cb3\u5e02\u7684\u5929\u8f89\u9a91\u58eb\u56e2\u3002"
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
        "You are a data extractor. Output ONLY valid JSON. No markdown, no explanation."
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
        print(f"  [Pass 1/2] Glossary extraction failed.")
        return {}
    try:
        cleaned = re.sub(r"```json\s*|\s*```", "", raw.strip(), flags=re.DOTALL).strip()
        if not cleaned.startswith("{"):
            m = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(0)
        items = json.loads(cleaned)
        if not isinstance(items, dict):
            return {}
        for key in DEFAULT_GLOSSARY:
            if key not in items:
                items[key] = {}
        counts = [f"{len(items[k])} {k}" for k in DEFAULT_GLOSSARY if items.get(k)]
        print(f"  [Pass 1/2] Extracted: {', '.join(counts) if counts else 'nothing'}.")
        return items
    except json.JSONDecodeError as e:
        print(f"  [Pass 1/2] JSON parse failed: {e}")
        return {}


def _translate_pass(model, text_to_translate, glossary_json_str, target_language):
    few_shot_user = (
        "Translate into English. Output ONLY the translation.\n\n"
        "--- CHINESE TEXT ---\n"
        "\u90a3\u4e2a\u53eb\u59ec\u767d\u7684\u9a91\u58eb\u6325\u821e\u7740\u7834\u5984\u5251\uff0c\u8bf4\u9053\uff1a\u201c\u8fd9\u6ce2\u662f\u4e94\u4e94\u5f00\uff0c\u4f60\u4eec\u5148\u6492\u3002\u201d\n"
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
    max_tokens_attempts = [-1]
    for i, max_tok in enumerate(max_tokens_attempts):
        label = "Unlimited" if max_tok == -1 else str(max_tok)
        print(f"  [Pass 2/2] Translating (max_tokens={label})...")
        raw = _call_lmstudio(
            model,
            system,
            prompt,
            temperature=0.2,
            max_tokens=max_tok,
            few_shot_user=few_shot_user,
            few_shot_assistant=few_shot_assistant,
        )
        if raw is None:
            return None
        if raw == "":
            if i < len(max_tokens_attempts) - 1:
                continue
            return None
        break
    translation = re.sub(
        r"^(Here is|Here's|Below is|The translation)[^\n]*\n+",
        "",
        raw.strip(),
        flags=re.IGNORECASE,
    ).strip()
    print(f"  [Pass 2/2] Translation complete ({len(translation)} chars).")
    return translation


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

    new_glossary_items = _glossary_pass(model, text_to_translate)
    filtered_new = {key: {} for key in DEFAULT_GLOSSARY}
    for cat in DEFAULT_GLOSSARY:
        for name, details in new_glossary_items.get(cat, {}).items():
            if name not in known_glossary_data.get(cat, {}):
                filtered_new[cat][name] = details
                filtered_glossary[cat][name] = details

    combined = json.dumps(filtered_glossary, ensure_ascii=False, separators=(",", ":"))
    translation = _translate_pass(model, text_to_translate, combined, target_language)
    if translation is None:
        return f"[Translation Error ({model_name} - Pass 2 Failed)]", {}
    return translation, filtered_new


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

            if i < len(files) - 1:
                time.sleep(1.0)
        except Exception as e:
            print(f"FATAL Error: {e}")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"[ERROR PROCESSING FILE: {e}]")

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
