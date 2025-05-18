import os
import time
import re
# Ensure you have the google-generativeai package installed
# pip install -U google-generativeai

# --- Configuration ---
INPUT_DIR = "scraped_syosetu_n9045bm"
OUTPUT_DIR = "translated_syosetu_n9045bm_en"

# --- Helper Function to Reformat Title (primarily for English translated titles) ---
def reformat_chapter_title_in_text(text_content: str) -> str:
    if not text_content or not text_content.strip():
        return text_content

    lines = text_content.split('\n', 1)
    first_line = lines[0]
    rest_of_content = lines[1] if len(lines) > 1 else ""

    match = re.match(r'^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)', first_line, re.IGNORECASE)
    if match:
        chapter_part = match.group(1).strip()
        title_part = match.group(2).strip()
        reformatted_first_line = f"{chapter_part} - {title_part}" if title_part else chapter_part
        return f"{reformatted_first_line}\n{rest_of_content}"

    numeric_match = re.match(r'^(\d+)\s+(.*)', first_line)
    if numeric_match:
        try:
            chapter_number_int = int(numeric_match.group(1))
            title_part = numeric_match.group(2).strip()
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            return f"{reformatted_first_line}\n{rest_of_content}"
        except ValueError:
            pass
    return text_content

# --- Gemini API Translation Function ---
def translate_text_with_gemini(text_to_translate: str, target_language: str = "English") -> str:
    try:
        import google.generativeai as genai_sdk
    except ImportError:
        print("CRITICAL ERROR: The 'google-generativeai' package is not installed.")
        return "[Translation Error: The 'google-generativeai' package is not installed.]"

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return "[Translation Error: 'GOOGLE_API_KEY' environment variable not set.]"

    genai_sdk.configure(api_key=api_key)
    
    # Ensure this is the model you intend to use.
    # Using "gemini-1.5-flash-latest" as a generally stable and available option.
    # You were using "gemini-2.5-flash-preview-04-17". If you switch back, ensure it's active.
    # model_name_for_api = "gemini-1.5-flash-latest"
    model_name_for_api = "gemini-2.5-flash-preview-04-17" # Your previously used model

    print(f"Attempting to translate Japanese text (length: {len(text_to_translate)} chars) to {target_language} using {model_name_for_api}...")

    # --- Strengthened Prompt ---
    prompt = (
        f"You are an expert Japanese-to-English translator. Your sole task is to translate the following Japanese text into high-quality, natural-sounding {target_language}. "
        f"CRITICAL INSTRUCTION: Your response MUST CONTAIN ONLY THE {target_language.upper()} TRANSLATION. "
        f"DO NOT include any of the original Japanese text in your response. "
        f"DO NOT include any extra explanations, apologies, summaries, preambles, or any text other than the direct {target_language} translation. "
        f"DO NOT use any markers like '' or similar annotations in your response. "
        f"Replace the Japanese text entirely with its {target_language} equivalent. "
        "Maintain the original paragraph structure and preserve the meaning and nuances of the source text, including the tone and style, appropriate for an English-speaking audience. "
        "If Japanese honorifics (e.g., -san, -chan, -kun, -sama) are present, translate them into appropriate English equivalents or omit them if it makes the English more natural, unless they are critical for character dynamics (in which case, use common English conventions or briefly note if essential, but prioritize smooth English). "
        "Ensure chapter titles, if present at the beginning of the text, are also translated and appear on their own line(s) as in the original structure. "
        "\n\n--- JAPANESE TEXT TO TRANSLATE START ---\n"
        f"{text_to_translate}"
        "\n--- JAPANESE TEXT TO TRANSLATE END ---\n\n"
        f"Please provide ONLY the {target_language.upper()} translation below:"
    )

    try:
        model = genai_sdk.GenerativeModel(
            model_name_for_api,
            request_options={"timeout": 300} # 5 minute timeout
        )
        response = model.generate_content(
            prompt,
            # To potentially increase determinism if still getting Japanese text:
            generation_config=genai_sdk.types.GenerationConfig(temperature=0.2)
        )

        translated_text = ""
        if response.text:
            translated_text = response.text
        elif response.candidates:
            try:
                # Ensure all parts are concatenated correctly
                translated_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            except (IndexError, AttributeError, TypeError) as e_cand:
                print(f"Warning: Could not extract text using candidate structure. Error: {e_cand}. Candidate content: {response.candidates[0].content if response.candidates else 'No candidates'}")
                return "[Translation Error: Could not extract text from API response candidate structure.]"
        else:
            # Check for blockages
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason_str = str(response.prompt_feedback.block_reason)
                print(f"Warning: Prompt blocked by API. Reason: {block_reason_str}")
                return f"[Translation Error: Prompt blocked by API - {block_reason_str}]"
            print(f"Warning: No text found in response and not blocked. Full response: {response}")
            return "[Translation Error: No text found in API response and not explicitly blocked.]"
        
        # Clean up any potential leftover markers, though the prompt aims to prevent them.
        translated_text = re.sub(r'\n---\s*' + target_language.upper() + r'\s*TRANSLATION\s*(END|START)\s*---', '', translated_text, flags=re.IGNORECASE).strip()
        translated_text = re.sub(r'^ENGLISH TRANSLATION ONLY:[\s\n]*', '', translated_text, flags=re.IGNORECASE).strip() # Remove our own prompt ending

        print(f"Translation API call successful with {model_name_for_api}.")
        return translated_text
    except Exception as e:
        # More detailed error logging
        error_type = type(e).__name__
        print(f"An error occurred during translation with {model_name_for_api}: {error_type} - {e}")
        # Log more details if it's a specific Google API error
        if hasattr(e, 'args') and e.args:
            print(f"Error details: {e.args}")
        return f"[Translation Error ({model_name_for_api} - {error_type}): {str(e)[:500]}]\n\nOriginal Text (first 100 chars):\n{text_to_translate[:100]}..."

