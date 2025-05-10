import os
import glob
import re
import json
import time
import pathlib 

# --- NLTK Setup ---
NLTK_AVAILABLE = False
# Attempt to set up a local directory for NLTK data first
local_nltk_data_path = os.path.join(os.getcwd(), 'nltk_data')
try:
    import nltk
    if not os.path.exists(local_nltk_data_path):
        print(f"Creating local NLTK data directory: {local_nltk_data_path}")
        os.makedirs(local_nltk_data_path, exist_ok=True)
    if local_nltk_data_path not in nltk.data.path:
        nltk.data.path.append(local_nltk_data_path)
    
    try:
        nltk.data.find('tokenizers/punkt')
        print("NLTK 'punkt' tokenizer found.")
        NLTK_AVAILABLE = True
    except LookupError:
        print("NLTK 'punkt' tokenizer not found. Attempting to download to local './nltk_data' directory...")
        try:
            nltk.download('punkt', download_dir=local_nltk_data_path, quiet=False)
            nltk.data.find('tokenizers/punkt') # Verify after download
            print("'punkt' downloaded and found. Please re-run the script if prompted by NLTK to restart.")
            NLTK_AVAILABLE = True
        except Exception as e_download:
            print(f"Warning: Failed to download 'punkt' for NLTK ({type(e_download).__name__}: {e_download}).")
            print("Sentence tokenization will be basic. For better results, ensure 'punkt' can be downloaded.")
except ImportError:
    print("Warning: NLTK library not found. Please install it: pip install nltk")
except Exception as e_nltk_init:
    print(f"Warning: General NLTK setup issue ({type(e_nltk_init).__name__}: {e_nltk_init}). Sentence tokenization will be basic.")

if NLTK_AVAILABLE:
    from nltk.tokenize import sent_tokenize
else:
    print("Using basic sentence splitter due to NLTK 'punkt' not being available.")
    def sent_tokenize(text):
        text = re.sub(r'\s+', ' ', text)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]

# --- Google Generative AI Setup ---
try:
    import google.generativeai as genai
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    print("ERROR: The 'google-generativeai' package is not installed. This script cannot run.")
    print("Please install it: pip install google-generativeai")
    GOOGLE_GENAI_AVAILABLE = False

# --- Configuration (Ensure these are correctly set for your environment) ---
ORIGINAL_TEXT_DIR = "scraped_tileas_worries_test"
TAGGED_TEXT_OUTPUT_DIR = "scraped_tileas_worries_tagged_for_tts"
CHARACTER_VOICE_MAP_FILE = "character_voice_config.json"
API_KEY_ENV_VARIABLE = "GEMINI_API_KEY"
GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"

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

character_voice_assignments = {}
male_voice_next_idx = 0
female_voice_next_idx = 0
# --- End Configuration ---


