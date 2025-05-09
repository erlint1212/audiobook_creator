import os
import time
import re # Added for regular expression matching

try:
    from google import genai
except ImportError:
    print("Error: Could not import 'genai' from 'google'.")
    print("Please ensure your 'google-genai' package is correctly installed and provides this module.")
    exit()

# --- Configuration ---
INPUT_DIR = "scraped_sfacg_novel"
OUTPUT_DIR = "translated_sfacg_novel_en_2_5_pro_exp_alt_client" 
API_KEY_ENV_VARIABLE = "GEMINI_API_KEY"

# --- Helper Function to Reformat Title ---
def reformat_chapter_title_in_text(text_content):
    """
    Reformats the first line of the text if it starts with a number.
    Example: "001 Curse" becomes "Chapter 1 - Curse"
    """
    if not text_content or not text_content.strip():
        return text_content # Return as is if empty or only whitespace

    lines = text_content.split('\n', 1) # Split into first line and the rest
    first_line = lines[0]
    rest_of_content = lines[1] if len(lines) > 1 else None

    # Regex to find titles starting with one or more digits, followed by a space, then the rest of the title.
    # e.g., "001 My Title", "42 Another Title"
    match = re.match(r'^(\d+)\s+(.*)', first_line)
    
    if match:
        chapter_number_str = match.group(1) # The numeric part, e.g., "001"
        title_part = match.group(2)         # The rest of the title, e.g., "My Title"
        try:
            chapter_number_int = int(chapter_number_str) # Convert "001" to 1
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            
            if rest_of_content is not None:
                return f"{reformatted_first_line}\n{rest_of_content}"
            else:
                return reformatted_first_line
        except ValueError:
            # This should not happen if the regex matches \d+, but as a safeguard
            print(f"Warning: Could not convert chapter number '{chapter_number_str}' to int for title: '{first_line}'")
            # Fall through to return original text if conversion fails
            
    return text_content # Return original text if no match or if there was an unexpected error

# --- Gemini API Translation Function (Unchanged) ---
def translate_text_with_gemini(text_to_translate, target_language="English"):
    model_name_for_api = "models/gemini-2.5-pro-exp-03-25" 
    print(f"Attempting to translate text (length: {len(text_to_translate)} chars) using {model_name_for_api} via genai.Client...")
    try:
        api_key = os.environ.get(API_KEY_ENV_VARIABLE)
        if not api_key:
            return f"[Translation Error: Environment variable '{API_KEY_ENV_VARIABLE}' not set.]"
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Please translate the following Chinese text into {target_language}. "
            "Preserve the original structure, such as chapter titles on their own lines "
            "and paragraph breaks."
            "\n\n--- CHINESE TEXT START ---\n"
            f"{text_to_translate}"
            "\n--- CHINESE TEXT END ---\n\n"
        )
        response = client.models.generate_content(model=model_name_for_api, contents=[prompt])
        if hasattr(response, 'text') and response.text:
            translated_text = response.text
        elif hasattr(response, 'candidates') and response.candidates:
            try:
                translated_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            except (IndexError, AttributeError, TypeError):
                print(f"Warning: Could not extract text using candidate structure. Response: {response}")
                return "[Translation Error: Could not extract text from API response candidate structure.]"
        else:
            print(f"Warning: Could not directly extract text from response. Response object: {response}")
            return "[Translation Error: Could not extract text from API response.]"
        translated_text = translated_text.replace(f"\n--- {target_language.upper()} TRANSLATION END ---", "").strip()
        print(f"Translation successful with {model_name_for_api} via genai.Client.")
        return translated_text
    except Exception as e:
        print(f"An error occurred during translation with {model_name_for_api} via genai.Client: {type(e).__name__} - {e}")
        return f"[Translation Error ({model_name_for_api} via genai.Client): {e}]\n\nOriginal Text (first 100 chars):\n{text_to_translate[:100]}..."

