import os
import glob
import re
import json
import time
import pathlib

try:
    from google import genai    
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    print("ERROR: The 'google-generativeai' package is not installed. This script cannot run.")
    print("Please install it: pip install google-generativeai")
    GOOGLE_GENAI_AVAILABLE = False

try:
    import nltk
    from nltk.tokenize import sent_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    print("Warning: NLTK library not found or an issue with download path. Sentence tokenization for chunking will be very basic.")
    NLTK_AVAILABLE = False
    def sent_tokenize(text):
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
except Exception as e_nltk: # Catch other NLTK download/path issues
    print(f"Warning: NLTK setup issue ({e_nltk}). Sentence tokenization will be basic.")
    NLTK_AVAILABLE = False
    def sent_tokenize(text):
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

# --- Configuration ---
ORIGINAL_TEXT_DIR = "scraped_tileas_worries"  # Source texts
TAGGED_TEXT_OUTPUT_DIR = "scraped_tileas_worries_tagged_gemini" # Output for tagged files
CHARACTER_VOICE_MAP_FILE = "character_voice_config.json"
API_KEY_ENV_VARIABLE = "GEMINI_API_KEY" # Your environment variable for the API key

# Paths to your voice files (use forward slashes for consistency)
VOICES_BASE_DIR_FULL = "C:/Users/etnor/Documents/tts/alltalk_tts/voices"
RVC_MODELS_BASE_DIR_FULL = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices"

MALE_XTTS_VOICES = [
    os.path.join(VOICES_BASE_DIR_FULL, "male_01.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "male_02.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "male_03.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "male_04.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "male_05.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "Arnold.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "Clint_Eastwood CC3 (enhanced).wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "David_Attenborough CC3.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "James_Earl_Jones CC3.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "Joshua_Graham.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "Morgan_Freeman CC3.wav").replace('\\', '/'),
]

