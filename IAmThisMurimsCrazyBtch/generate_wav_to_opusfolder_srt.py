import os
import glob
import whisper # The official OpenAI Whisper library
import datetime
import torch # For checking CUDA availability and version
import multiprocessing as mp # For multiprocessing
import time # For timing individual processes

# Keep your existing format_timestamp_srt and process_single_wav_to_srt functions as they are.
# (I'm including process_single_wav_to_srt here for completeness from the last version)

def format_timestamp_srt(seconds: float) -> str:
    """Converts seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    assert seconds >= 0, "non-negative timestamp expected"
    milliseconds = round(seconds * 1000.0)
    hours = milliseconds // 3_600_000
    milliseconds -= hours * 3_600_000
    minutes = milliseconds // 60_000
    milliseconds -= minutes * 60_000
    seconds_val = milliseconds // 1_000
    milliseconds -= seconds_val * 1_000
    return f"{hours:02d}:{minutes:02d}:{seconds_val:02d},{milliseconds:03d}"

def process_single_wav_to_srt(
    wav_filepath: str,
    srt_output_dir: str,
    model_name: str,
    language: str
):
    process_start_time = time.monotonic()
    wav_basename = os.path.basename(wav_filepath)
    pid = os.getpid()

    base_filename_no_ext = os.path.splitext(wav_basename)[0]
    srt_filename = f"{base_filename_no_ext}.srt"
    srt_filepath = os.path.join(srt_output_dir, srt_filename)

    if os.path.exists(srt_filepath):
        duration = time.monotonic() - process_start_time
        # print(f"PID {pid}: Skipping {wav_basename} - SRT already exists at {srt_filepath} (Checked in {duration:.2f}s)")
        return f"Skipped: {wav_basename} - SRT already exists."

    print(f"PID {pid}: Processing {wav_basename} with model '{model_name}'...")

    if not os.path.exists(wav_filepath):
        duration = time.monotonic() - process_start_time
        print(f"PID {pid}: Error - WAV file not found at {wav_filepath}. (Failed in {duration:.2f}s)")
        return f"Error: {wav_basename} - WAV file not found."

    try:
        device_to_use = "cuda" if torch.cuda.is_available() else "cpu"
        
        model_load_start_time = time.monotonic()
        model = whisper.load_model(model_name, device=device_to_use)
        model_load_duration = time.monotonic() - model_load_start_time
        print(f"PID {pid}: Whisper model '{model_name}' loaded on {device_to_use.upper()} in {model_load_duration:.2f}s.")

        transcribe_start_time = time.monotonic()
        transcribe_options = {"language": language} if language else {}
        # Ensure verbose=None is used to attempt to get Whisper's internal TQDM bar
        # If 'verbose' is not in transcribe_options, it defaults to None.
        # If you want textual progress per segment instead (if TQDM doesn't show in MP):
        # transcribe_options['verbose'] = True
        result = model.transcribe(wav_filepath, word_timestamps=False, **transcribe_options)
        transcribe_duration = time.monotonic() - transcribe_start_time
        print(f"PID {pid}: Transcription for {wav_basename} completed in {transcribe_duration:.2f}s.")
        
        srt_content = []
        for i, segment in enumerate(result["segments"]):
            start_time = format_timestamp_srt(segment["start"])
            end_time = format_timestamp_srt(segment["end"])
            text = segment["text"].strip()
            if not text: continue
            srt_content.append(f"{len(srt_content) // 3 + 1}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(f"{text}\n")

        if not srt_content:
            duration = time.monotonic() - process_start_time
            print(f"PID {pid}: Warning - No text segments found for {wav_basename}. SRT file will not be created. (Total time: {duration:.2f}s)")
            return f"Warning: {wav_basename} - No segments found."

        with open(srt_filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_content))
        duration = time.monotonic() - process_start_time
        print(f"PID {pid}: Successfully created SRT: {srt_filepath}. Total time for this file: {duration:.2f}s")
        return f"Success: {wav_basename} - SRT created in {duration:.2f}s."

    except Exception as e:
        duration = time.monotonic() - process_start_time
        # Check if the exception is KeyboardInterrupt from within the worker
        # This is less likely to be caught here cleanly if the interrupt primarily hits the main process
        if isinstance(e, KeyboardInterrupt):
            print(f"PID {pid}: Worker interrupted processing {wav_basename} after {duration:.2f}s.")
            return f"Interrupted: {wav_basename} (Processed for {duration:.2f}s)"
        
        print(f"PID {pid}: Error processing {wav_basename} after {duration:.2f}s: {type(e).__name__} - {e}")
        if "CUDA out of memory" in str(e):
            return f"Error: {wav_basename} - CUDA out of memory. (Failed after {duration:.2f}s)"
        elif "ffmpeg" in str(e).lower() and "not found" in str(e).lower():
             return f"Error: {wav_basename} - ffmpeg not found. (Failed after {duration:.2f}s)"
        return f"Error: {wav_basename} - {e} (Failed after {duration:.2f}s)"

main_pid_for_initial_prints = None

if __name__ == "__main__":
    main_pid_for_initial_prints = os.getpid()
    try:
        mp.set_start_method('spawn', force=True)
    except RuntimeError:
        print("Multiprocessing start method info: Already set or cannot be set to 'spawn'.")

    # --- Configuration --- (Keep your existing configurations)
    WAV_INPUT_DIR = "generated_audio_IATMCB"
    SRT_OUTPUT_DIR = "generated_audio_IATMCB_opus"
    WAV_FILENAME_PATTERN = "ch_*.wav"
    WHISPER_MODEL = "medium.en" 
    NUM_WORKERS = 1
    AUDIO_LANGUAGE = None
    # ---------------------
    
    overall_start_time = time.monotonic()

    print("--- Starting WAV to SRT Subtitle Generation (Multiprocessed with Timers) ---")
    # ... (rest of your initial print statements) ...
    print(f"WAV Input Directory: {os.path.abspath(WAV_INPUT_DIR)}")
    print(f"SRT Output Directory (Opus Folder): {os.path.abspath(SRT_OUTPUT_DIR)}")
    print(f"WAV Filename Pattern: {WAV_FILENAME_PATTERN}")
    print(f"Using Whisper Model: {WHISPER_MODEL}")
    print(f"Number of Worker Processes: {NUM_WORKERS}")
    if AUDIO_LANGUAGE:
        print(f"Specified Audio Language: {AUDIO_LANGUAGE}")
    else:
        print("Audio Language: Auto-detection by Whisper")
    
    if torch.cuda.is_available():
        print(f"PyTorch CUDA is available. GPU: {torch.cuda.get_device_name(0)}")
        print(f"PyTorch linked CUDA version: {torch.version.cuda}")
    else:
        print("Warning: PyTorch CUDA is NOT available in the main process. Whisper will run on CPU in workers.")
    print("-" * 70)

    if not os.path.isdir(WAV_INPUT_DIR):
        print(f"Error: WAV input directory '{WAV_INPUT_DIR}' not found.")
        exit()

    wav_files_to_process = glob.glob(os.path.join(WAV_INPUT_DIR, WAV_FILENAME_PATTERN))
    wav_files_to_process.sort()

    if not wav_files_to_process:
        print(f"No files matching pattern '{WAV_FILENAME_PATTERN}' found in '{WAV_INPUT_DIR}'.")
        exit()

    print(f"Found {len(wav_files_to_process)} WAV files to process.\n")

    if not os.path.exists(SRT_OUTPUT_DIR):
        try:
            os.makedirs(SRT_OUTPUT_DIR)
            print(f"Created SRT output directory: {SRT_OUTPUT_DIR}")
        except OSError as e:
            print(f"Error: Could not create SRT output directory '{SRT_OUTPUT_DIR}': {e}")
            exit()
            
    tasks = []
    for wav_path in wav_files_to_process:
        tasks.append((wav_path, SRT_OUTPUT_DIR, WHISPER_MODEL, AUDIO_LANGUAGE))

    pool = None  # Initialize pool to None for cleanup
    results = [] # Initialize results
    interrupted = False

    try:
        print(f"Starting transcription with {NUM_WORKERS} worker process(es)...\n")
        # Using 'with' context manager is good practice for Pools
        with mp.Pool(processes=NUM_WORKERS) as pool:
            results = pool.starmap(process_single_wav_to_srt, tasks)
        
    except KeyboardInterrupt:
        interrupted = True
        print("\n!!! Ctrl+C detected in main process! Terminating worker processes... !!!")
        # pool variable might not be in scope if KeyboardInterrupt happens during pool creation
        # However, 'with' statement handles pool.terminate() on exception implicitly if exit occurs within 'with'.
        # If KeyboardInterrupt is caught outside the 'with' or after it, explicit termination is needed.
        # For a running pool, pool.terminate() is needed.
        # The 'with' statement handles __exit__ which calls terminate on error.
        # So, this explicit terminate might be redundant if using 'with' but safe.
        if pool: # Check if pool was successfully initialized
            pool.terminate()
            pool.join() # Wait for terminated processes to exit
        print("Worker processes have been requested to terminate.")
    except Exception as e:
        interrupted = True
        print(f"\n--- An unexpected error occurred in the main process: {type(e).__name__} - {e} ---")
        if pool:
            pool.terminate()
            pool.join()
        print("Worker processes terminated due to an error.")
    finally:
        # This finally block ensures that if the pool object exists and might still be running
        # (e.g., if interrupt happened before 'with' statement fully exited or if 'with' is not used),
        # we try to terminate it. However, 'with' statement is robust.
        if pool and hasattr(pool, '_state') and pool._state == mp.pool.RUN: # Check if pool is technically still running
             print("Final cleanup: Terminating pool...")
             pool.terminate()
             pool.join()


    print("\n" + "-" * 70)
    if interrupted:
        print("--- Subtitle Generation Was Interrupted ---")
    else:
        print("--- Multiprocessed Subtitle Generation Attempt Complete ---")
        # You can still summarize results if any were collected
        # success_count = sum(1 for r in results if r and r.startswith("Success:"))
        # skipped_count = sum(1 for r in results if r and r.startswith("Skipped:"))
        # error_count = sum(1 for r in results if r and r.startswith("Error:"))
        # warning_count = sum(1 for r in results if r and r.startswith("Warning:"))
        # print(f"Summary: {success_count} succeeded, {skipped_count} skipped, {error_count} errors, {warning_count} warnings.")
        
    print(f"SRT files processed (or attempted) are in: {os.path.abspath(SRT_OUTPUT_DIR)}")
    
    overall_duration = time.monotonic() - overall_start_time
    print(f"Total script execution time: {overall_duration:.2f} seconds ({overall_duration/60:.2f} minutes).")
    if interrupted:
        print("Note: Total script time is for the duration until interruption.")
    print("Review console output for details on individual file processing times, skipped files, or errors.")
