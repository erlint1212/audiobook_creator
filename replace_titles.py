import os
import re # Import regular expressions

def extract_chapter_parts_for_sort(filename):
    """
    Helper function to extract chapter and part numbers for robust sorting.
    Returns a tuple (chapter_number, part_number).
    Handles filenames like 'chapter_77.txt' and 'chapter_77.1.txt'.
    """
    # Regex to capture base chapter number and optional part number
    match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        # If group 2 (part number) exists, use it, otherwise default to 0
        part_num = int(match.group(2)) if match.group(2) else 0
        return (chapter_num, part_num)
    else:
        # Return infinity to sort non-matching files last
        return (float('inf'), float('inf'))

def replace_chapter_titles(titles_filepath, chapters_dir):
    """
    Replaces the first line (title) of chapter text files with titles
    read from a specified titles file, looking up by chapter number.
    Handles split chapters like chapter_XX.Y.txt.
    """
    print(f"Starting title replacement process (Lookup Mode)...")
    print(f" - Reading correct titles from: {titles_filepath}")
    print(f" - Updating files in directory: {chapters_dir}")

    # --- 1. Read Correct Titles into a Dictionary ---
    correct_titles_dict = {}
    titles_read_count = 0
    try:
        with open(titles_filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                title = line.strip()
                if not title:
                    continue # Skip empty lines

                titles_read_count += 1
                # Extract chapter number from the title line itself
                # Regex looks for "Chapter XX" potentially followed by " –" or ":"
                match = re.match(r'Chapter (\d+)[ –:]?.*', title, re.IGNORECASE)
                if match:
                    chapter_num = int(match.group(1))
                    if chapter_num in correct_titles_dict:
                        print(f"  Warning: Duplicate chapter number {chapter_num} found in titles file near line {line_num}. Using the first one encountered.")
                    else:
                        correct_titles_dict[chapter_num] = title
                else:
                    print(f"  Warning: Could not extract chapter number from title line {line_num}: '{title[:50]}...'")

        if not correct_titles_dict:
            print(f"Error: No valid titles with extractable chapter numbers found in {titles_filepath}. Aborting.")
            return
        print(f"  Successfully read {titles_read_count} lines and mapped {len(correct_titles_dict)} titles to chapter numbers.")

    except FileNotFoundError:
        print(f"Error: Titles file not found at '{titles_filepath}'. Aborting.")
        return
    except Exception as e:
        print(f"Error reading titles file '{titles_filepath}': {e}. Aborting.")
        return

    # --- 2. Get and Sort Chapter Files ---
    chapter_files = []
    try:
        all_files = os.listdir(chapters_dir)
        # Filter for files matching the chapter pattern (including parts)
        chapter_files = [f for f in all_files if re.match(r'chapter_\d+(?:\.\d+)?\.txt$', f, re.IGNORECASE)]
        if not chapter_files:
             print(f"Error: No chapter files (like 'chapter_XX.txt' or 'chapter_XX.Y.txt') found in '{chapters_dir}'. Aborting.")
             return

        # Sort files using the improved sort key
        chapter_files.sort(key=extract_chapter_parts_for_sort)
        print(f"  Found {len(chapter_files)} chapter text files to process.")
        # print(f"  Sorted file order: {chapter_files}") # Optional: uncomment to verify sort order

    except FileNotFoundError:
        print(f"Error: Chapters directory not found at '{chapters_dir}'. Aborting.")
        return
    except Exception as e:
        print(f"Error listing or sorting files in '{chapters_dir}': {e}. Aborting.")
        return

    # --- 3. Replace Titles in Files using Dictionary Lookup ---
    updated_count = 0
    skipped_count = 0
    error_count = 0
    title_not_found_count = 0

    print(f"\nProcessing {len(chapter_files)} files...")

    for filename in chapter_files:
        filepath = os.path.join(chapters_dir, filename)

        # Extract base chapter number from filename
        match = re.match(r'chapter_(\d+)(?:\.\d+)?\.txt$', filename, re.IGNORECASE)
        if not match:
            print(f"  Skipping file with unexpected name format: {filename}")
            skipped_count += 1
            continue

        base_chapter_num = int(match.group(1))

        # Look up the correct title using the base chapter number
        correct_title = correct_titles_dict.get(base_chapter_num)

        if correct_title is None:
            print(f"  Warning: No title found in dictionary for chapter number {base_chapter_num} (from file {filename}). Skipping file.")
            title_not_found_count += 1
            skipped_count += 1
            continue

        # Proceed with file update
        try:
            # Read original content, skipping the first line
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if len(lines) < 1:
                print(f"  Skipping empty file: {filename}")
                skipped_count += 1
                continue # Skip empty files

            # Keep content from the second line onwards
            original_content_lines = lines[1:]

            # Write back with the correct title and original content
            with open(filepath, 'w', encoding='utf-8') as f:
                # Add part info to title ONLY if it's a part file (e.g., chapter_77.1.txt)
                part_match = re.match(r'chapter_\d+\.(\d+)\.txt$', filename, re.IGNORECASE)
                if part_match:
                     display_title = f"{correct_title} (Part {part_match.group(1)})"
                     f.write(display_title + '\n')
                else:
                     f.write(correct_title + '\n') # Write the looked-up title + newline

                f.writelines(original_content_lines) # Write the rest

            # print(f"  Updated title for: {filename} -> Chapter {base_chapter_num}") # Verbose
            updated_count += 1

        except Exception as e:
            print(f"  Error processing file '{filename}': {e}")
            error_count += 1

    # --- 4. Final Summary ---
    print("\n--- Title Replacement Summary ---")
    print(f"Total title lines read: {titles_read_count}")
    print(f"Titles mapped to chapter numbers: {len(correct_titles_dict)}")
    print(f"Total chapter files found: {len(chapter_files)}")
    print(f"Files successfully updated: {updated_count}")
    print(f"Files skipped (empty, bad format, no title found): {skipped_count}")
    print(f"  (Specifically skipped due to no title match: {title_not_found_count})")
    print(f"Errors encountered during file processing: {error_count}")
    print("--- Process Complete ---")


# --- Configuration ---
# Adjust these paths if your folders are located differently
TITLES_FILE_PATH = os.path.join("chapter_titles", "chapter_titles.txt")
CHAPTERS_DIRECTORY = "scraped_tileas_worries_mystic" # The output dir from previous script

# --- Run the script ---
if __name__ == "__main__":
    replace_chapter_titles(TITLES_FILE_PATH, CHAPTERS_DIRECTORY)
