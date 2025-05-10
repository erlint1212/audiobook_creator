import os
import glob
import re
import json
import shutil # For copying files if needed, or just writing new ones

# NLTK for sentence tokenization, which can help in processing text blocks
try:
    import nltk
    nltk.download('punkt', quiet=True) # Download if not present, quiet suppresses output if already there
    from nltk.tokenize import sent_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    print("Warning: NLTK library not found. Sentence tokenization will be basic.")
    print("Please install it: pip install nltk")
    NLTK_AVAILABLE = False
    # Basic fallback if NLTK is not available
    def sent_tokenize(text):
        # Simple fallback: split by common punctuation followed by space or newline.
        # This is not as robust as NLTK's punkt.
        text = re.sub(r'\s+', ' ', text) # Normalize whitespace
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]


# --- Configuration ---
# Based on your directory structure
ORIGINAL_TEXT_DIR = "scraped_tileas_worries"
TAGGED_TEXT_OUTPUT_DIR = "scraped_tileas_worries_tagged" # New directory for modified files
CHARACTER_VOICE_MAP_FILE = "character_voice_map.json"

# Paths to your voice files (use forward slashes for consistency in Python strings)
# These are the full paths that your Alltalk TTS API will likely need for XTTS_SPEAKER_WAV
VOICES_BASE_DIR = "C:/Users/etnor/Documents/tts/alltalk_tts/voices"

MALE_VOICE_WAVS = [
    os.path.join(VOICES_BASE_DIR, "male_01.wav"),
    os.path.join(VOICES_BASE_DIR, "male_02.wav"),
    os.path.join(VOICES_BASE_DIR, "male_03.wav"),
    os.path.join(VOICES_BASE_DIR, "male_04.wav"),
    os.path.join(VOICES_BASE_DIR, "male_05.wav"),
    # You can add more specific named male voices here if desired
    # os.path.join(VOICES_BASE_DIR, "Arnold.wav"),
]

FEMALE_VOICE_WAVS = [
    os.path.join(VOICES_BASE_DIR, "female_01.wav"),
    os.path.join(VOICES_BASE_DIR, "female_02.wav"),
    os.path.join(VOICES_BASE_DIR, "female_03.wav"),
    os.path.join(VOICES_BASE_DIR, "female_04.wav"),
    os.path.join(VOICES_BASE_DIR, "female_05.wav"),
    # You can add more specific named female voices here if desired
    # os.path.join(VOICES_BASE_DIR, "Sophie_Anderson CC3.wav"),
]

DEFAULT_NARRATOR_VOICE_WAV = os.path.join(VOICES_BASE_DIR, "Half_Light_Disco_Elysium.wav")
DEFAULT_NARRATOR_NAME = "NARRATOR"

# --- Global state for voice assignment (loaded from/saved to JSON) ---
character_voice_assignments = {}
# To cycle through available voices for new characters
# These will be dynamically calculated based on available voices
# and potentially excluding already assigned ones if desired for more variety.
# For simplicity, we'll just cycle through the full lists.
male_voice_next_idx = 0
female_voice_next_idx = 0
# --- End Configuration ---

def load_character_voice_map():
    global character_voice_assignments, male_voice_next_idx, female_voice_next_idx
    if os.path.exists(CHARACTER_VOICE_MAP_FILE):
        try:
            with open(CHARACTER_VOICE_MAP_FILE, 'r', encoding='utf-8') as f:
                character_voice_assignments = json.load(f)
            print(f"Loaded character voice map from {CHARACTER_VOICE_MAP_FILE}")
            # Recalculate next available indices based on loaded assignments (optional, simple cycling is fine too)
        except json.JSONDecodeError:
            print(f"Warning: Could not decode {CHARACTER_VOICE_MAP_FILE}. Starting with an empty map.")
            character_voice_assignments = {}
        except Exception as e:
            print(f"Error loading {CHARACTER_VOICE_MAP_FILE}: {e}. Starting with an empty map.")
            character_voice_assignments = {}
    else:
        print(f"{CHARACTER_VOICE_MAP_FILE} not found. Starting with an empty map.")
        character_voice_assignments = {}

    # Ensure Narrator has a voice
    if DEFAULT_NARRATOR_NAME.upper() not in character_voice_assignments:
         character_voice_assignments[DEFAULT_NARRATOR_NAME.upper()] = {
             "voice_wav": DEFAULT_NARRATOR_VOICE_WAV,
             "gender": "n" # neutral or narrator
         }


