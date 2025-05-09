# convert_audio_to_opus.py

import os
import glob
from pydub import AudioSegment
import shutil # Optional: for moving or deleting original WAVs

# --- Configuration ---
WAV_AUDIO_DIR = "generated_audio_tileas_worries"  # Directory where your WAV chapters are
OPUS_OUTPUT_DIR = "generated_audio_tileas_worries_opus" # Directory to save Opus files
# Or, you can save Opus in the same directory with a different extension,
# but a separate directory is often cleaner.

# Opus Export Settings
OPUS_BITRATE = "48k" # Good for mono speech (e.g., 32k, 48k, 64k)
# Note: For Opus, pydub passes parameters to FFmpeg.
# Ensure your FFmpeg build supports libopus.

DELETE_ORIGINAL_WAV = False # Set to True to delete WAV files after successful conversion
# --- End Configuration ---

def convert_wav_to_opus(wav_filepath, opus_filepath, bitrate="48k"):
    """Converts a single WAV file to Opus using pydub."""
    try:
        print(f"Converting: {os.path.basename(wav_filepath)} -> {os.path.basename(opus_filepath)}")
        audio = AudioSegment.from_wav(wav_filepath)
        
        # Ensure audio is mono (Opus often works best with mono for speech, and TTS is likely mono)
        # If you are certain your WAVs are already mono, you can skip this.
        if audio.channels > 1:
            print(f"  Info: Converting stereo WAV to mono for Opus export.")
            audio = audio.set_channels(1)
            
        # Export to Opus
        # pydub uses FFmpeg backend. Parameters are passed to FFmpeg.
        audio.export(opus_filepath, format="opus", parameters=["-c:a", "libopus", "-b:a", bitrate])
        
        print(f"  Successfully converted to {opus_filepath}")
        return True
    except Exception as e:
        print(f"  Error converting {wav_filepath} to Opus: {e}")
        return False

if __name__ == "__main__":
    print(f"--- Starting WAV to Opus Conversion ---")
    print(f"Input WAV Directory: {os.path.abspath(WAV_AUDIO_DIR)}")
    print(f"Output Opus Directory: {os.path.abspath(OPUS_OUTPUT_DIR)}")

    if not os.path.isdir(WAV_AUDIO_DIR):
        print(f"Error: Input WAV directory '{WAV_AUDIO_DIR}' not found.")
        exit()

    if not os.path.exists(OPUS_OUTPUT_DIR):
        os.makedirs(OPUS_OUTPUT_DIR)
        print(f"Created output Opus directory: {OPUS_OUTPUT_DIR}")

    wav_files = glob.glob(os.path.join(WAV_AUDIO_DIR, "ch_*.wav")) # Assuming your WAVs follow this pattern

    if not wav_files:
        print(f"No WAV files found in '{WAV_AUDIO_DIR}' matching 'ch_*.wav'.")
        exit()

    print(f"\nFound {len(wav_files)} WAV files to convert.")
    
    converted_count = 0
    failed_count = 0

    for wav_file_path in sorted(wav_files): # Process in order
        base_filename = os.path.splitext(os.path.basename(wav_file_path))[0]
        opus_file_path = os.path.join(OPUS_OUTPUT_DIR, f"{base_filename}.opus")

        # Optional: Skip if Opus file already exists
        # if os.path.exists(opus_file_path):
        #     print(f"Skipping {wav_file_path}, Opus file already exists: {opus_file_path}")
        #     converted_count +=1 # Or just pass
        #     continue

        if convert_wav_to_opus(wav_file_path, opus_file_path, bitrate=OPUS_BITRATE):
            converted_count += 1
            if DELETE_ORIGINAL_WAV:
                try:
                    os.remove(wav_file_path)
                    print(f"  Deleted original WAV: {wav_file_path}")
                except Exception as e:
                    print(f"  Error deleting original WAV {wav_file_path}: {e}")
        else:
            failed_count += 1

    print(f"\n--- Conversion Complete ---")
    print(f"Successfully converted: {converted_count} files.")
    print(f"Failed conversions   : {failed_count} files.")
    if DELETE_ORIGINAL_WAV:
        print(f"Original WAV files in '{WAV_AUDIO_DIR}' were set to be deleted upon successful conversion.")
    else:
        print(f"Original WAV files in '{WAV_AUDIO_DIR}' have been preserved.")
    print(f"Opus files are saved in: {OPUS_OUTPUT_DIR}")