# --- Helper Functions (load_character_voice_map, save_character_voice_map, get_or_assign_character_config, call_gemini_to_tag_text, process_chapter_file_with_gemini) ---
# These functions should be the same as in the previous version of gemini_audiobook_tagger_2.py
# For brevity, I'm not repeating them all here, but ensure you have their latest correct versions from that script.
# I will paste the full script at the end, including these.

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
        for char_data in character_voice_assignments.values():
            if char_data.get("xtts_speaker_wav"): char_data["xtts_speaker_wav"] = str(pathlib.Path(char_data["xtts_speaker_wav"]).as_posix())
            if char_data.get("rvc_model_api_path"): char_data["rvc_model_api_path"] = str(pathlib.Path(char_data["rvc_model_api_path"]).as_posix()) if char_data["rvc_model_api_path"] else None
            if char_data.get("rvc_index_api_path"): char_data["rvc_index_api_path"] = str(pathlib.Path(char_data["rvc_index_api_path"]).as_posix()) if char_data["rvc_index_api_path"] else None
        
        with open(CHARACTER_VOICE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(character_voice_assignments, f, indent=4, sort_keys=True)
    except Exception as e:
        print(f"Error saving character voice map: {e}")


def get_or_assign_character_config(character_name_input, gender_hint_from_tag=None):
    global character_voice_assignments, male_voice_next_idx, female_voice_next_idx
    
    char_key = character_name_input.strip().upper()
    if not char_key: return DEFAULT_NARRATOR_KEY

    if char_key in character_voice_assignments:
        if "original_name" not in character_voice_assignments[char_key] or \
           character_voice_assignments[char_key].get("original_name", char_key) != character_name_input:
            character_voice_assignments[char_key]["original_name"] = character_name_input # Update if casing changed
        return char_key

    print(f"\n>>> New character detected: '{character_name_input}' (Key will be: '{char_key}')")
    assigned_gender = gender_hint_from_tag.lower() if gender_hint_from_tag and gender_hint_from_tag.lower() in ['m', 'f', 'n', 'u'] else None

    if not assigned_gender or assigned_gender == 'u': # 'u' for unknown also prompts
        while True:
            gender_input = input(f"    What is the gender of '{character_name_input}'? (m=male, f=female, n=narrator/neutral, s=skip & use Narrator): ").strip().lower()
            if gender_input in ['m', 'f', 'n']:
                assigned_gender = gender_input; break
            elif gender_input == 's':
                print(f"    Assigning default narrator voice to '{character_name_input}'.")
                character_voice_assignments[char_key] = DEFAULT_NARRATOR_CONFIG.copy()
                character_voice_assignments[char_key]["original_name"] = character_name_input
                save_character_voice_map()
                return char_key
            print("    Invalid input. Please use 'm', 'f', 'n', or 's'.")

    assigned_xtts_wav = None
    if assigned_gender == 'm':
        if MALE_XTTS_VOICES:
            assigned_xtts_wav = MALE_XTTS_VOICES[male_voice_next_idx % len(MALE_XTTS_VOICES)]
            male_voice_next_idx += 1
        else: print(f"    Warning: No MALE_XTTS_VOICES configured. Using default narrator voice for '{character_name_input}'.")
    elif assigned_gender == 'f':
        if FEMALE_XTTS_VOICES:
            assigned_xtts_wav = FEMALE_XTTS_VOICES[female_voice_next_idx % len(FEMALE_XTTS_VOICES)]
            female_voice_next_idx += 1
        else: print(f"    Warning: No FEMALE_XTTS_VOICES configured. Using default narrator voice for '{character_name_input}'.")
    
    if not assigned_xtts_wav:
        assigned_xtts_wav = DEFAULT_NARRATOR_CONFIG["xtts_speaker_wav"]
        # If gender was 'm' or 'f' but no voices, assigned_gender is still 'm' or 'f'. 'n' is for explicit narrator/neutral.
        # If assigned_gender was 'n' initially, it remains 'n'.
        if assigned_gender not in ['m', 'f']: assigned_gender = 'n'
        print(f"    Assigned default narrator XTTS voice: {os.path.basename(assigned_xtts_wav)}")

    assigned_rvc_model_api_path = None
    assigned_rvc_index_api_path = None
    assigned_rvc_pitch = 0

    if input(f"    Assign specific RVC to '{character_name_input}' (Gender: {assigned_gender})? (y/n, default n): ").strip().lower() == 'y':
        while True:
            rvc_subfolder = input(f"      Enter RVC model's subfolder name under '{RVC_MODELS_BASE_DIR_FULL}' (e.g., 'john_rvc'): ").strip()
            if not rvc_subfolder:
                print("      RVC subfolder name cannot be empty. No RVC will be assigned."); break
            
            rvc_model_base_name = input(f"      Enter RVC .pth/.index base filename in '{rvc_subfolder}' (if same as folder, e.g., '{rvc_subfolder}', leave blank): ").strip()
            if not rvc_model_base_name: rvc_model_base_name = os.path.basename(rvc_subfolder)

            # Path for API (relative to Alltalk server's RVC models root)
            # Example: "john_rvc/john_model.pth"
            api_relative_pth_path = str(pathlib.Path(rvc_subfolder) / f"{rvc_model_base_name}.pth").replace('\\', '/')
            # Full path for local existence check
            full_pth_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_pth_path)

            if os.path.exists(full_pth_path_local_check):
                assigned_rvc_model_api_path = api_relative_pth_path
                print(f"      Found RVC model: {full_pth_path_local_check}")

                api_relative_index_path = str(pathlib.Path(rvc_subfolder) / f"{rvc_model_base_name}.index").replace('\\', '/')
                full_index_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_index_path)
                if os.path.exists(full_index_path_local_check):
                    assigned_rvc_index_api_path = api_relative_index_path
                    print(f"      Found RVC index: {full_index_path_local_check}")
                else:
                    print(f"      Note: RVC .index file not found at '{full_index_path_local_check}'. Storing as None.")
                
                while True:
                    try:
                        pitch_input = input(f"      Enter RVC pitch for '{character_name_input}' (integer, e.g., 0, default 0): ").strip()
                        assigned_rvc_pitch = int(pitch_input) if pitch_input else 0
                        break
                    except ValueError: print("      Invalid pitch. Please enter an integer.")
                break 
            else:
                print(f"      Error: RVC model .pth file not found at '{full_pth_path_local_check}'.")
                if input("      Try different RVC subfolder/name? (y/n): ").strip().lower() != 'y':
                    break 
    else:
        print(f"    No specific RVC model will be assigned to '{character_name_input}'.")

    character_voice_assignments[char_key] = {
        "original_name": character_name_input,
        "gender": assigned_gender,
        "xtts_speaker_wav": assigned_xtts_wav,
        "rvc_model_api_path": assigned_rvc_model_api_path,
        "rvc_index_api_path": assigned_rvc_index_api_path,
        "rvc_pitch": assigned_rvc_pitch
    }
    save_character_voice_map()
    return char_key