def save_character_voice_map():
    global character_voice_assignments
    try:
        with open(CHARACTER_VOICE_MAP_FILE, 'w', encoding='utf-8') as f:
            json.dump(character_voice_assignments, f, indent=4)
        print(f"Saved character voice map to {CHARACTER_VOICE_MAP_FILE}")
    except Exception as e:
        print(f"Error saving character voice map: {e}")

def get_voice_for_character(character_name_input, gender_hint_input=None):
    global character_voice_assignments, male_voice_next_idx, female_voice_next_idx
    
    character_name = character_name_input.strip().upper()
    if not character_name: # Should not happen if input is validated
        return DEFAULT_NARRATOR_NAME # Fallback

    if character_name in character_voice_assignments:
        return character_name # We just need the key, the TTS script will use the JSON

    # New character
    print(f"\nEncountered new character: '{character_name_input}'")
    assigned_voice_wav = None
    assigned_gender = None

    # Priority to gender_hint_input if provided by text markup
    if gender_hint_input and gender_hint_input.lower() in ['m', 'f', 'n']:
        assigned_gender = gender_hint_input.lower()
    else:
        while True:
            gender_input = input(f"  What is the gender of '{character_name_input}'? (m=male, f=female, n=neutral/narrator, s=skip/use_narrator): ").strip().lower()
            if gender_input in ['m', 'f', 'n']:
                assigned_gender = gender_input
                break
            elif gender_input == 's':
                 character_voice_assignments[character_name] = character_voice_assignments[DEFAULT_NARRATOR_NAME.upper()].copy()
                 character_voice_assignments[character_name]["original_name"] = character_name_input # Store original casing
                 print(f"  '{character_name_input}' assigned Narrator voice.")
                 save_character_voice_map() # Save immediately
                 return character_name
            else:
                print("  Invalid input. Please enter 'm', 'f', 'n', or 's'.")
    
    if assigned_gender == 'm':
        if not MALE_VOICE_WAVS:
            print(f"  Warning: No male voices defined in MALE_VOICE_WAVS for {character_name_input}. Assigning narrator.")
            assigned_voice_wav = DEFAULT_NARRATOR_VOICE_WAV
            assigned_gender = 'n'
        else:
            assigned_voice_wav = MALE_VOICE_WAVS[male_voice_next_idx % len(MALE_VOICE_WAVS)]
            male_voice_next_idx += 1
    elif assigned_gender == 'f':
        if not FEMALE_VOICE_WAVS:
            print(f"  Warning: No female voices defined in FEMALE_VOICE_WAVS for {character_name_input}. Assigning narrator.")
            assigned_voice_wav = DEFAULT_NARRATOR_VOICE_WAV
            assigned_gender = 'n'
        else:
            assigned_voice_wav = FEMALE_VOICE_WAVS[female_voice_next_idx % len(FEMALE_VOICE_WAVS)]
            female_voice_next_idx += 1
    else: # 'n' or fallback
        assigned_voice_wav = DEFAULT_NARRATOR_VOICE_WAV
        assigned_gender = 'n' # Ensure gender is 'n' for narrator

    character_voice_assignments[character_name] = {
        "voice_wav": assigned_voice_wav,
        "gender": assigned_gender,
        "original_name": character_name_input # Store original casing for potential use
    }
    print(f"  Assigned voice '{os.path.basename(assigned_voice_wav)}' to '{character_name_input}' (Gender: {assigned_gender}).")
    save_character_voice_map() # Save after each new assignment
    return character_name


