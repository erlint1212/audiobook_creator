import os
import time
import re
# Ensure you have the google-generativeai package installed
# pip install -U google-generativeai

# --- Configuration ---
# INPUT_DIR should contain your raw, unannotated English .txt files (e.g., from your scraping)
INPUT_DIR = "scraped_IATMCB_celsetial_pavilion" 
# OUTPUT_DIR is where the annotated files (ready for the Alltalk TTS script) will be saved
OUTPUT_DIR = "annotated_IATMCB_for_tts" 

# Define the 5 Half Light emotional style tags the script will use in the prompt
# These must match the tags your Alltalk TTS script expects.
HALF_LIGHT_STYLE_TAGS = [
    "[HL_Neutral_Narrative]",
    "[HL_Weary_Cynical]",
    "[HL_Internal_Thoughtful]",
    "[HL_Intense_Strained]",
    "[HL_Slightly_Unhinged_Insight]"
]

# --- Helper Function to Reformat Title (Optional - can be applied after annotation) ---
def reformat_chapter_title_in_text(text_content: str) -> str:
    if not text_content or not text_content.strip():
        return text_content

    lines = text_content.split('\n', 1)
    first_line = lines[0]
    rest_of_content = lines[1] if len(lines) > 1 else ""

    # Try to match "Chapter X: Title" or "Chapter X - Title"
    match = re.match(r'^(Chapter\s*\d+)\s*[:\-–—]?\s*(.*)', first_line, re.IGNORECASE)
    if match:
        chapter_part = match.group(1).strip()
        title_part = match.group(2).strip()
        # Ensure consistent "Chapter X - Title" format
        reformatted_first_line = f"{chapter_part} - {title_part}" if title_part else chapter_part
        return f"{reformatted_first_line}\n{rest_of_content}"

    # Try to match "NUMBER Title"
    numeric_match = re.match(r'^(\d+)\s+(.*)', first_line)
    if numeric_match:
        try:
            chapter_number_int = int(numeric_match.group(1))
            title_part = numeric_match.group(2).strip()
            reformatted_first_line = f"Chapter {chapter_number_int} - {title_part}"
            return f"{reformatted_first_line}\n{rest_of_content}"
        except ValueError:
            # Not a simple number leading the title
            pass
    return text_content

