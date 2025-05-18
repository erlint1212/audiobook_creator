import requests
import os
import glob
import time
import math
import re
import shutil
from urllib.parse import urljoin

import nltk
import os

# --- NLTK 'punkt' Setup ---
NLTK_SETUP_SUCCESSFUL = False
try:
    print("Attempting to use nltk.sent_tokenize to check 'punkt' status...")
    # Test with a simple sentence to force loading of language-specific parts
    nltk.sent_tokenize("This is a test. This is another test.")
    print("NLTK 'punkt' and its components seem to be available and working.")
    NLTK_SETUP_SUCCESSFUL = True
except LookupError as e:
    print(f"NLTK LookupError: {e}")
    print("This usually means 'punkt' or a sub-component like 'punkt_tab' is missing.")
    print("Attempting to download NLTK 'punkt' resource (this may take a moment)...")
    try:
        # Download with more verbosity and allow NLTK to choose the best download directory
        nltk.download('punkt', quiet=False) # Set quiet=False for more download output
        print("'punkt' download process finished.")
        print("Re-checking 'punkt' availability...")
        # Try to use it again immediately after download attempt
        nltk.sent_tokenize("This is a test. This is another test.")
        print("NLTK 'punkt' is now available and working after download.")
        NLTK_SETUP_SUCCESSFUL = True
    except Exception as download_e:
        print(f"An error occurred during 'punkt' download or re-check: {download_e}")
        print("\nMANUAL ACTION REQUIRED:")
        print("1. Open a Python console in your 'web_scraper_2' Conda environment.")
        print("2. Type the following commands:")
        print("   >>> import nltk")
        print("   >>> nltk.download('punkt')")
        print("3. If the downloader GUI appears, select 'punkt' and download it.")
        print("4. Ensure it downloads without errors. Note the download location.")
        print("5. If problems persist, you might need to manually clear NLTK data directories")
        print("   (e.g., C:\\Users\\etnor\\AppData\\Roaming\\nltk_data\\tokenizers\\punkt*) and try the manual download again.")
except Exception as general_e:
    print(f"An unexpected error occurred during NLTK setup: {general_e}")

if not NLTK_SETUP_SUCCESSFUL:
    print("\nNLTK 'punkt' setup failed. This resource is essential for sentence tokenization.")
    print("Please resolve the NLTK 'punkt' issue manually and then re-run the script.")
    exit(1)

from nltk.tokenize import sent_tokenize # Now safe to import if NLTK_SETUP_SUCCESSFUL is True
# --- End NLTK 'punkt' Setup ---

# --- Try importing pydub ---
try:
    from pydub import AudioSegment
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

TEXT_FILES_DIR = "scraped_IATMCB_celsetial_pavilion"
AUDIO_OUTPUT_DIR = "generated_audio_IATMCB"
TEMP_CHUNK_DIR = "temp_audio_chunks"

CHAPTER_STOP = 500


# TOKEN_LIMIT should be less than XTTS's strict 400 to allow for estimation inaccuracies.
# 350 is a good starting point, giving a 50 token buffer.
TOKEN_LIMIT = 300
# Average characters per token estimate. Adjust based on your text if needed.
# For English, 3-4 is common. A lower value (e.g., 2.5 or 3) makes the estimation more
# conservative, leading to potentially smaller chunks but safer against hitting the token limit.
AVG_CHARS_PER_TOKEN = 3.0 # Using a float for potentially more precision if desired

# Initial paragraph combination limit (less critical now that token limit is primary)
# This can help group related sentences from the same paragraph before token splitting.
PARAGRAPH_COMBINE_CHAR_LIMIT = 1100 # Characters

# --- Paths/Values needed by the Alltalk SERVER ---
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav"
XTTS_LANGUAGE = "en"
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_MODEL_NAME_FOR_API = 'half_light\\half_light.pth' # Make sure this matches Alltalk's expectation
RVC_PITCH = 0
USE_DEEPSPEED = True

OUTPUT_FORMAT = "wav"
# --- End Configuration ---


# --- Helper Functions ---

def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    """Estimates the number of tokens in a piece of text."""
    if not text: return 0
    # Ensure avg_chars_per_token is positive to avoid division by zero
    effective_avg_chars = max(1.0, avg_chars_per_token) # Use 1.0 as an absolute minimum
    return math.ceil(len(text) / effective_avg_chars)

