import requests
import os
import glob
import time
import math
import re
import shutil
import json # Viktig for å laste karakterkonfigurasjonen
import pydub
from urllib.parse import urljoin

try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError # Good for specific error handling
    PYDUB_AVAILABLE = True
    print("  Pydub library successfully imported.") # Optional: confirmation
except ImportError:
    print("Warning: pydub library not found. Audio chunk concatenation will not work.")
    print("Please install it: pip install pydub")
    print("You might also need ffmpeg installed on your system (add to PATH).")
    PYDUB_AVAILABLE = False

# --- Konfigurasjon ( behold fra ditt eksisterende skript) ---
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate" # Fra config.json eller hardkodet
ALLTALK_BASE_URL = "http://127.0.0.1:7851" # Fra config.json eller hardkodet
TEXT_FILES_DIR = "scraped_tileas_worries_tagged_for_tts"
AUDIO_OUTPUT_DIR = "generated_audio_tileas_worries_character"
TEMP_CHUNK_DIR = "temp_audio_chunks"
CHUNK_CHAR_LIMIT = 500
TOKEN_LIMIT = 200
AVG_CHARS_PER_TOKEN = 2 # Eller din foretrukne verdi
XTTS_LANGUAGE = "en"
OUTPUT_FORMAT = "wav"
PYDUB_AVAILABLE = True # Antatt basert på koden din

# Add this near your other global constants
ALLTALK_RVC_MODELS_BASE_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/"
# Ensure your script's default RVC model name is in the API-ready relative format
DEFAULT_XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav"
# DEFAULT_RVC_MODEL_NAME = 'half_light/half_light.pth' # This is already good
DEFAULT_RVC_MODEL_NAME = None # This is already good
DEFAULT_RVC_PITCH = 0 #

# Last inn stemmekonfigurasjon (bør gjøres én gang globalt eller per kapittel)
CHARACTER_VOICE_CONFIG = {}

# --- Hjelpefunksjoner (behold fra alltalk_tts_generator_chunky_4.py) ---
# _estimate_tokens, _split_into_sentences, _split_long_text_by_char_est,
# split_text_into_chunks (denne brukes på tekstblokker per karakter),
# download_audio_chunk, concatenate_audio_chunks

# --- Helper Functions (ensure these are in your new script) ---

# AVG_CHARS_PER_TOKEN should be defined, e.g., AVG_CHARS_PER_TOKEN = 2

def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN): # [cite: 1]
    """Estimates the number of tokens in a piece of text.""" # [cite: 1]
    if not text: return 0 # [cite: 1]
    effective_avg_chars = max(1, avg_chars_per_token) # [cite: 1]
    denominator = effective_avg_chars if effective_avg_chars > 0 else 1 # [cite: 1]
    return math.ceil(len(text) / denominator) # [cite: 1]

def _split_into_sentences(text): # [cite: 1]
    """
    Splits text into sentences using regex. Handles common cases.
    """ # [cite: 1]
    if not text: return [] # [cite: 1]
    # Look for sentence endings (. ! ?) possibly followed by quotes/parens,
    # then followed by whitespace or end-of-string. Positive lookbehind keeps delimiter.
    # Adjusted to better handle quotes etc.
    splits = re.split(r'(?<=[.!?\"\'\)])(?=\s|\Z)', text) # [cite: 1]
    # Clean up: strip whitespace and filter empty strings
    sentences = [s.strip() for s in splits if s and s.strip()] # [cite: 1]
    return sentences # [cite: 1]

def _split_long_text_by_char_est(text_to_split, token_limit, avg_chars_per_token): # [cite: 1]
    """
    Fallback: Force splits text based on character estimates for token limit.
    Used only when a single sentence is estimated to be too long.
    """ # [cite: 1]
    if not text_to_split: return [] # [cite: 1]
    sub_chunks = [] # [cite: 1]
    current_pos = 0 # [cite: 1]
    text_len = len(text_to_split) # [cite: 1]
    # Calculate hard character limit per sub-chunk
    hard_char_limit = max(1, int(token_limit * avg_chars_per_token)) # [cite: 1]

    while current_pos < text_len: # [cite: 1]
        end_pos = min(current_pos + hard_char_limit, text_len) # [cite: 1]
        chunk = text_to_split[current_pos:end_pos].strip() # Slice from original text # [cite: 1]
        if chunk: # [cite: 1]
            sub_chunks.append(chunk) # [cite: 1]

        if end_pos == current_pos: # Prevent infinite loop # [cite: 1]
            break # [cite: 1]
        current_pos = end_pos # [cite: 1]

    sub_chunks = [c for c in sub_chunks if c] # [cite: 1]
    return sub_chunks # [cite: 1]

