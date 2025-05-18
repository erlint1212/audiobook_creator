import os
import time
import re
from google.cloud import aiplatform # For Vertex AI
from google.auth import default as default_auth # For Vertex AI authentication

# --- Configuration ---
# Adjust these paths to match your project structure
# INPUT_DIR should point to where your Japanese .txt files from the scraper are
INPUT_DIR = "scraped_syosetu_n9045bm"  # Or "scraped_novel_jp"
# OUTPUT_DIR is where the translated English .txt files will be saved
OUTPUT_DIR = "translated_syosetu_n9045bm_en" # Or "translated_novel_en"

# Vertex AI Configuration (if you switch to Vertex AI SDK)
# PROJECT_ID = "your-gcp-project-id"  # Replace with your Google Cloud Project ID
# LOCATION = "your-gcp-project-location"    # Replace with your Project Location (e.g., "us-central1")
# MODEL_ID_FOR_VERTEX = "gemini-1.5-flash-001" # Example Vertex AI model

# --- Helper Function to Reformat Title (Assumes English title format after translation) ---
def reformat_chapter_title_in_text(text_content: str) -> str:
    """
    Reformats the first line of the text if it looks like a chapter title
    that might have been translated as "Chapter X: Title" or similar.
    Aims for "Chapter X - Title" or leaves as is if no clear pattern.
    This function might need adjustment based on how Gemini translates titles.
    """
    if not text_content or not text_content.strip():
        return text_content

    lines = text_content.split('\n', 1)
    first_line = lines[0]
    rest_of_content = lines[1] if len(lines) > 1 else "" # Ensure rest_of_content is a string

    # Regex to find titles like "Chapter 123 Title" or "Chapter 123: Title" or "Chapter 123 - Title"
    # It tries to capture the "Chapter X" part and the "Title" part.
    match = re.match(r'^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)', first_line, re.IGNORECASE)

    if match:
        chapter_part = match.group(1) # "Chapter 123"
        title_part = match.group(2)   # "Title"

        # If title_part is empty, it might mean the original was just "Chapter 123"
        if not title_part.strip() and ':' in first_line or '-' in first_line:
            # This could be a case where the title was on a new line in the source
            # and the translation put "Chapter X:" alone. We'll just use the chapter part.
             reformatted_first_line = chapter_part.strip()
        elif title_part.strip():
            reformatted_first_line = f"{chapter_part.strip()} - {title_part.strip()}"
        else: # Only chapter number was present, or no clear title part
            reformatted_first_line = chapter_part.strip()


        return f"{reformatted_first_line}\n{rest_of_content}"

    # Fallback for titles that might just be numbers if `reformat_chapter_title_in_text`
    # from your original script was intended for pre-translation formatting.
    # This assumes the title might be numeric *after* translation (less likely for Jap->Eng).
    numeric_match = re.match(r'^(\d+)\s+(.*)', first_line)
    if numeric_match:
        chapter_number_str = numeric_match.group(1)
        title_part = numeric_match.group(2)
        try:
            chapter_number_int = int(chapter_number_str)
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            return f"{reformatted_first_line}\n{rest_of_content}"
        except ValueError:
            pass # Ignore if not a simple number

    return text_content # Return original text if no relevant match

# --- Gemini API Translation Function ---
def translate_text_with_gemini(text_to_translate: str, target_language: str = "English") -> str:
    """
    Translates text using the Gemini API via the google-generativeai SDK.
    """
    # Ensure you have the `google-generativeai` package installed
    # and `GEMINI_API_KEY` environment variable set.
    try:
        import google.generativeai as genai_sdk # Renamed to avoid conflict if you have `google.genai`
    except ImportError:
        return "[Translation Error: The 'google-generativeai' package is not installed or 'GEMINI_API_KEY' is not set.]"

    api_key = os.environ.get("GEMINI_API_KEY") # Standard env var for this SDK
    if not api_key:
        return "[Translation Error: 'GEMINI_API_KEY' environment variable not set.]"

    genai_sdk.configure(api_key=api_key)
    model_name_for_api = "gemini-2.5-flash-preview-04-17" # Or your preferred model like "gemini-pro"
    
    print(f"Attempting to translate Japanese text (length: {len(text_to_translate)} chars) to {target_language} using {model_name_for_api}...")

    # Improved prompt for Japanese to English translation
    prompt = (
        f"Please translate the following Japanese text into natural-sounding, high-quality {target_language}. "
        "Pay attention to context, nuances, and try to convey the original tone and style appropriately for an English-speaking audience. "
        "If there are Japanese honorifics (e.g., -san, -chan, -kun, -sama), translate them into appropriate English equivalents or omit them if it makes the English more natural, unless they are critical for character dynamics (in which case, you can briefly note the original honorific in parentheses if essential for a first-time explanation, but generally aim for smooth English). "
        "Preserve the original structure, such as chapter titles on their own lines, and maintain paragraph breaks as in the original. "
        "Do not add any extra summaries, commentary, or text that was not part of the original Japanese input, other than the translation itself."
        "Do not echo back the Japanese text"
        "\n\n--- JAPANESE TEXT START ---\n"
        f"{text_to_translate}"
        "\n--- JAPANESE TEXT END ---\n\n"
        f"{target_language.upper()} TRANSLATION:"
    )

    try:
        model = genai_sdk.GenerativeModel(model_name_for_api)
        response = model.generate_content(
            prompt,
            # Optional: Add generation_config if needed
            # generation_config=genai_sdk.types.GenerationConfig(
            #     temperature=0.7,  # Adjust for creativity vs. fidelity
            # )
        )

        if response.text:
            translated_text = response.text
        elif response.candidates:
            try:
                translated_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            except (IndexError, AttributeError, TypeError) as e:
                print(f"Warning: Could not extract text using candidate structure. Error: {e} Response: {response.candidates[0].content if response.candidates else 'No candidates'}")
                return "[Translation Error: Could not extract text from API response candidate structure.]"
        else:
            print(f"Warning: No text found in response. Full response: {response}")
            return "[Translation Error: No text found in API response.]"
        
        # Remove any potential "ENGLISH TRANSLATION END" markers if the model adds them.
        translated_text = re.sub(r'\n---\s*' + target_language.upper() + r'\s*TRANSLATION\s*(END|START)\s*---', '', translated_text, flags=re.IGNORECASE).strip()

        print(f"Translation successful with {model_name_for_api}.")
        return translated_text
    except Exception as e:
        print(f"An error occurred during translation with {model_name_for_api}: {type(e).__name__} - {e}")
        # Consider logging the full error or parts of the text_to_translate for debugging
        return f"[Translation Error ({model_name_for_api}): {str(e)[:500]}]\n\nOriginal Text (first 100 chars):\n{text_to_translate[:100]}..."

