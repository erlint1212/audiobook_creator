import os
import re

# --- Configuration ---
CHAPTERS_DIRECTORY = "scraped_tileas_worries_mystic" # Directory with chapter_XX.txt files

# Hardcoded list of titles for "Volume 4 – Camilla Academy Arc"
# This list MUST be in the correct order corresponding to your files
# starting from chapter_86.txt (or chapter_86.1.txt if that's the first part)
VOLUME_4_TITLES = [
    "Chapter 1 – Miles and the Rumored Transfer Student",
    "Chapter 2 – I Am Transferring to a Magic Academy",
    "Chapter 3 – Miles and the Letter",
    "Chapter 4 – Anathy's Pride",
    "Chapter 5 – Elizabeth and Tirea's Meeting (Part 1)",
    "Chapter 6 – Elizabeth and Tirea's Meeting (Part 2)",
    "Chapter 7 – Miles and What Is a Best Friend?",
    "Chapter 8 – Elizabeth's Counterattack",
    "Chapter 9 – Ortissio's Struggle (Part 1)",
    "Chapter 10 – Ortissio's Struggle (Part 2)",
    "Chapter 11 – Ortissio's Struggle (Part 3)",
    "Chapter 12 – The Ordeal of Lycoris the Assassin (Part 1)",
    "Chapter 13 – The Ordeal of Lycoris the Assassin (Part 2)",
    "Chapter 14 – The Ordeal of Lycoris the Assassin (Part 3)",
    "Chapter 15 – Miles and the Peerage Title",
    "Chapter 16 – I Shall Enjoy Myself with an Assassin (Part 1)",
    "Chapter 17 – I Shall Enjoy Myself with an Assassin (Part 2)",
    "Chapter 18 – Miles and Tirea's Meeting (Part 1)",
    "Chapter 19 – Miles and Tirea's Meeting (Part 2)",
    "Chapter 20 – Miles and Tirea's Meeting (Part 3)",
    "Chapter 21 – Miles and Speculation",
    "Chapter 22 – Miles and Ortissio's Joint Performance (Part 1)",
    "Chapter 23 – Miles and Ortissio's Joint Performance (Part 2)",
    "Chapter 24 – Modern Knowledge Gets Misunderstood, Doesn't It? (Part 1)",
    "Chapter 25 – Modern Knowledge Gets Misunderstood, Doesn't It? (Part 2)",
    "Chapter 26 – Modern Knowledge Gets Misunderstood, Doesn't It? (Part 3)",
    "Chapter 27 – Miles and What Is Magical Science?",
    "Chapter 28 – Study Abroad in Front of the Station, Let's Together! (Part 1)",
    "Chapter 29 – Olu and Edim's Xenon Language Commotion! (Part 1)",
    "Chapter 30 – Olu and Edim's Xenon Language Commotion! (Part 2)",
    "Chapter 31 – Study Abroad in Front of the Station, Let's Together! (Part 2)",
    "Chapter 32 – Miles and Countermeasures for Elizabeth",
    "Chapter 33 – Miles and the Great Heist (Part 1)",
    "Chapter 34 – Miles and the Great Heist (Part 2)",
    "Chapter 35 – Miles and the Great Heist (Part 3)",
    "Chapter 36 – Miles and the Greatest Crisis (Part 1)",
    "Chapter 37 – Miles and the Greatest Crisis (Part 2)",
    "Chapter 38 – Miles and the Greatest Crisis (Part 3)",
    "Chapter 39 – Miles' Reunion with Ortissio (Part 1)",
    "Chapter 40 – Miles' Reunion with Ortissio (Part 2)",
    "Chapter 41 – Miles' Reunion with Ortissio (Part 3)",
    "Chapter 42 – Final Battle, Defeat the Villainess! (Part 1)",
    "Chapter 43 – Final Battle, Defeat the Villainess! (Part 2)",
    "Chapter 44 – Elizabeth's Counterattack (Black Revengin')",
    "Chapter 45 – Final Battle, Defeat the Villainess! (Part 3)",
    "Chapter 46 – Final Battle, Defeat the Villainess! (Part 4)",
    "Chapter 47 – Final Battle, Defeat the Villainess! (Part 5)",
    "Chapter 48 – Final Battle, Defeat the Villainess! (Part 6)",
    "Chapter 49 – Elizabeth's Final Stratagem",
    "Chapter 50 – Final Battle, Defeat the Villainess! (Part 7)",
    "Chapter 51 – Final Battle, Defeat the Villainess! (Part 8)",
    "Chapter 52 – Edim and the One-on-One Combat (Part 1)",
    "Chapter 53 – Edim and the One-on-One Combat (Part 2)",
    "Chapter 54 – For Whom Does Miles Become? (Part 1)",
    "Chapter 55 – For Whom Does Miles Become? (Part 2)",
    "Chapter 56 – Final Battle, Defeat the Villainess! (Part 9)",
    "Chapter 57 – Miles, the Demon Lord, and Then to Legend",
    "Chapter 58 – Miles and Awakening (Part 1)",
    "Chapter 59 – Miles and Awakening (Part 2)",
    "Chapter 60 – Miles and the High-Ranking Humans (Part 1)",
    "Chapter 61 – Miles and the High-Ranking Humans (Part 2)",
    "Chapter 62 – Because It's Evil God First (Part 1)",
    "Chapter 63 – Because It's Evil God First (Part 2)",
    "Chapter 64 – Because It's Evil God First (Part 3)",
    "Chapter 65 – Because It's Evil God First (Part 4)",
    "Chapter 66 – Miles and the Finance Minister (Part 1)",
    "Chapter 67 – Miles and the Finance Minister (Part 2)",
    "Chapter 68 – Miles and Elizabeth's Conclusion"
    # Add all titles for this "Volume 4" or "Camilla Academy Arc" here
    # Ensure this list exactly matches the number of files from chapter_86 onwards.
]

