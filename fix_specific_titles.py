import os
import re

def extract_chapter_parts_for_sort(filename):
    """
    Helper function to extract chapter and part numbers for robust sorting.
    Returns a tuple (chapter_number, part_number).
    Handles filenames like 'chapter_77.txt' and 'chapter_77.1.txt'.
    """
    match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        part_num = int(match.group(2)) if match.group(2) else 0
        return (chapter_num, part_num)
    else:
        return (float('inf'), float('inf'))

def fix_chapter_titles_from_offset(titles_filepath, chapters_dir,
                                   start_filename_chapter_num, # e.g., 86 for chapter_86.txt
                                   start_title_marker):        # e.g., "Chapter 1 – Miles and the Rumored Transfer Student"
    """
    Fixes titles for chapter files starting from a specific chapter number,
    mapping them to titles in titles_filepath starting from a specific marker.
    """
    print(f"--- Starting Specific Title Fix Process ---")
    print(f"Reading all titles from: {titles_filepath}")
    print(f"Updating files in directory: {chapters_dir}")
    print(f"Will start processing files from chapter number (in filename): {start_filename_chapter_num}")
    print(f"Will start matching titles from line: '{start_title_marker}'")

    # --- 1. Read ALL Correct Titles as an Ordered List ---
    all_titles_from_file = []
    try:
        with open(titles_filepath, 'r', encoding='utf-8') as f:
            for line in f:
                title = line.strip()
                if title:
                    all_titles_from_file.append(title)
        if not all_titles_from_file:
            print(f"Error: No titles found in {titles_filepath}. Aborting.")
            return
        print(f"  Successfully read {len(all_titles_from_file)} total titles.")
    except FileNotFoundError:
        print(f"Error: Titles file not found at '{titles_filepath}'. Aborting.")
        return
    except Exception as e:
        print(f"Error reading titles file '{titles_filepath}': {e}. Aborting.")
        return

    # --- 2. Find the starting index for titles in the list ---
    try:
        start_title_index = all_titles_from_file.index(start_title_marker)
        print(f"  Found start title marker at index {start_title_index} in the titles list.")
    except ValueError:
        print(f"Error: Start title marker '{start_title_marker}' not found in {titles_filepath}. Aborting.")
        return
    
    # Titles to be used for this specific fix, starting from the marker
    relevant_titles_list = all_titles_from_file[start_title_index:]
    if not relevant_titles_list:
        print(f"Error: No titles found after the marker '{start_title_marker}'. Aborting.")
        return
    print(f"  Will use {len(relevant_titles_list)} titles starting from the marker.")


    # --- 3. Get and Sort All Chapter Files in the Directory ---
    all_chapter_files_in_dir = []
    try:
        disk_files = os.listdir(chapters_dir)
        all_chapter_files_in_dir = [f for f in disk_files if re.match(r'chapter_\d+(?:\.(\d+))?\.txt$', f, re.IGNORECASE)]
        if not all_chapter_files_in_dir:
             print(f"Error: No chapter files found in '{chapters_dir}'. Aborting.")
             return
        all_chapter_files_in_dir.sort(key=extract_chapter_parts_for_sort)
        print(f"  Found and sorted {len(all_chapter_files_in_dir)} chapter files in directory.")
    except FileNotFoundError: # Should not happen if previous check passed, but good practice
        print(f"Error: Chapters directory not found at '{chapters_dir}'. Aborting.")
        return
    except Exception as e:
        print(f"Error listing or sorting files in '{chapters_dir}': {e}. Aborting.")
        return

    # --- 4. Find the starting index for files to process ---
    start_file_index = -1
    for idx, filename in enumerate(all_chapter_files_in_dir):
        # Extract base chapter number from filename like chapter_86.txt or chapter_86.1.txt
        match = re.match(r'chapter_(\d+)(?:\.\d+)?\.txt$', filename, re.IGNORECASE)
        if match:
            file_base_num = int(match.group(1))
            if file_base_num == start_filename_chapter_num:
                # We want the first occurrence of this chapter number (e.g. chapter_86.txt or chapter_86.1.txt)
                start_file_index = idx
                print(f"  Starting file processing from: '{filename}' (at index {start_file_index} in sorted list).")
                break 
    
    if start_file_index == -1:
        print(f"Error: Could not find a starting file matching chapter number {start_filename_chapter_num} (e.g., chapter_{start_filename_chapter_num}.txt). Aborting.")
        return

    files_to_process = all_chapter_files_in_dir[start_file_index:]
    if not files_to_process:
        print("Error: No files to process from the determined start point. Aborting")
        return
    print(f"  Will attempt to update {len(files_to_process)} files from '{files_to_process[0]}' onwards.")


    # --- 5. Replace Titles for the selected range of files ---
    updated_count = 0
    skipped_count = 0
    error_count = 0

    num_can_process = min(len(files_to_process), len(relevant_titles_list))
    if len(files_to_process) != len(relevant_titles_list):
        print(f"\nWarning: Number of files to process ({len(files_to_process)}) does not match number of available titles from marker ({len(relevant_titles_list)}).")
        print(f"         Will process {num_can_process} items.")

    print(f"\nProcessing {num_can_process} files...")

    for i in range(num_can_process):
        filename = files_to_process[i]
        raw_title_from_list = relevant_titles_list[i]
        filepath = os.path.join(chapters_dir, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                print(f"  Skipping empty file: {filename}")
                skipped_count += 1
                continue

            original_content_lines = lines[1:]

            display_title = raw_title_from_list
            fn_part_match = re.match(r'chapter_\d+\.(\d+)\.txt$', filename, re.IGNORECASE)
            title_already_has_part = re.search(r'\s*\(Part \d+\)$', raw_title_from_list, re.IGNORECASE)

            if fn_part_match and not title_already_has_part:
                part_num_from_fn = fn_part_match.group(1)
                display_title = f"{raw_title_from_list} (Part {part_num_from_fn})"
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(display_title + '\n')
                f.writelines(original_content_lines)
            
            # print(f"  Updated title for: {filename} with: '{display_title}'") # Verbose
            updated_count += 1

        except Exception as e:
            print(f"  Error processing file '{filename}': {e}")
            error_count += 1
            
    # --- 6. Final Summary ---
    print("\n--- Specific Title Fix Summary ---")
    print(f"Files targeted for update (from '{files_to_process[0]}' onwards): {len(files_to_process)}")
    print(f"Titles available from marker ('{start_title_marker}'): {len(relevant_titles_list)}")
    print(f"Files successfully updated: {updated_count}")
    skipped_due_to_mismatch = max(0, len(files_to_process) - num_can_process) + \
                              max(0, len(relevant_titles_list) - num_can_process)
    print(f"Files skipped (empty, or due to list length mismatch): {skipped_count + skipped_due_to_mismatch}")
    print(f"Errors encountered during file processing: {error_count}")
    print("--- Process Complete ---")

# --- Configuration ---
TITLES_FILE_PATH = os.path.join("chapter_titles", "chapter_titles.txt")
CHAPTERS_DIRECTORY = "scraped_tileas_worries_mystic" # Directory with chapter_XX.txt files

# Define where the fix should start for filenames and titles
# This is the chapter number in your FILENAME (e.g., 86 for chapter_86.txt)
# that corresponds to the START_TITLE_MARKER below.
START_FILENAME_CHAPTER_NUMBER = 86 # The file like chapter_86.txt is where the new title sequence begins

# This is the exact title string from chapter_titles.txt where the new sequence of titles begins
START_TITLE_MARKER_IN_FILE = "Chapter 1 – Miles and the Rumored Transfer Student"


if __name__ == "__main__":
    fix_chapter_titles_from_offset(
        TITLES_FILE_PATH,
        CHAPTERS_DIRECTORY,
        START_FILENAME_CHAPTER_NUMBER,
        START_TITLE_MARKER_IN_FILE
    )