FEMALE_XTTS_VOICES = [
    os.path.join(VOICES_BASE_DIR_FULL, "female_01.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_02.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_03.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_04.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_05.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_06.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "female_07.wav").replace('\\', '/'),
    os.path.join(VOICES_BASE_DIR_FULL, "Sophie_Anderson CC3.wav").replace('\\', '/'),
]

DEFAULT_NARRATOR_CONFIG = {
    "original_name": "NARRATOR",
    "gender": "n",
    "xtts_speaker_wav": os.path.join(VOICES_BASE_DIR_FULL, "Half_Light_Disco_Elysium.wav").replace('\\', '/'),
    "rvc_model_api_path": os.path.join(RVC_MODELS_BASE_DIR_FULL, "half_light/half_light.pth").replace('\\', '/'),
    "rvc_index_api_path": None,
    "rvc_pitch": -2
}
DEFAULT_NARRATOR_KEY = DEFAULT_NARRATOR_CONFIG["original_name"].upper()

# --- Global state ---
character_voice_assignments = {}
male_voice_next_idx = 0
female_voice_next_idx = 0
# --- End Configuration ---

def load_character_voice_map():
    global character_voice_assignments
    if os.path.exists(CHARACTER_VOICE_MAP_FILE):
        try:
            with open(CHARACTER_VOICE_MAP_FILE, 'r', encoding='utf-8') as f:
                character_voice_assignments = json.load(f)
            print(f"Loaded character voice map from '{CHARACTER_VOICE_MAP_FILE}'")
        except Exception as e:
            print(f"Warning: Could not load '{CHARACTER_VOICE_MAP_FILE}': {e}. Starting fresh map.")
            character_voice_assignments = {}
    
    narrator_key_upper = DEFAULT_NARRATOR_CONFIG["original_name"].upper()
    if narrator_key_upper not in character_voice_assignments:
        character_voice_assignments[narrator_key_upper] = DEFAULT_NARRATOR_CONFIG.copy()
        print(f"Initialized default narrator '{narrator_key_upper}' in voice map.")

def save_character_voice_map():
    global character_voice_assignments
    try:
        # Ensure paths use forward slashes
        for char_data in character_voice_assignments.values():
            if char_data.get("xtts_speaker_wav"): char_data["xtts_speaker_wav"] = char_data["xtts_speaker_wav"].replace('\\', '/')
            if char_data.get("rvc_model_api_path"): char_data["rvc_model_api_path"] = char_data["rvc_model_api_path"].replace('\\', '/')
            if char_data.get("rvc_index_api_path"): char_data["rvc_index_api_path"] = char_data["rvc_index_api_path"].replace('\\', '/')
        
        with open(CHARACTER_VOICE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(character_voice_assignments, f, indent=4, sort_keys=True)
        # print(f"Saved character voice map to '{CHARACTER_VOICE_MAP_FILE}'")
    except Exception as e:
        print(f"Error saving character voice map: {e}")

def get_or_assign_character_config(char_name_from_ai, gender_guess_from_ai=None):
    global character_voice_assignments, male_voice_next_idx, female_voice_next_idx
    
    char_key = char_name_from_ai.strip().upper()
    if not char_key: return DEFAULT_NARRATOR_KEY # Should not happen

    if char_key in character_voice_assignments:
        # Update original_name if AI provides a slightly different casing/version
        character_voice_assignments[char_key]["original_name"] = char_name_from_ai 
        return char_key

    print(f"\n>>> New character detected by AI: '{char_name_from_ai}' (Key: '{char_key}')")
    
    # 1. Determine Gender
    assigned_gender = None
    if gender_guess_from_ai and gender_guess_from_ai.lower() in ['m', 'f', 'n']:
        assigned_gender = gender_guess_from_ai.lower()
        print(f"    AI suggested gender: '{assigned_gender}'")
        if input(f"    Confirm gender as '{assigned_gender}' for '{char_name_from_ai}'? (y/n, or enter m/f/n): ").strip().lower() != 'y':
            assigned_gender = None # User wants to override

    if not assigned_gender:
        while True:
            gender_input = input(f"    What is the gender of '{char_name_from_ai}'? (m=male, f=female, n=narrator/neutral, s=skip & use Narrator): ").strip().lower()
            if gender_input in ['m', 'f', 'n']:
                assigned_gender = gender_input; break
            elif gender_input == 's':
                print(f"    Assigning default narrator voice to '{char_name_from_ai}'.")
                character_voice_assignments[char_key] = DEFAULT_NARRATOR_CONFIG.copy()
                character_voice_assignments[char_key]["original_name"] = char_name_from_ai
                save_character_voice_map()
                return char_key
            print("    Invalid input. Please use 'm', 'f', 'n', or 's'.")

    # 2. Assign XTTS Speaker WAV
    assigned_xtts_wav = None
    if assigned_gender == 'm':
        if MALE_XTTS_VOICES:
            assigned_xtts_wav = MALE_XTTS_VOICES[male_voice_next_idx % len(MALE_XTTS_VOICES)]
            male_voice_next_idx += 1
        else: print(f"    Warning: No MALE_XTTS_VOICES for {char_name_from_ai}. Using Narrator.")
    elif assigned_gender == 'f':
        if FEMALE_XTTS_VOICES:
            assigned_xtts_wav = FEMALE_XTTS_VOICES[female_voice_next_idx % len(FEMALE_XTTS_VOICES)]
            female_voice_next_idx += 1
        else: print(f"    Warning: No FEMALE_XTTS_VOICES for {char_name_from_ai}. Using Narrator.")
    
    if not assigned_xtts_wav:
        assigned_xtts_wav = DEFAULT_NARRATOR_CONFIG["xtts_speaker_wav"]
        assigned_gender = DEFAULT_NARRATOR_CONFIG["gender"]
        print(f"    Assigned default narrator XTTS voice: {os.path.basename(assigned_xtts_wav)}")
    else:
        print(f"    Assigned XTTS speaker WAV: {os.path.basename(assigned_xtts_wav)}")

    # 3. Assign RVC (Optional)
    assigned_rvc_model_api_path = None
    assigned_rvc_index_api_path = None
    assigned_rvc_pitch = 0

    if input(f"    Assign specific RVC to '{char_name_from_ai}' (Gender: {assigned_gender})? (y/n, default n): ").strip().lower() == 'y':
        while True:
            rvc_subfolder = input(f"      Enter RVC model subfolder under '{RVC_MODELS_BASE_DIR_FULL}' (e.g., 'my_char_voice'): ").strip()
            if not rvc_subfolder:
                print("      RVC subfolder name cannot be empty. Skipping RVC assignment for this character.")
                break
            
            # User might provide just folder, or folder/model_base_name
            # Assume pth and index share the same base name as the folder, or ask if more complex
            rvc_model_base_name = input(f"      Enter RVC .pth/.index base filename in '{rvc_subfolder}' (if different from folder name, else leave blank): ").strip()
            if not rvc_model_base_name:
                rvc_model_base_name = os.path.basename(rvc_subfolder) # Use folder name if base name not given

            api_relative_pth_path = f"{rvc_subfolder}/{rvc_model_base_name}.pth".replace('\\', '/')
            full_pth_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_pth_path)

            if os.path.exists(full_pth_path_local_check):
                assigned_rvc_model_api_path = api_relative_pth_path
                print(f"      Found RVC model: {full_pth_path_local_check}")

                api_relative_index_path = f"{rvc_subfolder}/{rvc_model_base_name}.index".replace('\\', '/')
                full_index_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_index_path)
                if os.path.exists(full_index_path_local_check):
                    assigned_rvc_index_api_path = api_relative_index_path
                    print(f"      Found RVC index: {full_index_path_local_check}")
                else:
                    print(f"      Note: RVC .index file not found at '{full_index_path_local_check}' (optional).")
                
                while True:
                    try:
                        pitch_input = input(f"      Enter RVC pitch for '{char_name_from_ai}' (integer, e.g., 0, default 0): ").strip()
                        assigned_rvc_pitch = int(pitch_input) if pitch_input else 0
                        break
                    except ValueError: print("      Invalid pitch. Please enter an integer.")
                break # Exit RVC name loop
            else:
                print(f"      Error: RVC model .pth file not found at '{full_pth_path_local_check}'.")
                if input("      Try different RVC subfolder/name? (y/n): ").strip().lower() != 'y':
                    break 
    else:
        print(f"    No specific RVC model will be assigned to '{char_name_from_ai}'.")

    character_voice_assignments[char_key] = {
        "original_name": char_name_from_ai, # Store the name AI found or user confirmed
        "gender": assigned_gender,
        "xtts_speaker_wav": assigned_xtts_wav,
        "rvc_model_api_path": assigned_rvc_model_api_path,
        "rvc_index_api_path": assigned_rvc_index_api_path,
        "rvc_pitch": assigned_rvc_pitch
    }
    save_character_voice_map()
    return char_key


