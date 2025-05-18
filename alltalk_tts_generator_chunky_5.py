import requests
import os
import glob
import time
import math # Make sure to import math
import re   # Import regex for sentence splitting
import shutil
from urllib.parse import urljoin

import nltk
from nltk.tokenize import sent_tokenize

# --- Try importing pydub ---
try:
    from pydub import AudioSegment
    # Added specific exception handling
    from pydub.exceptions import CouldntDecodeError
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

TEXT_FILES_DIR = "TheArtOfWar/artofwar_chapters_revised"
AUDIO_OUTPUT_DIR = "generated_audio_TheArtOfWar"
TEMP_CHUNK_DIR = "temp_audio_chunks_TAoW"

# Character limit for combining \n\n segments initially
CHUNK_CHAR_LIMIT = 800
# Token limit check - chunks exceeding this estimated limit will be split further
TOKEN_LIMIT = 350 # Using 250 gives buffer below XTTS's 400 limit
# Average characters per token estimate - Use a conservative value
AVG_CHARS_PER_TOKEN = 3  # Assuming ~3 chars/token to overestimate tokens slightly

# --- Paths/Values needed by the Alltalk SERVER ---
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav"
XTTS_LANGUAGE = "en"
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_MODEL_NAME_FOR_API = 'half_light\\half_light.pth'
RVC_PITCH = 0
USE_DEEPSPEED = True # Ensure enabled in Alltalk settings/config

OUTPUT_FORMAT = "wav" # Keep as WAV for generation, convert later if desired
# --- End Configuration ---


# --- Main Chunking Logic ---

#def split_text_into_chunks(text, char_combination_limit, token_split_limit, avg_chars_per_token_est):
def chunk_text(text, max_chunk_len=300):
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if len(current_chunk) + len(sentence) + 1 <= max_chunk_len:
            current_chunk += " " + sentence if current_chunk else sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

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

# --- Main Processing Function for a Chapter ---
# (process_chapter_file remains the same - calls updated split_text_into_chunks)
def process_chapter_file(text_filepath, final_audio_output_path):
    print(f"\n--- Processing Chapter File: {text_filepath} ---")
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, base_filename_no_ext)
    os.makedirs(chapter_temp_dir, exist_ok=True)
    print(f"  Using temporary directory for chunks: {chapter_temp_dir}")

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            full_text_content = f.read()
        if not full_text_content.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            try:
                if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
            except OSError: pass
            return True
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    # Call the updated splitting function
    text_chunks = chunk_text(full_text_content, CHUNK_CHAR_LIMIT)

    if not text_chunks:
        print("  No text chunks generated after splitting.")
        if full_text_content.strip(): # Only try to remove dir if original text was not empty
            try:
                if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
            except OSError: pass
        return False

    all_chunks_acquired = True
    local_chunk_paths = []

    # Loop through chunks, call API, download
    for i, chunk_text in enumerate(text_chunks):
        chunk_num = i + 1
        chunk_output_basename = f"{base_filename_no_ext}_chunk_{chunk_num:03d}"
        local_chunk_filepath = os.path.join(chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")

        print(f"\n  Processing Chunk {chunk_num}/{len(text_chunks)} (Expected local file: {os.path.basename(local_chunk_filepath)})...")

        if os.path.exists(local_chunk_filepath) and os.path.getsize(local_chunk_filepath) > 100:
            print(f"    Found existing local chunk: {os.path.basename(local_chunk_filepath)}. Skipping generation/download.")
            local_chunk_paths.append(local_chunk_filepath)
            continue

        if not chunk_text: # Should be filtered by split_text_into_chunks now, but double check
             print(f"    Warning: Skipping empty chunk_text for chunk {chunk_num}.")
             continue

        payload = {
            "text_input": chunk_text,
            "character_voice_gen": XTTS_SPEAKER_WAV,
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API,
            "rvccharacter_pitch": RVC_PITCH,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_output_basename
        }

        print(f"    Local chunk not found. Requesting generation from API...")
        # Print summary to avoid huge logs if chunk_text is long
        print(f"    Payload Summary: {{'text_input_len': {len(chunk_text)}, est_tokens: {_estimate_tokens(chunk_text)}, "
              f"'char_voice': '{os.path.basename(payload['character_voice_gen'])}', "
              f"'rvc_voice': '{payload['rvccharacter_voice_gen']}', ...}}")

        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=600) # Increased timeout just in case
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            print(f"    API Response Status Code: {response.status_code}")
            response_data = response.json()
            # print(f"    API Response JSON: {response_data}") # Can be verbose

            if isinstance(response_data, dict) and 'output_file_url' in response_data and response_data['output_file_url']:
                chunk_relative_url = response_data['output_file_url']
                print(f"    API reports SUCCESS for chunk {chunk_num}.")# URL: {chunk_relative_url}")
                if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_chunk_filepath):
                    local_chunk_paths.append(local_chunk_filepath)
                else:
                    print(f"    FAILED to download newly generated chunk {chunk_num}.")
                    all_chunks_acquired = False; break
            else:
                 print(f"    API did not return a valid 'output_file_url' for chunk {chunk_num}.")
                 if isinstance(response_data, dict):
                      error_msg = response_data.get('error') or response_data.get('status') or response_data.get('message')
                      if error_msg: print(f"      API Error/Status: {error_msg}")
                      else: print(f"      API Response content (abbreviated): {str(response_data)[:200]}...")
                 all_chunks_acquired = False; break

        except requests.exceptions.Timeout:
            print(f"    Error: Request timed out for chunk {chunk_num}.")
            all_chunks_acquired = False; break
        except requests.exceptions.HTTPError as http_err:
            # Specific handling for HTTP errors (like the 500 we saw)
            print(f"    HTTP error occurred for chunk {chunk_num}: {http_err}")
            if http_err.response is not None:
                 print(f"      API Response Status Code: {http_err.response.status_code}")
                 try:
                      # Try to print specific error from AllTalk if available
                      response_json = http_err.response.json()
                      error_detail = response_json.get('detail') or response_json.get('error') or str(response_json)
                      print(f"      API Error Detail: {error_detail[:500]}...")
                 except Exception: # If response is not JSON or other error
                      try:
                          print(f"      API Response Text: {http_err.response.text[:500]}...")
                      except Exception:
                          print("      Could not get specific error details from API response.")
            # Log the text that caused the error if possible
            print(f"      Problematic Text Chunk (approx {len(chunk_text)} chars, est. {_estimate_tokens(chunk_text)} tokens):\n      '{chunk_text[:250]}...'")
            all_chunks_acquired = False; break
        except requests.exceptions.RequestException as req_err:
            print(f"    Request error occurred for chunk {chunk_num}: {req_err}")
            all_chunks_acquired = False; break
        except Exception as e:
            print(f"    An unexpected error occurred processing chunk {chunk_num}: {e}")
            import traceback
            traceback.print_exc()
            all_chunks_acquired = False; break

        delay = 1
        print(f"    Pausing for {delay} second(s)...")
        time.sleep(delay)
        # --- End Chunk Loop ---

    # Concatenate and Cleanup
    if all_chunks_acquired and len(local_chunk_paths) == len(text_chunks):
        # Extra check: ensure expected number of chunks matches validated local paths
        existing_chunk_paths = [p for p in local_chunk_paths if os.path.exists(p) and os.path.getsize(p) > 100]
        if len(existing_chunk_paths) != len(text_chunks):
             print(f"  Error: Mismatch after processing. Expected {len(text_chunks)} chunks, validated {len(existing_chunk_paths)} files. Cannot concatenate.")
             return False

        if concatenate_audio_chunks(existing_chunk_paths, final_audio_output_path):
            print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
            try:
                print(f"  Attempting to clean up temporary directory: {chapter_temp_dir}")
                shutil.rmtree(chapter_temp_dir)
                print(f"  Cleaned up temporary directory successfully.")
            except Exception as e:
                print(f"  Warning: Failed to clean up temporary directory {chapter_temp_dir}: {e}")
            return True
        else:
            print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---")
            print(f"      Chunks remain in: {chapter_temp_dir}")
            return False
    else:
        reason = "Unknown processing error"
        if not all_chunks_acquired:
             reason = "Error during API call/download"
        elif len(local_chunk_paths) != len(text_chunks):
             reason = f"Mismatch: Expected {len(text_chunks)}, Got {len(local_chunk_paths)} paths"
        print(f"--- Chapter File Processing FAILED ({reason}): {text_filepath} ---")
        print(f"      Temporary chunks (if any) remain in: {chapter_temp_dir}")
        return False