def process_text_file_for_tagging(input_filepath, output_filepath):
    print(f"\n--- Processing text file: {os.path.basename(input_filepath)} ---")
    with open(input_filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple paragraph splitting, assumes \n\n or more \n is a paragraph break
    # Handles cases with multiple blank lines between paragraphs
    paragraphs = re.split(r'\n\s*\n+', content.strip())
    
    tagged_lines = []
    current_speaker_key = DEFAULT_NARRATOR_NAME.upper() # Start with Narrator

    # Regex to find dialogue quotes. This is simple and might need refinement.
    # It captures text before quote (prefix), the quoted text, and text after quote (suffix)
    # dialogue_pattern = re.compile(r'(.*?)"([^"]+)"(.*?)$')
    # More robust: handles lines that are *only* quotes, or quotes with attribution
    # This pattern tries to find character attributions like "Name said/asked/etc."
    # It's a starting point and will NOT be perfect.
    attribution_pattern = re.compile(
        r'^(.*?)(["“](.+?)["”])\s*(?:,\s*said\s+([A-Za-z\s]+)|,\s*([A-Za-z\s]+)\s+said|\.\s*([A-Za-z\s]+)\s+muttered|sighed\s+([A-Za-z\s]+))?(.*?)$',
        re.IGNORECASE
    )
    # Simpler patterns if you use explicit tags like "CHARACTER:" in input already
    # For now, we assume raw text.

    for para_idx, paragraph_text in enumerate(paragraphs):
        if not paragraph_text.strip():
            tagged_lines.append("") # Preserve empty lines between paragraphs
            continue

        # Try to detect explicit CHARACTER: lines first if you adopt that format
        # For now, let's process raw text.

        # If NLTK is available, split paragraph into sentences for finer-grained processing
        sentences = sent_tokenize(paragraph_text) if NLTK_AVAILABLE else [paragraph_text] # Treat whole para as one "sentence" if no NLTK

        paragraph_tagged_lines = []
        
        for sentence_idx, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if not sentence:
                continue

            # Attempt to find dialogue within the sentence
            # This is a very basic way to handle it. Proper dialogue attribution is complex.
            # We'll look for quotes. If found, we try to guess speaker, or ask.
            
            # Check for quotes:
            quote_match = re.search(r'["“](.+?)["”]', sentence)

            if quote_match:
                dialogue_content = quote_match.group(1)
                
                # Try to find speaker attribution (very simplified)
                # Look for patterns like "Name said", "asked Name", "Name:" at start of line
                # This is where it gets tricky and user interaction is best for accuracy.
                
                # For now, let's implement a simple interactive approach for ANY quoted line
                # or lines where speaker changes.

                # Heuristic: if a line starts with an uppercase word followed by 'said', 'asked', etc.
                # OR if a character name is mentioned near the quote. This is hard to make robust.

                # --- Interactive Part ---
                print(f"\n  Paragraph {para_idx+1}, Sentence: \"{sentence[:100]}...\"")
                
                # Try a simple pattern for lines like "CHARACTER:" or "CHARACTER (m/f):"
                # This assumes the user might pre-tag some lines for easier processing.
                pre_tag_match = re.match(r"^\s*([\w\s]+?)(?:\s*\(([mfns])\))?:\s*(.*)", sentence, re.IGNORECASE)
                
                identified_char_name_input = None
                identified_gender_hint = None

                if pre_tag_match:
                    potential_char_name = pre_tag_match.group(1).strip()
                    potential_gender = pre_tag_match.group(2).strip().lower() if pre_tag_match.group(2) else None
                    text_after_tag = pre_tag_match.group(3).strip()
                    
                    # Check if this is a known character or if we need to confirm
                    if potential_char_name.upper() in character_voice_assignments or \
                       input(f"    Found potential tag: '{potential_char_name}'. Is this the speaker? (y/n/s=skip line): ").strip().lower() == 'y':
                        identified_char_name_input = potential_char_name
                        identified_gender_hint = potential_gender
                        sentence = text_after_tag # Use text after the tag for processing
                        current_speaker_key = get_voice_for_character(identified_char_name_input, identified_gender_hint)
                    elif _ == 's': # Skip this line from tagging
                        paragraph_tagged_lines.append(sentence) # Add original sentence
                        continue

                if not identified_char_name_input: # If not pre-tagged or user said no
                    # Ask for speaker if dialogue is present or if context suggests a change
                    # For simplicity, we will ask for ANY sentence containing a quote if speaker isn't pre-tagged.
                    if quote_match or sentence_idx == 0: # Ask for first sentence of paragraph too
                        existing_chars = list(character_voice_assignments.keys())
                        prompt = f"    Who is speaking this (or is it narration)? \n    '{sentence[:150]}...' \n    Known: {', '.join(k for k in existing_chars if k != DEFAULT_NARRATOR_NAME.upper())[:100]} \n    (Enter name, or 'N' for Narrator, '{current_speaker_key.capitalize()}' to keep current, or type new name): "
                        speaker_input = input(prompt).strip()

                        if speaker_input.upper() == 'N':
                            current_speaker_key = DEFAULT_NARRATOR_NAME.upper()
                        elif speaker_input and speaker_input.upper() == current_speaker_key:
                            pass # Keep current speaker
                        elif speaker_input:
                            # This will trigger gender prompt if new, or use existing if known
                            current_speaker_key = get_voice_for_character(speaker_input) 
                        # If empty input, assume continuation of current_speaker_key (especially for non-quoted lines)
                        elif not quote_match and sentence_idx > 0: # Non-quoted continuation in paragraph
                            pass # Keep current_speaker_key
                        else: # Fallback to narrator if unsure or empty input for dialogue
                             current_speaker_key = DEFAULT_NARRATOR_NAME.upper()


                # Get the assigned gender for the tag
                final_char_name = character_voice_assignments[current_speaker_key].get("original_name", current_speaker_key)
                final_gender_tag = character_voice_assignments[current_speaker_key]['gender']
                
                if final_gender_tag and final_gender_tag != 'n':
                    tagged_line = f"{final_char_name.strip()} ({final_gender_tag}): {sentence}"
                else: # Narrator or neutral
                    tagged_line = f"{final_char_name.strip()}: {sentence}"
                paragraph_tagged_lines.append(tagged_line)

            else: # No quotes, assume narration or continuation of current speaker
                # If it's the start of a paragraph and not dialogue, assume narrator unless changed
                if sentence_idx == 0:
                     current_speaker_key = DEFAULT_NARRATOR_NAME.upper()

                final_char_name = character_voice_assignments[current_speaker_key].get("original_name", current_speaker_key)
                final_gender_tag = character_voice_assignments[current_speaker_key]['gender']

                if final_gender_tag and final_gender_tag != 'n':
                    tagged_line = f"{final_char_name.strip()} ({final_gender_tag}): {sentence}"
                else: # Narrator or neutral
                    tagged_line = f"{final_char_name.strip()}: {sentence}"
                paragraph_tagged_lines.append(tagged_line)

        tagged_lines.extend(paragraph_tagged_lines)
        tagged_lines.append("") # Add a blank line after each original paragraph's content

    # Write the tagged content
    if not os.path.exists(os.path.dirname(output_filepath)):
        os.makedirs(os.path.dirname(output_filepath))
        
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write("\n".join(tagged_lines).strip()) # Remove trailing newlines from the very end
    print(f"  Tagged file saved to: {output_filepath}")


if __name__ == "__main__":
    if not NLTK_AVAILABLE and input("NLTK not found, sentence tokenization will be basic. Continue? (y/n): ").lower() != 'y':
        exit()

    load_character_voice_map()

    if not os.path.exists(ORIGINAL_TEXT_DIR):
        print(f"Error: Original text directory '{ORIGINAL_TEXT_DIR}' not found.")
        exit()
    
    if not os.path.exists(TAGGED_TEXT_OUTPUT_DIR):
        os.makedirs(TAGGED_TEXT_OUTPUT_DIR)
        print(f"Created output directory for tagged files: {TAGGED_TEXT_OUTPUT_DIR}")

    # Verify voice files exist (optional but good)
    for voice_path_list in [MALE_VOICE_WAVS, FEMALE_VOICE_WAVS, [DEFAULT_NARRATOR_VOICE_WAV]]:
        for vp in voice_path_list:
            if not os.path.exists(vp):
                print(f"Warning: Defined voice WAV file not found: {vp}")


    source_text_files = glob.glob(os.path.join(ORIGINAL_TEXT_DIR, "*.txt"))
    source_text_files.sort()

    if not source_text_files:
        print(f"No .txt files found in '{ORIGINAL_TEXT_DIR}'.")
        exit()

    print(f"\nFound {len(source_text_files)} text files to process for tagging in '{ORIGINAL_TEXT_DIR}'.")
    print(f"Character voice map will be loaded from/saved to: {CHARACTER_VOICE_MAP_FILE}")
    print(f"Tagged files will be saved in: {TAGGED_TEXT_OUTPUT_DIR}")
    print("You will be prompted to identify speakers for dialogue and assign voices to new characters.")
    input("Press Enter to begin...")

    for text_filepath in source_text_files:
        base_filename = os.path.basename(text_filepath)
        output_filepath = os.path.join(TAGGED_TEXT_OUTPUT_DIR, base_filename)

        # Simple skip if output already exists - you might want to make this configurable
        if os.path.exists(output_filepath):
            if input(f"Tagged file '{output_filepath}' already exists. Overwrite? (y/n, default n): ").strip().lower() != 'y':
                print(f"Skipping {base_filename} as output already exists.")
                continue
        
        process_text_file_for_tagging(text_filepath, output_filepath)
        save_character_voice_map() # Save map after each file in case of interruption

    print("\n--- Text Tagging Process Complete ---")
    print(f"Final character voice map saved to {CHARACTER_VOICE_MAP_FILE}")
    print(f"Tagged text files are in {TAGGED_TEXT_OUTPUT_DIR}")