def _split_long_text_char_fallback(text_to_split, target_token_limit, avg_chars_per_token):
    """
    Fallback: Splits text based on character estimates for token limit.
    Tries to break at spaces for slightly cleaner splits.
    """
    if not text_to_split: return []
    sub_chunks = []
    current_pos = 0
    text_len = len(text_to_split)
    # Calculate a hard character limit per sub-chunk based on token limit
    hard_char_limit = max(1, int(target_token_limit * avg_chars_per_token))

    while current_pos < text_len:
        end_pos = min(current_pos + hard_char_limit, text_len)
        # Try to find a space to break at, for slightly cleaner char breaks
        # Look for the last space within the ideal chunk [current_pos, end_pos]
        # If no space, or the only space is too far back (e.g. very long word), take the hard_char_limit
        actual_end_pos = text_to_split.rfind(" ", current_pos, end_pos)

        # If no space is found in the range, or if breaking at the space makes the chunk too small
        # (e.g. long word at start), then just cut at hard_char_limit.
        # A simple heuristic: if the found space is in the first half of the potential hard_char_limit slice,
        # and the slice is already near hard_char_limit, prefer the hard cut.
        # More simply: if no space, or if the character slice is short anyway, use end_pos.
        if actual_end_pos == -1 or (end_pos - actual_end_pos > hard_char_limit * 0.75 and end_pos - current_pos < hard_char_limit * 0.5) :
            actual_end_pos = end_pos
        elif actual_end_pos <= current_pos: # Ensure forward progress if rfind result is before current_pos
             actual_end_pos = end_pos


        chunk = text_to_split[current_pos:actual_end_pos].strip()
        if chunk:
            sub_chunks.append(chunk)

        if actual_end_pos == current_pos : # Prevent infinite loop if no progress is made
            # This might happen if hard_char_limit is very small or due to unusual text.
            # Force progress by taking at least one char or the rest of the string.
            remaining_text = text_to_split[current_pos:].strip()
            if remaining_text:
                sub_chunks.append(remaining_text)
            break
        current_pos = actual_end_pos

    return [c for c in sub_chunks if c]


# --- Main Chunking Logic (Reinstating Token-Aware Splitting) ---

def split_text_for_tts(text_content, paragraph_char_limit, token_limit_per_chunk, avg_chars_token_est):
    """
    Splits text into chunks suitable for TTS, prioritizing full sentences and respecting token limits.
    1. Splits text into paragraphs (based on '\n\n').
    2. Combines adjacent small paragraphs if they fit within paragraph_char_limit.
    3. For each resulting paragraph/segment:
        a. Splits into sentences using NLTK.
        b. Combines sentences into chunks, ensuring each chunk is <= token_limit_per_chunk.
        c. If a single sentence exceeds token_limit_per_chunk, it's split using a character-based fallback.
    """
    final_tts_chunks = []
    if not text_content or not text_content.strip():
        return final_tts_chunks

    # Phase 1: Combine paragraphs based on character limit (less critical but can group related short paragraphs)
    raw_paragraphs = text_content.split('\n\n')
    intermediate_segments = []
    current_segment = ""
    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        if not current_segment:
            current_segment = para
        else:
            if len(current_segment) + len(para) + 2 <= paragraph_char_limit: # +2 for '\n\n'
                current_segment += "\n\n" + para # Retain paragraph structure if combining
            else:
                intermediate_segments.append(current_segment)
                current_segment = para
    if current_segment:
        intermediate_segments.append(current_segment)

    # Phase 2: Process each segment for token limit using sentences
    for segment in intermediate_segments:
        sentences = sent_tokenize(segment)
        if not sentences:
            continue

        current_chunk_sentences_list = []
        current_chunk_tokens = 0

        for sentence_text in sentences:
            sentence_text = sentence_text.strip()
            if not sentence_text:
                continue

            estimated_sentence_tokens = _estimate_tokens(sentence_text, avg_chars_token_est)

            if estimated_sentence_tokens > token_limit_per_chunk:
                # This single sentence is too long. Add any accumulated chunk first.
                if current_chunk_sentences_list:
                    final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                    current_chunk_sentences_list = []
                    current_chunk_tokens = 0
                
                # Split this oversized sentence using character-based fallback
                print(f"    Warning: Sentence (length {len(sentence_text)} chars, est. {estimated_sentence_tokens} tokens) "
                      f"exceeds token limit ({token_limit_per_chunk}). Using character fallback split.")
                char_split_sub_chunks = _split_long_text_char_fallback(sentence_text, token_limit_per_chunk, avg_chars_token_est)
                final_tts_chunks.extend(char_split_sub_chunks) # Add all sub-parts
            
            elif current_chunk_tokens + estimated_sentence_tokens <= token_limit_per_chunk:
                # Sentence fits into the current chunk
                current_chunk_sentences_list.append(sentence_text)
                current_chunk_tokens += estimated_sentence_tokens
                # Add a small token count for the space if it's not the first sentence in chunk
                if len(current_chunk_sentences_list) > 1:
                    current_chunk_tokens += _estimate_tokens(" ", avg_chars_token_est)
            else:
                # Sentence does not fit. Finalize the current chunk.
                if current_chunk_sentences_list:
                    final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                
                # Start a new chunk with the current sentence
                current_chunk_sentences_list = [sentence_text]
                current_chunk_tokens = estimated_sentence_tokens

        # Add any remaining accumulated chunk
        if current_chunk_sentences_list:
            final_tts_chunks.append(" ".join(current_chunk_sentences_list))

    # Final filter for any potentially empty chunks
    final_tts_chunks = [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]
    
    print(f"  Split text into {len(final_tts_chunks)} final TTS chunks (Token Limit: {token_limit_per_chunk}, Avg Chars/Token: {avg_chars_token_est}).")
    return final_tts_chunks