# The chapter number (from filename, e.g., 86 from chapter_86.txt)
# that corresponds to the FIRST title in VOLUME_4_TITLES above.
START_FILENAME_CHAPTER_NUMBER_FOR_VOL4 = 86


def extract_chapter_parts_for_sort(filename):
    match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        part_num = int(match.group(2)) if match.group(2) else 0
        return (chapter_num, part_num)
    else:
        return (float('inf'), float('inf'))

def apply_hardcoded_titles(chapters_dir, start_filename_num, titles_list):
    print(f"--- Applying Hardcoded Titles ---")
    print(f"Target directory: {chapters_dir}")
    print(f"Starting from files matching chapter number: {start_filename_num}")
    print(f"Using {len(titles_list)} hardcoded titles.")

    if not os.path.isdir(chapters_dir):
        print(f"Error: Chapters directory '{chapters_dir}' not found. Aborting.")
        return

    # --- 1. Get and Sort All Chapter Files ---
    all_files_in_dir = []
    try:
        disk_files = os.listdir(chapters_dir)
        all_files_in_dir = [f for f in disk_files if re.match(r'chapter_\d+(?:\.\d+)?\.txt$', f, re.IGNORECASE)]
        if not all_files_in_dir:
             print(f"Error: No chapter files found in '{chapters_dir}'. Aborting.")
             return
        all_files_in_dir.sort(key=extract_chapter_parts_for_sort)
    except Exception as e:
        print(f"Error listing or sorting files: {e}")
        return

    # --- 2. Find the starting file index ---
    start_file_index = -1
    for idx, filename in enumerate(all_files_in_dir):
        match = re.match(r'chapter_(\d+)(?:\.\d+)?\.txt$', filename, re.IGNORECASE)
        if match:
            file_base_num = int(match.group(1))
            if file_base_num >= start_filename_num: # Start from this chapter number onwards
                # Find the first file that matches or exceeds the start_filename_num
                # This handles if chapter_86.txt is missing but chapter_86.1.txt exists
                # More accurately, we want to find the first file whose base number is start_filename_num
                # and then process sequentially from there.
                
                # Let's find the exact starting file more carefully
                # We need the sublist of files that logically start from where chapter_86.txt would be
                
                # Simpler: iterate all and only process those >= start_filename_num
                # This assumes the hardcoded list corresponds to all files from 86 onwards.
                # A better way is to find the *actual* starting file.
                
                temp_match_start = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
                if temp_match_start and int(temp_match_start.group(1)) == start_filename_num :
                    start_file_index = idx # Found the first file for the start chapter number
                    print(f"  Identified starting file for processing: '{filename}' at sorted index {start_file_index}.")
                    break
                elif int(temp_match_start.group(1)) > start_filename_num and start_file_index == -1:
                    # If we passed chapter 86 and didn't find it, it means chapter_86.txt (or .1) might be missing
                    print(f"  Warning: Did not find an exact match for chapter_{start_filename_num}, starting with first file >= that number: {filename}")
                    start_file_index = idx
                    break

    if start_file_index == -1:
        print(f"Error: Could not find any files matching or exceeding chapter number {start_filename_num} (e.g., chapter_{start_filename_num}.txt). Aborting.")
        return

    files_to_process_for_vol4 = all_files_in_dir[start_file_index:]
    
    print(f"  Will attempt to update {len(files_to_process_for_vol4)} files starting from '{files_to_process_for_vol4[0]}'.")

    # --- 3. Replace Titles ---
    updated_count = 0
    skipped_count = 0
    error_count = 0

    num_can_process = min(len(files_to_process_for_vol4), len(titles_list))
    if len(files_to_process_for_vol4) != len(titles_list):
        print(f"\nWarning: Number of files from chapter {start_filename_num} onwards ({len(files_to_process_for_vol4)}) "
              f"does not match number of hardcoded Volume 4 titles ({len(titles_list)}).")
        print(f"         Will process {num_can_process} items based on the shorter list.")

    print(f"\nProcessing {num_can_process} files for Volume 4 titles...")

    for i in range(num_can_process):
        filename = files_to_process_for_vol4[i]
        correct_title = titles_list[i] # Get title sequentially from hardcoded list
        filepath = os.path.join(chapters_dir, filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                print(f"  Skipping empty file: {filename}")
                skipped_count += 1
                continue
            
            original_content_lines = lines[1:]

            # For hardcoded titles, we assume the title is already complete with part info if needed.
            # If you still want to append (Part X) based on filename for these hardcoded titles:
            display_title = correct_title
            fn_part_match = re.match(r'chapter_\d+\.(\d+)\.txt$', filename, re.IGNORECASE)
            title_already_has_part = re.search(r'\s*\(Part \d+\)$', correct_title, re.IGNORECASE)

            if fn_part_match and not title_already_has_part:
                part_num_from_fn = fn_part_match.group(1)
                display_title = f"{correct_title} (Part {part_num_from_fn})"

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(display_title + '\n')
                f.writelines(original_content_lines)
            
            # print(f"  Updated title for: {filename} with: '{display_title}'")
            updated_count += 1
        except Exception as e:
            print(f"  Error processing file '{filename}': {e}")
            error_count += 1

    print("\n--- Hardcoded Title Fix Summary ---")
    print(f"Files targeted for update: {len(files_to_process_for_vol4)}")
    print(f"Hardcoded titles available: {len(titles_list)}")
    print(f"Files successfully updated: {updated_count}")
    skipped_due_to_mismatch = max(0, len(files_to_process_for_vol4) - num_can_process) + \
                              max(0, len(titles_list) - num_can_process)
    print(f"Files skipped (empty or list length mismatch): {skipped_count + skipped_due_to_mismatch}")
    print(f"Errors encountered: {error_count}")
    print("--- Process Complete ---")


if __name__ == "__main__":
    # Populate VOLUME_4_TITLES carefully.
    # Ensure START_FILENAME_CHAPTER_NUMBER_FOR_VOL4 correctly identifies the first file
    # that should receive the first title from VOLUME_4_TITLES.
    
    if not VOLUME_4_TITLES:
        print("Error: VOLUME_4_TITLES list is empty. Please populate it with the correct titles.")
    else:
        apply_hardcoded_titles(
            CHAPTERS_DIRECTORY,
            START_FILENAME_CHAPTER_NUMBER_FOR_VOL4,
            VOLUME_4_TITLES
        )
