# convert_audio_to_opus.py (with Normalization and Skip Existing)

import os
import glob
from pydub import AudioSegment
import shutil # Not strictly needed for this modification, but was in original

# --- Configuration ---
WAV_AUDIO_DIR = "generated_audio_tileas_worries"
OPUS_OUTPUT_DIR = "generated_audio_tileas_worries_opus"

# Opus Export Settings
OPUS_BITRATE = "48k"  # e.g., 32k, 48k, 64k

# Normalization Settings
ENABLE_NORMALIZATION = True  # Set to True to enable normalization
NORMALIZATION_TARGET_DBFS = -20.0  # Target loudness in dBFS (RMS). -18 to -23 is common.

DELETE_ORIGINAL_WAV = False
# --- End Configuration ---

def normalize_audio(sound, target_dbfs):
    """Normalizes a pydub AudioSegment object to target dBFS."""
    if sound.dBFS == float('-inf'):  # Avoid division by zero if sound is silent
        print("  Warning: Audio segment is silent, skipping normalization.")
        return sound
    change_in_dbfs = target_dbfs - sound.dBFS
    return sound.apply_gain(change_in_dbfs)

def convert_wav_to_opus(wav_filepath, opus_filepath, bitrate="48k", apply_normalization=False, target_dbfs=-20.0):
    """Converts a WAV file to Opus, optionally normalizing first."""
    try:
        print(f"Processing: {os.path.basename(wav_filepath)} -> {os.path.basename(opus_filepath)}")
        audio = AudioSegment.from_wav(wav_filepath)

        # --- Apply Normalization (Before other processing/export) ---
        if apply_normalization:
            print(f"  Normalizing to {target_dbfs} dBFS...")
            audio = normalize_audio(audio, target_dbfs)
        # ----------------------------------------------------------

        # Ensure mono if needed
        if audio.channels > 1:
            print(f"  Info: Converting to mono for Opus export.")
            audio = audio.set_channels(1)

        # Export to Opus
        print(f"  Converting to Opus ({bitrate})...")
        audio.export(opus_filepath, format="opus", parameters=["-c:a", "libopus", "-b:a", bitrate])

        print(f"  Successfully processed and saved to {opus_filepath}")
        return True
    except Exception as e:
        print(f"  Error processing {wav_filepath}: {e}")
        return False

if __name__ == "__main__":
    print(f"--- Starting WAV Processing & Opus Conversion ---")
    print(f"Input WAV Directory : {os.path.abspath(WAV_AUDIO_DIR)}")
    print(f"Output Opus Directory: {os.path.abspath(OPUS_OUTPUT_DIR)}")
    if ENABLE_NORMALIZATION:
        print(f"Normalization Enabled: Target {NORMALIZATION_TARGET_DBFS} dBFS")
    else:
        print("Normalization Disabled.")
    print(f"Opus Bitrate: {OPUS_BITRATE}")

    if not os.path.isdir(WAV_AUDIO_DIR):
        print(f"Error: Input WAV directory '{WAV_AUDIO_DIR}' not found.")
        exit()

    if not os.path.exists(OPUS_OUTPUT_DIR):
        os.makedirs(OPUS_OUTPUT_DIR)
        print(f"Created output Opus directory: {OPUS_OUTPUT_DIR}")

    wav_files = glob.glob(os.path.join(WAV_AUDIO_DIR, "ch_*.wav"))

    if not wav_files:
        print(f"No WAV files found in '{WAV_AUDIO_DIR}' matching 'ch_*.wav'.")
        exit()

    print(f"\nFound {len(wav_files)} WAV files to process.")

    processed_count = 0
    skipped_count = 0 # New counter for skipped files
    failed_count = 0

    for wav_file_path in sorted(wav_files):
        base_filename = os.path.splitext(os.path.basename(wav_file_path))[0]
        opus_file_path = os.path.join(OPUS_OUTPUT_DIR, f"{base_filename}.opus")

        # --- MODIFICATION START: Check if Opus file already exists ---
        if os.path.exists(opus_file_path):
            print(f"Skipping: Output file '{opus_file_path}' already exists.")
            skipped_count += 1
            continue  # Move to the next WAV file
        # --- MODIFICATION END ---

        if convert_wav_to_opus(wav_file_path, opus_file_path,
                               bitrate=OPUS_BITRATE,
                               apply_normalization=ENABLE_NORMALIZATION,
                               target_dbfs=NORMALIZATION_TARGET_DBFS):
            processed_count += 1
            if DELETE_ORIGINAL_WAV:
                try:
                    os.remove(wav_file_path)
                    print(f"  Deleted original WAV: {wav_file_path}")
                except Exception as e:
                    print(f"  Error deleting original WAV {wav_file_path}: {e}")
        else:
            failed_count += 1

    print(f"\n--- Processing Complete ---")
    print(f"Successfully processed: {processed_count} files.")
    print(f"Skipped (already exist): {skipped_count} files.") # New line for skipped count
    print(f"Failed processing   : {failed_count} files.")
    if DELETE_ORIGINAL_WAV and processed_count > 0 :
        print(f"Original WAV files were set to be deleted upon successful processing.")
    elif not DELETE_ORIGINAL_WAV:
        print(f"Original WAV files in '{WAV_AUDIO_DIR}' have been preserved.")
    print(f"Opus files are saved in: {OPUS_OUTPUT_DIR}")
