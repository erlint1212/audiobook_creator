import requests
import os
import glob
import time
import math
import re
import shutil
import traceback

import nltk
from nltk.tokenize import sent_tokenize

# --- NLTK Setup ---
NLTK_SETUP_SUCCESSFUL = False
try:
    nltk.sent_tokenize("This is a test.")
    NLTK_SETUP_SUCCESSFUL = True
except LookupError:
    print("Attempting to download NLTK 'punkt' resource...")
    try:
        nltk.download('punkt', quiet=False)
        nltk.sent_tokenize("This is a test.")
        print("NLTK 'punkt' is now available.")
        NLTK_SETUP_SUCCESSFUL = True
    except Exception as download_e:
        print(f"An error occurred during 'punkt' download: {download_e}")
if not NLTK_SETUP_SUCCESSFUL:
    print("\nNLTK 'punkt' setup failed. Please resolve this issue manually and re-run.")
    exit(1)
# --- End NLTK Setup ---

# --- Pydub Setup ---
try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError
    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub library not found. Audio concatenation will not work.")
    PYDUB_AVAILABLE = False
# ---------------------------

# --- Configuration ---
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate"
ALLTALK_BASE_URL = "http://127.0.0.1:7851"

LOG_FILE = "failed_chunks.log"
TEXT_FILES_DIR = os.getenv("PROJECT_INPUT_TEXT_DIR", "BlleatTL_Novels") 
AUDIO_OUTPUT_DIR = os.getenv("PROJECT_AUDIO_WAV_DIR", "generated_audio_MistakenFairy")
TEMP_CHUNK_DIR = "temp_audio_chunks"

CHAPTER_START = 0
CHAPTER_STOP = 0

# --- Fallback Token/Char Limits ---
# This is now our *primary* token limit
FALLBACK_TOKEN_LIMIT = 170 
AVG_CHARS_PER_TOKEN = 1.9
# This is the character limit for our chunks (Lvl 1, 2, 3)
FALLBACK_CHAR_LIMIT = FALLBACK_TOKEN_LIMIT * AVG_CHARS_PER_TOKEN

# --- Validation Limit ---
MIN_BYTES_PER_CHAR = 1500 

# --- Paths/Values ---
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav"
XTTS_LANGUAGE = "en"
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_MODEL_NAME_FOR_API = 'half_light\\half_light.pth'
RVC_PITCH = -2
SPEED = 1.0
USE_DEEPSPEED = True
OUTPUT_FORMAT = "wav"
# --- End Configuration ---


# --- Helper Functions ---

def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    if not text: return 0
    return math.ceil(len(text) / max(1.0, avg_chars_per_token))

