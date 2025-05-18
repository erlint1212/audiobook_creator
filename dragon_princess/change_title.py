# rename_chapters.py
import os
import re
from typing import List, Tuple

def rename_chapter_files(
    target_directory: str,
    file_pattern_regex: str = r"^(n\d+[a-zA-Z]{0,2})_(\d+)\.txt$", # Matches nCODE_CHAPTER.txt
    new_filename_prefix: str = "ch_",
    new_start_number: int = 1, # Default starting chapter number for the new scheme
    dry_run: bool = True # IMPORTANT: Set to False to actually rename files
) -> None:
    """
    Renames chapter files in a specified directory based on a pattern,
    sorting them by their original chapter number and assigning new iterative names.

    Args:
        target_directory (str): The path to the directory containing the chapter files.
        file_pattern_regex (str): Regex to match and capture parts of the old filenames.
                                  It should capture the series identifier (like ncode)
                                  and the old chapter number.
                                  Default: r"^(n\\d+[a-zA-Z]{0,2})_(\\d+)\\.txt$"
                                  Group 1: ncode (e.g., "n9045bm")
                                  Group 2: chapter number (e.g., "232")
        new_filename_prefix (str): The prefix for the new filenames (e.g., "ch_").
        new_start_number (int): The starting number for the new iterative filenames.
        dry_run (bool): If True, only print what would be renamed.
                        If False, perform actual renaming. Defaults to True.
    """

    if not os.path.isdir(target_directory):
        print(f"Error: Directory not found: {target_directory}")
        return

    print(f"Scanning directory: {target_directory}")
    print(f"File pattern: {file_pattern_regex}")
    print(f"New filename prefix: '{new_filename_prefix}'")
    print(f"New start number: {new_start_number}")
    if dry_run:
        print("--- DRY RUN MODE: No files will actually be renamed. ---")
    else:
        print("--- LIVE RUN MODE: Files WILL be renamed. ---")
        # Add a small safety delay and confirmation for live runs
        confirm = input("Are you sure you want to proceed with renaming files? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Renaming cancelled by user.")
            return
        # print("Proceeding with renaming in 3 seconds...")
        # time.sleep(3) # Uncomment if you want an actual time delay

    files_to_rename: List[Tuple[str, int, str]] = [] # (original_filename, old_chapter_no, ncode_part)

    for filename in os.listdir(target_directory):
        match = re.match(file_pattern_regex, filename)
        if match:
            try:
                ncode_part: str = match.group(1)
                old_chapter_no_str: str = match.group(2)
                old_chapter_no: int = int(old_chapter_no_str)
                files_to_rename.append((filename, old_chapter_no, ncode_part))
            except ValueError:
                print(f"Warning: Could not parse chapter number from '{filename}'. Skipping.")
            except IndexError:
                print(f"Warning: Regex did not capture expected groups from '{filename}'. Check regex. Skipping.")

    if not files_to_rename:
        print("No files found matching the pattern.")
        return

    # Sort files by their original chapter number
    files_to_rename.sort(key=lambda x: x[1])

    print(f"\nFound {len(files_to_rename)} files to rename (sorted by old chapter number):")

    current_new_number: int = new_start_number
    renamed_count: int = 0
    failed_count: int = 0

    for original_filename, old_chapter_no, _ in files_to_rename:
        new_filename: str = f"{new_filename_prefix}{current_new_number}.txt"
        old_filepath: str = os.path.join(target_directory, original_filename)
        new_filepath: str = os.path.join(target_directory, new_filename)

        print(f"  Processing: '{original_filename}' (Old chapter: {old_chapter_no})")
        print(f"    -> Proposed new name: '{new_filename}'")

        if os.path.exists(new_filepath) and new_filepath != old_filepath :
            print(f"    Error: Target filename '{new_filename}' already exists. Skipping to avoid overwrite.")
            failed_count +=1
            # Potentially increment current_new_number here if you want unique names even if source is skipped
            # current_new_number += 1
            continue


        if not dry_run:
            try:
                os.rename(old_filepath, new_filepath)
                print(f"    SUCCESS: Renamed '{original_filename}' to '{new_filename}'")
                renamed_count += 1
            except OSError as e:
                print(f"    ERROR: Could not rename '{original_filename}': {e}")
                failed_count += 1
        else:
            # In dry run, we still increment to show the full sequence
            pass


        current_new_number += 1

    print("\n--- Renaming Summary ---")
    if dry_run:
        print(f"DRY RUN COMPLETE: {len(files_to_rename)} files would have been processed.")
        print("No actual changes were made.")
    else:
        print(f"LIVE RUN COMPLETE:")
        print(f"  Successfully renamed: {renamed_count} files")
        print(f"  Failed to rename: {failed_count} files")

if __name__ == "__main__":
    # --- Configuration ---
    # IMPORTANT: SET THE CORRECT DIRECTORY WHERE YOUR 'n9045bm_232.txt' etc. FILES ARE!
    directory_to_scan: str = "./scraped_syosetu_n9045bm" # Example, adjust this path!

    # Regex explanation for default:
    # ^                   : Start of the string
    # (n\d+[a-zA-Z]{0,2}) : Capture group 1 (ncode part)
    #                       n - literal 'n'
    #                       \d+ - one or more digits
    #                       [a-zA-Z]{0,2} - zero to two letters (for ncodes like 'n123ab')
    # _                   : Literal underscore
    # (\d+)               : Capture group 2 (old chapter number)
    #                       \d+ - one or more digits
    # \.txt               : Literal ".txt"
    # $                   : End of the string
    # Example match: "n9045bm_232.txt" -> group 1: "n9045bm", group 2: "232"
    # Example match: "n123_1.txt"      -> group 1: "n123",    group 2: "1"
    # Example match: "n123ab_10.txt"   -> group 1: "n123ab",  group 2: "10"
    regex_pattern: str = r"^(n\d+[a-zA-Z]{0,2})_(\d+)\.txt$"

    output_prefix: str = "ch_"
    # Set the starting number for your new file names.
    # If your first original chapter was "n9045bm_232.txt" and you want it to become "ch_259.txt",
    # and the files are sorted, this will be the number for the *lowest numbered original chapter*.
    output_start_number: int = 259 # As per your example "ch_259"

    # --- Execution ---
    # Run in DRY RUN mode first to see what changes would be made:
    rename_chapter_files(
        target_directory=directory_to_scan,
        file_pattern_regex=regex_pattern,
        new_filename_prefix=output_prefix,
        new_start_number=output_start_number,
        dry_run=False
    )

    # If you are satisfied with the DRY RUN output, change dry_run to False:
    # print("\n\n--- !!! WARNING: Next run is LIVE if dry_run is set to False !!! ---")
    # rename_chapter_files(
    #     target_directory=directory_to_scan,
    #     file_pattern_regex=regex_pattern,
    #     new_filename_prefix=output_prefix,
    #     new_start_number=output_start_number,
    #     dry_run=False # SET TO FALSE TO ACTUALLY RENAME
    # )