# --- Main Chunking Logic (This is the function causing the NameError) ---

def split_text_into_chunks(text, char_combination_limit, token_split_limit, avg_chars_per_token_est): # [cite: 1]
    """
    Splits text into chunks using a two-phase approach:
    1. Combine '\n\n' segments based on character limit (char_combination_limit).
    2. Split the resulting chunks further based on sentence boundaries if their
       estimated token count exceeds token_split_limit.
    """ # [cite: 1]
    # Phase 1: Combine based on character limit
    raw_segments = text.split('\n\n') # [cite: 1]
    intermediate_char_chunks = [] # [cite: 1]
    current_accumulated_char_chunk = "" # [cite: 1]
    separator = "\n\n" # [cite: 1]
    separator_len = len(separator) # [cite: 1]

    for segment_text in raw_segments: # [cite: 1]
        segment_text = segment_text.strip() # [cite: 1]
        if not segment_text: continue # [cite: 1]
        if not current_accumulated_char_chunk: # [cite: 1]
            current_accumulated_char_chunk = segment_text # [cite: 1]
        else: # [cite: 1]
            potential_combined_len = len(current_accumulated_char_chunk) + separator_len + len(segment_text) # [cite: 1]
            if potential_combined_len <= char_combination_limit: # [cite: 1]
                current_accumulated_char_chunk += separator + segment_text # [cite: 1]
            else: # [cite: 1]
                intermediate_char_chunks.append(current_accumulated_char_chunk) # [cite: 1]
                current_accumulated_char_chunk = segment_text # [cite: 1]
    if current_accumulated_char_chunk: # [cite: 1]
        intermediate_char_chunks.append(current_accumulated_char_chunk) # [cite: 1]

    # Phase 2: Process intermediate chunks for token limit using sentences
    final_chunks = [] # [cite: 1]
    for char_chunk in intermediate_char_chunks: # [cite: 1]
        char_chunk = char_chunk.strip() # [cite: 1]
        if not char_chunk: continue # [cite: 1]

        total_est_tokens = _estimate_tokens(char_chunk, avg_chars_per_token_est) # [cite: 1]

        if total_est_tokens <= token_split_limit: # [cite: 1]
            final_chunks.append(char_chunk) # Chunk is fine as is # [cite: 1]
        else: # [cite: 1]
            print(f"  Info: Chunk (length {len(char_chunk)} chars, est. {total_est_tokens} tokens) exceeds token limit ({token_split_limit}). Splitting by sentence.") # [cite: 1]
            sentences = _split_into_sentences(char_chunk) # [cite: 1]

            if not sentences: # If sentence splitting yielded nothing # [cite: 1]
                 print(f"    Warning: Could not split chunk into sentences (Text: '{char_chunk[:50]}...'). Using fallback char split.") # [cite: 1]
                 final_chunks.extend(_split_long_text_by_char_est(char_chunk, token_split_limit, avg_chars_per_token_est)) # [cite: 1]
                 continue # Move to next char_chunk # [cite: 1]

            current_sub_chunk_sentences = "" # [cite: 1]
            for sentence in sentences: # [cite: 1]
                sentence = sentence.strip() # [cite: 1]
                if not sentence: continue # [cite: 1]

                sentence_tokens = _estimate_tokens(sentence, avg_chars_per_token_est) # [cite: 1]

                if sentence_tokens > token_split_limit: # [cite: 1]
                    print(f"    Warning: Sentence (length {len(sentence)} chars, est. {sentence_tokens} tokens) exceeds token limit ({token_split_limit}). Using fallback char split for this sentence.") # [cite: 1]
                    if current_sub_chunk_sentences: # [cite: 1]
                        final_chunks.append(current_sub_chunk_sentences) # [cite: 1]
                    final_chunks.extend(_split_long_text_by_char_est(sentence, token_split_limit, avg_chars_per_token_est)) # [cite: 1]
                    current_sub_chunk_sentences = "" # Reset accumulator # [cite: 1]
                else: # [cite: 1]
                    separator_for_sentences = " " if current_sub_chunk_sentences else "" # [cite: 1]
                    potential_next_chunk_text = current_sub_chunk_sentences + separator_for_sentences + sentence # [cite: 1]
                    potential_tokens = _estimate_tokens(potential_next_chunk_text, avg_chars_per_token_est) # [cite: 1]

                    if potential_tokens <= token_split_limit: # [cite: 1]
                        current_sub_chunk_sentences = potential_next_chunk_text # [cite: 1]
                    else: # [cite: 1]
                        if current_sub_chunk_sentences: # [cite: 1]
                            final_chunks.append(current_sub_chunk_sentences) # [cite: 1]
                        current_sub_chunk_sentences = sentence # [cite: 1]
            if current_sub_chunk_sentences: # [cite: 1]
                final_chunks.append(current_sub_chunk_sentences) # [cite: 1]
    final_chunks = [chunk for chunk in final_chunks if chunk] # [cite: 1]
    print(f"  Split text into {len(final_chunks)} final chunks (char_limit combine: {char_combination_limit}, token_limit split: {token_split_limit}, chars_per_token est: {avg_chars_per_token_est}).") # [cite: 1]
    return final_chunks # [cite: 1]