# --- Audio Download and Concatenation Functions (largely unchanged) ---
def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    try:
        if relative_audio_url.startswith('/'):
            full_url = f"{server_base_url.rstrip('/')}{relative_audio_url}"
        else:
            full_url = urljoin(server_base_url.rstrip('/') + "/", relative_audio_url)

        print(f"    Downloading chunk: {full_url}")
        response = requests.get(full_url, stream=True, timeout=180)
        response.raise_for_status()
        with open(local_temp_path, 'wb') as f:
            for chunk_data in response.iter_content(chunk_size=8192):
                f.write(chunk_data)
        return True
    except Exception as e:
        print(f"    Error downloading {relative_audio_url}: {e}")
        return False

def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    if not PYDUB_AVAILABLE:
        print("  Error: pydub library not available. Cannot concatenate audio.")
        return False
    if not chunk_filepaths:
        print("  Error: No audio chunk files provided for concatenation.")
        return False
    
    print(f"  Concatenating {len(chunk_filepaths)} audio chunks...")
    combined = AudioSegment.empty()
    valid_chunk_files_processed = 0

    for filepath in chunk_filepaths:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 100: # Basic check for validity
            try:
                segment = AudioSegment.from_wav(filepath)
                combined += segment
                valid_chunk_files_processed +=1
            except FileNotFoundError:
                 print(f"    Error: Chunk file not found during concatenation: {filepath}. Skipping.")
            except CouldntDecodeError:
                 print(f"    Error: Could not decode chunk file (possibly corrupt/empty): {filepath}. Skipping.")
            except Exception as e:
                 print(f"    Error loading/processing chunk {filepath}: {e}. Skipping.")
        else:
            print(f"    Warning: Skipping invalid/empty chunk file during concatenation: {filepath}")

    if valid_chunk_files_processed == 0: # if no chunks were actually loaded
        print("  Error: No valid audio chunks were successfully processed for concatenation.")
        return False
    
    if len(combined) > 0:
        output_dir = os.path.dirname(final_output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        try:
            combined.export(final_output_path, format="wav") # Assuming OUTPUT_FORMAT is "wav"
            print(f"  Concatenated audio saved successfully to: {final_output_path}")
            return True
        except Exception as export_e:
            print(f"  Error exporting combined audio: {export_e}")
            return False
    else:
        print("  Error: Combined audio is empty after attempting to process chunks (all chunks might have been invalid or empty).")
        return False

# --- Main Processing Function for a Chapter ---
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
            try: # Try to clean up empty temp dir
                if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
            except OSError: pass
            return True # Consider this a "success" for an empty file
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    # Use the new token-aware splitting function
    text_chunks = split_text_for_tts(full_text_content, PARAGRAPH_COMBINE_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)

    if not text_chunks:
        print("  No text chunks generated after splitting.")
        # if full_text_content.strip(): # Only remove dir if text was not empty initially
        #     try:
        #         if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
        #     except OSError: pass
        return False # If no chunks from non-empty text, it's a failure

    all_chunks_acquired = True
    local_chunk_paths = []

    for i, chunk_text_content in enumerate(text_chunks): # Renamed variable for clarity
        chunk_num = i + 1
        # Sanitize base_filename_no_ext further to remove problematic chars for output_file_name
        sanitized_base_for_api = re.sub(r'[^\w_.-]', '_', base_filename_no_ext)
        chunk_output_basename = f"{sanitized_base_for_api}_chunk_{chunk_num:03d}"
        local_chunk_filepath = os.path.join(chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")

        # Estimate tokens for the current chunk for logging/debugging
        current_chunk_estimated_tokens = _estimate_tokens(chunk_text_content, AVG_CHARS_PER_TOKEN)
        print(f"\n  Processing Chunk {chunk_num}/{len(text_chunks)} (Length: {len(chunk_text_content)} chars, Est. Tokens: {current_chunk_estimated_tokens})")
        if current_chunk_estimated_tokens > TOKEN_LIMIT + 50: # +50 is a buffer for API's own counting
             print(f"    POTENTIAL ISSUE: Estimated tokens ({current_chunk_estimated_tokens}) significantly exceed TOKEN_LIMIT ({TOKEN_LIMIT}). API might reject or truncate.")


        if os.path.exists(local_chunk_filepath) and os.path.getsize(local_chunk_filepath) > 100:
            print(f"    Found existing valid local chunk: {os.path.basename(local_chunk_filepath)}. Skipping generation.")
            local_chunk_paths.append(local_chunk_filepath)
            continue

        if not chunk_text_content:
             print(f"    Warning: Skipping empty chunk_text_content for chunk {chunk_num}.")
             continue

        if len(chunk_text_content) < 2:
            chunk_text_content = "....."

        payload = {
            "text_input": chunk_text_content,
            "character_voice_gen": XTTS_SPEAKER_WAV,
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API,
            "rvccharacter_pitch": RVC_PITCH,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_output_basename # API will add .wav
        }

        print(f"    Requesting generation from API...")
        # print(f"    Payload Summary: {{'text_input': '{chunk_text_content[:70]}...', ...}}") # More useful summary

        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=600)
            response.raise_for_status()

            # print(f"    API Response Status Code: {response.status_code}")
            response_data = response.json()

            if isinstance(response_data, dict) and 'output_file_url' in response_data and response_data['output_file_url']:
                chunk_relative_url = response_data['output_file_url']
                # print(f"    API reports SUCCESS. URL: {chunk_relative_url}")
                if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_chunk_filepath):
                    local_chunk_paths.append(local_chunk_filepath)
                else:
                    print(f"    FAILED to download newly generated chunk {chunk_num}.")
                    all_chunks_acquired = False; break
            else:
                 print(f"    API did not return a valid 'output_file_url' for chunk {chunk_num}.")
                 if isinstance(response_data, dict):
                      error_msg = response_data.get('error') or response_data.get('status') or response_data.get('message') or response_data.get('detail')
                      if error_msg: print(f"      API Error/Status: {error_msg}")
                      else: print(f"      API Response content (abbreviated): {str(response_data)[:200]}...")
                 all_chunks_acquired = False; break

        except requests.exceptions.Timeout:
            print(f"    Error: Request timed out for chunk {chunk_num}.")
            all_chunks_acquired = False; break
        except requests.exceptions.HTTPError as http_err:
            print(f"    HTTP error occurred for chunk {chunk_num}: {http_err}")
            if http_err.response is not None:
                 print(f"      API Response Status Code: {http_err.response.status_code}")
                 try:
                      response_json = http_err.response.json()
                      error_detail = response_json.get('detail') or response_json.get('error') or str(response_json)
                      print(f"      API Error Detail: {error_detail[:500]}...")
                 except Exception:
                      try:
                          print(f"      API Response Text: {http_err.response.text[:500]}...")
                      except Exception:
                          print("      Could not get specific error details from API response.")
            print(f"      Problematic Text (approx {len(chunk_text_content)} chars, est. {current_chunk_estimated_tokens} tokens):\n      '{chunk_text_content[:150]}...'")
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
        # print(f"    Pausing for {delay} second(s)...") # Can be noisy
        time.sleep(delay)

    if all_chunks_acquired and len(local_chunk_paths) > 0 and len(local_chunk_paths) == len(text_chunks):
        if concatenate_audio_chunks(local_chunk_paths, final_audio_output_path):
            print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
            try:
                # print(f"  Attempting to clean up temporary directory: {chapter_temp_dir}")
                shutil.rmtree(chapter_temp_dir)
                # print(f"  Cleaned up temporary directory successfully.")
            except Exception as e:
                print(f"  Warning: Failed to clean up temporary directory {chapter_temp_dir}: {e}")
            return True
        else:
            print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---")
            print(f"      Chunks remain in: {chapter_temp_dir}")
            return False
    elif not text_chunks and not full_text_content.strip(): # Original file was empty
        return True # Considered processed successfully
    else:
        reason = "Unknown processing error or not all chunks acquired."
        if not all_chunks_acquired:
             reason = "Error during API call/download for one or more chunks."
        elif len(local_chunk_paths) != len(text_chunks):
             reason = f"Mismatch: Expected {len(text_chunks)} TTS chunks, but only got {len(local_chunk_paths)} audio files."
        print(f"--- Chapter File Processing FAILED ({reason}): {text_filepath} ---")
        print(f"      Temporary chunks (if any) remain in: {chapter_temp_dir}")
        return False

