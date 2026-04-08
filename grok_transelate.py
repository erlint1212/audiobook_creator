import json
import os
import re
import time

try:
    from openai import (
        APIError,
        APITimeoutError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except ImportError:
    print("CRITICAL: 'openai' package not installed. Run: pip install openai")
    exit()

from prompts import DEFAULT_GLOSSARY, SYSTEM_COMBINED, build_combined_prompt

# --- Configuration ---
INPUT_DIR = os.getenv("PROJECT_TRANS_INPUT_DIR", "SnakeFairy_CH_Qushucheng")
OUTPUT_DIR = os.getenv("PROJECT_TRANS_OUTPUT_DIR", "SnakeFairy_EN_transelated")
XAI_MODEL_NAME = "grok-4-0709"
XAI_BASE_URL = "https://api.x.ai/v1"
API_TIMEOUT_SECONDS = 300.0
GLOSSARY_JSON_FILE = "translation_glossary.json"


def load_glossary_from_json(filepath):
    if not os.path.exists(filepath):
        print(f"Glossary not found at '{filepath}'. Creating new.")
        return dict(DEFAULT_GLOSSARY)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for key in DEFAULT_GLOSSARY:
                if key not in data:
                    data[key] = {}
            return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading glossary: {e}. Starting fresh.")
        return dict(DEFAULT_GLOSSARY)


def save_glossary_to_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Saved glossary to '{filepath}'.")
    except IOError as e:
        print(f"Error writing glossary: {e}")


def reformat_chapter_title_in_text(text_content):
    if not text_content or not text_content.strip():
        return text_content
    lines = text_content.split("\n", 1)
    first_line, rest = lines[0], lines[1] if len(lines) > 1 else ""
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


def translate_text_with_xai(
    text_to_translate, known_glossary_data, target_language="English"
):
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        return "[Translation Error: 'XAI_API_KEY' not set.]", {}

    try:
        client = OpenAI(
            api_key=api_key, base_url=XAI_BASE_URL, timeout=API_TIMEOUT_SECONDS
        )
    except Exception as e:
        return f"[Translation Error: {type(e).__name__}: {e}]", {}

    # Dynamic glossary filtering across all categories
    filtered_glossary = {key: {} for key in DEFAULT_GLOSSARY}
    for category in DEFAULT_GLOSSARY:
        for name_key, details in known_glossary_data.get(category, {}).items():
            if name_key in text_to_translate:
                filtered_glossary[category][name_key] = details

    known_glossary_json_str = json.dumps(
        filtered_glossary, ensure_ascii=False, separators=(",", ":")
    )

    total = sum(len(known_glossary_data.get(c, {})) for c in DEFAULT_GLOSSARY)
    relevant = sum(len(filtered_glossary[c]) for c in DEFAULT_GLOSSARY)
    print(f"  Glossary: {relevant}/{total} entries relevant to this chapter.")
    print(f"Translating (length: {len(text_to_translate)} chars)...")

    # Build prompt from shared templates
    prompt = build_combined_prompt(
        text_to_translate, known_glossary_json_str, target_language
    )

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_COMBINED},
                {"role": "user", "content": prompt},
            ],
            model=XAI_MODEL_NAME,
            temperature=0.2,
        )

        raw_response_text = (
            chat_completion.choices[0].message.content
            if chat_completion.choices and chat_completion.choices[0].message
            else ""
        )

        separator = "---JSON---"
        new_glossary_items = {}
        translation_part = raw_response_text

        if separator in raw_response_text:
            parts = raw_response_text.split(separator, 1)
            translation_part = parts[0].strip()
            json_part = parts[1].strip()
            try:
                json_cleaned = re.sub(
                    r"```json\s*|\s*```", "", json_part, flags=re.DOTALL
                ).strip()
                if json_cleaned:
                    new_glossary_items = json.loads(json_cleaned)
                    for key in DEFAULT_GLOSSARY:
                        if key not in new_glossary_items:
                            new_glossary_items[key] = {}
                    print(f"  Parsed glossary data from response.")
            except json.JSONDecodeError as e:
                print(f"  Warning: JSON parse failed: {e}")
        else:
            print("  Warning: ---JSON--- separator not found.")

        final_translation = re.sub(
            r"\n---\s*"
            + target_language.upper()
            + r"\s*TRANSLATION\s*(END|START)\s*---"
            r"|\^ENGLISH TRANSLATION ONLY:[\s\n]*",
            "",
            translation_part,
            flags=re.IGNORECASE,
        ).strip()
        print(f"Translation successful.")
        return final_translation, new_glossary_items

    except (APIError, APITimeoutError, AuthenticationError, RateLimitError) as e:
        error_type = type(e).__name__
        print(f"  API error: {error_type} - {e}")
        return f"[Translation Error ({XAI_MODEL_NAME} - {error_type})]", {}
    except Exception as e:
        error_type = type(e).__name__
        print(f"  Unexpected error: {error_type} - {e}")
        return f"[Translation Error ({XAI_MODEL_NAME} - {error_type})]", {}


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
        print(f"No .txt files in '{input_dir}'.")
        return

    print(f"Found {len(files)} file(s) from '{input_dir}'.")

    for i, filename in enumerate(files):
        in_path = os.path.join(input_dir, filename)
        out_path = os.path.join(output_dir, filename)
        print(f"\n[{i+1}/{len(files)}] {filename}...")

        if os.path.exists(out_path):
            try:
                with open(out_path, "r", encoding="utf-8") as f:
                    check = f.read(200)
                    if "[Translation Error" not in check and "[ERROR" not in check:
                        print(f"  Valid output exists. Skipping.")
                        continue
            except Exception:
                pass

        try:
            with open(in_path, "r", encoding="utf-8") as f:
                source = f.read()
            clean = "\n".join(
                l
                for l in source.splitlines()
                if l.strip() and re.search(r"[\u4e00-\u9fff]", l)
            ).strip()

            if not clean:
                translated = "[No Chinese content found]"
            else:
                translated, new_items = translate_text_with_xai(clean, glossary_data)
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
            print(f"  Saved: {out_path}")
            save_glossary_to_json(glossary_path, glossary_data)

            if i < len(files) - 1:
                time.sleep(5.0)
        except Exception as e:
            print(f"  FATAL: {e}")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"[ERROR PROCESSING FILE: {e}]")

    print(f"\n--- Done. {len(files)} files checked ---")


if __name__ == "__main__":
    print("Starting Chinese to English translation (Grok/xAI)...")
    if not os.environ.get("XAI_API_KEY"):
        print("CRITICAL: 'XAI_API_KEY' not set.")
        exit()
    process_files_for_translation()