# --- Audio Download and Concatenation Functions ---
# (download_audio_chunk remains the same)
def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    try:
        if relative_audio_url.startswith('/'): full_url = f"{server_base_url}{relative_audio_url}"
        else: full_url = urljoin(server_base_url + "/", relative_audio_url)
        print(f"    Downloading chunk: {full_url}")
        response = requests.get(full_url, stream=True, timeout=180); response.raise_for_status()
        with open(local_temp_path, 'wb') as f:
            for chunk_data in response.iter_content(chunk_size=8192): f.write(chunk_data)
        return True
    except Exception as e: print(f"    Error downloading {relative_audio_url}: {e}"); return False

# (concatenate_audio_chunks remains the same - still outputs WAV based on OUTPUT_FORMAT)
def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    if not PYDUB_AVAILABLE: print("  Error: pydub library not available. Cannot concatenate audio."); return False
    if not chunk_filepaths: print("  Error: No audio chunk files provided for concatenation."); return False
    print(f"  Concatenating {len(chunk_filepaths)} audio chunks...");
    try:
        combined = AudioSegment.empty()
        valid_chunks = []
        for filepath in chunk_filepaths:
            if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
                valid_chunks.append(filepath)
            else:
                print(f"    Warning: Skipping invalid/empty chunk file: {filepath}")

        if not valid_chunks:
             print("  Error: No valid audio chunk files found for concatenation.")
             return False

        for i, filepath in enumerate(valid_chunks):
            try:
                segment = AudioSegment.from_wav(filepath)
                combined += segment
            except FileNotFoundError:
                 print(f"    Error: Chunk file not found during concatenation: {filepath}. Skipping.")
            except CouldntDecodeError: # More specific pydub exception
                 print(f"    Error: Could not decode chunk file (possibly corrupt/empty): {filepath}. Skipping.")
            except Exception as e:
                 print(f"    Error loading/processing chunk {filepath}: {e}. Skipping.")

        if len(combined) > 0:
            output_dir = os.path.dirname(final_output_path)
            if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)

            # Export based on global OUTPUT_FORMAT
            export_format = OUTPUT_FORMAT.lower()
            print(f"    Exporting concatenated audio as {export_format}...") # Info
            try:
                # Add logic here if you want different formats like mp3/opus later
                if export_format == "wav":
                     combined.export(final_output_path, format="wav")
                # Example: Add other formats if needed
                # elif export_format == "mp3":
                #     combined.export(final_output_path, format="mp3", bitrate="96k")
                # elif export_format == "opus":
                #     combined.export(final_output_path, format="opus", parameters=["-c:a", "libopus", "-b:a", "48k"])
                else:
                     print(f"    Warning: Unsupported OUTPUT_FORMAT '{OUTPUT_FORMAT}' for export. Defaulting to WAV.")
                     combined.export(final_output_path, format="wav")

                print(f"  Concatenated audio saved successfully to: {final_output_path}")
                return True
            except Exception as export_e:
                 print(f"  Error exporting combined audio to {export_format}: {export_e}")
                 return False
        else:
            print("  Error: Combined audio is empty after attempting to process chunks.")
            return False
    except Exception as e:
        print(f"  Error during audio concatenation: {e}")
        return False