# --- Main Processing Logic ---
def process_files_for_translation():
    model_id_for_log = 'models/gemini-2.5-pro-exp-03-25'
    if not os.path.exists(INPUT_DIR):
        print(f"Error: Input directory '{INPUT_DIR}' not found.")
        return

    if not os.path.exists(OUTPUT_DIR):
        try:
            os.makedirs(OUTPUT_DIR)
            print(f"Created output directory: {OUTPUT_DIR}")
        except OSError as e:
            print(f"Error creating output directory '{OUTPUT_DIR}': {e}")
            return

    files_to_process = [f for f in os.listdir(INPUT_DIR) if f.endswith(".txt")]
    total_files = len(files_to_process)
    
    if total_files == 0:
        print(f"No .txt files found in '{INPUT_DIR}'.")
        return

    print(f"Found {total_files} potential file(s) to process from '{INPUT_DIR}'.")
    
    attempted_translations_count = 0
    skipped_count = 0

    for i, filename in enumerate(files_to_process):
        input_filepath = os.path.join(INPUT_DIR, filename)
        output_filepath = os.path.join(OUTPUT_DIR, filename)

        print(f"\n[{i+1}/{total_files}] Checking: {filename}...")

        if os.path.exists(output_filepath):
            is_valid_translation = True 
            try:
                if os.path.getsize(output_filepath) == 0:
                    is_valid_translation = False
                    print(f"Output file '{output_filepath}' exists but is empty. Will re-translate.")
                else:
                    with open(output_filepath, 'r', encoding='utf-8') as f_check:
                        content_check = f_check.read(100) 
                        if "[Translation Error" in content_check or "[ERROR PROCESSING FILE" in content_check:
                            is_valid_translation = False
                            print(f"Output file '{output_filepath}' exists but contains an error marker. Will re-translate.")
            except Exception as e_check:
                print(f"Could not properly check existing file {output_filepath}, assuming it's fine: {e_check}")

            if is_valid_translation:
                print(f"Output file '{output_filepath}' already exists and seems valid. Skipping translation.")
                skipped_count += 1
                continue 
        
        attempted_translations_count +=1
        print(f"Translating: {filename} (to {output_filepath})")

        try:
            with open(input_filepath, 'r', encoding='utf-8') as f:
                chinese_content = f.read()
            
            translated_content = "" # Initialize
            if not chinese_content.strip():
                print("Source file is empty. Creating an empty output file.")
                # translated_content will remain empty
            else:
                translated_content = translate_text_with_gemini(chinese_content)
            
            # --- REFORMAT THE TITLE ---
            if not (translated_content.startswith("[Translation Error") or translated_content.startswith("[ERROR PROCESSING FILE")):
                print("Reformatting title for translated content...")
                final_content_to_write = reformat_chapter_title_in_text(translated_content)
            else:
                print("Skipping title reformat due to translation error.")
                final_content_to_write = translated_content # Keep error message as is
            # --- END REFORMAT ---
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            if i < total_files - 1: 
                 sleep_duration = 3.0 
                 time.sleep(sleep_duration) 
                 print(f"Paused for {sleep_duration} seconds...")

        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            try:
                with open(output_filepath, 'w', encoding='utf-8') as f_err: 
                    f_err.write(f"[ERROR PROCESSING FILE: {e}]\n\nOriginal content could not be translated.")
                print(f"Error marker written to: {output_filepath}")
            except Exception as e_write:
                print(f"Additionally, could not write error to output file {output_filepath}: {e_write}")
    
    print(f"\n--- Translation Run Summary ---")
    print(f"Total source files checked: {total_files}")
    print(f"Files attempted for translation in this run: {attempted_translations_count}")
    print(f"Files skipped (already existed and seemed valid): {skipped_count}")
    print(f"-----------------------------")

if __name__ == "__main__":
    model_id_for_main_log = 'models/gemini-2.5-pro-exp-03-25'
    print(f"Starting translation process with {model_id_for_main_log} using genai.Client style...")
    print(f"Input folder: '{INPUT_DIR}'")
    print(f"Output folder: '{OUTPUT_DIR}' (Will only translate missing or invalid files)")
    
    process_files_for_translation()
    print("Translation process finished.")