# --- Gemini API Annotation Function ---
def annotate_text_with_gemini(text_to_annotate: str) -> str:
    try:
        import google.generativeai as genai_sdk
    except ImportError:
        print("CRITICAL ERROR: The 'google-generativeai' package is not installed.")
        return "[Annotation Error: The 'google-generativeai' package is not installed.]"

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "[Annotation Error: 'GEMINI_API_KEY' environment variable not set.]"

    genai_sdk.configure(api_key=api_key)
    
    # Your log indicates you're using this model. Ensure it's still valid.
    model_name_for_api = "gemini-2.5-flash-preview-04-17" 
    # If issues persist, try a stable alternative:
    # model_name_for_api = "gemini-1.5-flash-latest" 

    print(f"Attempting to annotate English text (length: {len(text_to_annotate)} chars) with Half Light styles using {model_name_for_api}...")

    style_definitions = (
        "1.  `[HL_Neutral_Narrative]`: Use for general narration, descriptions of settings or actions, and calm, objective exposition. The tone is Half Light's baseline observational voice.\n"
        "2.  `[HL_Weary_Cynical]`: Use for lines expressing fatigue, disillusionment, sarcasm, or dry, cynical observations about events, characters, or the world.\n"
        "3.  `[HL_Internal_Thoughtful]`: Use for introspective lines, internal monologues by the main character (as narrated by Half Light), moments of quiet realization, contemplation, or when memories surface.\n"
        "4.  `[HL_Intense_Strained]`: Use for lines describing or during moments of high tension, urgency, duress, conflict, violence, or when strong negative emotions like anger, fear, or pain are prominent.\n"
        "5.  `[HL_Slightly_Unhinged_Insight]`: Use for lines where Half Light's unique, sometimes fractured, perception of reality comes through, or when he offers a piece of peculiar, unsettling wisdom or a profound, bleak observation."
    )

    prompt = (
        f"You are an expert text annotator. Your primary goal is to process a chapter from a novel and insert emotional style tags appropriate for a narration by the character \"Half Light\" from Disco Elysium. The aim is to create an annotated version of the original text where tags precede substantial blocks of text (ideally multiple sentences or paragraphs) that share a consistent emotional tone. Your output MUST be only the original text with these tags inserted.\n\n"
        f"The 5 emotional style tags to use are:\n"
        "1.  `[HL_Neutral_Narrative]`: Use for general narration, descriptions of settings or actions, and calm, objective exposition. This tag should cover extended passages of neutral storytelling.\n"
        "2.  `[HL_Weary_Cynical]`: Use for sections expressing sustained fatigue, disillusionment, sarcasm, or dry, cynical observations about events, characters, or the world. This tone may persist for several lines or paragraphs.\n"
        "3.  `[HL_Internal_Thoughtful]`: Use for blocks of text reflecting introspective lines, internal monologues by the main character (as narrated by Half Light), moments of quiet realization, contemplation, or when memories surface. This can cover a character's extended thought process.\n"
        "4.  `[HL_Intense_Strained]`: Use for passages describing or occurring during moments of high tension, urgency, duress, conflict, violence, or when strong negative emotions like anger, fear, or pain are prominent and sustained for a period.\n"
        "5.  `[HL_Slightly_Unhinged_Insight]`: Use for segments where Half Light's unique, sometimes fractured, perception of reality comes through, or when he offers a piece of peculiar, unsettling wisdom or a profound, bleak observation that might color several subsequent lines.\n\n"
        f"CRITICAL INSTRUCTIONS FOR BLOCK SIZE AND TAG PLACEMENT:\n"
        f"- **Prioritize larger blocks of text under a single tag.** Avoid inserting a new tag for every sentence or short line unless there is a very clear and significant shift in emotional tone.\n"
        f"- A single tag should ideally cover multiple sentences, and often multiple paragraphs, if the emotional tone or narrative style remains consistent. If a style lasts for half a page, use one tag for that half page.\n"
        f"- Only insert a new style tag when you detect a **distinct and meaningful change** in the required narrative emotion from the previous block of text. If the emotion is subtly shifting but still broadly within the same category, do not add a new tag.\n"
        f"- Use the MINIMUM number of tags necessary. Strive for the fewest tags possible while still capturing major emotional shifts.\n"
        f"- Each tag (e.g., `[HL_Neutral_Narrative]`) MUST be on its own line, immediately preceding the text block it applies to.\n"
        f"- Preserve the original paragraph structure and all original text. Ensure no text is lost or summarized.\n"
        f"- Do NOT add any extra explanations, summaries, apologies, preambles, or any text other than the original text with the inserted tags.\n"
        f"- Do NOT use any other markers or annotations. Only use the 5 provided tags.\n"
        f"- Apply tags thoughtfully to capture significant shifts in narrative tone and emotion, aiming for a natural flow suitable for audiobook narration where a narrator wouldn't change their core emotion line by line unless absolutely necessary.\n\n"
        f"EXAMPLE OF DESIRED ANNOTATION STYLE:\n\n"
        f"--- EXAMPLE INPUT TEXT START ---\n"
        "The old detective stared out at the rain-slicked streets of Revachol. Another dead-end case, another bottle nearing empty. He sighed, the sound like gravel shifting in a forgotten crypt. This city, it chewed you up and spat you out, leaving nothing but a bitter taste and a ringing in your ears.\n\n"
        "He remembered a different time, or thought he did. Flashes of sunlight on a forgotten shore. A woman's laughter, like wind chimes. Were they real? Or just phantoms conjured by a desperate mind? He rubbed his temples. The thoughts were slippery, like eels in the dark.\n\n"
        "Suddenly, a sharp rap on the door. His hand instinctively went to the worn butt of his pistol. 'Who is it?' he growled, his voice rougher than usual. The only answer was another, more insistent knock. He braced himself. Trouble always found him, didn't it? It was practically a calling card.\n"
        f"--- EXAMPLE INPUT TEXT END ---\n\n"
        f"--- CORRECTLY ANNOTATED EXAMPLE OUTPUT START ---\n"
        "[HL_Weary_Cynical]\n"
        "The old detective stared out at the rain-slicked streets of Revachol. Another dead-end case, another bottle nearing empty. He sighed, the sound like gravel shifting in a forgotten crypt. This city, it chewed you up and spat you out, leaving nothing but a bitter taste and a ringing in your ears.\n\n"
        "[HL_Internal_Thoughtful]\n"
        "He remembered a different time, or thought he did. Flashes of sunlight on a forgotten shore. A woman's laughter, like wind chimes. Were they real? Or just phantoms conjured by a desperate mind? He rubbed his temples. The thoughts were slippery, like eels in the dark.\n\n"
        "[HL_Intense_Strained]\n"
        "Suddenly, a sharp rap on the door. His hand instinctively went to the worn butt of his pistol. 'Who is it?' he growled, his voice rougher than usual. The only answer was another, more insistent knock. He braced himself. Trouble always found him, didn't it? It was practically a calling card.\n"
        f"--- CORRECTLY ANNOTATED EXAMPLE OUTPUT END ---\n\n"
        f"Now, apply this same principle of substantial, emotionally consistent blocks using the MINIMUM number of tags necessary to the text provided below.\n\n"
        f"--- TEXT TO ANNOTATE START ---\n"
        f"{text_to_annotate}"
        f"\n--- TEXT TO ANNOTATE END ---\n\n"
        f"Please provide ONLY the annotated text, with tags applied to appropriately sized blocks, below:"
    )
    try:
        # Corrected: Initialize model without request_options
        model = genai_sdk.GenerativeModel(
            model_name_for_api
        )
        
        # Corrected: Pass request_options to generate_content
        response = model.generate_content(
            prompt,
            generation_config=genai_sdk.types.GenerationConfig(temperature=0.3),
            request_options={"timeout": 400} # Set timeout for the API call
        )

        annotated_text = ""
        if response.text:
            annotated_text = response.text
        elif response.candidates:
            try:
                annotated_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            except (IndexError, AttributeError, TypeError) as e_cand:
                print(f"Warning: Could not extract text using candidate structure. Error: {e_cand}. Candidate content: {response.candidates[0].content if response.candidates else 'No candidates'}")
                return "[Annotation Error: Could not extract text from API response candidate structure.]"
        else:
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                block_reason_str = str(response.prompt_feedback.block_reason)
                print(f"Warning: Prompt blocked by API. Reason: {block_reason_str}")
                return f"[Annotation Error: Prompt blocked by API - {block_reason_str}]"
            print(f"Warning: No text found in response and not blocked. Full response: {response}")
            return "[Annotation Error: No text found in API response and not explicitly blocked.]"
        
        print(f"Annotation API call successful with {model_name_for_api}.")
        return annotated_text.strip() # Strip any leading/trailing whitespace from the whole response
    except Exception as e:
        error_type = type(e).__name__
        print(f"An error occurred during annotation with {model_name_for_api}: {error_type} - {e}")
        if hasattr(e, 'args') and e.args: print(f"Error details: {e.args}")
        return f"[Annotation Error ({model_name_for_api} - {error_type}): {str(e)[:500]}]\n\nOriginal Text (first 100 chars):\n{text_to_annotate[:100]}..."