def load_character_voice_config(config_path="character_voice_config.json"):
    global CHARACTER_VOICE_CONFIG, DEFAULT_XTTS_SPEAKER_WAV, DEFAULT_RVC_MODEL_NAME, DEFAULT_RVC_PITCH
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            CHARACTER_VOICE_CONFIG = json.load(f)
        print(f"  Successfully loaded character voice config from: {config_path}")
        # Oppdater standardverdier hvis de finnes i config
        if "DEFAULT" in CHARACTER_VOICE_CONFIG:
            DEFAULT_XTTS_SPEAKER_WAV = CHARACTER_VOICE_CONFIG["DEFAULT"].get("xtts_speaker_wav", DEFAULT_XTTS_SPEAKER_WAV)
            DEFAULT_RVC_MODEL_NAME = CHARACTER_VOICE_CONFIG["DEFAULT"].get("rvc_model", DEFAULT_RVC_MODEL_NAME)
            DEFAULT_RVC_PITCH = CHARACTER_VOICE_CONFIG["DEFAULT"].get("pitch", DEFAULT_RVC_PITCH)
    except Exception as e:
        print(f"  Error loading character voice config from {config_path}: {e}. Using script defaults for all.")
        # Sørg for at DEFAULT eksisterer for nødfall
        CHARACTER_VOICE_CONFIG["DEFAULT"] = {
            "xtts_speaker_wav": DEFAULT_XTTS_SPEAKER_WAV,
            "rvc_model": DEFAULT_RVC_MODEL_NAME,
            "pitch": DEFAULT_RVC_PITCH
        }


def get_voice_params_for_speaker(speaker_tag):
    # Normaliserer speaker_tag for oppslag, f.eks. "CAMILLA (f)" -> "CAMILLA"
    # Nøkler i CHARACTER_VOICE_CONFIG bør være bare navnet.
    clean_speaker_name = re.sub(r'\s*\([fm]\)\s*$', '', speaker_tag).upper()
    
    if clean_speaker_name in CHARACTER_VOICE_CONFIG:
        return CHARACTER_VOICE_CONFIG[clean_speaker_name]
    elif "NARRATOR" in CHARACTER_VOICE_CONFIG and clean_speaker_name == "NARRATOR": # Direkte match for NARRATOR
        return CHARACTER_VOICE_CONFIG["NARRATOR"]
    else:
        print(f"    Warning: Voice config not found for '{speaker_tag}' (cleaned: '{clean_speaker_name}'). Using DEFAULT.")
        return CHARACTER_VOICE_CONFIG.get("DEFAULT", {}) # Returner tom dict hvis DEFAULT mangler