def call_gemini_to_tag_text(text_content, filename_for_context="this chapter"):
    # (Keep this function as provided in the previous response that included it)
    # For brevity, assuming it's the same. Key is it returns tagged text or error string.
    if not GOOGLE_GENAI_AVAILABLE:
        return f"[ERROR: Gemini library not available for {filename_for_context}]"
    print(f"  Sending text from '{filename_for_context}' to Gemini for speaker tagging (length: {len(text_content)} chars)...")
    api_key = os.getenv(API_KEY_ENV_VARIABLE)
    if not api_key:
        return f"[ERROR: Gemini API Key ({API_KEY_ENV_VARIABLE}) not set for {filename_for_context}]"
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        return f"[ERROR: Configuring Gemini API: {e} for {filename_for_context}]"

    known_character_names = [details.get("original_name", key) for key, details in character_voice_assignments.items() if key != DEFAULT_NARRATOR_KEY]
    known_chars_prompt_part = ""
    if known_character_names:
        known_chars_prompt_part = f"Previously identified characters include: {', '.join(list(set(known_character_names))[:15])}. Please be consistent with these names if they appear again.\n"

    prompt = f"""Analyze the following novel chapter text. Your task is to identify narration and dialogue sections.
For each distinct segment of speech (narration or a character's dialogue line), prepend it with a speaker tag.
The required output format for EACH line of text is:
SPEAKER_NAME (g): Text content

Where:
- 'SPEAKER_NAME' is the character's name (e.g., John, Mary, Guard Captain) or 'NARRATOR' for narration.
- '(g)' is a gender hint: (m) for male, (f) for female, (n) for neutral/narrator (ALWAYS use (n) for NARRATOR tag), or (u) if gender is genuinely unknown/unclear from the text for a character.
- 'Text content' is the original text of that line.

Detailed instructions:
1. Identify all dialogue, typically enclosed in quotation marks ("..." or “...”).
2. For dialogue, determine who is speaking. Look for attribution cues like "Character said,", "asked Character,", or a character's name on a preceding line if the context is clear.
3. If dialogue is unattributed and the speaker is ambiguous from immediate context, use "UNKNOWN_SPEAKER (u):".
4. ALL text not part of specific character dialogue should be tagged as "NARRATOR (n):". This includes descriptive text, action sequences not part of dialogue, etc. Every line must have a speaker tag.
5. Preserve original paragraph breaks (empty lines between paragraphs should be output as empty lines).
6. If a character speaks multiple consecutive lines/sentences within the same paragraph without intervening narration, each of those dialogue lines/sentences should still get the character's tag.
7. Ensure character names are spelled consistently. If a name has multiple parts, include them (e.g., "Old Man Fitzwilliam").
{known_chars_prompt_part}
Here is the text:
--- TEXT START ---
{text_content}
--- TEXT END ---

Provide the FULL text with your tags applied to every line or paragraph segment. Ensure every non-empty line in the output starts with a speaker tag.
"""
    try:
        # Using gemini-1.5-flash-latest as it's faster and often sufficient for structured tasks.
        # If results are poor, consider 'gemini-1.5-pro-latest'
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=0.1),
            safety_settings=[ # More permissive safety settings
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        )
        
        if response.parts:
            tagged_text = "".join(part.text for part in response.parts)
            print(f"  Successfully received tagged text from Gemini for '{filename_for_context}'.")
            return tagged_text.strip()
        elif response.prompt_feedback and response.prompt_feedback.block_reason:
            block_reason_str = str(response.prompt_feedback.block_reason)
            print(f"  Error: Prompt blocked by Gemini for '{filename_for_context}'. Reason: {block_reason_str}")
            if response.prompt_feedback.safety_ratings:
                for rating in response.prompt_feedback.safety_ratings: print(f"    Safety Rating: {rating.category} - {rating.probability}")
            return f"[GEMINI_ERROR:PROMPT_BLOCKED for {filename_for_context} - Reason: {block_reason_str}]"
        else:
            # Handle cases where response.parts might be empty but text might be in response.text
            if hasattr(response, 'text') and response.text:
                print(f"  Successfully received tagged text (via response.text) from Gemini for '{filename_for_context}'.")
                return response.text.strip()
            print(f"  Warning: Gemini response for '{filename_for_context}' had no parts or direct text. Full response: {response}")
            return f"[GEMINI_ERROR:NO_TEXT_RETURNED for {filename_for_context}]"

    except Exception as e:
        print(f"  Error calling Gemini API for '{filename_for_context}': {type(e).__name__} - {e}")
        return f"[GEMINI_API_ERROR for {filename_for_context}: {e}]"