# --- Main Processing Logic ---
def process_files_for_annotation():
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

    print(f"Found {total_files} potential file(s) to process from '{INPUT_DIR}' for annotation.")
    attempted_annotations_count = 0
    skipped_count = 0

    for i, filename in enumerate(files_to_process):
        input_filepath = os.path.join(INPUT_DIR, filename)
        output_filepath = os.path.join(OUTPUT_DIR, filename) # Save with the same name in the output dir
        print(f"\n[{i+1}/{total_files}] Checking: {filename}...")

        # Simple check: if output exists and is not an error marker, skip.
        if os.path.exists(output_filepath):
            is_valid_annotation = True
            try:
                if os.path.getsize(output_filepath) < 20: # Annotated files should be slightly larger
                    is_valid_annotation = False
                    print(f"Output file '{output_filepath}' exists but is very small. Will re-annotate.")
                else:
                    with open(output_filepath, 'r', encoding='utf-8') as f_check:
                        content_check = f_check.read(500) # Read more to check for tags
                        if "[Annotation Error" in content_check or "[ERROR PROCESSING FILE" in content_check:
                            is_valid_annotation = False
                            print(f"Output file '{output_filepath}' exists but contains an error marker. Will re-annotate.")
                        # Check if it actually contains any of our style tags
                        elif not any(tag in content_check for tag in HALF_LIGHT_STYLE_TAGS):
                            is_valid_annotation = False
                            print(f"Output file '{output_filepath}' exists but does not seem to contain style tags. Will re-annotate.")
            except Exception as e_check:
                print(f"Could not properly check existing file {output_filepath}, assuming it's fine: {e_check}")

            if is_valid_annotation:
                print(f"Output file '{output_filepath}' already exists and seems validly annotated. Skipping.")
                skipped_count += 1
                continue
        
        attempted_annotations_count +=1
        print(f"Processing for annotation: {filename} (to {output_filepath})")

        try:
            with open(input_filepath, 'r', encoding='utf-8') as f:
                source_content = f.read()
            
            if not source_content.strip():
                print(f"  Input file '{filename}' is empty. Skipping annotation, writing empty output.")
                annotated_content = "" # Or a specific marker like "[Empty Source File]"
            else:
                # Optional: Apply title reformatting to the source before sending to API if needed
                # source_content_for_api = reformat_chapter_title_in_text(source_content)
                source_content_for_api = source_content # Usually better to annotate raw then format
                
                print(f"  Sending text (length: {len(source_content_for_api)} chars) to API for annotation...")
                annotated_content = annotate_text_with_gemini(source_content_for_api)
            
            final_content_to_write = annotated_content

            # Optional: Apply title reformatting to the *annotated* output
            if not (annotated_content.startswith("[Annotation Error") or 
                    annotated_content.startswith("[ERROR PROCESSING FILE")):
                final_content_to_write = reformat_chapter_title_in_text(annotated_content) # Apply to the AI's output
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(final_content_to_write)
            print(f"Saved: {output_filepath}")

            if i < total_files - 1: # Avoid API rate limits if processing many files
                 sleep_duration = 5.0 # Adjust as needed
                 print(f"Pausing for {sleep_duration} seconds before next file...")
                 time.sleep(sleep_duration)

        except Exception as e:
            print(f"FATAL Error processing file {filename}: {e}")
            try:
                with open(output_filepath, 'w', encoding='utf-8') as f_err:
                    f_err.write(f"[ERROR PROCESSING FILE: {e}]\n\nOriginal content from '{filename}' could not be annotated.")
                print(f"Error marker written to: {output_filepath}")
            except Exception as e_write:
                print(f"Additionally, could not write error to output file {output_filepath}: {e_write}")

    print(f"\n--- Annotation Run Summary ---")
    print(f"Total source files checked: {total_files}")
    print(f"Files attempted for annotation in this run: {attempted_annotations_count}")
    print(f"Files skipped (already existed and seemed validly annotated): {skipped_count}")
    print(f"-----------------------------")

if __name__ == "__main__":
    print(f"Starting Text Annotation process for Half Light TTS...")
    print(f"Input folder (raw English text): '{INPUT_DIR}'")
    print(f"Output folder (annotated text): '{OUTPUT_DIR}'")

    if not os.environ.get("GEMINI_API_KEY"):
        print("\nCRITICAL ERROR: The 'GEMINI_API_KEY' environment variable is not set.")
        print("Please set it before running the script.")
        exit()
        
    process_files_for_annotation()
    print("Annotation process finished.")