# --- Main Processing Logic (Mostly unchanged, but uses updated paths and function calls) ---
def process_files_for_translation():
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

    # Process files sorted by name (e.g., ch_001.txt, ch_002.txt)
    files_to_process = sorted([f for f in os.listdir(INPUT_DIR) if f.endswith(".txt") and os.path.isfile(os.path.join(INPUT_DIR, f))])
    total_files = len(files_to_process)
    
    if total_files == 0:
        print(f"No .txt files found in '{INPUT_DIR}'.")
        return

    print(f"Found {total_files} potential file(s) to process from '{INPUT_DIR}'.")
    
    attempted_translations_count = 0
    skipped_count = 0

    for i, filename in enumerate(files_to_process):
        input_filepath = os.path.join(INPUT_DIR, filename)
        # For Syosetu, output filename should probably be the same as input
        output_filename = filename # e.g. "ch_259.txt"
        output_filepath = os.path.join(OUTPUT_DIR, output_filename)


        print(f"\n[{i+1}/{total_files}] Checking: {filename}...")

        if os.path.exists(output_filepath):
            is_valid_translation = True 
            try:
                if os.path.getsize(output_filepath) < 10: # Check for very small files (likely errors or empty)
                    is_valid_translation = False
                    print(f"Output file '{output_filepath}' exists but is very small. Will re-translate.")
                else:
                    with open(output_filepath, 'r', encoding='utf-8') as f_check:
                        content_check = f_check.read(200) # Read a bit more to catch error markers
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
                source_content = f.read() # Changed variable name for clarity
            
            translated_content = ""
            if not source_content.strip():
                print("Source file is empty. Creating an empty output file.")
                # translated_content will remain empty
            else:
                translated_content = translate_text_with_gemini(source_content, target_language="English") # Explicitly English
            
            # --- REFORMAT THE TITLE (if needed for translated content) ---
            # This step assumes the title is the first line of the translated_content
            if not (translated_content.startswith("[Translation Error") or translated_content.startswith("[ERROR PROCESSING FILE")):
                print("Applying post-translation title reformatting (if applicable)...")
                final_content_to_write = reformat_chapter_title_in_text(translated_content)
            else:
                print("Skipping title reformat due to translation error.")
                final_content_to_write = translated_content
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            if i < total_files - 1: 
                 sleep_duration = 1.0 # Increased sleep duration to be safer with API rate limits
                 print(f"Pausing for {sleep_duration} seconds...")
                 time.sleep(sleep_duration) 

        except Exception as e:
            print(f"Error processing file {filename}: {e}")
            try:
                with open(output_filepath, 'w', encoding='utf-8') as f_err: 
                    f_err.write(f"[ERROR PROCESSING FILE: {e}]\n\nOriginal content from '{filename}' could not be translated.")
                print(f"Error marker written to: {output_filepath}")
            except Exception as e_write:
                print(f"Additionally, could not write error to output file {output_filepath}: {e_write}")
    
    print(f"\n--- Translation Run Summary ---")
    print(f"Total source files checked: {total_files}")
    print(f"Files attempted for translation in this run: {attempted_translations_count}")
    print(f"Files skipped (already existed and seemed valid): {skipped_count}")
    print(f"-----------------------------")

if __name__ == "__main__":
    print(f"Starting Japanese to English translation process...")
    print(f"Input folder: '{INPUT_DIR}'")
    print(f"Output folder: '{OUTPUT_DIR}' (Will only translate missing or previously errored files)")
    
    # Important: Ensure your GEMINI_API_KEY environment variable is set.
    if not os.environ.get("GEMINI_API_KEY"):
        print("\nCRITICAL ERROR: The 'GEMINI_API_KEY' environment variable is not set.")
        print("Please set it before running the script.")
        print("Example (Linux/macOS): export GEMINI_API_KEY='your_api_key_here'")
        print("Example (Windows CMD): set GEMINI_API_KEY=your_api_key_here")
        print("Example (Windows PowerShell): $env:GEMINI_API_KEY='your_api_key_here'")
        exit()
        
    process_files_for_translation()
    print("Translation process finished.")
