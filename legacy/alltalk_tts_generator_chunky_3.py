import requests
import os
import glob
import time
import math # Make sure to import math at the top of your script
# import tempfile # No longer using tempfile.TemporaryDirectory
import shutil    # For removing the persistent temp chapter directory upon success
from urllib.parse import urljoin

# --- Try importing pydub ---
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub library not found. Audio chunk concatenation will not work.")
    print("Please install it: pip install pydub")
    print("You might also need ffmpeg installed on your system.")
    PYDUB_AVAILABLE = False
# ---------------------------

# --- Configuration ---
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate" 
ALLTALK_BASE_URL = "http://127.0.0.1:7851" 

TEXT_FILES_DIR = "scraped_tileas_worries" # Contains ch_XXX.txt
# Where the FINAL concatenated chapter audio will be saved locally
AUDIO_OUTPUT_DIR = "generated_audio_tileas_worries" 
# Persistent directory to store downloaded chunks during processing
TEMP_CHUNK_DIR = "temp_audio_chunks" 

CHUNK_CHAR_LIMIT = 800
TOKEN_LIMIT = 250  # Max tokens the TTS can handle per request
AVG_CHARS_PER_TOKEN = 3  # Estimated average characters per token (for English)

# --- Paths/Values needed by the Alltalk SERVER ---
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav" 
XTTS_LANGUAGE = "en"
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_MODEL_NAME_FOR_API = 'half_light\\half_light.pth' # Relative name might be required by API
RVC_PITCH = -2 
REPETITION_PENALTY = 10.0 # Commented out - Use fixed global setting instead
# DeepSpeed (Needs to be enabled in Alltalk settings/config)
USE_DEEPSPEED = True # <<< --- ENSURE THIS LINE IS PRESENT AND NOT COMMENTED OUT

OUTPUT_FORMAT = "wav"
# --- End of Configuration ---

def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    """Estimates the number of tokens in a piece of text."""
    if not text:
        return 0
    # Ensure avg_chars_per_token is at least 1 to avoid division by zero
    effective_avg_chars = max(1, avg_chars_per_token)
    return math.ceil(len(text) / effective_avg_chars)

def _sub_split_for_tokens(text_to_split, token_limit, avg_chars_per_token):
    """
    Splits a piece of text if its estimated token count exceeds token_limit.
    It aims to create chunks roughly corresponding to token_limit based on
    avg_chars_per_token, then finds natural breaks within those character estimates.
    """
    sub_chunks = []
    current_pos = 0
    text_len = len(text_to_split)

    if text_len == 0:
        return []

    while current_pos < text_len:
        # Estimate the target character length for the current sub-chunk
        # to stay within token_limit.
        target_chars_for_sub_chunk = math.ceil(token_limit * avg_chars_per_token)
        target_chars_for_sub_chunk = max(1, int(target_chars_for_sub_chunk)) # Ensure at least 1 char

        # Define the slice of text we're initially considering.
        ideal_char_end_for_slice = min(current_pos + target_chars_for_sub_chunk, text_len)
        
        actual_split_char_pos = ideal_char_end_for_slice # Default to hard cut

        # Try to find a natural break point (sentence end, then word end)
        # by searching backwards from ideal_char_end_for_slice.
        if ideal_char_end_for_slice > current_pos: # Only search if there's a slice
            s_dot = text_to_split.rfind('.', current_pos, ideal_char_end_for_slice)
            s_qmark = text_to_split.rfind('?', current_pos, ideal_char_end_for_slice)
            s_exclam = text_to_split.rfind('!', current_pos, ideal_char_end_for_slice)
            sentence_break_pos = max(s_dot, s_qmark, s_exclam)

            if sentence_break_pos > current_pos: # Found sentence break
                actual_split_char_pos = sentence_break_pos + 1 # Include punctuation
            else:
                space_break_pos = text_to_split.rfind(' ', current_pos, ideal_char_end_for_slice)
                if space_break_pos > current_pos: # Found space break
                    actual_split_char_pos = space_break_pos # Split before space (it'll be stripped)
        
        # Ensure progress if no natural break advanced the position or if slice was tiny
        if actual_split_char_pos <= current_pos and current_pos < text_len:
            actual_split_char_pos = current_pos + 1 
        actual_split_char_pos = min(actual_split_char_pos, text_len) # Don't exceed text length

        sub_chunk_text = text_to_split[current_pos:actual_split_char_pos].strip()

        if sub_chunk_text:
            # This sub-chunk is formed based on character estimates for the token limit.
            # A more robust system might re-estimate tokens here and shorten further if needed,
            # but that adds complexity. We'll rely on this char-based slicing.
            sub_chunks.append(sub_chunk_text)
        
        if actual_split_char_pos <= current_pos : # Break if no progress is made
             if sub_chunk_text : # we got something, next iteration will use the new current_pos
                 current_pos = actual_split_char_pos
             else: # Stuck and got nothing
                 # print(f"      Warning: Sub-split for tokens appears stuck. Pos: {current_pos}, SplitAt: {actual_split_char_pos}. Breaking.")
                 break 
        else:
            current_pos = actual_split_char_pos

        # Skip leading whitespace for the next potential sub-chunk
        while current_pos < text_len and text_to_split[current_pos].isspace():
            current_pos += 1
            
    # Fallback: if the splitting somehow resulted in no chunks, but the original text wasn't empty.
    if not sub_chunks and text_to_split.strip():
        # This might happen if text is very short but initial token estimate was high,
        # or if splitting logic had an edge case. Return original text as one chunk.
        # print(f"    Warning: Token-based sub-splitting yielded no chunks for input of length {len(text_to_split)}. Returning original.")
        return [text_to_split.strip()]
        
    return sub_chunks

