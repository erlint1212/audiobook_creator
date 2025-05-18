import requests
import os
import glob
import time
import math
import re
import shutil
from urllib.parse import urljoin

import nltk
# import os # Already imported

# --- NLTK 'punkt' Setup ---
NLTK_SETUP_SUCCESSFUL = False
try:
    print("Attempting to use nltk.sent_tokenize to check 'punkt' status...")
    nltk.sent_tokenize("This is a test. This is another test.")
    print("NLTK 'punkt' and its components seem to be available and working.")
    NLTK_SETUP_SUCCESSFUL = True
except LookupError as e:
    print(f"NLTK LookupError: {e}")
    print("Attempting to download NLTK 'punkt' resource...")
    try:
        nltk.download('punkt', quiet=False)
        print("'punkt' download process finished.")
        nltk.sent_tokenize("This is a test. This is another test.")
        print("NLTK 'punkt' is now available and working after download.")
        NLTK_SETUP_SUCCESSFUL = True
    except Exception as download_e:
        print(f"An error occurred during 'punkt' download or re-check: {download_e}")
        # (Manual instructions retained from original script but usually not needed if download works)
except Exception as general_e:
    print(f"An unexpected error occurred during NLTK setup: {general_e}")

if not NLTK_SETUP_SUCCESSFUL:
    print("\nNLTK 'punkt' setup failed. Please resolve manually.")
    exit(1)

from nltk.tokenize import sent_tokenize
# --- End NLTK 'punkt' Setup ---

# --- Try importing pydub ---
try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError
    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub library not found. Audio chunk concatenation will not work.")
    PYDUB_AVAILABLE = False
# ---------------------------

# --- Configuration ---
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate"
ALLTALK_BASE_URL = "http://127.0.0.1:7851"

TEXT_FILES_DIR = "annotated_IATMCB_for_tts" 
AUDIO_OUTPUT_DIR = "generated_audio_IATMCB_annotated"
TEMP_CHUNK_DIR = "temp_audio_chunks"

TOKEN_LIMIT = 350
AVG_CHARS_PER_TOKEN = 3.0
PARAGRAPH_COMBINE_CHAR_LIMIT = 1100

XTTS_LANGUAGE = "en"
RVC_MODEL_PATH_LOCAL_CHECK = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_MODEL_NAME_FOR_API = 'half_light/half_light.pth' 
RVC_PITCH = 0
OUTPUT_FORMAT = "wav"

VOICES_BASE_PATH_ON_SERVER = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/" 

HALF_LIGHT_STYLES = {
    # "HL_Neutral_Narrative": os.path.join(VOICES_BASE_PATH_ON_SERVER, "Half_Light_Disco_Elysium.wav"),
    "HL_Neutral_Narrative": os.path.join(VOICES_BASE_PATH_ON_SERVER, "half_light_styles/HL_Neutral_Narrative.wav"),
    "HL_Weary_Cynical": os.path.join(VOICES_BASE_PATH_ON_SERVER, "half_light_styles/HL_Weary_Cynical.wav"),
    "HL_Internal_Thoughtful": os.path.join(VOICES_BASE_PATH_ON_SERVER, "half_light_styles/HL_Internal_Thoughtful.wav"),
    "HL_Intense_Strained": os.path.join(VOICES_BASE_PATH_ON_SERVER, "half_light_styles/HL_Intense_Strained.wav"),
    "HL_Slightly_Unhinged_Insight": os.path.join(VOICES_BASE_PATH_ON_SERVER, "half_light_styles/HL_Slightly_Unhinged_Insight.wav"),
    "DEFAULT_STYLE": os.path.join(VOICES_BASE_PATH_ON_SERVER, "Half_Light_Disco_Elysium.wav")
}

for style, path in HALF_LIGHT_STYLES.items():
    if not os.path.exists(path):
        print(f"WARNING: Local check: Reference audio for style '{style}' not found at: {path}")
        if style != "DEFAULT_STYLE" and not os.path.exists(HALF_LIGHT_STYLES["DEFAULT_STYLE"]):
             print(f"ERROR: Default style audio also missing. Critical error. Exiting.")
             exit(1)
        elif style != "DEFAULT_STYLE":
             print(f"         Will fallback to DEFAULT_STYLE if '{style}' is requested and server can't find it.")

STYLE_ANNOTATION_RE = re.compile(r"^\s*\[([A-Za-z0-9_]+)\]\s*(.*)") # Allow leading spaces before tag
# --- End Configuration ---


