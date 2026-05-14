import glob
import os
import sys

# --- 1. WINDOWS UNICODE FIX ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# --- Configuration ---
# Inputs from GUI (Environment Variables)
WAV_AUDIO_DIR = os.getenv("WAV_AUDIO_DIR", "03_Audio_WAV")
OPUS_OUTPUT_DIR = os.getenv("OPUS_OUTPUT_DIR", "04_Audio_Opus")

# Minimum size (in bytes) for an Opus file to be considered "valid"
# Anything smaller is likely a corrupt or empty file
MIN_OPUS_SIZE_BYTES = 1024  # 1 KB

# Set to True to actually delete files; False for dry-run mode
DRY_RUN = os.getenv("WAV_CLEANUP_DRY_RUN", "false").lower() == "true"


def cleanup_wav_files():
    """
    Scans the WAV directory and deletes any WAV file that has a corresponding
    valid Opus file in the Opus directory.
    """
    print("--- WAV Cleanup ---")
    print(f"WAV Source:  {WAV_AUDIO_DIR}")
    print(f"Opus Source: {OPUS_OUTPUT_DIR}")
    print(f"Mode: {'DRY RUN (no files will be deleted)' if DRY_RUN else 'LIVE (files will be deleted)'}")

    if not os.path.isdir(WAV_AUDIO_DIR):
        print(f"Error: WAV directory not found: {WAV_AUDIO_DIR}")
        sys.exit(1)

    if not os.path.isdir(OPUS_OUTPUT_DIR):
        print(f"Error: Opus directory not found: {OPUS_OUTPUT_DIR}")
        print("Cannot verify Opus files exist before deletion. Aborting.")
        sys.exit(1)

    wav_files = sorted(glob.glob(os.path.join(WAV_AUDIO_DIR, "*.wav")))

    if not wav_files:
        print(f"No WAV files found in '{WAV_AUDIO_DIR}'. Nothing to clean.")
        sys.exit(0)

    print(f"\nFound {len(wav_files)} WAV files to check.\n")

    deleted = 0
    skipped_no_opus = 0
    skipped_small_opus = 0
    space_freed_bytes = 0
    errors = 0

    for wav_path in wav_files:
        filename_no_ext = os.path.splitext(os.path.basename(wav_path))[0]
        opus_path = os.path.join(OPUS_OUTPUT_DIR, f"{filename_no_ext}.opus")

        # Check 1: Does the corresponding Opus file exist?
        if not os.path.exists(opus_path):
            print(f"[SKIP] {filename_no_ext}.wav - No matching Opus file found.")
            skipped_no_opus += 1
            continue

        # Check 2: Is the Opus file a reasonable size? (Sanity check against corrupt files)
        try:
            opus_size = os.path.getsize(opus_path)
        except OSError as e:
            print(f"[ERROR] Could not stat Opus file {filename_no_ext}.opus: {e}")
            errors += 1
            continue

        if opus_size < MIN_OPUS_SIZE_BYTES:
            print(f"[SKIP] {filename_no_ext}.wav - Opus file too small ({opus_size} bytes), may be corrupt.")
            skipped_small_opus += 1
            continue

        # Both checks passed - safe to delete the WAV
        try:
            wav_size = os.path.getsize(wav_path)

            if DRY_RUN:
                print(f"[DRY RUN] Would delete: {filename_no_ext}.wav ({wav_size / (1024*1024):.2f} MB)")
            else:
                os.remove(wav_path)
                print(f"[DELETED] {filename_no_ext}.wav ({wav_size / (1024*1024):.2f} MB)")

            deleted += 1
            space_freed_bytes += wav_size

        except Exception as e:
            print(f"[ERROR] Could not delete {filename_no_ext}.wav: {e}")
            errors += 1

    # Summary
    print("\n--- Cleanup Summary ---")
    if DRY_RUN:
        print(f"Would have deleted: {deleted} WAV files")
        print(f"Would have freed: {space_freed_bytes / (1024*1024*1024):.2f} GB")
    else:
        print(f"Deleted: {deleted} WAV files")
        print(f"Space freed: {space_freed_bytes / (1024*1024*1024):.2f} GB")
    print(f"Skipped (no matching Opus): {skipped_no_opus}")
    print(f"Skipped (Opus too small):   {skipped_small_opus}")
    if errors:
        print(f"Errors: {errors}")
    print("Done.")


if __name__ == "__main__":
    cleanup_wav_files()