# --- End Function process_chapter_file ---


# --- Main Execution Logic ---
# (Main block remains the same)
if __name__ == "__main__":
    # ... (Setup checks remain the same) ...
    if not os.path.exists(TEMP_CHUNK_DIR): os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.isdir(TEXT_FILES_DIR): print(f"Error: Input directory not found: {TEXT_FILES_DIR}"); exit()
    if not os.path.exists(XTTS_SPEAKER_WAV): print(f"Error: XTTS Speaker WAV not found: {XTTS_SPEAKER_WAV}"); exit()
    # ... (RVC Check) ...
    text_files = glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))
    if not text_files: print(f"No .txt files found in {TEXT_FILES_DIR}"); exit()
    if not os.path.exists(AUDIO_OUTPUT_DIR): os.makedirs(AUDIO_OUTPUT_DIR)

    print(f"\nFound {len(text_files)} text files to process.")
    print(f"Targeting API: {ALLTALK_API_URL}")
    print(f"--- Using Endpoint: {ALLTALK_API_URL} (Requires Text Splitting & Local Concatenation) ---")
    print(f"--- Chunking Params: Combine Chars <= {CHUNK_CHAR_LIMIT}, Split Tokens <= {TOKEN_LIMIT} (using {AVG_CHARS_PER_TOKEN} chars/token est.) ---") # Updated info line
    print(f"--- Sending RVC parameters directly. ---")
    if not PYDUB_AVAILABLE: print(f"--- !!! WARNING: pydub not installed. Concatenation/Format Export may fail. !!! ---")

    chapters_processed = 0
    chapters_failed = 0

    for text_file_path in sorted(text_files):
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0]
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")

        if os.path.exists(final_output_audio_path):
            print(f"\nSkipping chapter: Final audio file already exists at {final_output_audio_path}")
            chapters_processed += 1
            continue

        if process_chapter_file(text_file_path, final_output_audio_path):
            chapters_processed += 1
        else:
            # Optional: Add more details on failure? process_chapter_file prints reasons.
            chapters_failed += 1
            exit(1)

        # Optional: Add a slightly longer delay if server seems overloaded?
        chapter_delay = 0.1 # Reduced delay slightly if things are working
        print(f"\nPausing for {chapter_delay} seconds before next chapter...")
        time.sleep(chapter_delay)

    print(f"\n--- Processing Complete ---")
    print(f"Chapters attempted: {chapters_processed + chapters_failed}")
    print(f"Chapters successfully processed: {chapters_processed}")
    print(f"Chapters failed: {chapters_failed}")
    if chapters_failed > 0:
         print(f"  (Check logs for chapters that failed. Temporary files might remain in '{TEMP_CHUNK_DIR}')")
    print(f"\nGenerated audio files saved in: {AUDIO_OUTPUT_DIR}")