# --- Helper Functions ( Largely Unchanged) ---
def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    if not text: return 0
    effective_avg_chars = max(1.0, avg_chars_per_token)
    return math.ceil(len(text) / effective_avg_chars)

def _split_long_text_char_fallback(text_to_split, target_token_limit, avg_chars_per_token):
    if not text_to_split: return []
    sub_chunks = []
    current_pos = 0
    text_len = len(text_to_split)
    hard_char_limit = max(1, int(target_token_limit * avg_chars_per_token))
    while current_pos < text_len:
        end_pos = min(current_pos + hard_char_limit, text_len)
        actual_end_pos = text_to_split.rfind(" ", current_pos, end_pos)
        if actual_end_pos == -1 or (end_pos - actual_end_pos > hard_char_limit * 0.75 and end_pos - current_pos < hard_char_limit * 0.5) :
            actual_end_pos = end_pos
        elif actual_end_pos <= current_pos:
             actual_end_pos = end_pos
        chunk = text_to_split[current_pos:actual_end_pos].strip()
        if chunk: sub_chunks.append(chunk)
        if actual_end_pos == current_pos :
            remaining_text = text_to_split[current_pos:].strip()
            if remaining_text: sub_chunks.append(remaining_text)
            break
        current_pos = actual_end_pos
    return [c for c in sub_chunks if c]

def split_text_for_tts(text_content, paragraph_char_limit, token_limit_per_chunk, avg_chars_token_est):
    final_tts_chunks = []
    if not text_content or not text_content.strip(): return final_tts_chunks
    raw_paragraphs = text_content.split('\n\n')
    intermediate_segments = []
    current_segment = ""
    for para in raw_paragraphs:
        para = para.strip()
        if not para: continue
        if not current_segment: current_segment = para
        else:
            if len(current_segment) + len(para) + 2 <= paragraph_char_limit:
                current_segment += "\n\n" + para
            else:
                intermediate_segments.append(current_segment)
                current_segment = para
    if current_segment: intermediate_segments.append(current_segment)
    for segment in intermediate_segments:
        sentences = sent_tokenize(segment)
        if not sentences: continue
        current_chunk_sentences_list = []
        current_chunk_tokens = 0
        for sentence_text in sentences:
            sentence_text = sentence_text.strip()
            if not sentence_text: continue
            estimated_sentence_tokens = _estimate_tokens(sentence_text, avg_chars_token_est)
            if estimated_sentence_tokens > token_limit_per_chunk:
                if current_chunk_sentences_list:
                    final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                    current_chunk_sentences_list = []; current_chunk_tokens = 0
                print(f"    Warning: Sentence (len {len(sentence_text)}, est. {estimated_sentence_tokens} tokens) "
                      f"exceeds limit ({token_limit_per_chunk}). Using char fallback.")
                char_split_sub_chunks = _split_long_text_char_fallback(sentence_text, token_limit_per_chunk, avg_chars_token_est)
                final_tts_chunks.extend(char_split_sub_chunks)
            elif current_chunk_tokens + estimated_sentence_tokens <= token_limit_per_chunk:
                current_chunk_sentences_list.append(sentence_text)
                current_chunk_tokens += estimated_sentence_tokens
                if len(current_chunk_sentences_list) > 1: current_chunk_tokens += _estimate_tokens(" ", avg_chars_token_est)
            else:
                if current_chunk_sentences_list: final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                current_chunk_sentences_list = [sentence_text]
                current_chunk_tokens = estimated_sentence_tokens
        if current_chunk_sentences_list: final_tts_chunks.append(" ".join(current_chunk_sentences_list))
    final_tts_chunks = [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]
    return final_tts_chunks

def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    try:
        full_url = urljoin(server_base_url.rstrip('/') + "/", relative_audio_url.lstrip('/'))
        print(f"    Downloading chunk: {full_url}")
        response = requests.get(full_url, stream=True, timeout=180)
        response.raise_for_status()
        with open(local_temp_path, 'wb') as f:
            for chunk_data in response.iter_content(chunk_size=8192): f.write(chunk_data)
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
        if os.path.exists(filepath) and os.path.getsize(filepath) > 100:
            try:
                segment = AudioSegment.from_wav(filepath)
                combined += segment
                valid_chunk_files_processed +=1
            except Exception as e: print(f"    Error loading/processing chunk {filepath}: {e}. Skipping.")
        else: print(f"    Warning: Skipping invalid/empty chunk file during concatenation: {filepath}")
    if valid_chunk_files_processed == 0:
        print("  Error: No valid audio chunks were successfully processed.")
        return False
    if len(combined) > 0:
        output_dir = os.path.dirname(final_output_path)
        if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir)
        try:
            combined.export(final_output_path, format="wav")
            print(f"  Concatenated audio saved successfully to: {final_output_path}")
            return True
        except Exception as export_e:
            print(f"  Error exporting combined audio: {export_e}")
            return False
    else:
        print("  Error: Combined audio is empty after attempting to process chunks.")
        return False

