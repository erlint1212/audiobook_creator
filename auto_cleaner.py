import argparse
import json
import os

# --- Directory Configuration ---
# Change these if your project structure is slightly different
DIR_TRANSLATED = "02_Translated"
DIR_WAV = "03_Audio_WAV"
DIR_OPUS = "04_Audio_Opus"  # Adjust if your opus files are saved in a different folder
JSON_REPORT_FILE = "early_cutoff_chapters.json"


def delete_file(filepath):
    """Deletes a file if it exists and logs the action."""
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            print(f"  🗑️  [DELETED] {filepath}")
            return True
        except Exception as e:
            print(f"  ❌ [ERROR] Could not delete {filepath}: {e}")
            return False
    return False


def clean_chapter(novel_dir, chapter_filename):
    """Deletes the .txt, .wav, and .opus files for a given chapter base name."""
    # Ensure we just have the base name (e.g., "ch_0484" instead of "ch_0484.txt")
    base_name = os.path.splitext(chapter_filename)[0]

    # Construct full paths
    trans_path = os.path.join(novel_dir, DIR_TRANSLATED, f"{base_name}.txt")
    wav_path = os.path.join(novel_dir, DIR_WAV, f"{base_name}.wav")
    opus_path = os.path.join(novel_dir, DIR_OPUS, f"{base_name}.opus")

    print(f"\nTargeting: {base_name}")

    deleted_any = False
    if delete_file(trans_path):
        deleted_any = True
    if delete_file(wav_path):
        deleted_any = True
    if delete_file(opus_path):
        deleted_any = True

    if not deleted_any:
        print(f"  [SKIPPED] No files existed for this chapter.")


def auto_clean_from_json(novel_dir):
    """Reads the early_cutoff_chapters.json report and deletes all flagged files, updating the JSON."""
    json_path = os.path.join(novel_dir, JSON_REPORT_FILE)

    if not os.path.exists(json_path):
        print(f"Error: No JSON report found at '{json_path}'.")
        print("Run the detection script first to generate the report.")
        return

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            suspects = json.load(f)
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return

    if not suspects:
        print("JSON report is empty. Nothing to clean!")
        return

    print(f"Found {len(suspects)} flagged chapters in {JSON_REPORT_FILE}.")

    # Prompt for safety confirmation
    confirm = input(
        f"Are you sure you want to delete the translation, WAV, and Opus files for these {len(suspects)} chapters? (y/N): "
    )
    if confirm.lower() != "y":
        print("Aborting.")
        return

    # Convert keys to a list so we can modify the dictionary while iterating
    for chapter_filename in list(suspects.keys()):
        clean_chapter(novel_dir, chapter_filename)

        # Pop the chapter from the dictionary now that it's clean
        suspects.pop(chapter_filename)

        # Update the JSON file immediately so our progress is saved
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(suspects, f, indent=4)

    # After the loop, the dictionary (and JSON file) will be empty!
    print(
        "\n✅ Auto-clean complete. All processed chapters have been removed from the JSON report."
    )

    # We can still offer to delete the empty JSON file just to tidy up the folder
    cleanup_json = input(
        f"The '{JSON_REPORT_FILE}' is now empty. Do you want to delete it? (y/N): "
    )
    if cleanup_json.lower() == "y":
        delete_file(json_path)


def main():
    parser = argparse.ArgumentParser(
        description="Clean up malformed translations and their generated audio files."
    )

    # REQUIRED: The specific novel folder name
    parser.add_argument(
        "novel",
        type=str,
        help="The exact folder name of the novel (e.g., The_Blood_Princess_And_The_Knight)",
    )

    # Optional arguments for targeting specific files instead of the JSON
    parser.add_argument(
        "--chapter",
        type=str,
        help="Target a specific chapter to clean instead of using the JSON (e.g., 'ch_0484.txt' or 'ch_0484')",
        default=None,
    )

    parser.add_argument(
        "--base",
        type=str,
        default="Novels",
        help="Base directory containing the novel folders (default: 'Novels')",
    )

    args = parser.parse_args()
    novel_path = os.path.join(args.base, args.novel)

    if not os.path.exists(novel_path):
        print(f"Error: Novel directory '{novel_path}' does not exist.")
        return

    # Check if user wants to delete a specific chapter manually
    if args.chapter:
        confirm = input(
            f"Are you sure you want to delete text/audio for {args.chapter}? (y/N): "
        )
        if confirm.lower() == "y":
            clean_chapter(novel_path, args.chapter)
            # Note: We don't pop from JSON here since this is a manual, single-file override.
        else:
            print("Aborted.")
    else:
        # Default behavior: run the auto-cleaner based on the JSON
        auto_clean_from_json(novel_path)


if __name__ == "__main__":
    main()