def process_chapter_file_with_gemini(input_filepath, output_filepath):
    # (Keep this function as provided in the previous response that included it)
    # For brevity, assuming it's the same. Key is it calls call_gemini_to_tag_text,
    # then parses Gemini's output, calls get_or_assign_character_config, and writes the final tagged file.
    print(f"\n--- Processing file for AI tagging: {os.path.basename(input_filepath)} ---")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            original_content = f.read()
        if not original_content.strip():
            print(f"  Skipping empty original file: {input_filepath}")
            if not os.path.exists(os.path.dirname(output_filepath)): os.makedirs(os.path.dirname(output_filepath))
            with open(output_filepath, 'w', encoding='utf-8') as f_out: f_out.write("")
            return True
    except Exception as e:
        print(f"  Error reading original file {input_filepath}: {e}")
        return False

    gemini_tagged_text = call_gemini_to_tag_text(original_content, os.path.basename(input_filepath))

    if gemini_tagged_text is None or "[GEMINI_ERROR" in gemini_tagged_text or "[GEMINI_API_ERROR" in gemini_tagged_text :
        print(f"  Failed to get valid tags from Gemini for {os.path.basename(input_filepath)}. Saving error message.")
        final_output_text = gemini_tagged_text if gemini_tagged_text else f"[ERROR: No response/error from Gemini for {os.path.basename(input_filepath)}]"
    else:
        print(f"  Gemini output received. Now parsing and finalizing character assignments for {os.path.basename(input_filepath)}...")
        SPEAKER_LINE_PATTERN = re.compile(r"^\s*([\w\s.'-]+?)(?:\s*\(([mfnu])\))?:\s*(.*)$", re.IGNORECASE)
        
        final_processed_lines = []
        gemini_lines = gemini_tagged_text.splitlines()

        for line_from_gemini in gemini_lines:
            stripped_line = line_from_gemini.strip()
            if not stripped_line: 
                final_processed_lines.append("")
                continue

            match = SPEAKER_LINE_PATTERN.match(stripped_line)
            if match:
                char_name_ai = match.group(1).strip()
                gender_hint_ai = match.group(2).strip().lower() if match.group(2) else None
                text_segment = match.group(3).strip()

                if "UNKNOWN_SPEAKER" in char_name_ai.upper() or not char_name_ai: # Also handle if AI gives empty speaker
                    print(f"    AI tagged speaker as '{char_name_ai}' or empty. Prompting for clarification...")
                    user_char_name = input(f"      For text: \"{text_segment[:70]}...\", who is speaking? (Enter name or N for Narrator): ").strip()
                    if user_char_name.upper() == 'N' or not user_char_name:
                        char_name_ai = DEFAULT_NARRATOR_CONFIG["original_name"]
                        gender_hint_ai = 'n' # Narrator is neutral
                    else:
                        char_name_ai = user_char_name
                        # gender_hint_ai will be prompted by get_or_assign_character_config if new

                char_key = get_or_assign_character_config(char_name_ai, gender_hint_ai)
                
                char_config = character_voice_assignments[char_key]
                display_name = char_config["original_name"]
                display_gender = char_config["gender"]
                
                if display_gender and display_gender != 'n':
                    final_processed_lines.append(f"{display_name} ({display_gender}): {text_segment}")
                else:
                    final_processed_lines.append(f"{display_name}: {text_segment}")
            else:
                print(f"    Warning: Line from Gemini not matching tag format: '{stripped_line[:100]}...' Defaulting to Narrator.")
                char_config = character_voice_assignments[DEFAULT_NARRATOR_KEY]
                display_name = char_config["original_name"]
                final_processed_lines.append(f"{display_name}: {stripped_line}")
        
        final_output_text = "\n".join(final_processed_lines)

    if not os.path.exists(os.path.dirname(output_filepath)):
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True)
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(final_output_text.strip() + "\n")
    print(f"  Saved processed text to: {output_filepath}")
    return not ("[GEMINI_ERROR" in final_output_text or "[GEMINI_API_ERROR" in final_output_text)


