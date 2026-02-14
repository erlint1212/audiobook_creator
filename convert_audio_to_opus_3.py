import glob
import os
import sys

from pydub import AudioSegment

# --- 1. WINDOWS UNICODE FIX ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# --- Configuration ---
# 1. Dynamic Inputs from GUI
# Defaults are fallbacks for testing
WAV_AUDIO_DIR = os.getenv("WAV_AUDIO_DIR", "generated_audio_MistakenFairy")
OPUS_OUTPUT_DIR = os.getenv("OPUS_OUTPUT_DIR", "generated_audio_MistakenFairy_opus")

# Opus Export Settings
# 48k is excellent for speech; 32k is the sweet spot for file size vs quality.
OPUS_BITRATE = "48k"

# Normalization Settings
ENABLE_NORMALIZATION = True
NORMALIZATION_TARGET_DBFS = -20.0  # Industry standard for clear, consistent narration.

DELETE_ORIGINAL_WAV = False  # Keep as False until you verify the Opus quality
# --- End Configuration ---


def normalize_audio(sound, target_dbfs):
    """Normalizes a pydub AudioSegment object to target dBFS."""
    if sound.dBFS == float("-inf"):
        print("   Warning: Audio segment is silent, skipping normalization.")
        return sound
    change_in_dbfs = target_dbfs - sound.dBFS
    return sound.apply_gain(change_in_dbfs)


def convert_wav_to_opus(
    wav_filepath,
    opus_filepath,
    bitrate="48k",
    apply_normalization=False,
    target_dbfs=-20.0,
):
    """Converts a WAV file to Opus, optionally normalizing and converting to mono."""
    try:
        print(
            f"Processing: {os.path.basename(wav_filepath)} -> {os.path.basename(opus_filepath)}"
        )
        audio = AudioSegment.from_wav(wav_filepath)

        # 1. Apply Normalization
        if apply_normalization:
            print(f"   Normalizing to {target_dbfs} dBFS...")
            audio = normalize_audio(audio, target_dbfs)

        # 2. Force Mono
        # Audiobooks don't need stereo. Mono cuts Opus file size in half without losing quality.
        if audio.channels > 1:
            print(f"   Info: Converting to mono for smaller file size.")
            audio = audio.set_channels(1)

        # 3. Export to Opus
        # Uses libopus codec via ffmpeg
        print(f"   Exporting Opus ({bitrate})...")
        audio.export(
            opus_filepath,
            format="opus",
            parameters=["-c:a", "libopus", "-b:a", bitrate],
        )

        print(f"   Success.")
        return True
    except Exception as e:
        print(f"   Error processing {wav_filepath}: {e}")
        return False


if __name__ == "__main__":
    print(f"--- Audio Processing & Opus Conversion ---")
    print(f"Input: {WAV_AUDIO_DIR}")
    print(f"Output: {OPUS_OUTPUT_DIR}")

    if not os.path.isdir(WAV_AUDIO_DIR):
        print(f"Error: Input directory '{WAV_AUDIO_DIR}' not found.")
        # If run via GUI, we exit cleanly so the pipe catches the error
        sys.exit(1)

    if not os.path.exists(OPUS_OUTPUT_DIR):
        os.makedirs(OPUS_OUTPUT_DIR)

    # Search for files matching any WAV pattern (handling different naming conventions)
    wav_files = sorted(glob.glob(os.path.join(WAV_AUDIO_DIR, "*.wav")))

    if not wav_files:
        print(f"No WAV files found in '{WAV_AUDIO_DIR}'.")
        sys.exit(0)  # Not an error, just nothing to do

    print(
        f"Found {len(wav_files)} WAV files. Normalization: {'ON' if ENABLE_NORMALIZATION else 'OFF'}"
    )

    processed = 0
    skipped = 0
    failed = 0

    for wav_path in wav_files:
        filename_no_ext = os.path.splitext(os.path.basename(wav_path))[0]
        opus_path = os.path.join(OPUS_OUTPUT_DIR, f"{filename_no_ext}.opus")

        # Skip if already converted
        if os.path.exists(opus_path):
            print(f"Skipping: '{filename_no_ext}.opus' already exists.")
            skipped += 1
            continue

        success = convert_wav_to_opus(
            wav_path,
            opus_path,
            bitrate=OPUS_BITRATE,
            apply_normalization=ENABLE_NORMALIZATION,
            target_dbfs=NORMALIZATION_TARGET_DBFS,
        )

        if success:
            processed += 1
            if DELETE_ORIGINAL_WAV:
                try:
                    os.remove(wav_path)
                    print(f"   Deleted original WAV.")
                except Exception as e:
                    print(f"   Warning: Could not delete WAV: {e}")
        else:
            failed += 1

    print(f"\n--- Done ---")
    print(f"Processed: {processed} | Skipped: {skipped} | Failed: {failed}")