def normalize_text(text):
    replacements = {
        '“': '"',  '”': '"',  '‘': "'",  '’': "'",
        '…': '...', '—': '-',   '–': '-',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

# --- *** NEW CASCADING FALLBACK LOGIC (LVL 1, 2, 3) *** ---

def _split_by_force_chars(text_content, char_limit):
    """
    (Lvl 3) Brute-force splitter.
    Takes text (assumed to be a single sentence) and splits it
    by character limit, trying to respect spaces.
    """
    if len(text_content) <= char_limit:
        return [text_content]
        
    chunks = []
    current_chunk_start = 0
    
    while current_chunk_start < len(text_content):
        end_index = min(current_chunk_start + int(char_limit), len(text_content))
        
        # If we're not at the end, try to find a space to split at
        if end_index < len(text_content):
            space_index = text_content.rfind(' ', current_chunk_start, end_index)
            if space_index != -1 and space_index > current_chunk_start:
                end_index = space_index
        
        chunk = text_content[current_chunk_start:end_index].strip()
        if chunk:
            chunks.append(chunk)
        
        # Move start to the character *after* the split
        current_chunk_start = end_index + 1 
        # Find the next non-space character to avoid empty chunks
        while current_chunk_start < len(text_content) and text_content[current_chunk_start] == ' ':
            current_chunk_start += 1
            
    return chunks

def _split_by_sentence_groups(text_content, token_limit, avg_chars_token_est):
    """
    (Lvl 2) Splits a block of text into sentence groups.
    If a single sentence is over the limit, it passes it to Lvl 3.
    """
    final_tts_chunks = []
    char_limit = token_limit * avg_chars_token_est

    try:
        sentences = sent_tokenize(text_content)
    except Exception as e:
        print(f"      [!] NLTK sent_tokenize failed: {e}. Falling back to Lvl 3 (force split).")
        return _split_by_force_chars(text_content, char_limit)

    if not sentences:
        return []

    current_chunk_sentences_list = []
    current_chunk_tokens = 0
    
    for sentence_text in sentences:
        sentence_text = sentence_text.strip()
        if not sentence_text: continue
        
        estimated_sentence_tokens = _estimate_tokens(sentence_text, avg_chars_token_est)

        # --- *** CRITICAL BUG FIX *** ---
        # Check if the *single* sentence is too long *first*.
        if estimated_sentence_tokens > token_limit:
            # First, add any pending chunks we have.
            if current_chunk_sentences_list:
                final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                current_chunk_sentences_list = []
                current_chunk_tokens = 0
            
            # Now, pass the long sentence to Lvl 3 to be brute-forced
            print(f"      [Lvl 2] Sentence too long ({len(sentence_text)} chars). Passing to Lvl 3 (force split).")
            final_tts_chunks.extend(
                _split_by_force_chars(sentence_text, char_limit)
            )
            
        elif current_chunk_tokens + estimated_sentence_tokens <= token_limit:
            # Add to current chunk
            current_chunk_sentences_list.append(sentence_text)
            current_chunk_tokens += estimated_sentence_tokens
        else:
            # This sentence makes the chunk too big. Finalize the old one.
            if current_chunk_sentences_list:
                final_tts_chunks.append(" ".join(current_chunk_sentences_list))
            
            # Start a new chunk with this sentence
            current_chunk_sentences_list = [sentence_text]
            current_chunk_tokens = estimated_sentence_tokens
        # --- *** END BUG FIX *** ---

    if current_chunk_sentences_list:
        final_tts_chunks.append(" ".join(current_chunk_sentences_list))

    return [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]


def _split_by_line_groups(text_content, token_limit, avg_chars_token_est):
    """
    (Lvl 1) Splits a block of text by individual lines (\n) and groups them.
    If a single line is over the limit, it passes it to Lvl 2.
    This is now the *primary* chunking function.
    """
    final_tts_chunks = []
    char_limit = token_limit * avg_chars_token_est
    
    if not text_content or not text_content.strip():
        return final_tts_chunks

    lines = [line.strip() for line in text_content.split('\n') if line.strip()]
    if not lines:
        return []

    current_chunk_lines_list = []
    current_chunk_tokens = 0
    
    for line_text in lines:
        estimated_line_tokens = _estimate_tokens(line_text, avg_chars_token_est)

        # --- *** CRITICAL BUG FIX *** ---
        # Check if the *single* line is too long *first*.
        if estimated_line_tokens > token_limit:
            # First, add any pending chunks we have.
            if current_chunk_lines_list:
                final_tts_chunks.append("\n".join(current_chunk_lines_list))
                current_chunk_lines_list = []
                current_chunk_tokens = 0
            
            # Now, pass the long line to Lvl 2 to be split by sentence
            print(f"      [Lvl 1] Line too long ({len(line_text)} chars). Passing to Lvl 2 (sentence split).")
            final_tts_chunks.extend(
                _split_by_sentence_groups(line_text, token_limit, avg_chars_token_est)
            )

        elif current_chunk_tokens + estimated_line_tokens <= token_limit:
            # Add to current chunk
            current_chunk_lines_list.append(line_text)
            current_chunk_tokens += estimated_line_tokens
        else:
            # This line makes the chunk too big. Finalize the old one.
            if current_chunk_lines_list:
                final_tts_chunks.append("\n".join(current_chunk_lines_list))
            
            # Start a new chunk with this line
            current_chunk_lines_list = [line_text]
            current_chunk_tokens = estimated_line_tokens
        # --- *** END BUG FIX *** ---

    if current_chunk_lines_list:
        final_tts_chunks.append("\n".join(current_chunk_lines_list))

    return [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]


# --- *** REMOVED group_paragraphs_for_tts (Lvl 0) FUNCTION *** ---


def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    try:
        full_url = server_base_url.rstrip('/') + "/" + relative_audio_url.lstrip('/')
        print(f"      Downloading chunk: {full_url}")
        # --- *** MODIFIED: This can now be interrupted by Ctrl+C *** ---
        response = requests.get(full_url, stream=True, timeout=300) 
        response.raise_for_status()
        with open(local_temp_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)
        if os.path.exists(local_temp_path) and os.path.getsize(local_temp_path) > 100: 
            return True
        else:
            print(f"      Error: Downloaded file {local_temp_path} is empty or invalid.")
            if os.path.exists(local_temp_path): os.remove(local_temp_path) 
            return False
    # --- *** MODIFIED: Allow KeyboardInterrupt to pass through *** ---
    except KeyboardInterrupt:
        print(f"      Download interrupted.")
        raise # Re-raise the exception to be caught by the main loop
    except Exception as e:
        print(f"      Error downloading {full_url}: {e}")
        return False

def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    if not PYDUB_AVAILABLE: return False
    if not chunk_filepaths: return False
    
    print(f"  Concatenating {len(chunk_filepaths)} audio chunks...")
    combined = AudioSegment.empty()
    for filepath in sorted(chunk_filepaths): # Sort to ensure order
        try:
            combined += AudioSegment.from_wav(filepath) 
        except CouldntDecodeError:
            print(f"      Error: Could not decode chunk (corrupt?): {filepath}. Skipping.")
    
    if len(combined) > 0:
        combined.export(final_output_path, format=OUTPUT_FORMAT) 
        print(f"  Concatenated audio saved to: {final_output_path}")
        return True
    return False


# --- Main Processing Function ---
def process_chapter_file(text_filepath, final_audio_output_path):
    print(f"\n--- Processing Chapter File: {text_filepath} ---")
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    sanitized_base = re.sub(r'[^\w_.-]', '_', base_filename_no_ext)
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, sanitized_base) 
    os.makedirs(chapter_temp_dir, exist_ok=True)

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            full_text_content = f.read()
            
        print("  Normalizing text (replacing smart quotes, etc.)...")
        full_text_content = normalize_text(full_text_content)
            
        if not full_text_content.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            return True # Success
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False # Failure

    # --- *** MODIFIED: Lvl 0 logic removed. Go straight to Lvl 1. *** ---
    print(f"  Splitting text by lines (Lvl 1) for primary chunking...")
    initial_text_chunks = _split_by_line_groups(
        full_text_content, 
        FALLBACK_TOKEN_LIMIT, 
        AVG_CHARS_PER_TOKEN
    )
    # --- *** END MODIFICATION *** ---

    if not initial_text_chunks:
        print(f"  Warning: No text chunks generated from file: {text_filepath}.")
        return False # Failure

    pending_jobs = []
    for i, text_content in enumerate(initial_text_chunks):
        pending_jobs.append({
            "text": text_content,
            # --- *** MODIFIED: Suffix 'l' for line is now the default *** ---
            "output_suffix": f"l_{i+1:03d}", 
            "fallback_level": 1 # Start at Lvl 1
        })

    generated_audio_files = [] 
    any_chunk_failed_or_skipped = False 
    job_idx = 0
    
    # --- *** MODIFIED: try/except for Ctrl+C is removed from here *** ---
    # It will now propagate to the main loop, stopping concatenation.
    
    while job_idx < len(pending_jobs):
        current_job = pending_jobs[job_idx]
        
        text_to_process = current_job["text"]
        output_suffix = current_job["output_suffix"]
        fallback_level = current_job.get("fallback_level", 0)
        
        if fallback_level == 1:
            job_type = "Line-Group (Lvl 1)"
        elif fallback_level == 2:
            job_type = "Sentence-Group (Lvl 2)"
        else: # fallback_level 3+
            job_type = "Forced-Split (Lvl 3)"
        
        print(f"\n  Processing Job {job_idx + 1}/{len(pending_jobs)} (Type: {job_type}, Suffix: {output_suffix})")
        print(f"      Text Length: {len(text_to_process)} chars, Text: '{text_to_process[:120].replace(chr(10), ' ')}...'")

        chunk_output_basename = f"{sanitized_base}_{output_suffix}"
        local_chunk_filepath = os.path.join(chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")

        # --- (Existing file check logic is unchanged) ---
        if os.path.exists(local_chunk_filepath) and os.path.getsize(local_chunk_filepath) > 100:
            file_size = os.path.getsize(local_chunk_filepath)
            text_length = len(text_to_process)
            if text_length == 0: text_length = 1
            bytes_per_char = file_size / text_length
            
            if bytes_per_char < MIN_BYTES_PER_CHAR:
                print(f"      Error: Existing chunk is too small ({file_size} bytes for {text_length} chars).")
                print(f"      Ratio: {bytes_per_char:.2f} bytes/char (Min: {MIN_BYTES_PER_CHAR}). Deleting and regenerating.")
                try:
                    os.remove(local_chunk_filepath)
                except Exception as del_e:
                    print(f"      Warning: Could not delete invalid chunk: {del_e}. Skipping job.")
                    job_idx += 1
                    continue
            else:
                print(f"      Found existing valid chunk: {os.path.basename(local_chunk_filepath)}. Skipping generation.")
                generated_audio_files.append(local_chunk_filepath)
                job_idx += 1
                continue
        # --- (End of file check) ---

        payload = {
            "text_input": text_to_process,
            "character_voice_gen": XTTS_SPEAKER_WAV,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_output_basename,
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API if RVC_MODEL_PATH else "", 
            "rvccharacter_pitch": RVC_PITCH,
            "speed": SPEED 
        }
        
        try:
            print(f"      Requesting generation from API...")
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=720)
            response.raise_for_status()
            response_data = response.json()

            if 'output_file_url' in response_data and response_data['output_file_url']:
                if download_audio_chunk(ALLTALK_BASE_URL, response_data['output_file_url'], local_chunk_filepath):
                    
                    file_size = os.path.getsize(local_chunk_filepath)
                    text_length = len(text_to_process)
                    if text_length == 0: text_length = 1
                    bytes_per_char = file_size / text_length
                    
                    if bytes_per_char < MIN_BYTES_PER_CHAR:
                        print(f"      Error: Downloaded chunk is too small ({file_size} bytes for {text_length} chars).")
                        print(f"      Ratio: {bytes_per_char:.2f} bytes/char (Min: {MIN_BYTES_PER_CHAR}).")
                        raise Exception(f"Downloaded file too small (truncated). Ratio: {bytes_per_char:.2f} B/char.")
                        
                    generated_audio_files.append(local_chunk_filepath)
                else:
                    raise Exception("Failed to download generated chunk.")
            else:
                raise Exception(f"API Error: {response_data.get('error', 'No URL returned')}")

            job_idx += 1 
            time.sleep(0.5)

        except Exception as e:
            print(f"      [!!] An error occurred processing {output_suffix}: {e}")
            
            cooldown_seconds = 5 
            print(f"      [!!] Waiting {cooldown_seconds}s for server to recover before fallback...")
            time.sleep(cooldown_seconds)
            
            is_http_500 = False
            if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 500:
                is_http_500 = True

            fallback_level = current_job.get("fallback_level", 1) # Default to Lvl 1
            new_sub_jobs = []

            # --- *** MODIFIED: Fallback logic starts from Lvl 1 *** ---

            # --- FALLBACK 2: Line-Group (Lvl 1) -> Sentence-Group (Lvl 2) ---
            if fallback_level == 1:
                print(f"      Line-group (Lvl 1) chunk failed. FALLING BACK: Splitting into sentence-based groups (Lvl 2).")
                refined_sub_chunks = _split_by_sentence_groups(
                    text_to_process, FALLBACK_TOKEN_LIMIT, AVG_CHARS_PER_TOKEN
                )
                if refined_sub_chunks:
                    for sub_i, sub_chunk_text in enumerate(refined_sub_chunks):
                        new_sub_jobs.append({
                            "text": sub_chunk_text,
                            "output_suffix": f"{output_suffix}_s_{sub_i+1:02d}", # 's' for sentence
                            "fallback_level": 2
                        })

            # --- FALLBACK 3: Sentence-Group (Lvl 2) -> Forced-Split (Lvl 3) ---
            elif fallback_level == 2:
                print(f"      Sentence-group (Lvl 2) chunk failed. FALLING BACK: Force-splitting chunk (Lvl 3).")
                refined_sub_chunks = _split_by_force_chars(
                    text_to_process, FALLBACK_CHAR_LIMIT
                )
                if refined_sub_chunks:
                    for sub_i, sub_chunk_text in enumerate(refined_sub_chunks):
                        new_sub_jobs.append({
                            "text": sub_chunk_text,
                            "output_suffix": f"{output_suffix}_f_{sub_i+1:02d}", # 'f' for forced
                            "fallback_level": 3
                        })
            
            # --- FINAL FALLBACK: Lvl 3 failed ---
            elif fallback_level >= 3:
                print(f"      Forced-split (Lvl 3) chunk failed. This is the final fallback. Logging and skipping.")
                # new_sub_jobs remains empty

            # --- Job Replacement Logic ---
            if new_sub_jobs:
                pending_jobs = pending_jobs[:job_idx] + new_sub_jobs + pending_jobs[job_idx+1:]
                print(f"          Replaced failed Lvl {fallback_level} job '{output_suffix}' with {len(new_sub_jobs)} new Lvl {fallback_level+1} jobs.")
                continue # Restart loop with the first new sub-job
            else:
                # This path is taken if Lvl 3 fails, or if any Lvl fails to produce new chunks
                print(f"      Could not recover from error. This chunk will be SKIPPED.")
                if not is_http_500: 
                     traceback.print_exc()
                any_chunk_failed_or_skipped = True
                with open(LOG_FILE, "a", encoding="utf-8") as log_f:
                     http_code = e.response.status_code if isinstance(e, requests.exceptions.HTTPError) and e.response else 'N/A'
                     log_f.write(f"--- FAILED JOB (Error: {e.__class__.__name__}, HTTP: {http_code}): {output_suffix} (Fallback Lvl {fallback_level}) ---\nError: {e}\nText: {text_to_process}\n\n")
                job_idx += 1 # Skip and move on
                
    # --- Chapter Conclusion ---
    if not generated_audio_files and full_text_content.strip():
         print(f"--- Chapter Processing FAILED: No audio chunks were successfully generated for: {text_filepath} ---")
         return False # Failure

    if concatenate_audio_chunks(generated_audio_files, final_audio_output_path):
        if any_chunk_failed_or_skipped:
            print(f"--- Chapter Processed with SKIPPED chunks: {final_audio_output_path} ---")
            print(f"          Check logs ({LOG_FILE}). Chunks remain in: {chapter_temp_dir}")
        else:
            print(f"--- Chapter Successfully Processed: {final_audio_output_path} ---")
            try:
                shutil.rmtree(chapter_temp_dir)
                print(f"  Cleaned up temporary directory: {chapter_temp_dir}")
            except Exception as e:
                print(f"  Warning: Failed to clean up temp dir {chapter_temp_dir}: {e}")
        return True # Success
    else:
        print(f"--- Chapter Processing FAILED (Concatenation Error): {text_filepath} ---")
        return False # Failure