def call_gemini_to_tag_text(text_content, filename_for_context="this chapter"):
    if not GOOGLE_GENAI_AVAILABLE:
        print("ERROR: google-genai module not available. Cannot call Gemini.")
        return None

    print(f"  Sending text from '{filename_for_context}' to Gemini for speaker tagging (length: {len(text_content)} chars)...")
    
    # Ensure API key is configured
    api_key = os.getenv(API_KEY_ENV_VARIABLE)
    if not api_key:
        print(f"  Error: Environment variable '{API_KEY_ENV_VARIABLE}' for Gemini API Key is not set.")
        return None
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"  Error configuring Gemini API with key: {e}")
        return None

    # Define known characters to help Gemini be consistent (optional, but can improve results)
    known_character_names = [details.get("original_name", key) for key, details in character_voice_assignments.items() if key != DEFAULT_NARRATOR_KEY]
    known_chars_prompt_part = ""
    if known_character_names:
        known_chars_prompt_part = f"Known characters so far include: {', '.join(known_char_names)}. Please try to be consistent with these names if they appear.\n"


    # Carefully crafted prompt
    prompt = f"""
Please analyze the following text from a novel chapter.
Your task is to identify narration and dialogue.
For each line or segment of text, prepend it with a speaker tag.
The format for the tag should be:
SPEAKER_NAME (g): Text content
Where 'SPEAKER_NAME' is the name of the character speaking or 'NARRATOR' for narration.
And '(g)' is a gender hint: (m) for male, (f) for female, (n) for neutral/narrator, or (u) if unknown or not applicable.
If a character speaks multiple consecutive lines, repeat their tag for each line.
Be careful to attribute dialogue correctly to the characters.
If a character's name is mentioned in attribution (e.g., "John said", "replied Mary"), use that name.
If dialogue is unattributed, try to infer the speaker from context or mark as UNKNOWN_SPEAKER (u).
Preserve original paragraph breaks (empty lines between paragraphs).

{known_chars_prompt_part}
Here is the text:
--- TEXT START ---
{text_content}
--- TEXT END ---

Please provide the full text with your tags.
"""
    try:
        model = genai.GenerativeModel('gemini-2.5-pro-preview-05-06') # Or 'gemini-1.5-pro-latest' for potentially better (slower/pricier) results
        # Safety settings can be adjusted if content is flagged too aggressively
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2 # Lower temperature for more deterministic output
            ),
            # safety_settings=[ # Example: Adjust if needed
            #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            # ]
        )
        
        if response.parts:
            tagged_text = "".join(part.text for part in response.parts)
            print(f"  Successfully received tagged text from Gemini for '{filename_for_context}'.")
            return tagged_text.strip()
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"  Error: Prompt blocked by Gemini for '{filename_for_context}'. Reason: {response.prompt_feedback.block_reason}")
            if response.prompt_feedback.safety_ratings:
                for rating in response.prompt_feedback.safety_ratings:
                    print(f"    Safety Rating: {rating.category} - {rating.probability}")
            return f"[GEMINI_ERROR:PROMPT_BLOCKED for {filename_for_context} - Reason: {response.prompt_feedback.block_reason}]"
        else:
            print(f"  Warning: Gemini response for '{filename_for_context}' had no parts or unexpected structure. Full response: {response}")
            return f"[GEMINI_ERROR:NO_TEXT_RETURNED for {filename_for_context}]"

    except Exception as e:
        print(f"  Error calling Gemini API for '{filename_for_context}': {type(e).__name__} - {e}")
        return f"[GEMINI_API_ERROR for {filename_for_context}: {e}]"