def split_text_into_chunks(text, char_combination_limit, token_split_limit, avg_chars_per_token_est):
    """
    Splits text into chunks.
    1. Initially splits by '\n\n' into segments.
    2. Attempts to combine consecutive segments if their total character length
       (plus separator) is within 'char_combination_limit'.
    3. Each of these resulting chunks is then checked against 'token_split_limit'
       using an estimated token count.
    4. If a chunk's estimated tokens exceed 'token_split_limit', it is sub-split
       into smaller pieces, each aimed to be within the token limit.
    """
    raw_segments = text.split('\n\n')
    intermediate_char_chunks = []
    current_accumulated_char_chunk = ""
    separator = "\n\n"
    separator_len = len(separator)

    # Step 1: Combine based on character limit (char_combination_limit)
    for segment_text in raw_segments:
        segment_text = segment_text.strip()
        if not segment_text:
            continue

        if not current_accumulated_char_chunk:
            current_accumulated_char_chunk = segment_text
        else:
            potential_combined_len = len(current_accumulated_char_chunk) + separator_len + len(segment_text)
            if potential_combined_len <= char_combination_limit:
                current_accumulated_char_chunk += separator + segment_text
            else:
                intermediate_char_chunks.append(current_accumulated_char_chunk)
                current_accumulated_char_chunk = segment_text
    
    if current_accumulated_char_chunk: # Add any remaining accumulated chunk
        intermediate_char_chunks.append(current_accumulated_char_chunk)

    # Step 2: Process intermediate_char_chunks for token limit (token_split_limit)
    final_chunks = []
    for char_chunk in intermediate_char_chunks:
        if not char_chunk.strip(): # Should not happen if logic above is correct, but as a safeguard
            continue

        estimated_tokens = _estimate_tokens(char_chunk, avg_chars_per_token_est)
        
        if estimated_tokens <= token_split_limit:
            final_chunks.append(char_chunk)
        else:
            # This chunk (formed by char-based combining) is too long in estimated tokens.
            # It needs to be sub-split.
            print(f"  Info: Chunk (length {len(char_chunk)} chars, est. {estimated_tokens} tokens) exceeds token limit ({token_split_limit}). Sub-splitting.")
            token_sub_chunks = _sub_split_for_tokens(char_chunk, token_split_limit, avg_chars_per_token_est)
            if token_sub_chunks: # Only extend if sub-splitting produced results
                final_chunks.extend(token_sub_chunks)
            elif char_chunk.strip(): # If sub-splitting failed but chunk had content, add original (should be rare)
                print(f"    Warning: Sub-splitting returned no token_sub_chunks for a non-empty char_chunk. Adding original char_chunk.")
                final_chunks.append(char_chunk) # Fallback, might still be over limit
            
    print(f"  Split text into {len(final_chunks)} chunks (char_limit for combining: {char_combination_limit}, token_limit for splitting: {token_split_limit}).")
    return final_chunks

