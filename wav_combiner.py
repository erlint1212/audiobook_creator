import os
import glob
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

# --- Configuration ---
# Directory where your individual chapter audio files are located
# This should match the AUDIO_OUTPUT_DIR from your TTS generation script
CHAPTER_AUDIO_DIR = "generated_audio_TheArtOfWar"

# Name for the final combined audio file
COMBINED_AUDIO_FILENAME = "TheArtOfWar_HalfLight.wav" # You can change the name
OUTPUT_FILE_FORMAT = "wav" # Ensure this matches the format of your chapter files

# Optional: A directory to save the combined file, if different from CHAPTER_AUDIO_DIR
# If None, it will be saved in the current working directory or you can specify one.
FINAL_OUTPUT_DIR = "TheArtOfWar" # Saves in the current directory. Change if needed, e.g., "final_audiobook"
# --- End Configuration ---

def combine_audio_files(input_dir, output_filename, audio_format="wav"):
    """
    Finds all audio files in the input_dir, sorts them,
    concatenates them, and saves to output_filename.
    """
    if not os.path.isdir(input_dir):
        print(f"Error: Input directory '{input_dir}' not found.")
        return False

    # Find all audio files of the specified format
    # The glob pattern should match your chapter audio filenames
    # Assuming they are named like 'ch_001.wav', 'ch_002.wav' etc.
    # or based on the original text file names like 'some_text_file.wav'
    # Sorting is crucial here.
    search_pattern = os.path.join(input_dir, f"*.{audio_format}")
    chapter_files = sorted(glob.glob(search_pattern))

    if not chapter_files:
        print(f"No .{audio_format} files found in '{input_dir}'.")
        return False

    print(f"Found {len(chapter_files)} audio files to combine from '{input_dir}':")
    # for f_path in chapter_files: # Optional: print all files to be combined
    #     print(f"  - {os.path.basename(f_path)}")

    combined_audio = AudioSegment.empty()
    valid_files_processed = 0

    print("\nStarting concatenation...")
    for i, file_path in enumerate(chapter_files):
        print(f"  Processing file {i+1}/{len(chapter_files)}: {os.path.basename(file_path)}", end="")
        if os.path.exists(file_path) and os.path.getsize(file_path) > 100: # Basic check for validity
            try:
                segment = AudioSegment.from_file(file_path, format=audio_format)
                combined_audio += segment
                valid_files_processed += 1
                print(" ... Done")
            except FileNotFoundError:
                print(f" ... SKIPPED (Error: File not found).")
            except CouldntDecodeError:
                print(f" ... SKIPPED (Error: Could not decode file - possibly corrupt or wrong format).")
            except Exception as e:
                print(f" ... SKIPPED (Error loading/processing: {e}).")
        else:
            print(f" ... SKIPPED (Invalid or empty file).")

    if valid_files_processed == 0:
        print("\nError: No valid audio files were successfully processed for concatenation.")
        return False

    if len(combined_audio) > 0:
        # Ensure the final output directory exists
        if FINAL_OUTPUT_DIR and not os.path.exists(FINAL_OUTPUT_DIR):
            try:
                os.makedirs(FINAL_OUTPUT_DIR)
                print(f"Created output directory: {FINAL_OUTPUT_DIR}")
            except OSError as e:
                print(f"Error creating output directory '{FINAL_OUTPUT_DIR}': {e}")
                return False
        
        final_save_path = os.path.join(FINAL_OUTPUT_DIR, output_filename)

        try:
            print(f"\nExporting combined audio to: {final_save_path} (Format: {audio_format})")
            combined_audio.export(final_save_path, format=audio_format)
            print("Combined audio saved successfully!")
            return True
        except Exception as export_e:
            print(f"Error exporting combined audio: {export_e}")
            return False
    else:
        print("\nError: Combined audio is empty after attempting to process chapter files.")
        return False

if __name__ == "__main__":
    print("--- Starting Audio Chapter Combination Script ---")
    
    # Check for pydub dependency
    try:
        from pydub import AudioSegment
    except ImportError:
        print("\nCRITICAL ERROR: The 'pydub' library is not installed.")
        print("This script requires pydub for audio manipulation.")
        print("Please install it by running: pip install pydub")
        print("You might also need FFmpeg installed and available in your system's PATH.")
        print("FFmpeg is used by pydub for handling various audio formats.")
        print("You can download FFmpeg from: https://ffmpeg.org/download.html")
        exit(1)

    if combine_audio_files(CHAPTER_AUDIO_DIR, COMBINED_AUDIO_FILENAME, OUTPUT_FILE_FORMAT):
        print("\n--- Combination process finished successfully. ---")
    else:
        print("\n--- Combination process failed. Please check errors above. ---")
