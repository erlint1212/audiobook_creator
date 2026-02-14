import json
import os
import re
import time

# Ensure you have the openai package installed
# pip install openai
try:
    from openai import (
        APIError,
        APITimeoutError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except ImportError:
    print(
        "CRITICAL ERROR: The 'openai' package is not installed. Please install it by running: pip install openai"
    )
    exit()

# --- Configuration ---
# Updated to support the GUI Pipeline (os.getenv) with fallbacks to your original folders
INPUT_DIR = os.getenv("PROJECT_TRANS_INPUT_DIR", "SnakeFairy_CH_Qushucheng")
OUTPUT_DIR = os.getenv("PROJECT_TRANS_OUTPUT_DIR", "SnakeFairy_EN_transelated")
XAI_MODEL_NAME = "grok-4-0709"
XAI_BASE_URL = "https://api.x.ai/v1"
API_TIMEOUT_SECONDS = 300.0
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
            # Ensure both top-level keys exist
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

    match = re.match(r"^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)", first_line, re.IGNORECASE)
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


# --- MODIFIED: xAI API Translation Function with Context Optimization ---
def translate_text_with_xai(
    text_to_translate: str, known_glossary_data: dict, target_language: str = "English"
) -> (str, dict):
    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        return "[Translation Error: 'XAI_API_KEY' environment variable not set.]", {}

    try:
        client = OpenAI(
            api_key=api_key, base_url=XAI_BASE_URL, timeout=API_TIMEOUT_SECONDS
        )
    except Exception as e:
        return (
            f"[Translation Error: Could not initialize OpenAI client for xAI - {type(e).__name__}: {e}]",
            {},
        )

    # --- OPTIMIZATION START: Dynamic Glossary Filtering ---
    # This logic matches the Gemini script: only send relevant glossary items to save context.
    filtered_glossary = {"characters": {}, "places": {}}

    # 1. Filter Characters
    for name_key, details in known_glossary_data.get("characters", {}).items():
        if name_key in text_to_translate:
            filtered_glossary["characters"][name_key] = details

    # 2. Filter Places
    for place_key, details in known_glossary_data.get("places", {}).items():
        if place_key in text_to_translate:
            filtered_glossary["places"][place_key] = details

    # 3. Minify JSON (remove whitespace)
    known_glossary_json_str = json.dumps(
        filtered_glossary, ensure_ascii=False, separators=(",", ":")
    )

    total_chars = len(known_glossary_data.get("characters", {}))
    relevant_chars = len(filtered_glossary["characters"])
    print(
        f"  Glossary Optimization: Sending {relevant_chars}/{total_chars} characters relevant to this chapter."
    )
    # --- OPTIMIZATION END ---

    print(
        f"Attempting to translate and extract glossary items from text (length: {len(text_to_translate)} chars)..."
    )

    # --- UPDATED PROMPT: Aligned with Gemini prompt for consistency ---
    prompt = (
        f"You are an expert Chinese-to-English translator and data extractor.\n"
        f"Your task is twofold:\n"
        f"1. Translate the Chinese text into high-quality, natural-sounding {target_language}. For names and places, you MUST use the 'english_name' from the 'Relevant Glossary' below if present.\n"
        f"2. Identify new character names and place names in the text NOT already in the 'Relevant Glossary', and extract their details.\n\n"
        f"--- RELEVANT GLOSSARY (Specific to this text) ---\n"
        f"{known_glossary_json_str}\n\n"
        f"--- RESPONSE FORMATTING RULES ---\n"
        f"- Your response MUST have two parts separated by '---JSON---'.\n"
        f"- PART 1 (Translation): MUST ONLY contain the final {target_language.upper()} translation.\n"
        f"- PART 2 (Data): MUST start on a new line immediately after '---JSON---' and contain a single JSON object of NEW entities. This object should have two keys: 'characters' and 'places'.\n"
        f"- Under 'characters', provide new characters with their 'pinyin', 'english_name', and 'pronoun'.\n"
        f"- Under 'places', provide new places with their 'pinyin' and 'english_name'.\n"
        f'- Example JSON Format: {{"characters": {{"兰波": {{"pinyin": "Lan Bo", "english_name": "Lan Bo", "pronoun": "he/him"}}}}, "places": {{"清河市": {{"pinyin": "Qinghe Shi", "english_name": "Qinghe City"}}}}}}\n'
        f'- If NO NEW entities of a type are found, that key\'s value must be an empty object: e.g., {{"characters": {{}}, "places": {{...}}}}\n\n'
        f"--- CHINESE TEXT TO PROCESS ---\n"
        f"{text_to_translate}\n"
        f"--- END OF TEXT ---\n\n"
        f"Please provide your response following all rules."
    )

    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that follows instructions precisely.",
                },
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
                json_part_cleaned = re.sub(
                    r"```json\s*|\s*```", "", json_part, flags=re.DOTALL
                ).strip()
                if json_part_cleaned:
                    new_glossary_items = json.loads(json_part_cleaned)
                    print(f"  Successfully parsed glossary data from API response.")
            except json.JSONDecodeError as e:
                print(f"  Warning: Failed to parse JSON from API response. Error: {e}")
        else:
            print("  Warning: JSON separator not found in API response.")

        final_translation = re.sub(
            r"\n---\s*"
            + target_language.upper()
            + r"\s*TRANSLATION\s*(END|START)\s*---|\^ENGLISH TRANSLATION ONLY:[\s\n]*",
            "",
            translation_part,
            flags=re.IGNORECASE,
        ).strip()
        print(f"Translation API call successful.")
        return final_translation, new_glossary_items

    except (APIError, APITimeoutError, AuthenticationError, RateLimitError) as e:
        error_type = type(e).__name__
        print(f"An API error occurred during translation: {error_type} - {e}")
        return f"[Translation Error ({XAI_MODEL_NAME} - {error_type})]", {}
    except Exception as e:
        error_type = type(e).__name__
        print(f"An unexpected error occurred during translation: {error_type} - {e}")
        return f"[Translation Error ({XAI_MODEL_NAME} - {error_type})]", {}


# --- MODIFIED: Main Processing Logic with Glossary ---
def process_files_for_translation():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Using the global variables configured via os.getenv above
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
                translated_content, new_glossary_items = translate_text_with_xai(
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

            # --- Save glossary after each file is processed ---
            save_glossary_to_json(glossary_json_full_path, glossary_data)

            if i < len(files_to_process) - 1:
                print(f"Pausing for 5.0 seconds...")
                time.sleep(5.0)

        except Exception as e:
            print(f"FATAL Error processing file {filename}: {e}")
            with open(output_filepath, "w", encoding="utf-8") as f_err:
                f_err.write(f"[ERROR PROCESSING FILE: {e}]")

    print(f"\n--- Translation Run Summary ---")
    print(f"Total source files checked: {len(files_to_process)}")
    print(f"-----------------------------")


if __name__ == "__main__":
    print(f"Starting Chinese to English translation process...")
    if not os.environ.get("XAI_API_KEY"):
        print("\nCRITICAL ERROR: 'XAI_API_KEY' environment variable not set.")
        exit()

    process_files_for_translation()
    print("Translation process finished.")