def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    """Downloads an audio chunk from the server."""
    # (Keep the download_audio_chunk function from the previous version)
     # ... (implementation omitted for brevity, use the one from the previous response) ...
    try:
        if relative_audio_url.startswith('/'): full_url = f"{server_base_url}{relative_audio_url}"
        else: full_url = urljoin(server_base_url + "/", relative_audio_url) 
        print(f"    Downloading chunk: {full_url}")
        response = requests.get(full_url, stream=True, timeout=180); response.raise_for_status()
        with open(local_temp_path, 'wb') as f:
            for chunk_data in response.iter_content(chunk_size=8192): f.write(chunk_data)
        return True
    except Exception as e: print(f"    Error downloading {relative_audio_url}: {e}"); return False


def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    """Concatenates downloaded audio chunks using pydub."""
    # (Keep the concatenate_audio_chunks function from the previous version)
    # ... (implementation omitted for brevity, use the one from the previous response) ...
    if not PYDUB_AVAILABLE: print("  Error: pydub library not available. Cannot concatenate audio."); return False
    if not chunk_filepaths: print("  Error: No audio chunk files provided for concatenation."); return False
    print(f"  Concatenating {len(chunk_filepaths)} audio chunks...");
    try:
        combined = AudioSegment.empty()
        for i, filepath in enumerate(chunk_filepaths):
            try: segment = AudioSegment.from_wav(filepath); combined += segment
            except Exception as e: print(f"    Error loading/processing chunk {filepath}: {e}. Skipping.")
        if len(combined) > 0:
             output_dir = os.path.dirname(final_output_path)
             if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)
             combined.export(final_output_path, format="wav"); print(f"  Concatenated audio saved successfully to: {final_output_path}"); return True
        else: print("  Error: Combined audio is empty after processing chunks."); return False
    except Exception as e: print(f"  Error during audio concatenation: {e}"); return False