# --- MODIFIED: Text Parsing Logic ---
def parse_annotated_text(full_text_content):
    """
    Parses text with style annotations, combining text under the same consecutive style.
    Yields tuples of (style_key, text_segment_for_that_style).
    """
    current_style_key = "DEFAULT_STYLE"
    current_segment_lines = []

    for line_raw in full_text_content.splitlines():
        match = STYLE_ANNOTATION_RE.match(line_raw) # Match includes potential leading spaces
        
        encountered_style_key = None
        text_on_tag_line = ""

        if match:
            potential_new_style_key = match.group(1)
            text_on_tag_line = match.group(2).strip() # Text after the tag on the same line

            if potential_new_style_key in HALF_LIGHT_STYLES:
                encountered_style_key = potential_new_style_key
            else:
                # This case means the regex matched a bracketed term, but it's not a known style.
                # Treat the whole line as content.
                print(f"    Info: Line '{line_raw[:50]}...' looks like a tag but '[{potential_new_style_key}]' is not a recognized style. Treating as content.")
                pass # Let it fall through to content appending logic

        if encountered_style_key:
            # A known style tag was found
            if encountered_style_key != current_style_key and current_segment_lines:
                # The style has changed, and we have buffered lines for the *previous* style.
                # Yield the collected segment for the previous style.
                yield (current_style_key, "\n".join(current_segment_lines).strip())
                current_segment_lines = [] # Reset buffer for the new style
            
            current_style_key = encountered_style_key # Update to the new current style

            if text_on_tag_line: # If there was text on the same line as the (new or same) tag
                current_segment_lines.append(text_on_tag_line)
        else:
            # This line is not a recognized style tag. It's content.
            # Append the line to the current segment if it's not just whitespace.
            # We use line_raw.strip() to check for content, but append line_raw to keep original spacing.
            if line_raw.strip(): 
                current_segment_lines.append(line_raw)
    
    # After the loop, yield any remaining buffered segment
    if current_segment_lines:
        yield (current_style_key, "\n".join(current_segment_lines).strip())