# --- Main Processing Logic ---
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
        output_filepath = os.path.join(OUTPUT_DIR, filename)
        print(f"\n[{i+1}/{total_files}] Checking: {filename}...")

        if os.path.exists(output_filepath):
            is_valid_translation = True
            try:
                if os.path.getsize(output_filepath) < 10:
                    is_valid_translation = False
                    print(f"Output file '{output_filepath}' exists but is very small. Will re-translate.")
                else:
                    with open(output_filepath, 'r', encoding='utf-8') as f_check:
                        content_check = f_check.read(200)
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
        print(f"Processing for translation: {filename} (to {output_filepath})")

        try:
            with open(input_filepath, 'r', encoding='utf-8') as f:
                source_content = f.read()
            
            # --- Crucial: Pre-process input if it contains tags and mixed English/Japanese ---
            # This part assumes your INPUT file might be structured like the ch_259.txt you uploaded
            # It tries to extract only the Japanese lines before sending to API
            
            lines_for_translation = []
            potential_japanese_buffer = []

            for line in source_content.splitlines():
                line_stripped = line.strip()
                if line_stripped.startswith("<Japanese Text>")
                    # Skip the line
                    continue
                
                # A simple heuristic: if a line is not a source tag and not empty, assume it's Japanese.
                # This might need refinement if English lines (not part of source tags) are also present.
                if line_stripped: # If line is not empty
                    # Check if it is predominantly English or other non-Japanese (heuristic)
                    # This is a very basic check.
                    if not re.match(r'^[a-zA-Z0-9\s\W]*$', line_stripped) or \
                       re.search(r'[\u3040-\u30ff\u31f0-\u31ff\u3400-\u9fff]', line_stripped): # Contains Japanese
                        potential_japanese_buffer.append(line_stripped)
                    else: # Likely an English line that's not a source tag
                        if potential_japanese_buffer: # If there was Japanese before this English, add it.
                             lines_for_translation.extend(potential_japanese_buffer)
                             lines_for_translation.append("")
                             potential_japanese_buffer = []
                        # Decide whether to skip these non-source-tag English lines or include them (currently skips)
                        # print(f"  Skipping non-source, potentially English line: {line_stripped[:50]}...")
                elif potential_japanese_buffer: # Empty line, flush buffer
                    lines_for_translation.extend(potential_japanese_buffer)
                    lines_for_translation.append("") # Preserve paragraph break
                    potential_japanese_buffer = []
            
            if potential_japanese_buffer: # Add any remaining buffered lines
                lines_for_translation.extend(potential_japanese_buffer)

            clean_source_for_api = "\n".join(lines_for_translation).strip()

            if not clean_source_for_api: # After cleaning, if no Japanese text is left
                print(f"  No Japanese content extracted from '{filename}' after pre-processing. Output will be marked.")
                translated_content = "[No Japanese content found in source after pre-processing]"
            else:
                print(f"  Sending cleaned Japanese text (length: {len(clean_source_for_api)} chars) to API...")
                translated_content = translate_text_with_gemini(clean_source_for_api, target_language="English")
            
            final_content_to_write = translated_content

            if not (translated_content.startswith("[Translation Error") or \
                    translated_content.startswith("[ERROR PROCESSING FILE") or \
                    translated_content.startswith("[No Japanese content found")):
                
                # Heuristic check for remaining Japanese in output
                japanese_chars_in_output = len(re.findall(r'[\u3040-\u30ff\u31f0-\u31ff\u3200-\u32ff\u3300-\u33ff\u3400-\u4dbf\u4dc0-\u4dff\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]', translated_content))
                content_len = len(translated_content)
                
                if content_len > 50 and (japanese_chars_in_output / content_len) > 0.05: # If >5% Japanese chars
                    print(f"Warning: Output for '{filename}' still appears to contain significant Japanese text. This might indicate a translation issue or that the API did not fully comply with the prompt. Output will be saved as is, but review is recommended.")
                    # final_content_to_write remains translated_content
                else:
                    print("Applying post-translation title reformatting (if applicable)...")
                    final_content_to_write = reformat_chapter_title_in_text(translated_content)
            else:
                print("Skipping title reformat due to prior error or no content.")
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            if i < total_files - 1:
                 sleep_duration = 5.0
                 print(f"Pausing for {sleep_duration} seconds...")
                 time.sleep(sleep_duration)

        except Exception as e:
            print(f"FATAL Error processing file {filename}: {e}")
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

    if not os.environ.get("GOOGLE_API_KEY"):
        print("\nCRITICAL ERROR: The 'GOOGLE_API_KEY' environment variable is not set.")
        print("Please set it before running the script.")
        exit()
        
    process_files_for_translation()
    print("Translation process finished.")