def process_chapter_file_speaker_aware(text_filepath, final_audio_output_path):
    print(f"\n--- Processing Chapter File (Speaker Aware): {text_filepath} ---")
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, base_filename_no_ext)
    os.makedirs(chapter_temp_dir, exist_ok=True)
    print(f"  Using temporary directory for chunks: {chapter_temp_dir}")

    # Dette er listen som vil inneholde (speaker_tag, text_chunk) for API-kall
    api_ready_chunks_with_speaker = []

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    current_speaker_tag = None
    current_speaker_text_lines = []
    
    # Regex for å identifisere linjer med taler, f.eks. "NARRATOR: tekst" eller "KARAKTER (x): tekst"
    # Den fanger talernavnet (gruppe 1) og teksten (gruppe 2)
    speaker_line_re = re.compile(r"^\s*([A-Z\s]+(?:\([fm]\))?):\s*(.*)")

    for line_num, raw_line in enumerate(lines):
        line_content = raw_line.strip()

        # Hopp over tomme linjer, men de kan signalisere slutten på en blokk
        if not line_content:
            if current_speaker_tag and current_speaker_text_lines:
                full_block_text = "\n".join(current_speaker_text_lines).strip()
                if full_block_text:
                    # Bruk din eksisterende chunk-splitter på denne blokken
                    sub_chunks = split_text_into_chunks(full_block_text, CHUNK_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)
                    for sc_text in sub_chunks:
                        api_ready_chunks_with_speaker.append({"speaker": current_speaker_tag, "text": sc_text})
                current_speaker_text_lines = [] # Nullstill for neste
            # Ikke nullstill current_speaker_tag her ennå, neste linje kan være en fortsettelse
            continue

        match = speaker_line_re.match(raw_line) # Match på rå linje for å bevare innrykk i dialog

        if match:
            identified_speaker = match.group(1).strip()
            text_after_tag = match.group(2).strip()

            if current_speaker_tag != identified_speaker:
                # Taleren har endret seg. Prosesser den forrige talerens innsamlede linjer.
                if current_speaker_tag and current_speaker_text_lines:
                    full_block_text = "\n".join(current_speaker_text_lines).strip()
                    if full_block_text:
                        sub_chunks = split_text_into_chunks(full_block_text, CHUNK_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)
                        for sc_text in sub_chunks:
                            api_ready_chunks_with_speaker.append({"speaker": current_speaker_tag, "text": sc_text})
                    current_speaker_text_lines = []
                current_speaker_tag = identified_speaker # Start ny talerblokk
            
            if text_after_tag: # Legg bare til hvis det er tekst etter taggen
                current_speaker_text_lines.append(text_after_tag)
        else:
            # Linjen har ikke en talertagg. Anta at den er en fortsettelse.
            if line_content and current_speaker_tag: # Bare hvis linjen har innhold og en aktiv taler
                current_speaker_text_lines.append(line_content)
            elif line_content and not current_speaker_tag: # Tekst før første talertagg
                current_speaker_tag = "NARRATOR" # Eller din standard
                current_speaker_text_lines.append(line_content)
                
    # Prosesser eventuelle gjenværende linjer for den siste taleren
    if current_speaker_tag and current_speaker_text_lines:
        full_block_text = "\n".join(current_speaker_text_lines).strip()
        if full_block_text:
            sub_chunks = split_text_into_chunks(full_block_text, CHUNK_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)
            for sc_text in sub_chunks:
                api_ready_chunks_with_speaker.append({"speaker": current_speaker_tag, "text": sc_text})

    if not api_ready_chunks_with_speaker:
        print("  No text chunks with speaker info generated.")
        # Rydd opp i tom temp-mappe hvis den ble opprettet
        try:
            if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
        except OSError: pass
        return True # Eller False hvis dette anses som en feil

    # --- API-kall og nedlastingsløkke ---
    local_chunk_audio_paths = []
    all_audio_chunks_acquired = True

    for i, chunk_data in enumerate(api_ready_chunks_with_speaker):
        chunk_idx = i + 1
        speaker_tag = chunk_data["speaker"]
        text_for_api = chunk_data["text"]
        
        voice_config = get_voice_params_for_speaker(speaker_tag)
        print(f"    Debug: Speaker Tag: '{speaker_tag}', Fetched voice_config: {voice_config}") # DEBUG

        # Hent stemmeparametere, med fallback til globale standarder
        api_xtts_wav = voice_config.get("xtts_speaker_wav", DEFAULT_XTTS_SPEAKER_WAV)

        # Get RVC model path and pitch using the correct keys from your JSON structure
        rvc_model_path_from_json = voice_config.get("rvc_model_api_path") # Correct key
        api_rvc_pitch = voice_config.get("rvc_pitch", DEFAULT_RVC_PITCH) # Correct key

        if rvc_model_path_from_json and isinstance(rvc_model_path_from_json, str) and rvc_model_path_from_json.strip() != "":
            # Path is a non-empty string, assume it's an absolute path from your JSON. Convert to relative.
            normalized_json_path = rvc_model_path_from_json.replace("\\", "/")
            normalized_base_path = ALLTALK_RVC_MODELS_BASE_PATH.replace("\\", "/") 

            if normalized_json_path.startswith(normalized_base_path):
                api_rvc_model = normalized_json_path[len(normalized_base_path):]
            else:
                print(f"    Warning: rvc_model_api_path '{rvc_model_path_from_json}' for speaker '{speaker_tag}' does not start with the defined RVC base path '{ALLTALK_RVC_MODELS_BASE_PATH}'. Using the value as is.")
                api_rvc_model = rvc_model_path_from_json 
            
            api_rvc_model = api_rvc_model.replace("\\", "/") # Ensure consistent slash usage
            print(f"    Info: Using specific RVC model '{api_rvc_model}' for speaker '{speaker_tag}'.")

        elif rvc_model_path_from_json is None:
            # "rvc_model_api_path" was explicitly null in JSON for this character.
            # API documentation states to use the string "Disabled" for no RVC.
            print(f"    Info: rvc_model_api_path is null for speaker '{speaker_tag}'. Setting RVC model to 'Disabled' (as per API docs).")
            api_rvc_model = "Disabled"  # <-- THIS IS THE KEY CHANGE

        elif isinstance(rvc_model_path_from_json, str) and rvc_model_path_from_json.strip() == "":
            # "rvc_model_api_path" was an empty string in JSON for this character.
            # Interpret this also as "no RVC" and send "Disabled".
            print(f"    Info: rvc_model_api_path is an empty string for speaker '{speaker_tag}'. Setting RVC model to 'Disabled'.")
            api_rvc_model = "Disabled"
        else:
            # The key "rvc_model_api_path" was entirely missing for this character in the JSON,
            # or the character was not found in the config (voice_config is empty).
            # Fall back to the script's defined default RVC model.
            print(f"    Info: rvc_model_api_path key missing or character not fully defined for '{speaker_tag}'. Using script's default RVC model: '{DEFAULT_RVC_MODEL_NAME}'")
            api_rvc_model = DEFAULT_RVC_MODEL_NAME

        print(f"    Debug: api_xtts_wav: '{api_xtts_wav}'") # DEBUG
        print(f"    Debug: api_rvc_model: '{api_rvc_model}' (from voice_config.get('rvc_model', fallback_to_DEFAULT_RVC_MODEL_NAME: '{DEFAULT_RVC_MODEL_NAME}'))") # DEBUG
        print(f"    Debug: api_rvc_pitch: {api_rvc_pitch}") # DEBUG





        # Lag et unikt filnavn for midlertidig chunk
        # Fjern ugyldige tegn fra speaker_tag for filnavn
        safe_speaker_name = re.sub(r'[^a-zA-Z0-9_-]', '', speaker_tag.replace(" ", "_"))
        chunk_file_basename = f"{base_filename_no_ext}_speaker_{safe_speaker_name}_part_{chunk_idx:03d}"
        local_temp_chunk_path = os.path.join(chapter_temp_dir, f"{chunk_file_basename}.{OUTPUT_FORMAT}")

        print(f"\n  Processing API Chunk {chunk_idx}/{len(api_ready_chunks_with_speaker)} for Speaker: '{speaker_tag}' (Voice: {os.path.basename(api_xtts_wav)})")

        if os.path.exists(local_temp_chunk_path) and os.path.getsize(local_temp_chunk_path) > 100: #
            print(f"    Found existing local audio chunk: {os.path.basename(local_temp_chunk_path)}. Skipping.")
            local_chunk_audio_paths.append(local_temp_chunk_path)
            continue
        
        if not text_for_api.strip():
            print(f"    Skipping empty text for chunk {chunk_idx}.")
            continue

        # The rest of your payload setup:
        payload = {
            "text_input": text_for_api,
            "character_voice_gen": api_xtts_wav,
            "rvccharacter_voice_gen": api_rvc_model, # This will now have the potentially relative path or default
            "rvccharacter_pitch": api_rvc_pitch,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_file_basename
        }        

        print(f"    Requesting TTS from API for chunk {chunk_idx}...")
        print(f"    Payload Summary: {{'text_input_len': {len(text_for_api)}, est_tokens: {_estimate_tokens(text_for_api)}, "
              f"'char_voice': '{os.path.basename(payload['character_voice_gen'])}', "
              f"'rvc_voice': '{payload['rvccharacter_voice_gen']}', ...}}") #

        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=600) #
            response.raise_for_status()
            response_data = response.json()

            if isinstance(response_data, dict) and response_data.get('output_file_url'):
                chunk_relative_url = response_data['output_file_url']
                print(f"    API reports SUCCESS. URL: {chunk_relative_url}") #
                if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_temp_chunk_path): #
                    local_chunk_audio_paths.append(local_temp_chunk_path)
                else:
                    print(f"    FAILED to download newly generated chunk {chunk_idx}.")
                    all_audio_chunks_acquired = False; break 
            else:
                print(f"    API did not return a valid 'output_file_url' for chunk {chunk_idx}.") #
                # ... (din eksisterende feilhåndtering) ...
                all_audio_chunks_acquired = False; break
        except requests.exceptions.Timeout: #
            print(f"    Error: Request timed out for chunk {chunk_idx}.")
            all_audio_chunks_acquired = False; break
        except requests.exceptions.HTTPError as http_err: #
            print(f"    HTTP error occurred for chunk {chunk_idx}: {http_err}")
            # ... (din eksisterende feilhåndtering) ...
            all_audio_chunks_acquired = False; break
        except Exception as e: #
            print(f"    An unexpected error occurred processing chunk {chunk_idx}: {e}")
            all_audio_chunks_acquired = False; break
        
        time.sleep(1) # Pause mellom API-kall

    # --- Slutt på API-kall løkke ---

    if all_audio_chunks_acquired and len(local_chunk_audio_paths) > 0: # Sjekk at vi faktisk har noen lydfiler
        # Ekstra validering som i ditt originale skript
        valid_for_concat = [p for p in local_chunk_audio_paths if os.path.exists(p) and os.path.getsize(p) > 100]
        if not valid_for_concat:
            print(f"  Error: No valid audio files to concatenate for {text_filepath}.")
            return False
        if len(valid_for_concat) != len([c for c in api_ready_chunks_with_speaker if c['text'].strip()]): # Sammenlign med antall ikke-tomme tekst-chunks
            print(f"  Warning: Mismatch in expected vs. acquired audio files. Expected for non-empty text chunks, Got {len(valid_for_concat)}. Proceeding with what was acquired.")
            # Dette kan indikere at noen API-kall feilet stille eller at tomme tekst-chunks ble sendt.

        if concatenate_audio_chunks(valid_for_concat, final_audio_output_path): #
            print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
            try:
                print(f"  Attempting to clean up temporary directory: {chapter_temp_dir}") #
                shutil.rmtree(chapter_temp_dir) #
                print(f"  Cleaned up temporary directory successfully.")
            except Exception as e:
                print(f"  Warning: Failed to clean up temporary directory {chapter_temp_dir}: {e}") #
            return True
        else:
            print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---") #
            return False
    elif not local_chunk_audio_paths and all_audio_chunks_acquired: # Ingen feil, men ingen lydfiler
        print(f"--- Chapter File Processing resulted in no audio output (possibly empty input or all chunks skipped): {text_filepath} ---")
        # Rydd opp tom temp-mappe
        try:
            if os.path.exists(chapter_temp_dir) and not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
        except OSError: pass
        return True # Ikke nødvendigvis en feil hvis input var tom
    else: # Feil under API-kall/nedlasting
        print(f"--- Chapter File Processing FAILED (Error during API/Download): {text_filepath} ---") #
        print(f"      Temporary chunks (if any) remain in: {chapter_temp_dir}")
        return False

