import requests
import os
import glob
import time
import tempfile # For temporary chunk downloads
from urllib.parse import urljoin

# --- Try importing pydub ---
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub library not found. Audio chunk concatenation will be skipped.")
    print("Please install it: pip install pydub")
    print("You might also need ffmpeg installed on your system.")
    PYDUB_AVAILABLE = False
# ---------------------------

# --- Configuration ---
# Using the non-streaming endpoint which accepts RVC params per UI JS
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate" 
ALLTALK_BASE_URL = "http://127.0.0.1:7851" # Base URL for downloading audio chunks

TEXT_FILES_DIR = "scraped_tileas_worries" # Contains ch_XXX.txt
# Where the FINAL concatenated chapter audio will be saved locally
AUDIO_OUTPUT_DIR = "generated_audio_tileas_worries" 

# Max characters per chunk for /api/tts-generate (leaving some buffer)
CHUNK_CHAR_LIMIT = 1800 

# --- Paths/Values needed by the Alltalk SERVER ---
# Path for the XTTS 'character_voice_gen' parameter
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav" 
XTTS_LANGUAGE = "en"

# RVC parameters to send in payload (Names from UI JS)
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
# Using relative name might be safer - match the name from RVC voices list / UI dropdown
RVC_MODEL_NAME_FOR_API = 'half_light\\half_light.pth' 
RVC_PITCH = -2 # As used in your previous attempt

# RVC Reference WAV MUST be configured globally in Alltalk settings

# Repetition Penalty - WARNING: Value 10 likely invalid. Relying on fixed global setting recommended.
# Sending it anyway as per user direction, but strongly suggest changing to 1.0 if errors occur.
REPETITION_PENALTY = 10.0 

# DeepSpeed assumed PRE-CONFIGURED in Alltalk
USE_DEEPSPEED = True 

OUTPUT_FORMAT = "wav" # For final concatenated file and chunk requests
# --- End of Configuration ---

def split_text_into_chunks(text, limit):
    """
    Splits text into chunks under a character limit, trying to respect paragraphs.
    Basic implementation, might split mid-sentence if paragraphs are too long.
    """
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
            
        para_len = len(para)
        
        # If adding the next paragraph (plus newline space) exceeds limit
        if current_chunk and len(current_chunk) + para_len + 2 > limit:
            chunks.append(current_chunk)
            current_chunk = "" # Start new chunk

        # If a single paragraph itself exceeds the limit, split it
        if para_len > limit:
            print(f"  Warning: Paragraph length ({para_len}) exceeds limit ({limit}). Performing basic split.")
            start_index = 0
            while start_index < para_len:
                # Find the best split point within the limit
                end_index = min(start_index + limit, para_len)
                # Try to split at the last sentence-ending punctuation before the limit
                split_pos = max(para.rfind('.', start_index, end_index), 
                                para.rfind('?', start_index, end_index), 
                                para.rfind('!', start_index, end_index))
                
                # If no punctuation found, try splitting at last space
                if split_pos <= start_index: 
                    split_pos = para.rfind(' ', start_index, end_index)

                # If no space found, force split at limit
                if split_pos <= start_index:
                    split_pos = end_index
                else:
                    split_pos += 1 # Include the punctuation/space in the split

                sub_para = para[start_index:split_pos].strip()
                if sub_para:
                    # If adding sub_para exceeds limit for the current_chunk
                    if current_chunk and len(current_chunk) + len(sub_para) + 2 > limit:
                         chunks.append(current_chunk)
                         current_chunk = sub_para
                    # If current chunk is empty or sub_para fits
                    elif not current_chunk:
                        current_chunk = sub_para
                    else: # Add to current chunk
                        current_chunk += "\n\n" + sub_para
                        
                    # Check if the added chunk needs to be finalized immediately
                    if len(current_chunk) > limit : 
                        # This case handles where sub_para itself was > limit
                        # Or adding it just tipped over. Finalize it.
                        chunks.append(current_chunk)
                        current_chunk = "" 

                start_index = split_pos
                
        # Else, the paragraph fits (or is the start of a new chunk)
        else:
            if not current_chunk:
                current_chunk = para
            else:
                current_chunk += "\n\n" + para

    # Add the last remaining chunk
    if current_chunk:
        chunks.append(current_chunk)
        
    print(f"  Split text into {len(chunks)} chunks.")
    return chunks

def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
     """Downloads an audio chunk from the server."""
     try:
         # Ensure relative URL starts with / or join properly
         if relative_audio_url.startswith('/'):
             full_url = f"{server_base_url}{relative_audio_url}"
         else:
             full_url = urljoin(server_base_url + "/", relative_audio_url) 
             
         print(f"    Downloading chunk: {full_url}")
         response = requests.get(full_url, stream=True, timeout=180) 
         response.raise_for_status()
         with open(local_temp_path, 'wb') as f:
             for chunk_data in response.iter_content(chunk_size=8192):
                 f.write(chunk_data)
         # print(f"    Downloaded to: {local_temp_path}")
         return True
     except Exception as e:
         print(f"    Error downloading {relative_audio_url}: {e}")
         return False

