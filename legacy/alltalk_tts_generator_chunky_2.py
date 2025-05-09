import requests
import os
import glob
import time
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

CHUNK_CHAR_LIMIT = 1000

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

def split_text_into_chunks(text, limit):
    """Splits text into chunks under a character limit."""
    # (Keep the split_text_into_chunks function from the previous version)
    # ... (implementation omitted for brevity, use the one from the previous response) ...
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""    
    for para in paragraphs:
        para = para.strip();
        if not para: continue
        para_len = len(para)
        if current_chunk and len(current_chunk) + para_len + 2 > limit:
            chunks.append(current_chunk); current_chunk = ""
        if para_len > limit:
            print(f"  Warning: Paragraph length ({para_len}) exceeds limit ({limit}). Splitting."); start_index = 0
            while start_index < para_len:
                end_index = min(start_index + limit, para_len)
                split_pos = max(para.rfind('.', start_index, end_index), para.rfind('?', start_index, end_index), para.rfind('!', start_index, end_index))
                if split_pos <= start_index: split_pos = para.rfind(' ', start_index, end_index)
                if split_pos <= start_index: split_pos = end_index
                else: split_pos += 1
                sub_para = para[start_index:split_pos].strip()
                if sub_para:
                    if current_chunk and len(current_chunk) + len(sub_para) + 2 > limit: chunks.append(current_chunk); current_chunk = sub_para
                    elif not current_chunk: current_chunk = sub_para
                    else: current_chunk += "\n\n" + sub_para
                    if len(current_chunk) > limit : chunks.append(current_chunk); current_chunk = "" 
                start_index = split_pos
        else:
            if not current_chunk: current_chunk = para
            else: current_chunk += "\n\n" + para
    if current_chunk: chunks.append(current_chunk)
    print(f"  Split text into {len(chunks)} chunks.")
    return chunks


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

    text_chunks = split_text_into_chunks(full_text_content, CHUNK_CHAR_LIMIT)
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
