import os
import glob
import re
import json
import shutil
import time # Added for potential use, though not strictly in the core logic yet

# NLTK for sentence tokenization
try:
    import nltk
    from nltk.tokenize import sent_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    print("Warning: NLTK library not found. Sentence tokenization will be basic (paragraph-based).")
    print("Please install it: pip install nltk")
    NLTK_AVAILABLE = False
    def sent_tokenize(text): # Basic fallback
        return [p.strip() for p in text.splitlines() if p.strip()]


# --- Configuration ---
ORIGINAL_TEXT_DIR = "scraped_tileas_worries"
TAGGED_TEXT_OUTPUT_DIR = "scraped_tileas_worries_tagged_for_tts"
CHARACTER_VOICE_MAP_FILE = "character_voice_config.json"

VOICES_BASE_DIR = "C:/Users/etnor/Documents/tts/alltalk_tts/voices"
RVC_MODELS_BASE_DIR_FULL = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices"

# --- Available Voices for Assignment (Full Paths for XTTS) ---
MALE_XTTS_VOICES = [os.path.join(VOICES_BASE_DIR, f"male_0{i}.wav") for i in range(1, 6)]
FEMALE_XTTS_VOICES = [os.path.join(VOICES_BASE_DIR, f"female_0{i}.wav") for i in range(1, 6)]
# Example: Add more specific named voices if you have more than 5 of each gender for rotation
# MALE_XTTS_VOICES.append(os.path.join(VOICES_BASE_DIR, "Arnold.wav"))
# FEMALE_XTTS_VOICES.append(os.path.join(VOICES_BASE_DIR, "female_06.wav"))


DEFAULT_NARRATOR_CONFIG = {
    "original_name": "NARRATOR", # This will be the key in JSON, uppercased
    "gender": "n",
    "xtts_speaker_wav": os.path.join(VOICES_BASE_DIR, "Half_Light_Disco_Elysium.wav"),
    "rvc_model_api_path": None, # This should be relative to Alltalk's RVC models dir
    "rvc_index_api_path": None, # This should also be relative
    "rvc_pitch": 0
}
DEFAULT_NARRATOR_KEY = DEFAULT_NARRATOR_CONFIG["original_name"].upper()

# --- Global state for voice assignment ---
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
            print(f"Loaded character voice map from {CHARACTER_VOICE_MAP_FILE}")
        except Exception as e:
            print(f"Warning: Could not load {CHARACTER_VOICE_MAP_FILE}: {e}. Starting fresh.")
            character_voice_assignments = {}
    
    # Ensure Narrator has a voice configuration
    # Use original_name from config as the key for comparison/initialization
    narrator_map_key = DEFAULT_NARRATOR_CONFIG["original_name"].upper()
    if narrator_map_key not in character_voice_assignments:
        character_voice_assignments[narrator_map_key] = DEFAULT_NARRATOR_CONFIG.copy() # Use .copy()
        print(f"Initialized default narrator '{narrator_map_key}' in voice map.")

