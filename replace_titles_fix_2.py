import os
import re
from typing import List, Tuple, Optional


def extract_chapter_parts_for_sort(filename: str) -> Tuple[int, int]:
    """
    Extracts chapter and part numbers for sorting filenames.

    Args:
        filename (str): The name of the file (e.g., 'chapter_77.txt' or 'chapter_77.1.txt').

    Returns:
        Tuple[int, int]: A tuple containing the chapter number and part number.
                          Part number is 0 if not present in the filename.
                          Returns (float('inf'), float('inf')) for invalid filenames to sort them last.
    """
    match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
    if match:
        chapter_num = int(match.group(1))
        part_num = int(match.group(2)) if match.group(2) else 0
        return (chapter_num, part_num)
    else:
        return (float('inf'), float('inf'))


def read_titles(titles_filepath: str) -> dict[str, str]:
    """
    Reads titles from a file and stores them in a dictionary
    where keys are chapter numbers (e.g., "46", "52.1") and values are titles.

    Args:
        titles_filepath (str): Path to the file containing titles.

    Returns:
        dict[str, str]: A dictionary of titles.
    """
    titles: dict[str, str] = {}
    try:
        with open(titles_filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(':', 1)  # Split into key and title
                    if len(parts) == 2:
                        key, title = parts[0].strip(), parts[1].strip()
                        titles[key] = title
                    else:
                        print(f"Warning: Invalid title line: {line}")
    except FileNotFoundError:
        print(f"Error: Titles file not found at '{titles_filepath}'.")
    except Exception as e:
        print(f"Error reading titles file: {e}")
    return titles


def replace_titles_with_mapping(titles: dict[str, str], chapters_dir: str) -> None:
    """
    Replaces titles in chapter files based on a provided dictionary mapping.

    Args:
        titles (dict[str, str]): A dictionary where keys are chapter identifiers
                                  (e.g., "46", "52.1") and values are the correct titles.
        chapters_dir (str): The directory containing the chapter files.
    """

    chapter_files: List[str] = []
    try:
        all_files_in_dir = os.listdir(chapters_dir)
        chapter_files = [f for f in all_files_in_dir if re.match(r'chapter_\d+(?:\.\d+)?\.txt$', f, re.IGNORECASE)]
        chapter_files.sort(key=extract_chapter_parts_for_sort)
    except FileNotFoundError:
        print(f"Error: Chapters directory not found at '{chapters_dir}'.")
        return
    except Exception as e:
        print(f"Error listing or sorting files: {e}")
        return

    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0

    for filename in chapter_files:
        match = re.match(r'chapter_(\d+)(?:\.(\d+))?\.txt$', filename, re.IGNORECASE)
        if match:
            chapter_num = match.group(1)
            part_num = match.group(2)
            title_key = f"{chapter_num}.{part_num}" if part_num else chapter_num
        else:
            print(f"Warning: Unexpected filename format: {filename}")
            skipped_count += 1
            continue

        filepath = os.path.join(chapters_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not lines:
                print(f"Skipping empty file: {filename}")
                skipped_count += 1
                continue

            original_content_lines = lines[1:]

            if title_key in titles:
                display_title = titles[title_key]
                if part_num and not re.search(r'\s*\(Part \d+\)$', display_title, re.IGNORECASE):
                    display_title = f"{display_title} (Part {part_num})"

                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(display_title + '\n')
                    f.writelines(original_content_lines)
                updated_count += 1
            else:
                print(f"Title not found for {filename} (key: {title_key})")
                skipped_count += 1

        except Exception as e:
            print(f"Error processing file '{filename}': {e}")
            error_count += 1

    print("\n--- Title Replacement Summary ---")
    print(f"Total chapter files found: {len(chapter_files)}")
    print(f"Files successfully updated: {updated_count}")
    print(f"Files skipped: {skipped_count}")
    print(f"Errors encountered: {error_count}")
    print("--- Process Complete ---")


# --- Configuration ---
TITLES_FILE_PATH = os.path.join("chapter_titles", "chapter_titles.txt")
CHAPTERS_DIRECTORY = "scraped_tileas_worries_mystic"

if __name__ == "__main__":
    titles_dict = read_titles(TITLES_FILE_PATH)
    if titles_dict:
        replace_titles_with_mapping(titles_dict, CHAPTERS_DIRECTORY)