# --- Main Execution Logic ---
if __name__ == "__main__":
    if not os.path.exists(TEMP_CHUNK_DIR): os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.isdir(TEXT_FILES_DIR):
        print(f"Error: Input directory not found: {TEXT_FILES_DIR}"); exit(1)
    
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"--- TTS Generation Log ({time.asctime()}) ---\n\n")

    text_files = sorted(glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt")))
    if not text_files:
        print(f"No .txt files found in {TEXT_FILES_DIR}"); exit(1)
    if not os.path.exists(AUDIO_OUTPUT_DIR): os.makedirs(AUDIO_OUTPUT_DIR)

    print(f"\nFound {len(text_files)} text files to process.")
    print(f"--- STRATEGY: Normalizing text and splitting by lines (Lvl 1) first. ---")
    print(f"--- If a chunk fails, it will trigger the fallback logic. ---")
    
    # --- *** MODIFIED: Updated Print Statements *** ---
    print(f"--- Lvl 1 (Lines) -> Lvl 2 (Sentences) -> Lvl 3 (Forced). ---")
    print(f"--- Primary chunk token limit: {FALLBACK_TOKEN_LIMIT}. ---")
    # --- *** END MODIFICATION *** ---
    
    print(f"--- Truncation check (WAV): {MIN_BYTES_PER_CHAR} bytes per character. ---")
    print(f"--- Failed/Skipped chunks will be logged to: {LOG_FILE} ---")

    chapters_succeeded = 0
    chapters_failed = 0

    # --- *** MODIFIED: Main try/except now handles Ctrl+C and stops all processing *** ---
    try: 
        for idx, text_file_path in enumerate(text_files):
            current_chapter_num = idx + 1

            if current_chapter_num < CHAPTER_START:
                continue
            
            print(f"\n{'='*10} Processing Chapter {current_chapter_num}/{len(text_files)}: {os.path.basename(text_file_path)} {'='*10}")
            
            if CHAPTER_STOP > 0 and current_chapter_num > CHAPTER_STOP: 
                print(f"Reached CHAPTER_STOP limit ({CHAPTER_STOP}). Stopping."); break 

            sanitized_output_base = re.sub(r'[^\w_.-]', '_', os.path.splitext(os.path.basename(text_file_path))[0])
            final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{sanitized_output_base}.{OUTPUT_FORMAT}")

            if os.path.exists(final_output_audio_path) and os.path.getsize(final_output_audio_path) > 1024:
                print(f"Skipping chapter: Final audio file already exists: {final_output_audio_path}")
                chapters_succeeded += 1
                continue
            
            if process_chapter_file(text_file_path, final_output_audio_path):
                chapters_succeeded += 1
            else:
                chapters_failed += 1
            
    except KeyboardInterrupt: 
        print("\n\n[!!] User pressed Ctrl+C. Stopping processing.")
        print("--- Partial processing results below ---")
        print("--- NOTE: The current chapter was NOT finished and will NOT be concatenated. ---")
        
    print(f"\n--- Processing Complete ---")
    print(f"Chapters Succeeded (File Generated/Skipped): {chapters_succeeded}")
    print(f"Chapters Failed (No File Generated): {chapters_failed}")
    if chapters_failed > 0 or (os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 100):
         print(f"    Check logs ('{LOG_FILE}') for failed chunks. Temp files may remain in '{TEMP_CHUNK_DIR}'")