def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    """Concatenates downloaded audio chunks using pydub."""
    if not PYDUB_AVAILABLE:
        print("  Error: pydub library not available. Cannot concatenate audio.")
        return False
    if not chunk_filepaths:
        print("  Error: No audio chunk files provided for concatenation.")
        return False
        
    print(f"  Concatenating {len(chunk_filepaths)} audio chunks...")
    try:
        combined = AudioSegment.empty()
        for i, filepath in enumerate(chunk_filepaths):
            try:
                # print(f"    Adding chunk {i+1}: {filepath}")
                segment = AudioSegment.from_wav(filepath) # Assumes WAV
                combined += segment
            except Exception as e:
                print(f"    Error loading/processing chunk {filepath}: {e}. Skipping.")
        
        if len(combined) > 0:
             # Ensure output directory exists
             output_dir = os.path.dirname(final_output_path)
             if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
             combined.export(final_output_path, format="wav") # Save as WAV
             print(f"  Concatenated audio saved successfully to: {final_output_path}")
             return True
        else:
             print("  Error: Combined audio is empty after processing chunks.")
             return False
            
    except Exception as e:
        print(f"  Error during audio concatenation: {e}")
        return False

def process_chapter_file(text_filepath, final_audio_output_path):
    """
    Splits chapter text, calls API for each chunk, downloads chunks, 
    and concatenates them into the final audio file.
    Returns True if successful, False otherwise.
    """
    print(f"\n--- Processing Chapter File: {text_filepath} ---")
    
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            full_text_content = f.read()
        if not full_text_content.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            return True # Consider empty file success? Or False? Let's say True.
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    text_chunks = split_text_into_chunks(full_text_content, CHUNK_CHAR_LIMIT)
    if not text_chunks:
        print("  No text chunks generated after splitting.")
        return False

    generated_chunk_relative_urls = []
    all_chunks_successful = True

    # Create a temporary directory for downloaded chunks for this chapter
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"  Using temporary directory for chunks: {temp_dir}")
        downloaded_chunk_paths = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_num = i + 1
            # Create a unique base name for the server to save this chunk
            chunk_output_basename = f"{base_filename_no_ext}_chunk_{chunk_num:03d}" 
            
            print(f"\n  Processing Chunk {chunk_num}/{len(text_chunks)}...")

            # --- Construct the API Payload (Form Data) for this chunk ---
            payload = {
                "text_input": chunk_text,
                "character_voice_gen": XTTS_SPEAKER_WAV, 
                "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API, 
                "rvccharacter_pitch": RVC_PITCH,           
                "language": XTTS_LANGUAGE,
                "output_file_name": chunk_output_basename # BASE filename WITHOUT extension
                # "repetition_penalty": REPETITION_PENALTY # Not sending based on likely global setting
            }
            
            # Add penalty if user insists, despite potential issues
            if 'REPETITION_PENALTY' in globals() and REPETITION_PENALTY is not None:
                 payload["repetition_penalty"] = REPETITION_PENALTY # Sending 10.0 as per user request
                 print(f"    Including repetition_penalty: {REPETITION_PENALTY} in payload.")
                 if REPETITION_PENALTY == 10.0:
                     print("    WARNING: repetition_penalty=10.0 might cause errors. Consider 1.0 or removing.")

            print(f"    Sending request to Alltalk API ({ALLTALK_API_URL})")
            print(f"    Payload (Form Data): {{'text_input': '...', "
                  # ... (rest of payload logging) ...
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
                    generated_chunk_relative_urls.append(chunk_relative_url)
                    print(f"    API reports SUCCESS for chunk {chunk_num}. URL: {chunk_relative_url}")

                    # Download the chunk immediately
                    local_chunk_filename = os.path.join(temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}")
                    if download_audio_chunk(ALLTALK_BASE_URL, chunk_relative_url, local_chunk_filename):
                        downloaded_chunk_paths.append(local_chunk_filename)
                    else:
                        print(f"    FAILED to download chunk {chunk_num}. Stopping chapter processing.")
                        all_chunks_successful = False
                        break # Stop processing chunks for this chapter if one fails to download
                else:
                     print(f"    API did not return a valid 'output_file_url' for chunk {chunk_num}. Stopping chapter processing.")
                     all_chunks_successful = False
                     # Try to get more error info
                     if isinstance(response_data, dict) and ('error' in response_data or 'status' in response_data):
                         print(f"      API Error/Status: {response_data.get('error') or response_data.get('status') or response_data.get('message')}")
                     break # Stop processing chunks for this chapter

            except requests.exceptions.Timeout: print(f"    Error: Request timed out for chunk {chunk_num}."); all_chunks_successful = False; break
            except requests.exceptions.RequestException as e:
                print(f"    Error sending request for chunk {chunk_num}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"      API Response Status Code: {e.response.status_code}")
                    try: error_detail = e.response.json(); print(f"      API Error Detail: {error_detail}") 
                    except ValueError: print(f"      API Response Text: {e.response.text[:500]}...")
                all_chunks_successful = False; break
            except Exception as e: print(f"    An unexpected error occurred processing chunk {chunk_num}: {e}"); all_chunks_successful = False; break

            # Add delay between API calls for chunks
            delay = 1 # Shorter delay between chunks might be okay
            print(f"    Pausing for {delay} second(s)...")
            time.sleep(delay)
            #--- End Chunk Loop ---

        # After processing all chunks (or breaking due to error)
        if all_chunks_successful and downloaded_chunk_paths:
            # Concatenate downloaded chunks
            if concatenate_audio_chunks(downloaded_chunk_paths, final_audio_output_path):
                 print(f"--- Chapter File Successfully Processed: {final_audio_output_path} ---")
                 return True
            else:
                 print(f"--- Chapter File Processing FAILED (Concatenation Error): {text_filepath} ---")
                 return False
        else:
            print(f"--- Chapter File Processing FAILED (API/Download Error): {text_filepath} ---")
            # Optional: Clean up any partially downloaded chunks in temp_dir if needed,
            # but TemporaryDirectory handles cleanup automatically on exit.
            return False
            
    #--- End Function process_chapter_file ---


# --- Main Execution Logic ---
if __name__ == "__main__":
    # (Checks for directories and files remain the same)
    if not os.path.isdir(TEXT_FILES_DIR): print(f"Error: Input directory not found: {TEXT_FILES_DIR}"); exit()
    if not os.path.exists(XTTS_SPEAKER_WAV): print(f"Error: XTTS Speaker WAV not found: {XTTS_SPEAKER_WAV}"); exit()
    if not os.path.exists(RVC_MODEL_PATH): print(f"Warning: RVC model path '{RVC_MODEL_PATH}' not found locally. Ensure server configured correctly with '{RVC_MODEL_NAME_FOR_API}'.") 

    text_files = glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))
    if not text_files: print(f"No .txt files found in {TEXT_FILES_DIR}"); exit()

    # Create local output directory if it doesn't exist
    if not os.path.exists(AUDIO_OUTPUT_DIR):
        os.makedirs(AUDIO_OUTPUT_DIR)
        print(f"Created local audio output directory: {AUDIO_OUTPUT_DIR}")

    print(f"\nFound {len(text_files)} text files to process.")
    print(f"Targeting API: {ALLTALK_API_URL}") # /api/tts-generate
    print(f"--- Using Endpoint: {ALLTALK_API_URL} (Requires Text Splitting) ---")
    print(f"--- Sending RVC parameters directly. Verify server accepts these! ---")
    print(f"--- !!! Action Required: FIX 'repetitionpenalty_set: 10' in Alltalk Settings & Restart Server if penalty errors occur !!! ---")
    print(f"--- Ensure RVC Reference WAV & DeepSpeed ({USE_DEEPSPEED}) are PRE-CONFIGURED in Alltalk ---")

    chapters_processed = 0
    chapters_failed = 0

    for text_file_path in sorted(text_files): # Processes ch_001.txt etc.
        base_filename_no_ext = os.path.splitext(os.path.basename(text_file_path))[0] 
        # Define final output path for the concatenated audio
        final_output_audio_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_filename_no_ext}.{OUTPUT_FORMAT}")
        
        # Optional: Skip if final file already exists
        if os.path.exists(final_output_audio_path):
             print(f"\nSkipping chapter: Final audio file already exists at {final_output_audio_path}")
             chapters_processed += 1
             continue

        if process_chapter_file(text_file_path, final_output_audio_path):
            chapters_processed += 1
        else:
            chapters_failed += 1
        
        # Delay between processing CHAPTERS (longer delay perhaps?)
        chapter_delay = 3
        print(f"\nPausing for {chapter_delay} seconds before next chapter...")
        time.sleep(chapter_delay)

    print(f"\n--- Processing Complete ---")
    print(f"Chapters attempted: {chapters_processed + chapters_failed}")
    print(f"Chapters successfully processed: {chapters_processed}")
    print(f"Chapters failed: {chapters_failed}")
    print(f"\nGenerated audio files saved in: {AUDIO_OUTPUT_DIR}")
