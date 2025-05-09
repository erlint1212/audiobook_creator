import requests
import os
import glob
import time

# --- Configuration ---
# Reverting to the streaming endpoint, which should handle long text
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate-streaming" 

TEXT_FILES_DIR = "scraped_tileas_worries" # Contains ch_001.txt etc.
AUDIO_OUTPUT_DIR_REFERENCE = "generated_audio_tileas_worries" # Local reference path

# --- Paths needed by the Alltalk SERVER ---
# Path for the XTTS 'voice' parameter
XTTS_SPEAKER_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav" 
XTTS_LANGUAGE = "en"

# RVC Model/Ref WAV paths (Used by Alltalk's global settings)
RVC_MODEL_PATH = "C:/Users/etnor/Documents/tts/alltalk_tts/models/rvc_voices/half_light/half_light.pth"
RVC_REFERENCE_WAV = "C:/Users/etnor/Documents/tts/alltalk_tts/voices/Half_Light_Disco_Elysium.wav"
RVC_INDEX_PATH = "" 

# DeepSpeed (Used by Alltalk's global settings)
USE_DEEPSPEED = True 
OUTPUT_FORMAT = "wav" 
# --- End of Configuration ---

def generate_audio_via_api(text_filepath, output_filename_on_server):
    """
    Sends request to the Alltalk TTS API endpoint (/api/tts-generate-streaming).
    Uses parameters required by this endpoint. Assumes RVC/DeepSpeed/Penalty
    are configured server-side. Sends as Form Data.
    Returns True if API call seems successful based on response.
    """
    print(f"\nProcessing text file: {text_filepath}")

    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            text_content = f.read()
        if not text_content.strip():
            print(f"  Skipping empty text file: {text_filepath}")
            return True 
    except Exception as e:
        print(f"  Error reading text file {text_filepath}: {e}")
        return False

    # --- Construct the API Payload (Form Data) ---
    # Using ONLY parameters confirmed for /api/tts-generate-streaming from /docs
    payload = {
        "text": text_content,
        "voice": XTTS_SPEAKER_WAV,   
        "language": XTTS_LANGUAGE,
        "output_file": output_filename_on_server # Expects filename WITH extension (e.g., "ch_001.wav")
    }
    
    print(f"  Sending request to Alltalk API ({ALLTALK_API_URL})")
    print(f"  Payload (Form Data): {{'text': '...', 'voice': '{payload['voice']}', 'language': '{payload['language']}', 'output_file': '{payload['output_file']}'}}") 
    print(f"  Reminder: RVC/DeepSpeed/Penalty assumed active/configured on the server.")

    try:
        # Using data= for application/x-www-form-urlencoded
        response = requests.post(ALLTALK_API_URL, data=payload, timeout=600) # Long timeout
        response.raise_for_status() # Raise HTTPError for bad status codes (4xx or 5xx)

        print(f"  API Response Status Code: {response.status_code}")
        
        # --- Interpret Response ---
        # Expecting JSON like {'output_file_path': 'filename.wav'} on success for this endpoint.
        try:
            response_data = response.json()
            print(f"  API Response JSON: {response_data}")
            # Check if the expected key is present
            if isinstance(response_data, dict) and 'output_file_path' in response_data:
                 if response_data['output_file_path'] == payload['output_file']:
                    print(f"  API reports SUCCESS for {payload['output_file']}. (File saved by server).")
                    return True
                 else:
                     # Log mismatch but still consider it success if status 200 and key present
                     print(f"  API reports success (key present), but output path '{response_data['output_file_path']}' doesn't match expected '{payload['output_file']}'. Assuming success.")
                     return True
            # Handle other possible success/error structures as fallback
            elif isinstance(response_data, dict):
                 if response_data.get('status') == 'success' or 'completed' in response_data.get('message', '').lower() or response_data.get('result') == 'ok':
                    print(f"  API indicates success (alternative format) for {payload['output_file']}. (File saved by server).")
                    return True
                 elif 'error' in response_data or response_data.get('status') == 'error':
                     print(f"  API returned an error: {response_data.get('error') or response_data.get('message')}")
                     return False
                 else:
                     print("  API response JSON received, but success status is unclear.")
                     return False 
            else:
                 response_text = str(response_data)
                 print(f"  API Response (non-dict JSON): {response_text}")
                 if "success" in response_text.lower() or "ok" in response_text.lower() or "completed" in response_text.lower():
                      print(f"  API indicates success for {payload['output_file']}. (File saved by server).")
                      return True
                 else:
                     print("  API response JSON format unexpected or doesn't indicate success.")
                     return False

        except ValueError: # Response body wasn't JSON
            response_text = response.text
            print(f"  API Response Text (non-JSON, first 500 chars): {response_text[:500]}...")
            if response.status_code == 200: 
                 print(f"  API status OK but response body unclear/empty. Assuming success for {payload['output_file']}. (Check server's output location).")
                 return True
            else:
                 print("  API response text unclear and status code not OK.")
                 return False 

    except requests.exceptions.Timeout:
        print(f"  Error: Request to Alltalk API timed out for {text_filepath}.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"  Error sending request to Alltalk API for {text_filepath}: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  API Response Status Code: {e.response.status_code}")
            try: 
                error_detail = e.response.json()
                print(f"  API Error Detail: {error_detail}") # Show specific validation error if JSON
            except ValueError: 
                 print(f"  API Response Text: {e.response.text[:500]}...")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred while processing {text_filepath}: {e}")
        return False

# --- Main Execution Logic ---
if __name__ == "__main__":
    # (Checks for directories and files remain the same)
    if not os.path.isdir(TEXT_FILES_DIR): print(f"Error: Input directory not found: {TEXT_FILES_DIR}"); exit()
    if not os.path.exists(XTTS_SPEAKER_WAV): print(f"Error: XTTS Speaker WAV not found: {XTTS_SPEAKER_WAV}"); exit()
    if not os.path.exists(RVC_MODEL_PATH): print(f"Warning: RVC model path not found: {RVC_MODEL_PATH}") 
    if not os.path.exists(RVC_REFERENCE_WAV): print(f"Warning: RVC reference WAV not found: {RVC_REFERENCE_WAV}") 
    if RVC_INDEX_PATH and not os.path.exists(RVC_INDEX_PATH): print(f"Warning: RVC index path not found: {RVC_INDEX_PATH}")

    text_files = glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt"))
    if not text_files: print(f"No .txt files found in {TEXT_FILES_DIR}"); exit()

    print(f"\nFound {len(text_files)} text files to process.")
    print(f"Targeting API: {ALLTALK_API_URL}")
    print(f"--- !!! Action Required: Ensure 'repetitionpenalty_set' is FIXED in Alltalk Settings (e.g., to 1.0) & Server Restarted !!! ---")
    print(f"--- Ensure RVC ({os.path.basename(RVC_MODEL_PATH)}) & DeepSpeed ({USE_DEEPSPEED}) are PRE-CONFIGURED in Alltalk ---")

    successful_calls = 0
    failed_calls = 0

    for text_file_path in sorted(text_files): # Now processes ch_001.txt etc.
        base_filename = os.path.splitext(os.path.basename(text_file_path))[0]
        # Create filename WITH extension for the 'output_file' parameter
        output_filename_param = f"{base_filename}.{OUTPUT_FORMAT}" 
        
        if generate_audio_via_api(text_file_path, output_filename_param):
            successful_calls += 1
        else:
            failed_calls += 1
        
        delay = 2 
        print(f"  Pausing for {delay} seconds...")
        time.sleep(delay)

    print(f"\n--- Processing Complete ---")
    print(f"API calls reported success/started: {successful_calls}")
    print(f"API calls failed or reported errors: {failed_calls}")
    print(f"\nIMPORTANT: If calls failed, double-check the Alltalk server console and ensure the 'repetitionpenalty_set' setting was fixed.")
    print(f"If calls succeeded, check the Alltalk TTS server's output directory for the generated '{OUTPUT_FORMAT}' files.")