def process_and_save_tagged_file(input_filepath, output_filepath):
    print(f"\n--- Processing file for AI tagging: {os.path.basename(input_filepath)} ---")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
        if not original_content.strip():
            print(f"  Skipping empty original file: {input_filepath}")
            if not os.path.exists(os.path.dirname(output_filepath)): os.makedirs(os.path.dirname(output_filepath))
            with open(output_filepath, 'w', encoding='utf-8') as f_out: f_out.write("")
            return True # Consider empty file as "processed"
    except Exception as e:
        print(f"  Error reading original file {input_filepath}: {e}")
        return False

    gemini_tagged_text = call_gemini_to_tag_text(original_content, os.path.basename(input_filepath))

    if gemini_tagged_text is None or "[GEMINI_ERROR" in gemini_tagged_text or "[GEMINI_API_ERROR" in gemini_tagged_text :
        print(f"  Failed to get valid tags from Gemini for {os.path.basename(input_filepath)}. Saving error message.")
        final_output_text = gemini_tagged_text if gemini_tagged_text else f"[ERROR: No response from Gemini for {os.path.basename(input_filepath)}]"
    else:
        # Now, parse Gemini's output and finalize character assignments
        print(f"  Parsing Gemini's output and finalizing character voice assignments for {os.path.basename(input_filepath)}...")
        
        # Regex to parse lines like: SPEAKER_NAME (g): Text
        # Allows for names with spaces. Gender hint (m), (f), (n), (u) is optional.
        SPEAKER_LINE_PATTERN = re.compile(r"^\s*([\w\s.'-]+?)(?:\s*\(([mfnu])\))?:\s*(.*)$", re.IGNORECASE)
        
        final_tagged_lines = []
        gemini_lines = gemini_tagged_text.splitlines()

        for line_from_gemini in gemini_lines:
            match = SPEAKER_LINE_PATTERN.match(line_from_gemini)
            if match:
                char_name_ai = match.group(1).strip()
                gender_hint_ai = match.group(2).strip().lower() if match.group(2) else None
                text_segment = match.group(3).strip()

                # Ensure character is in our map, prompting if new
                # `get_or_assign_character_config` handles adding to JSON and assigning voice/RVC paths
                char_key = get_or_assign_character_config(char_name_ai, gender_hint_ai)
                
                # Reconstruct the line with the canonical name and gender from our map
                char_config = character_voice_assignments[char_key]
                display_name = char_config["original_name"]
                display_gender = char_config["gender"]
                
                if display_gender and display_gender != 'n':
                    final_tagged_lines.append(f"{display_name} ({display_gender}): {text_segment}")
                else:
                    final_tagged_lines.append(f"{display_name}: {text_segment}")
            else:
                # Line doesn't match speaker tag format, could be empty or just text (assume Narrator if so)
                if line_from_gemini.strip(): # if it's not just an empty line for spacing
                    # This case implies Gemini didn't tag a line it should have, or it's narration it missed tagging.
                    # We can default it to NARRATOR or ask the user. For now, default to Narrator.
                    char_config = character_voice_assignments[DEFAULT_NARRATOR_KEY]
                    display_name = char_config["original_name"]
                    final_tagged_lines.append(f"{display_name}: {line_from_gemini.strip()}")
                else:
                    final_tagged_lines.append("") # Preserve empty lines

        final_output_text = "\n".join(final_tagged_lines)

    # Save the processed (or error-marked) text
    if not os.path.exists(os.path.dirname(output_filepath)):
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(final_output_text.strip() + "\n")
    print(f"  Saved processed text to: {output_filepath}")
    return not ("[GEMINI_ERROR" in final_output_text or "[GEMINI_API_ERROR" in final_output_text)