# --- Hovedutførelseslogikk ---
if __name__ == "__main__":
    # Last inn karakterkonfigurasjon FØR du begynner å prosessere filer
    # Du må spesifisere riktig sti til din character_voice_config.json
    # For eksempel, hvis den ligger i rotmappen til prosjektet:
    character_config_file_path = "character_voice_config.json" 
    load_character_voice_config(character_config_file_path)

    # Resten av din __main__ blokk fra alltalk_tts_generator_chunky_4.py
    # ... (oppsett og sjekker) ...
    if not os.path.exists(TEMP_CHUNK_DIR): os.makedirs(TEMP_CHUNK_DIR)
    # ... etc.
    
    text_files = glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))
    # ... (sjekk om text_files er tom) ...

    chapters_processed = 0
    chapters_failed = 0

    for text_file_path in sorted(text_files):
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0]
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")

        if os.path.exists(final_output_audio_path):
            print(f"\nSkipping chapter: Final audio file already exists at {final_output_audio_path}")
            chapters_processed += 1
            continue

        # KALL DEN NYE FUNKSJONEN HER
        if process_chapter_file_speaker_aware(text_file_path, final_output_audio_path):
            chapters_processed += 1
        else:
            chapters_failed += 1
            # Vurder om du vil avslutte ved første feil, eller fortsette med neste kapittel
            # exit(1) # Som i ditt originale skript hvis du vil stoppe ved feil

        time.sleep(0.1) #

    print(f"\n--- Processing Complete ---") #
    # ... (oppsummering av prosesserte/feilede kapitler) ...
