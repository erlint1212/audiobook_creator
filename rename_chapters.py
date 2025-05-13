import os
import re
import shutil # For a safer backup option if you prefer

# --- Configuration ---
SOURCE_DIRECTORY = "scraped_tileas_worries_mystic"
NEW_FILENAME_PREFIX = "ch_"
START_NUMBER = 148
DRY_RUN = False # IMPORTANT: True to only print actions, False to actually rename files.

def extract_chapter_parts_for_sort(filename):
    """
    Helper function to extract chapter and part numbers for robust sorting.
    Handles filenames like 'chapter_77.txt' and 'chapter_77.1.txt'.
    Returns a tuple (chapter_number, part_number).
    """
    # Regex to capture base chapter number and optional part number
    # Ignores case for "chapter_"
    match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        # If group 2 (part number) exists, use it, otherwise default to 0 (main chapter)
        part_num = int(match.group(2)) if match.group(2) else 0
        return (chapter_num, part_num)
    else:
        # Return infinity to sort non-matching/unexpected files last
        return (float('inf'), float('inf'))

def rename_chapter_files(source_dir, new_prefix, start_num, dry_run=True):
    """
    Renames chapter files in the source directory to a new sequential format.
    Example: chapter_51.txt -> ch_147.txt
             chapter_77.1.txt -> ch_148.txt (if it's next in sorted order)
    """
    print(f"--- Starting Chapter Renaming Process ---")
    if dry_run:
        print("!!! DRY RUN MODE: No files will actually be renamed. !!!")
    print(f"Source directory: '{source_dir}'")
    print(f"New filename prefix: '{new_prefix}'")
    print(f"Starting number for new filenames: {start_num}")

    if not os.path.isdir(source_dir):
        print(f"Error: Source directory '{source_dir}' not found. Aborting.")
        return

    # --- 1. Get and Sort Current Chapter Files ---
    try:
        all_files = os.listdir(source_dir)
        # Filter for .txt files that match the expected 'chapter_...' pattern
        current_chapter_files = [
            f for f in all_files
            if f.lower().startswith('chapter_') and f.lower().endswith('.txt') and \
               re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', f, re.IGNORECASE)
        ]

        if not current_chapter_files:
            print(f"No files matching 'chapter_....txt' found in '{source_dir}'. Nothing to do.")
            return

        # Sort files based on chapter and part number
        current_chapter_files.sort(key=extract_chapter_parts_for_sort)
        print(f"Found {len(current_chapter_files)} chapter files to rename. Sorted order:")
        # for f_idx, f_name in enumerate(current_chapter_files): # Optional: print sorted list
        #     print(f"  {f_idx+1}. {f_name}")

    except Exception as e:
        print(f"Error listing or sorting files in '{source_dir}': {e}. Aborting.")
        return

    # --- 2. Perform Renaming ---
    renamed_count = 0
    current_new_number = start_num

    print(f"\n--- Proposed Renames (or Actual if DRY_RUN is False) ---")
    for old_filename in current_chapter_files:
        new_filename = f"{new_prefix}{current_new_number:03d}.txt" # Ensures 3-digit padding, e.g., ch_147.txt

        old_filepath = os.path.join(source_dir, old_filename)
        new_filepath = os.path.join(source_dir, new_filename)

        print(f"'{old_filename}'  ->  '{new_filename}'")

        if not dry_run:
            try:
                if os.path.exists(new_filepath):
                    print(f"  Warning: Target file '{new_filename}' already exists! Skipping rename for '{old_filename}'.")
                    continue # Avoid overwriting existing files with the new name

                os.rename(old_filepath, new_filepath)
                renamed_count += 1
            except Exception as e:
                print(f"  Error renaming '{old_filename}' to '{new_filename}': {e}")

        current_new_number += 1

    # --- 3. Final Summary ---
    print("\n--- Renaming Summary ---")
    if dry_run:
        print(f"{len(current_chapter_files)} files would be processed (DRY RUN).")
        print("No actual changes were made.")
    else:
        print(f"Total files processed: {len(current_chapter_files)}")
        print(f"Files successfully renamed: {renamed_count}")
        if len(current_chapter_files) != renamed_count:
            print(f"Files skipped or failed: {len(current_chapter_files) - renamed_count}")
    print("--- Process Complete ---")

if __name__ == "__main__":
    # --- Optional: Create a backup before running (recommended) ---
    # if not DRY_RUN and os.path.isdir(SOURCE_DIRECTORY):
    #     backup_dir = SOURCE_DIRECTORY + "_backup_" + time.strftime("%Y%m%d_%H%M%S")
    #     try:
    #         shutil.copytree(SOURCE_DIRECTORY, backup_dir)
    #         print(f"Successfully created backup at '{backup_dir}'")
    #     except Exception as e:
    #         print(f"Error creating backup: {e}. Proceed with caution or backup manually.")
    #         if input("Continue without backup? (yes/no): ").lower() != 'yes':
    #             print("Aborting.")
    #             exit()

    rename_chapter_files(SOURCE_DIRECTORY, NEW_FILENAME_PREFIX, START_NUMBER, dry_run=DRY_RUN)