# --- Updated Function to Process a Single Chapter ---
def process_chapter_file(text_filepath, final_audio_output_path):
    """
    Splits chapter text, calls API for MISSING chunks, downloads chunks, 
    and concatenates them into the final audio file. Checks for existing local chunks.
    Returns True if successful, False otherwise.
    """
    print(f"\n--- Processing Chapter File: {text_filepath} ---")
    
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    
    # Create a persistent temporary directory for this chapter's chunks
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, base_filename_no_ext)
    os.makedirs(chapter_temp_dir, exist_ok=True) 
    print(f"  Using temporary directory for chunks: {chapter_temp_dir}")

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            full_text_content = f.read()
        if not full_text_content.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            # Clean up empty temp dir if created
            try: os.rmdir(chapter_temp_dir) 
            except OSError: pass 
            return True 
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    text_chunks = split_text_into_chunks(full_text_content, CHUNK_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)
    if not text_chunks:
        print("  No text chunks generated after splitting.")
        try: os.rmdir(chapter_temp_dir) 
        except OSError: pass 
        return False

    all_chunks_acquired = True
    local_chunk_paths = [] # List to store paths to local chunk files (downloaded or existing)

    for i, chunk_text in enumerate(text_chunks):
        chunk_num = i + 1
        chunk_output_basename = f"{base_filename_no_ext}_chunk_{chunk_num:03d}" 
        # Define the path where the downloaded chunk SHOULD be saved locally
        local_chunk_filepath = os.path.join(chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")
        
        print(f"\n  Processing Chunk {chunk_num}/{len(text_chunks)} (Expected local file: {os.path.basename(local_chunk_filepath)})...")

        # --- Check if chunk already exists locally ---
        if os.path.exists(local_chunk_filepath) and os.path.getsize(local_chunk_filepath) > 100: # Check size > 100 bytes to avoid empty files
            print(f"    Found existing local chunk: {os.path.basename(local_chunk_filepath)}. Skipping generation/download.")
            local_chunk_paths.append(local_chunk_filepath)
            continue # Move to the next chunk
        # --------------------------------------------

        # --- If local chunk doesn't exist, call API ---
        payload = {
            "text_input": chunk_text,
            "character_voice_gen": XTTS_SPEAKER_WAV, 
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API, 
            "rvccharacter_pitch": RVC_PITCH,           
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_output_basename # Send BASE filename WITHOUT extension
            # Removed "repetition_penalty": REPETITION_PENALTY - Relying on fixed global setting
        }

        # Optional: Add penalty back if needed for testing, but verify global setting first
        # if 'REPETITION_PENALTY' in globals() and REPETITION_PENALTY is not None:
        #     payload["repetition_penalty"] = REPETITION_PENALTY 

        print(f"    Local chunk not found. Requesting generation from API...")
        print(f"    Payload (Form Data): {{'text_input': '...', "
              f"'character_voice_gen': '{payload['character_voice_gen']}', "
              f"'rvccharacter_voice_gen': '{payload['rvccharacter_voice_gen']}', "
              f"'rvccharacter_pitch': {payload['rvccharacter_pitch']}, "
              f"'language': '{payload['language']}', "
              f"'output_file_name': '{payload['output_file_name']}'" +
              (f", 'repetition_penalty': {payload['repetition_penalty']}" if 'repetition_penalty' in payload else '') +
              f"}}")

        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=600) 
            response.raise_for_status() 

            print(f"    API Response Status Code: {response.status_code}")
            
            response_data = response.json()
            print(f"    API Response JSON: {response_data}")

            if isinstance(response_data, dict) and 'output_file_url' in response_data and response_data['output_file_url']:
                chunk_relative_url = response_data['output_file_url']
                print(f"    API reports SUCCESS for chunk {chunk_num}. URL: {chunk_relative_url}")

                # Download the newly generated chunk
                if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_chunk_filepath):
                    local_chunk_paths.append(local_chunk_filepath)
                else:
                    print(f"    FAILED to download newly generated chunk {chunk_num}.")
                    all_chunks_acquired = False; break 
            else:
                 print(f"    API did not return a valid 'output_file_url' for chunk {chunk_num}.")
                 if isinstance(response_data, dict) and ('error' in response_data or 'status' in response_data):
                     print(f"      API Error/Status: {response_data.get('error') or response_data.get('status') or response_data.get('message')}")
                 all_chunks_acquired = False; break 

        except requests.exceptions.Timeout: print(f"    Error: Request timed out for chunk {chunk_num}."); all_chunks_acquired = False; break
        except requests.exceptions.RequestException as e:
            print(f"    Error sending request for chunk {chunk_num}: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"      API Response Status Code: {e.response.status_code}")
                if e.response.status_code == 500:
                    print(f"    Text input: {payload['text_input']}")
                try: error_detail = e.response.json(); print(f"      API Error Detail: {error_detail}") 
                except ValueError: print(f"      API Response Text: {e.response.text[:500]}...")
            all_chunks_acquired = False; break
        except Exception as e: print(f"    An unexpected error occurred processing chunk {chunk_num}: {e}"); all_chunks_acquired = False; break

        # Add delay between API calls for chunks
        delay = 1 
        print(f"    Pausing for {delay} second(s)...")
        time.sleep(delay)
        #--- End Chunk Loop ---

    # After processing all chunks (or breaking due to error)
    if all_chunks_acquired and len(local_chunk_paths) == len(text_chunks):
        # Ensure all paths in list actually exist before concatenation
        existing_chunk_paths = [p for p in local_chunk_paths if os.path.exists(p)]
        if len(existing_chunk_paths) != len(text_chunks):
             print(f"  Error: Mismatch between expected chunks ({len(text_chunks)}) and existing local chunks ({len(existing_chunk_paths)}). Cannot concatenate.")
             return False # Keep temp folder for inspection
             
        # Concatenate downloaded chunks
        if concatenate_audio_chunks(existing_chunk_paths, final_audio_output_path):
             print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
             # Clean up temporary directory for this chapter upon success
             try:
                 print(f"  Attempting to clean up temporary directory: {chapter_temp_dir}")
                 shutil.rmtree(chapter_temp_dir)
                 print(f"  Cleaned up temporary directory successfully.")
             except Exception as e:
                 print(f"  Warning: Failed to clean up temporary directory {chapter_temp_dir}: {e}")
             return True
        else: # Concatenation failed
            print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---")
            print(f"      Chunks remain in: {chapter_temp_dir}") # Keep temp folder
            return False
    else: # Not all chunks acquired
        print(f"--- Chapter File Processing FAILED (Missing Chunks / API / Download Error): {text_filepath} ---")
        print(f"      Temporary chunks (if any) remain in: {chapter_temp_dir}") # Keep temp folder
        return False
        
    #--- End Function process_chapter_file ---


# --- Main Execution Logic ---
if __name__ == "__main__":
    # Create the main temp directory if it doesn't exist
    if not os.path.exists(TEMP_CHUNK_DIR):
        os.makedirs(TEMP_CHUNK_DIR)
        print(f"Created temporary chunk directory: {TEMP_CHUNK_DIR}")
        
    # (Checks for directories and files remain the same)
    if not os.path.isdir(TEXT_FILES_DIR): print(f"Error: Input directory not found: {TEXT_FILES_DIR}"); exit()
    if not os.path.exists(XTTS_SPEAKER_WAV): print(f"Error: XTTS Speaker WAV not found: {XTTS_SPEAKER_WAV}"); exit()
    if not os.path.exists(RVC_MODEL_PATH): print(f"Warning: RVC model path '{RVC_MODEL_PATH}' not found locally. Ensure server configured correctly with '{RVC_MODEL_NAME_FOR_API}'.") 

    text_files = glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))
    if not text_files: print(f"No .txt files found in {TEXT_FILES_DIR}"); exit()

    if not os.path.exists(AUDIO_OUTPUT_DIR):
        os.makedirs(AUDIO_OUTPUT_DIR)
        print(f"Created local audio output directory: {AUDIO_OUTPUT_DIR}")

    print(f"\nFound {len(text_files)} text files to process.")
    print(f"Targeting API: {ALLTALK_API_URL}") # /api/tts-generate
    print(f"--- Using Endpoint: {ALLTALK_API_URL} (Requires Text Splitting & Local Concatenation) ---")
    print(f"--- Sending RVC parameters directly. ---")
    print(f"--- !!! Action Required: Ensure 'repetitionpenalty_set' is FIXED in Alltalk Settings if errors occur !!! ---")
    print(f"--- Ensure RVC Reference WAV & DeepSpeed ({USE_DEEPSPEED}) are PRE-CONFIGURED in Alltalk ---")
    if not PYDUB_AVAILABLE: print(f"--- !!! WARNING: pydub not installed. Concatenation will fail. !!! ---")

    chapters_processed = 0
    chapters_failed = 0

    for text_file_path in sorted(text_files): 
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0] 
        # Define final output path for the concatenated audio IN THE LOCAL SCRIPT'S OUTPUT DIR
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")
        
        # --- Check if FINAL concatenated file already exists ---
        if os.path.exists(final_output_audio_path):
             print(f"\nSkipping chapter: Final audio file already exists at {final_output_audio_path}")
             chapters_processed += 1
             continue
        # -----------------------------------------------------

        if process_chapter_file(text_file_path, final_output_audio_path):
            chapters_processed += 1
        else:
            chapters_failed += 1
            exit(1)
        
        # Delay between processing CHAPTERS
        chapter_delay = 3
        print(f"\nPausing for {chapter_delay} seconds before next chapter...")
        time.sleep(chapter_delay)

    print(f"\n--- Processing Complete ---")
    print(f"Chapters attempted: {chapters_processed + chapters_failed}")
    print(f"Chapters successfully processed: {chapters_processed}")
    print(f"Chapters failed: {chapters_failed}")
    print(f"\nGenerated audio files saved in: {AUDIO_OUTPUT_DIR}")
    print(f"(Temporary chunk files are stored in '{TEMP_CHUNK_DIR}' and should be cleaned up for successful chapters).")