def process_chapter_file(text_filepath, final_audio_output_path):
    print(f"\n--- Processing Chapter File: {text_filepath} ---")
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, base_filename_no_ext)
    os.makedirs(chapter_temp_dir, exist_ok=True)
    print(f"  Using temporary directory for chunks: {chapter_temp_dir}")

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            full_text_content_annotated = f.read()
        if not full_text_content_annotated.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            try:
                if not os.listdir(chapter_temp_dir): os.rmdir(chapter_temp_dir)
            except OSError: pass
            return True
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    all_tts_requests = []
    for style_key, styled_text_segment in parse_annotated_text(full_text_content_annotated):
        if not styled_text_segment.strip(): # Skip if the segment for a style is empty
            print(f"  Skipping empty text segment for style: {style_key}")
            continue

        full_speaker_path = HALF_LIGHT_STYLES.get(style_key, HALF_LIGHT_STYLES["DEFAULT_STYLE"])
        speaker_wav_for_api = full_speaker_path # Assuming direct path access or correctly relative server paths
        # If paths in HALF_LIGHT_STYLES need to be made relative to VOICES_BASE_PATH_ON_SERVER for API:
        # try:
        #     server_base = os.path.join(VOICES_BASE_PATH_ON_SERVER, "") 
        #     speaker_wav_for_api = os.path.relpath(full_speaker_path, server_base).replace("\\", "/")
        # except ValueError:
        #     speaker_wav_for_api = os.path.basename(full_speaker_path) # Fallback if relpath fails
        
        print(f"  Segment for Style: {style_key} (using API speaker: '{speaker_wav_for_api}')")
        print(f"    Text (first 100 chars): '{styled_text_segment[:100].replace(chr(8203), '')}... total {len(styled_text_segment)} chars'")


        tts_chunks_for_style = split_text_for_tts(styled_text_segment, PARAGRAPH_COMBINE_CHAR_LIMIT, TOKEN_LIMIT, AVG_CHARS_PER_TOKEN)
        for chunk in tts_chunks_for_style:
            all_tts_requests.append((chunk, speaker_wav_for_api))

    if not all_tts_requests:
        print("  No valid TTS requests generated after parsing and splitting.")
        return False

    all_chunks_acquired = True
    local_chunk_paths = []
    total_api_requests = len(all_tts_requests)

    for i, (chunk_text_content, current_speaker_wav_for_api) in enumerate(all_tts_requests):
        chunk_num_overall = i + 1
        sanitized_base_for_api = re.sub(r'[^\w_.-]', '_', base_filename_no_ext)
        chunk_output_basename = f"{sanitized_base_for_api}_chunk_{chunk_num_overall:03d}"
        local_chunk_filepath = os.path.join(chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")
        current_chunk_estimated_tokens = _estimate_tokens(chunk_text_content, AVG_CHARS_PER_TOKEN)
        
        # Remove zero-width spaces before sending to API and for logging
        clean_chunk_text_content = chunk_text_content.replace(chr(8203), '')


        print(f"\n  Processing API Request {chunk_num_overall}/{total_api_requests} "
              f"(Length: {len(clean_chunk_text_content)} chars, Est. Tokens: {current_chunk_estimated_tokens})")
        print(f"    Using Speaker WAV for API: {current_speaker_wav_for_api}")

        if current_chunk_estimated_tokens > TOKEN_LIMIT + 50:
             print(f"    POTENTIAL ISSUE: Estimated tokens ({current_chunk_estimated_tokens}) significantly exceed TOKEN_LIMIT ({TOKEN_LIMIT}).")
        if os.path.exists(local_chunk_filepath) and os.path.getsize(local_chunk_filepath) > 100:
            print(f"    Found existing valid local chunk: {os.path.basename(local_chunk_filepath)}. Skipping generation.")
            local_chunk_paths.append(local_chunk_filepath)
            continue
        
        if not clean_chunk_text_content.strip(): # Check cleaned text
             print(f"    Warning: Skipping empty or whitespace-only chunk_text_content for request {chunk_num_overall}.")
             continue
        if len(clean_chunk_text_content.strip()) < 2 :
            print(f"    Warning: Chunk text content is too short ('{clean_chunk_text_content}'). Using placeholder '.....'")
            clean_chunk_text_content = "....."

        payload = {
            "text_input": clean_chunk_text_content, # Send cleaned text
            "character_voice_gen": current_speaker_wav_for_api,
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API,
            "rvccharacter_pitch": RVC_PITCH,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_output_basename
        }
        print(f"    Requesting generation from API...")
        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=600)
            response.raise_for_status()
            response_data = response.json()
            if isinstance(response_data, dict) and 'output_file_url' in response_data and response_data['output_file_url']:
                chunk_relative_url = response_data['output_file_url']
                if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_chunk_filepath):
                    local_chunk_paths.append(local_chunk_filepath)
                else:
                    print(f"    FAILED to download newly generated chunk {chunk_num_overall}.")
                    all_chunks_acquired = False; break
            else:
                 print(f"    API did not return a valid 'output_file_url' for chunk {chunk_num_overall}.")
                 if isinstance(response_data, dict):
                      error_msg = response_data.get('error') or response_data.get('status') or response_data.get('message') or response_data.get('detail')
                      if error_msg: print(f"      API Error/Status: {error_msg}")
                      else: print(f"      API Response content (abbreviated): {str(response_data)[:200]}...")
                 all_chunks_acquired = False; break
        except requests.exceptions.Timeout:
            print(f"    Error: Request timed out for chunk {chunk_num_overall}.")
            all_chunks_acquired = False; break
        except requests.exceptions.HTTPError as http_err:
            print(f"    HTTP error occurred for chunk {chunk_num_overall}: {http_err}")
            if http_err.response is not None:
                 print(f"      API Response Status Code: {http_err.response.status_code}")
                 try:
                      response_json = http_err.response.json()
                      error_detail = response_json.get('detail') or response_json.get('error') or str(response_json)
                      print(f"      API Error Detail: {error_detail[:500]}...")
                 except Exception:
                      try: print(f"      API Response Text: {http_err.response.text[:500]}...")
                      except Exception: print("      Could not get specific error details from API response.")
            print(f"      Problematic Text (approx {len(clean_chunk_text_content)} chars, est. {current_chunk_estimated_tokens} tokens):\n      '{clean_chunk_text_content[:150]}...'")
            all_chunks_acquired = False; break
        except requests.exceptions.RequestException as req_err:
            print(f"    Request error occurred for chunk {chunk_num_overall}: {req_err}")
            all_chunks_acquired = False; break
        except Exception as e:
            print(f"    An unexpected error occurred processing chunk {chunk_num_overall}: {e}")
            import traceback; traceback.print_exc()
            all_chunks_acquired = False; break
        delay = 1
        time.sleep(delay)

    if all_chunks_acquired and len(local_chunk_paths) > 0 and len(local_chunk_paths) == total_api_requests:
        if concatenate_audio_chunks(local_chunk_paths, final_audio_output_path):
            print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
            try: shutil.rmtree(chapter_temp_dir)
            except Exception as e: print(f"  Warning: Failed to clean up temporary directory {chapter_temp_dir}: {e}")
            return True
        else:
            print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---")
            print(f"      Chunks remain in: {chapter_temp_dir}")
            return False
    elif not all_tts_requests and not full_text_content_annotated.strip():
        return True
    else:
        reason = "Unknown processing error or not all chunks acquired."
        if not all_chunks_acquired: reason = "Error during API call/download for one or more chunks."
        elif len(local_chunk_paths) != total_api_requests: reason = f"Mismatch: Expected {total_api_requests} TTS chunks, but only got {len(local_chunk_paths)} audio files."
        print(f"--- Chapter File Processing FAILED ({reason}): {text_filepath} ---")
        print(f"      Temporary chunks (if any) remain in: {chapter_temp_dir}")
        return False