# --- Main Execution Logic ---
if __name__ == "__main__":
    if not os.path.exists(TEMP_CHUNK_DIR):
        os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.isdir(TEXT_FILES_DIR):
        print(f"Error: Input directory not found: {TEXT_FILES_DIR}")
        exit(1)
    if not os.path.exists(XTTS_SPEAKER_WAV):
        print(f"Error: XTTS Speaker WAV not found: {XTTS_SPEAKER_WAV}")
        exit(1)
    if not os.path.exists(RVC_MODEL_PATH): # Check if RVC model file itself exists
        print(f"Warning: RVC Model Path not found: {RVC_MODEL_PATH}. RVC will likely fail if enabled in Alltalk.")

    text_files = sorted(glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))) # Ensure sorted processing
    if not text_files:
        print(f"No .txt files found in {TEXT_FILES_DIR}")
        exit(1)
    if not os.path.exists(AUDIO_OUTPUT_DIR):
        os.makedirs(AUDIO_OUTPUT_DIR)

    print(f"\nFound {len(text_files)} text files to process from '{TEXT_FILES_DIR}'.")
    print(f"Targeting API: {ALLTALK_API_URL}")
    print(f"--- Chunking Params: Target Token Limit <= {TOKEN_LIMIT} (using {AVG_CHARS_PER_TOKEN} chars/token est.) ---")
    print(f"--- Initial Paragraph Combine Char Limit: {PARAGRAPH_COMBINE_CHAR_LIMIT} ---")
    if not PYDUB_AVAILABLE:
        print(f"--- !!! WARNING: pydub not installed. Concatenation/Format Export will fail. !!! ---")

    total_chapters = len(text_files)
    chapters_succeeded = 0
    chapters_failed_processing = 0

    for idx, text_file_path in enumerate(text_files):
        print(f"\n{'='*10} Processing Chapter {idx + 1}/{total_chapters}: {os.path.basename(text_file_path)} {'='*10}")
        if (idx + 1) >= CHAPTER_STOP:
            exit(1)
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0]
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")

        if os.path.exists(final_output_audio_path): 
            print(f"Skipping chapter: Final audio file already exists and seems valid at {final_output_audio_path}")
            chapters_succeeded += 1
            continue

        if process_chapter_file(text_file_path, final_output_audio_path):
            chapters_succeeded += 1
        else:
            chapters_failed_processing += 1
            # Decide if you want to stop on first failure
            # exit_on_failure = True
            # if exit_on_failure:
            #     print("\nHalting script due to chapter processing failure.")
            #     exit(1)

        # chapter_delay = 0.1
        # if chapter_delay > 0: time.sleep(chapter_delay) # No need for delay if requests are sequential

    print(f"\n--- Processing Complete ---")
    print(f"Total Chapters Found: {total_chapters}")
    print(f"Chapters Successfully Processed/Skipped: {chapters_succeeded}")
    print(f"Chapters Failed During Processing: {chapters_failed_processing}")
    if chapters_failed_processing > 0:
         print(f"  (Check logs for chapters that failed. Temporary files might remain in '{TEMP_CHUNK_DIR}')")
    print(f"\nGenerated audio files should be in: {AUDIO_OUTPUT_DIR}")