def save_character_voice_map():
    global character_voice_assignments
    try:
        # Ensure all paths use forward slashes for consistency in JSON
        for char_data in character_voice_assignments.values():
            if char_data.get("xtts_speaker_wav"):
                char_data["xtts_speaker_wav"] = char_data["xtts_speaker_wav"].replace('\\', '/')
            if char_data.get("rvc_model_api_path"):
                char_data["rvc_model_api_path"] = char_data["rvc_model_api_path"].replace('\\', '/')
            if char_data.get("rvc_index_api_path"):
                char_data["rvc_index_api_path"] = char_data["rvc_index_api_path"].replace('\\', '/')

        with open(CHARACTER_VOICE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(character_voice_assignments, f, indent=4, sort_keys=True)
        print(f"Saved character voice map to {CHARACTER_VOICE_MAP_FILE}")
    except Exception as e:
        print(f"Error saving character voice map: {e}")

def get_or_assign_character_voice(character_name_input, gender_hint_from_tag=None):
    global character_voice_assignments, male_voice_next_idx, female_voice_next_idx
    
    char_key = character_name_input.strip().upper()
    if not char_key: return DEFAULT_NARRATOR_KEY

    if char_key in character_voice_assignments:
        if "original_name" not in character_voice_assignments[char_key]: # Ensure original_name consistency
             character_voice_assignments[char_key]["original_name"] = character_name_input
        return char_key

    print(f"\n>>> New character encountered: '{character_name_input}' (Key: '{char_key}')")
    assigned_gender = gender_hint_from_tag.lower() if gender_hint_from_tag and gender_hint_from_tag.lower() in ['m', 'f', 'n'] else None

    if not assigned_gender:
        while True:
            gender_input = input(f"    What is the gender of '{character_name_input}'? (m=male, f=female, n=narrator/neutral, s=skip & use Narrator voice): ").strip().lower()
            if gender_input in ['m', 'f', 'n']:
                assigned_gender = gender_input
                break
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
        else: print("    Warning: No MALE_XTTS_VOICES defined. Will use Narrator voice.")
    elif assigned_gender == 'f':
        if FEMALE_XTTS_VOICES:
            assigned_xtts_wav = FEMALE_XTTS_VOICES[female_voice_next_idx % len(FEMALE_XTTS_VOICES)]
            female_voice_next_idx += 1
        else: print("    Warning: No FEMALE_XTTS_VOICES defined. Will use Narrator voice.")
    
    if not assigned_xtts_wav: # Fallback if gendered voices are missing or gender is 'n'
        assigned_xtts_wav = DEFAULT_NARRATOR_CONFIG["xtts_speaker_wav"]
        assigned_gender = DEFAULT_NARRATOR_CONFIG["gender"] # Use narrator's defined gender
        print(f"    Assigned default narrator XTTS voice: {os.path.basename(assigned_xtts_wav)}")

    # RVC Assignment
    assigned_rvc_model_api_path = None
    assigned_rvc_index_api_path = None
    assigned_rvc_pitch = 0

    if input(f"    Does '{character_name_input}' have a specific RVC model? (y/n, default n): ").strip().lower() == 'y':
        while True:
            rvc_subdir_and_model_name = input(f"      Enter RVC model's subfolder AND base filename (e.g., 'john_rvc/john_model' for '.../rvc_voices/john_rvc/john_model.pth'): ").strip()
            if not rvc_subdir_and_model_name:
                print("      RVC model name cannot be empty. Skipping RVC for this character.")
                break
            
            # Ensure forward slashes for constructing paths consistently
            rvc_subdir_and_model_name = rvc_subdir_and_model_name.replace('\\', '/')
            
            # Construct relative path for API (e.g., "john_rvc/john_model.pth")
            api_relative_pth_path = f"{rvc_subdir_and_model_name}.pth"
            # Full path for local check
            full_pth_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_pth_path)

            if os.path.exists(full_pth_path_local_check):
                assigned_rvc_model_api_path = api_relative_pth_path
                print(f"      Found RVC model: {full_pth_path_local_check}")

                api_relative_index_path = f"{rvc_subdir_and_model_name}.index"
                full_index_path_local_check = os.path.join(RVC_MODELS_BASE_DIR_FULL, api_relative_index_path)
                if os.path.exists(full_index_path_local_check):
                    assigned_rvc_index_api_path = api_relative_index_path
                    print(f"      Found RVC index: {full_index_path_local_check}")
                else:
                    print(f"      Note: RVC index file not found at '{full_index_path_local_check}' (this is optional for some RVC setups).")
                
                while True:
                    try:
                        pitch_input = input(f"      Enter RVC pitch for '{character_name_input}' (integer, e.g., 0, -2, 5, default 0): ").strip()
                        if not pitch_input: assigned_rvc_pitch = 0; break
                        assigned_rvc_pitch = int(pitch_input)
                        break
                    except ValueError:
                        print("      Invalid pitch. Please enter an integer.")
                break 
            else:
                print(f"      Error: RVC model .pth file not found at '{full_pth_path_local_check}'.")
                if input("      Try entering RVC model path part again? (y/n): ").strip().lower() != 'y':
                    break
    else:
        print(f"    No specific RVC model will be assigned to '{character_name_input}'.")

    character_voice_assignments[char_key] = {
        "original_name": character_name_input,
        "gender": assigned_gender,
        "xtts_speaker_wav": assigned_xtts_wav.replace('\\', '/'),
        "rvc_model_api_path": assigned_rvc_model_api_path.replace('\\', '/') if assigned_rvc_model_api_path else None,
        "rvc_index_api_path": assigned_rvc_index_api_path.replace('\\', '/') if assigned_rvc_index_api_path else None,
        "rvc_pitch": assigned_rvc_pitch
    }
    save_character_voice_map()
    return char_key