# --- Main Execution Logic (Largely Unchanged) ---
if __name__ == "__main__":
    if not os.path.exists(TEMP_CHUNK_DIR): os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.isdir(TEXT_FILES_DIR):
        print(f"Error: Input directory for annotated text files not found: {TEXT_FILES_DIR}")
        exit(1)
    if not os.path.exists(HALF_LIGHT_STYLES["DEFAULT_STYLE"]):
        print(f"Error: Default XTTS Speaker WAV not found: {HALF_LIGHT_STYLES['DEFAULT_STYLE']}")
        exit(1)
    if not os.path.exists(RVC_MODEL_PATH_LOCAL_CHECK):
        print(f"Warning: RVC Model Path (local check) not found: {RVC_MODEL_PATH_LOCAL_CHECK}.")

    text_files = sorted(glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt")))
    if not text_files:
        print(f"No .txt files found in {TEXT_FILES_DIR}")
        exit(1)
    if not os.path.exists(AUDIO_OUTPUT_DIR): os.makedirs(AUDIO_OUTPUT_DIR)

    print(f"\nFound {len(text_files)} text files to process from '{TEXT_FILES_DIR}'.")
    print(f"Targeting API: {ALLTALK_API_URL}")
    print(f"--- Chunking Params: Target Token Limit <= {TOKEN_LIMIT} (using {AVG_CHARS_PER_TOKEN} chars/token est.) ---")
    if not PYDUB_AVAILABLE: print(f"--- !!! WARNING: pydub not installed. Concatenation will fail. !!! ---")

    total_chapters = len(text_files)
    chapters_succeeded = 0
    chapters_failed_processing = 0

    for idx, text_file_path in enumerate(text_files):
        print(f"\n{'='*10} Processing Chapter {idx + 1}/{total_chapters}: {os.path.basename(text_file_path)} {'='*10}")
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0]
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")

        if os.path.exists(final_output_audio_path):
            print(f"Skipping chapter: Final audio file already exists at {final_output_audio_path}")
            chapters_succeeded += 1
            continue
        if process_chapter_file(text_file_path, final_output_audio_path):
            chapters_succeeded += 1
        else:
            chapters_failed_processing += 1
            # exit_on_failure = False # Set to True to stop on first chapter failure
            # if exit_on_failure:
            #     print("\nHalting script due to chapter processing failure.")
            #     exit(1)

    print(f"\n--- Processing Complete ---")
    print(f"Total Chapters Found: {total_chapters}")
    print(f"Chapters Successfully Processed/Skipped: {chapters_succeeded}")
    print(f"Chapters Failed During Processing: {chapters_failed_processing}")
    if chapters_failed_processing > 0:
         print(f"  (Check logs for chapters that failed. Temporary files might remain in '{TEMP_CHUNK_DIR}')")
    print(f"\nGenerated audio files should be in: {AUDIO_OUTPUT_DIR}")