if __name__ == "__main__":
    if not GOOGLE_GENAI_AVAILABLE:
        print("Exiting script because google-generativeai package is not available.")
        exit()
        
    os.makedirs(TAGGED_TEXT_OUTPUT_DIR, exist_ok=True)
    if NLTK_AVAILABLE and not os.path.exists('./nltk_data'):
        try: os.makedirs('./nltk_data')
        except OSError: print("Warning: Could not create ./nltk_data directory for NLTK.")

    load_character_voice_map()

    if not os.path.isdir(ORIGINAL_TEXT_DIR):
        print(f"Error: Original text directory '{ORIGINAL_TEXT_DIR}' not found."); exit()

    source_text_files = sorted(glob.glob(os.path.join(ORIGINAL_TEXT_DIR, "*.txt")))
    if not source_text_files:
        print(f"No .txt files found in '{ORIGINAL_TEXT_DIR}'."); exit()

    print(f"\nFound {len(source_text_files)} text files in '{ORIGINAL_TEXT_DIR}'.")
    print(f"Tagged files will be saved in: '{os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}'")
    print(f"Character voice configurations will be stored in: '{CHARACTER_VOICE_MAP_FILE}'")
    print("This script will use Gemini to attempt automatic speaker tagging.")
    print("For new characters identified by Gemini or by you, you'll be prompted for gender and RVC details.")
    
    if input("Press Enter to begin AI-assisted tagging... (or type 'q' to quit): ").strip().lower() == 'q':
        print("Exiting."); exit()

    overall_start_time = time.monotonic()
    files_processed_successfully = 0
    files_failed_or_skipped_by_user = 0 # Renamed for clarity

    for i, text_filepath in enumerate(source_text_files):
        base_filename = os.path.basename(text_filepath)
        output_filepath = os.path.join(TAGGED_TEXT_OUTPUT_DIR, base_filename)
        
        print(f"\n--- Chapter {i+1}/{len(source_text_files)}: {base_filename} ---")

        # --- MODIFIED SKIPPING LOGIC ---
        should_process_file = True
        if os.path.exists(output_filepath):
            try:
                if os.path.getsize(output_filepath) > 0:
                    with open(output_filepath, 'r', encoding='utf-8') as f_check:
                        # Read a bit more to catch multi-line error messages if they exist
                        content_sample = f_check.read(500) 
                    # Check for specific error markers we might write
                    error_markers = ["[GEMINI_ERROR", "[GEMINI_API_ERROR", "[ERROR: No response"]
                    if any(marker in content_sample for marker in error_markers):
                        print(f"  Tagged file '{output_filepath}' exists but contains error markers. Will re-process.")
                        should_process_file = True
                    else:
                        print(f"  Tagged file '{output_filepath}' already exists and seems valid. Skipping.")
                        should_process_file = False
                        files_processed_successfully += 1 # Count as success as it's already done
                else: # File exists but is empty
                    print(f"  Tagged file '{output_filepath}' exists but is empty. Will re-process.")
                    should_process_file = True
            except Exception as e_check_skip:
                print(f"  Could not properly check existing file {output_filepath}, will re-process: {e_check_skip}")
                should_process_file = True
        
        if not should_process_file:
            continue # Jump to the next file
        # --- END MODIFIED SKIPPING LOGIC ---
        
        if process_chapter_file_with_gemini(text_filepath, output_filepath):
            files_processed_successfully +=1
        else:
            files_failed_or_skipped_by_user +=1 # Count actual processing failures or if user quits a chapter
        
        save_character_voice_map() 
        if i < len(source_text_files) - 1:
            print("  Pausing briefly before next API call...")
            time.sleep(3) # API politeness delay increased slightly

    print("\n" + "-" * 70 + "\n--- AI Text Tagging Process Complete ---")
    print(f"Total source files considered: {len(source_text_files)}")
    print(f"Files successfully tagged or already valid: {files_processed_successfully}")
    print(f"Files that failed during processing or were skipped by user mid-process: {files_failed_or_skipped_by_user}")
    print(f"Final character voice map saved to '{os.path.abspath(CHARACTER_VOICE_MAP_FILE)}'")
    print(f"Tagged text files are in '{os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}'")
    overall_duration = time.monotonic() - overall_start_time
    print(f"Total script execution time: {overall_duration:.2f} seconds ({overall_duration/60:.2f} minutes).")
