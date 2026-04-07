import json
import os
import re
import sys  # Added for sys.exit()
import time

from google.generativeai.types import HarmBlockThreshold, HarmCategory

# Ensure you have the google-generativeai package installed
# pip install -U google-generativeai

# --- Configuration ---
INPUT_DIR = os.getenv("PROJECT_TRANS_INPUT_DIR", "SnakeFairy_CH_Qushucheng")
OUTPUT_DIR = os.getenv("PROJECT_TRANS_OUTPUT_DIR", "SnakeFairy_EN_transelated")
GLOSSARY_JSON_FILE = "translation_glossary.json"


# All supported glossary categories (shared across translation engines)
DEFAULT_GLOSSARY = {
    "characters": {},
    "places": {},
    "organizations": {},
    "items": {},
    "skills": {},
    "species": {},
}


# --- Helper Function to Load Glossary from JSON ---
def load_glossary_from_json(filepath: str) -> dict:
    """
    Loads a glossary dictionary from a JSON file.
    Ensures all category keys exist even if the file is from an older version.
    """
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
        print(f"Error reading or parsing JSON file '{filepath}': {e}. Starting fresh.")
        return dict(DEFAULT_GLOSSARY)


# --- Helper Function to Save Glossary to JSON ---
def save_glossary_to_json(filepath: str, data: dict):
    """Saves a glossary dictionary to a JSON file with pretty printing."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved updated glossary to '{filepath}'.")
    except IOError as e:
        print(f"Error writing to JSON file '{filepath}': {e}")


# --- Helper Function to Reformat Title (unchanged) ---
def reformat_chapter_title_in_text(text_content: str) -> str:
    if not text_content or not text_content.strip():
        return text_content
    lines = text_content.split("\n", 1)
    first_line, rest_of_content = lines[0], lines[1] if len(lines) > 1 else ""
    match = re.match(r"^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)", first_line, re.IGNORECASE)
    if match:
        chapter_part, title_part = match.group(1).strip(), match.group(2).strip()
        reformatted_first_line = (
            f"{chapter_part} - {title_part}" if title_part else chapter_part
        )
        return f"{reformatted_first_line}\n{rest_of_content}"
    numeric_match = re.match(r"^(\d+)\s+(.*)", first_line)
    if numeric_match:
        try:
            chapter_number_int, title_part = (
                int(numeric_match.group(1)),
                numeric_match.group(2).strip(),
            )
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            return f"{reformatted_first_line}\n{rest_of_content}"
        except ValueError:
            pass
    return text_content


# --- MODIFIED: Gemini API Translation Function for Glossary ---
def translate_text_with_gemini(
    text_to_translate: str, known_glossary_data: dict, target_language: str = "English"
) -> (str, dict):
    """
    Translates text and extracts new glossary items (characters and places).
    INCLUDES RETRY LOGIC for DeadlineExceeded and AUTO-QUIT for ResourceExhausted.
    """
    try:
        import google.generativeai as genai_sdk
        from google.api_core import (
            exceptions as google_exceptions,
        )  # Import specific exceptions
    except ImportError:
        return "[Translation Error: Package not installed.]", {}

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "[Translation Error: 'GEMINI_API_KEY' not set.]", {}

    genai_sdk.configure(api_key=api_key)
    model_name_for_api = "gemini-3-flash-preview"

    # --- OPTIMIZATION START: Dynamic Glossary Filtering ---
    filtered_glossary = {key: {} for key in DEFAULT_GLOSSARY}

    for category in DEFAULT_GLOSSARY:
        for name_key, details in known_glossary_data.get(category, {}).items():
            if name_key in text_to_translate:
                filtered_glossary[category][name_key] = details

    # Minify JSON
    known_glossary_json_str = json.dumps(
        filtered_glossary, ensure_ascii=False, separators=(",", ":")
    )

    total_entries = sum(
        len(known_glossary_data.get(cat, {})) for cat in DEFAULT_GLOSSARY
    )
    relevant_entries = sum(len(filtered_glossary[cat]) for cat in DEFAULT_GLOSSARY)
    print(
        f"  Glossary Optimization: Sending {relevant_entries}/{total_entries} entries relevant to this chapter."
    )
    # --- OPTIMIZATION END ---

    print(
        f"Attempting to translate and extract glossary items from text (length: {len(text_to_translate)} chars)..."
    )

    prompt = (
        f"You are an expert Chinese-to-English translator and data extractor.\n"
        f"Your task has three parts:\n"
        f"1. Translate the Chinese text into high-quality, natural-sounding {target_language}. For names and places, you MUST use the 'english_name' from the 'Relevant Glossary' below if present.\n"
        f"2. Identify new character names and place names in the text NOT already in the glossary, and extract their details.\n"
        f"3. Annotate cultural references, idioms, wordplay, internet slang, memes, inside jokes, or any phrase whose humor or meaning would be lost on a non-Chinese reader. Place the annotation IMMEDIATELY after the translated phrase using this exact syntax: translated phrase^[Brief explanation of the joke, reference, or cultural context]. Keep explanations concise (one or two sentences). Only annotate when the meaning would genuinely be unclear; do NOT annotate straightforward text.\n\n"
        f"--- ANNOTATION EXAMPLES ---\n"
        f"- Original: 他真是个柠檬精 → He was such a lemon spirit^[Chinese internet slang for someone who is extremely jealous or envious of others.]\n"
        f"- Original: 这波是五五开 → This was a fifty-fifty^[A gaming meme from Chinese esports meaning something is an even split, often used sarcastically when the odds are clearly not equal.]\n"
        f'- Original: 我太南了 → I\'m just too south^[A homophonic pun - "south" (南 nán) sounds like "hard/difficult" (难 nán), expressing that life is too hard.]\n'
        f"- Do NOT annotate simple/obvious phrases like greetings, common expressions, or straightforward dialogue.\n\n"
        f"--- RELEVANT GLOSSARY (Specific to this text) ---\n"
        f"{known_glossary_json_str}\n\n"
        f"--- RESPONSE FORMATTING RULES ---\n"
        f"- Your response MUST have two parts separated by '---JSON---'.\n"
        f"- PART 1 (Translation): MUST ONLY contain the final {target_language.upper()} translation (including any ^[annotation] markers inline).\n"
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

    safety_settings = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }

    # --- RETRY LOGIC START ---
    max_retries = 3
    retry_delay = 10  # seconds

    for attempt in range(max_retries):
        try:
            model = genai_sdk.GenerativeModel(model_name_for_api)
            # Increased timeout to 600
            response = model.generate_content(
                prompt,
                request_options={"timeout": 600},
                generation_config=genai_sdk.types.GenerationConfig(temperature=0.2),
                safety_settings=safety_settings,
            )

            # If successful, break out of retry loop and process response
            raw_response_text = response.text
            break

        except google_exceptions.ResourceExhausted:
            print(f"\nCRITICAL: Resource Exhausted (Quota limit reached).")
            print("Auto-quitting script to prevent further errors.")
            sys.exit(0)  # Quit the program entirely

        except google_exceptions.DeadlineExceeded:
            print(
                f"  Warning: API Deadline Exceeded (Timeout). Retrying {attempt + 1}/{max_retries} in {retry_delay}s..."
            )
            time.sleep(retry_delay)
            retry_delay *= 2  # Increase delay for next retry
            if attempt == max_retries - 1:
                return (
                    f"[Translation Error: Deadline Exceeded after {max_retries} attempts]",
                    {},
                )

        except Exception as e:
            # Handle other unexpected API errors
            error_type = type(e).__name__
            print(f"  API Error ({error_type}): {e}")
            return f"[Translation Error ({model_name_for_api} - {error_type})]", {}
    # --- RETRY LOGIC END ---

    try:
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

    except Exception as e:
        print(f"An error occurred during response parsing: {e}")
        return f"[Translation Error (Parsing)]", {}


# --- MODIFIED: Main Processing Logic for Glossary ---
def process_files_for_translation():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Resolve paths: if absolute (from GUI env), use directly; if relative, join with script_dir
    input_dir_full_path = (
        INPUT_DIR if os.path.isabs(INPUT_DIR) else os.path.join(script_dir, INPUT_DIR)
    )
    output_dir_full_path = (
        OUTPUT_DIR
        if os.path.isabs(OUTPUT_DIR)
        else os.path.join(script_dir, OUTPUT_DIR)
    )

    # Glossary lives in the project root (parent of input dir, e.g. Novels/BookName/)
    project_root = os.path.dirname(input_dir_full_path)
    glossary_json_full_path = os.path.join(project_root, GLOSSARY_JSON_FILE)
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
                translated_content, new_glossary_items = translate_text_with_gemini(
                    clean_source_for_api, glossary_data, target_language="English"
                )

                if new_glossary_items:
                    for category in DEFAULT_GLOSSARY:
                        new_entries = new_glossary_items.get(category, {})
                        if new_entries:
                            print(
                                f"  Updating {category} with {len(new_entries)} new entry/entries."
                            )
                            for name, details in new_entries.items():
                                if name not in glossary_data.get(category, {}):
                                    if category not in glossary_data:
                                        glossary_data[category] = {}
                                    glossary_data[category][name] = details
                                    print(f"    + [{category}] {name} -> {details}")

            final_content_to_write = (
                translated_content
                if translated_content.startswith("[")
                else reformat_chapter_title_in_text(translated_content)
            )
            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            # --- MODIFIED: Save glossary after each file is processed ---
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
    if not os.environ.get("GEMINI_API_KEY"):
        print("\nCRITICAL ERROR: 'GEMINI_API_KEY' environment variable not set.")
        exit()

    process_files_for_translation()
    print("Translation process finished.")