if __name__ == "__main__":
    if not GOOGLE_GENAI_AVAILABLE:
        exit()
        
    # Create necessary directories if they don't exist
    os.makedirs(TAGGED_TEXT_OUTPUT_DIR, exist_ok=True)
    # Ensure nltk_data path exists for download if NLTK is used
    if NLTK_AVAILABLE and not os.path.exists('./nltk_data'):
        try:
            os.makedirs('./nltk_data')
        except OSError:
            print("Warning: Could not create ./nltk_data directory. NLTK might try to download to user default.")

    load_character_voice_map()

    if not os.path.isdir(ORIGINAL_TEXT_DIR):
        print(f"Error: Original text directory '{ORIGINAL_TEXT_DIR}' not found.")
        exit()

    source_text_files = sorted(glob.glob(os.path.join(ORIGINAL_TEXT_DIR, "*.txt")))
    if not source_text_files:
        print(f"No .txt files found in '{ORIGINAL_TEXT_DIR}'.")
        exit()

    print(f"\nFound {len(source_text_files)} text files in '{ORIGINAL_TEXT_DIR}'.")
    print(f"Tagged files will be saved in: '{os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}'")
    print(f"Character voice configurations will be stored in: '{CHARACTER_VOICE_MAP_FILE}'")
    print("For new characters, you'll be prompted for gender and RVC details (if any).")
    
    overall_start_time = time.monotonic()
    files_processed_successfully = 0
    files_failed = 0

    for i, text_filepath in enumerate(source_text_files):
        base_filename = os.path.basename(text_filepath)
        output_filepath = os.path.join(TAGGED_TEXT_OUTPUT_DIR, base_filename)
        
        print(f"\n--- File {i+1}/{len(source_text_files)}: {base_filename} ---")

        if os.path.exists(output_filepath):
            if input(f"Tagged file '{output_filepath}' already exists. Overwrite? (y/n, default n): ").strip().lower() != 'y':
                print(f"Skipping {base_filename}.")
                files_processed_successfully +=1 # Count as success if skipped intentionally
                continue
        
        if process_and_save_tagged_file(text_filepath, output_filepath):
            files_processed_successfully +=1
        else:
            files_failed +=1
        
        save_character_voice_map() # Save map after each file
        
        # Add a small delay to be respectful of API rate limits if any
        if i < len(source_text_files) - 1:
            time.sleep(1) # 1-second delay between files

    print("\n--- Text Tagging Process Complete ---")
    print(f"Total files checked: {len(source_text_files)}")
    print(f"Files successfully processed/tagged (or skipped): {files_processed_successfully}")
    print(f"Files failed during processing: {files_failed}")
    print(f"Final character voice map saved to '{os.path.abspath(CHARACTER_VOICE_MAP_FILE)}'")
    print(f"Tagged text files are in '{os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}'")
    overall_duration = time.monotonic() - overall_start_time
    print(f"Total script execution time: {overall_duration:.2f} seconds ({overall_duration/60:.2f} minutes).")
