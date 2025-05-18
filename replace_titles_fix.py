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

def replace_chapter_titles_sequentially(titles_filepath, chapters_dir): # Renamed function for clarity
    """
    Replaces the first line (title) of chapter text files with titles
    read sequentially from a specified titles file.
    Handles split chapters like chapter_XX.Y.txt by appending (Part Y) if not already in title.
    """
    print(f"Starting title replacement process (Sequential Mode)...")
    print(f" - Reading correct titles sequentially from: {titles_filepath}")
    print(f" - Updating files in directory: {chapters_dir}")

    # --- 1. Read Correct Titles as an Ordered List ---
    correct_titles_list = []
    try:
        with open(titles_filepath, 'r', encoding='utf-8') as f:
            for line in f:
                title = line.strip()
                if title: # Ensure it's not an empty line
                    correct_titles_list.append(title)
        if not correct_titles_list:
            print(f"Error: No titles found in {titles_filepath}. Aborting.")
            return
        print(f"  Successfully read {len(correct_titles_list)} titles sequentially.")
    except FileNotFoundError:
        print(f"Error: Titles file not found at '{titles_filepath}'. Aborting.")
        return
    except Exception as e:
        print(f"Error reading titles file '{titles_filepath}': {e}. Aborting.")
        return

    # --- 2. Get and Sort Chapter Files ---
    chapter_files = []
    try:
        all_files_in_dir = os.listdir(chapters_dir)
        # Filter for files matching the chapter pattern (including parts)
        chapter_files = [f for f in all_files_in_dir if re.match(r'chapter_\d+(?:\.\d+)?\.txt$', f, re.IGNORECASE)]
        if not chapter_files:
             print(f"Error: No chapter files (like 'chapter_XX.txt' or 'chapter_XX.Y.txt') found in '{chapters_dir}'. Aborting.")
             return

        chapter_files.sort(key=extract_chapter_parts_for_sort)
        print(f"  Found {len(chapter_files)} chapter text files to process.")
        # print(f"  Sorted file order: {chapter_files}") # Optional
    except FileNotFoundError:
        print(f"Error: Chapters directory not found at '{chapters_dir}'. Aborting.")
        return
    except Exception as e:
        print(f"Error listing or sorting files in '{chapters_dir}': {e}. Aborting.")
        return

    # --- 3. Replace Titles using Sequential Matching ---
    updated_count = 0
    skipped_count = 0
    error_count = 0

    num_to_process = min(len(chapter_files), len(correct_titles_list))
    if len(chapter_files) != len(correct_titles_list):
        print(f"\nWarning: Mismatch in counts! Files: {len(chapter_files)}, Titles: {len(correct_titles_list)}.")
        print(f"         Will process {num_to_process} items based on the shorter list.")

    print(f"\nProcessing {num_to_process} files...")

    for i in range(num_to_process):
        filename = chapter_files[i]
        raw_title_from_list = correct_titles_list[i] # Get title by list index
        filepath = os.path.join(chapters_dir, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines: # Check if the file is empty
                print(f"  Skipping empty file: {filename}")
                skipped_count += 1
                continue

            original_content_lines = lines[1:] # Keep content from the second line onwards

            # Determine the final display title, potentially adding (Part X)
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

    # --- 4. Final Summary ---
    print("\n--- Title Replacement Summary ---")
    print(f"Total titles read from list: {len(correct_titles_list)}")
    print(f"Total chapter files found: {len(chapter_files)}")
    print(f"Files successfully updated: {updated_count}")
    print(f"Files skipped (empty, or due to list length mismatch): {skipped_count + (max(len(chapter_files), len(correct_titles_list)) - num_to_process)}")
    print(f"Errors encountered during file processing: {error_count}")
    print("--- Process Complete ---")

# --- Configuration ---
TITLES_FILE_PATH = os.path.join("chapter_titles", "chapter_titles.txt")
CHAPTERS_DIRECTORY = "scraped_tileas_worries_mystic"

if __name__ == "__main__":
    replace_chapter_titles_sequentially(TITLES_FILE_PATH, CHAPTERS_DIRECTORY)