def parse_and_tag_content(input_text_content):
    """
    Parses text, identifies speakers interactively, and returns tagged lines.
    """
    # Regex to match lines already tagged, e.g., CHARACTER (g): text
    # Allows for names with spaces. Gender hint (m), (f), (n) is optional.
    SPEAKER_TAG_PATTERN = re.compile(r"^\s*([\w\s.'-]+?)(?:\s*\(([mfns])\))?:\s*(.*)$", re.IGNORECASE)
    
    lines = input_text_content.splitlines()
    tagged_output_lines = []
    # Use original_name from narrator config for display and consistency
    current_speaker_display_name = DEFAULT_NARRATOR_CONFIG["original_name"] 
    
    print(f"\n  Starting tagging. Default/current speaker: {current_speaker_display_name}")

    for line_idx, line_content in enumerate(lines):
        line_stripped = line_content.strip()

        if not line_stripped: # Preserve empty lines (paragraph breaks)
            tagged_output_lines.append("")
            # When an empty line is hit, good time to reset speaker context to Narrator for next non-empty line
            # unless the dialogue spans multiple paragraphs (which this simple logic won't handle well yet)
            # For simplicity, let's not reset here, user must re-tag if narrator interjects after blank line.
            continue

        # 1. Check if line ALREADY has a speaker tag
        tag_match = SPEAKER_TAG_PATTERN.match(line_stripped)
        final_text_for_line = line_stripped
        
        if tag_match:
            char_name_from_tag = tag_match.group(1).strip()
            gender_hint_from_tag = tag_match.group(2).strip().lower() if tag_match.group(2) else None
            text_after_tag = tag_match.group(3).strip()
            
            # Confirm or assign voice based on this pre-tag
            current_speaker_key = get_or_assign_character_voice(char_name_from_tag, gender_hint_from_tag)
            current_speaker_display_name = character_voice_assignments[current_speaker_key]["original_name"]
            final_text_for_line = text_after_tag # Use the text part after the tag
            print(f"    Line {line_idx+1}: Pre-tagged as '{current_speaker_display_name}'. Text: '{text_after_tag[:60]}...'")
        else:
            # 2. No explicit tag, try to identify speaker or ask
            # For simplicity, and to ensure user has control:
            # We will be more interactive here.
            
            # Heuristic: If line contains quotes, it's likely dialogue.
            is_dialogue = bool(re.search(r'["“].*?["”]', line_stripped))
            
            # Prompt for every line to confirm/set speaker (can be refined later for more automation)
            # Build prompt with context
            context_line_display = line_stripped[:100] + "..." if len(line_stripped) > 100 else line_stripped
            known_char_names = [details.get("original_name", key) for key, details in character_voice_assignments.items() if key != DEFAULT_NARRATOR_KEY]
            
            prompt_msg = (f"\n  Line {line_idx+1}: \"{context_line_display}\"\n"
                          f"    Current assigned speaker: '{current_speaker_display_name}'.\n"
                          f"    Who is speaking this line? (Enter name, 'N' for Narrator, press Enter to keep current, or 'Q' to quit chapter):\n"
                          f"    Known characters: {', '.join(known_char_names[:10])}{'...' if len(known_char_names)>10 else ''}\n    Your choice: ")
            
            user_choice = input(prompt_msg).strip()

            if user_choice.upper() == 'Q':
                print("    Quitting current chapter processing.")
                return None # Signal to stop processing this chapter

            if user_choice.upper() == 'N':
                current_speaker_key = DEFAULT_NARRATOR_KEY
                current_speaker_display_name = character_voice_assignments[current_speaker_key]["original_name"]
            elif user_choice: # User entered a name or confirmed a different character
                current_speaker_key = get_or_assign_character_voice(user_choice) # This handles new/existing
                current_speaker_display_name = character_voice_assignments[current_speaker_key]["original_name"]
            # If user_choice is empty, current_speaker_key and current_speaker_display_name remain unchanged

        # Re-fetch details in case a new character was added or gender updated
        char_details = character_voice_assignments[current_speaker_key]
        final_char_name_for_tag = char_details["original_name"]
        final_gender_hint_for_tag = char_details["gender"]
        
        # Construct the tagged line
        if final_gender_hint_for_tag and final_gender_hint_for_tag != 'n':
            tagged_line = f"{final_char_name_for_tag} ({final_gender_hint_for_tag}): {final_text_for_line}"
        else: # Narrator or neutral gender
            tagged_line = f"{final_char_name_for_tag}: {final_text_for_line}"
        tagged_output_lines.append(tagged_line)

    return tagged_output_lines


def process_text_file_for_tagging_entry(input_filepath, output_filepath): # Renamed to avoid conflict
    print(f"\n--- Processing text file: {os.path.basename(input_filepath)} ---")
    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            full_text_content = f.read()
        if not full_text_content.strip():
            print(f"  Skipping empty text file: {input_filepath}")
            # Write an empty output file to mark as "processed"
            if not os.path.exists(os.path.dirname(output_filepath)): os.makedirs(os.path.dirname(output_filepath))
            with open(output_filepath, 'w', encoding='utf-8') as f: f.write("")
            return
    except Exception as e:
        print(f"  Error reading text file {input_filepath}: {e}")
        return

    tagged_lines = parse_and_tag_content(full_text_content)

    if tagged_lines is None: # User chose to quit processing this chapter
        print(f"  Skipped saving tagged file for {os.path.basename(input_filepath)} due to user quit.")
        return

    if not os.path.exists(os.path.dirname(output_filepath)):
        os.makedirs(os.path.dirname(output_filepath), exist_ok=True) # exist_ok=True
        
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(tagged_lines).strip() + "\n") # Ensure a final newline
    print(f"  Tagged file saved to: {output_filepath}")


if __name__ == "__main__":
    if not NLTK_AVAILABLE :
        if input("NLTK not found. Sentence tokenization will be basic. Continue? (y/n): ").strip().lower() != 'y':
            exit()

    load_character_voice_map() # Load existing map or initialize with Narrator

    if not os.path.isdir(ORIGINAL_TEXT_DIR):
        print(f"Error: Original text directory '{ORIGINAL_TEXT_DIR}' not found.")
        exit()
    
    os.makedirs(TAGGED_TEXT_OUTPUT_DIR, exist_ok=True)
    print(f"Tagged files will be saved in: {os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}")

    # Verify voice files exist (optional but good)
    for voice_list_name, voice_path_list in [("MALE_XTTS_VOICES", MALE_XTTS_VOICES), 
                                             ("FEMALE_XTTS_VOICES", FEMALE_XTTS_VOICES)]:
        if not voice_path_list:
            print(f"Warning: Voice list {voice_list_name} is empty in configuration.")
        for vp in voice_path_list:
            if not os.path.exists(vp):
                print(f"Warning: Configured voice WAV file not found: {vp}")
    if not os.path.exists(DEFAULT_NARRATOR_CONFIG["xtts_speaker_wav"]):
         print(f"Warning: Default narrator voice WAV not found: {DEFAULT_NARRATOR_CONFIG['xtts_speaker_wav']}")


    source_text_files = sorted(glob.glob(os.path.join(ORIGINAL_TEXT_DIR, "*.txt")))

    if not source_text_files:
        print(f"No .txt files found in '{ORIGINAL_TEXT_DIR}'.")
        exit()

    print(f"\nFound {len(source_text_files)} text files to process from '{ORIGINAL_TEXT_DIR}'.")
    print(f"Character voice map will be loaded from/saved to: '{CHARACTER_VOICE_MAP_FILE}'")
    print("You will be prompted to identify speakers and assign voices/RVC to new characters.")
    print("Speaker tags will be in the format: CHARACTER_NAME (g): Text")
    if input("Press Enter to begin processing files... (or type 'q' to quit now): ").strip().lower() == 'q':
        print("Exiting.")
        exit()

    for text_filepath in source_text_files:
        base_filename = os.path.basename(text_filepath)
        output_filepath = os.path.join(TAGGED_TEXT_OUTPUT_DIR, base_filename)

        if os.path.exists(output_filepath):
            user_overwrite_choice = input(f"Tagged file '{output_filepath}' already exists. Overwrite? (y/n/q=quit all, default n): ").strip().lower()
            if user_overwrite_choice == 'q':
                print("Quitting process.")
                break 
            if user_overwrite_choice != 'y':
                print(f"Skipping {base_filename}.")
                continue
        
        process_text_file_for_tagging_entry(text_filepath, output_filepath) # Corrected function name call
        save_character_voice_map() 

    print("\n--- Text Tagging Process Complete ---")
    print(f"Final character voice map saved to: {os.path.abspath(CHARACTER_VOICE_MAP_FILE)}")
    print(f"Tagged text files are in: {os.path.abspath(TAGGED_TEXT_OUTPUT_DIR)}")
