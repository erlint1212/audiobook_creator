import os
import glob
import re
import shutil # Using shutil.move for potentially safer renaming across drives

# --- Configuration ---
# Folder where the generated audio files (e.g., ch_001.wav) are located
AUDIO_DIR = "generated_audio_tileas_worries" 

# Folder where the original text files (e.g., ch_001.txt) with titles are located
TEXT_DIR = "scraped_tileas_worries"       

# Pattern to find the audio files to rename 
# (Adjust if your TTS script outputs slightly different names)
FILENAME_PATTERN = "ch_*.wav"  # Assumes files are named ch_001.wav, ch_002.wav etc.
# --- End Configuration ---

def sanitize_filename(name):
    """Removes invalid characters and shortens a string for use as a filename component."""
    if not name: return ""
    # Remove characters invalid for Windows filenames (adjust if on other OS)
    # Keep alphanumeric, underscore, hyphen, space. Replace others with underscore.
    s = re.sub(r'[\\/*?:"<>|]', '_', name) 
    s = s.strip()
    # Replace multiple spaces/underscores/hyphens with a single underscore
    s = re.sub(r'[-\s_]+', '_', s)
    # Remove leading/trailing underscores
    s = s.strip('_')
    # Limit length to avoid overly long filenames
    return s[:80] # Limit title part length (adjust if needed)

def rename_audio_files_with_titles():
    """
    Finds audio files, reads the title from the first line of the corresponding
    text file, and renames the audio file to include the sanitized title.
    """
    print(f"--- Starting Audio File Renaming ---")
    print(f"Looking for audio files in: {os.path.abspath(AUDIO_DIR)}")
    print(f"Reading titles from text files in: {os.path.abspath(TEXT_DIR)}")

    if not os.path.isdir(AUDIO_DIR):
        print(f"Error: Audio directory not found: '{AUDIO_DIR}'")
        return
    if not os.path.isdir(TEXT_DIR):
        print(f"Error: Text directory not found: '{TEXT_DIR}'")
        return

    # Find audio files matching the pattern
    audio_files = glob.glob(os.path.join(AUDIO_DIR, FILENAME_PATTERN))

    if not audio_files:
        print(f"No audio files matching '{FILENAME_PATTERN}' found in '{AUDIO_DIR}'.")
        return

    print(f"\nFound {len(audio_files)} audio files matching pattern '{FILENAME_PATTERN}'.")
    rename_count = 0
    skip_count = 0

    for old_audio_path in sorted(audio_files):
        print(f"\nProcessing: {os.path.basename(old_audio_path)}")
        
        # Extract base name (e.g., "ch_001")
        base_name_audio = os.path.splitext(os.path.basename(old_audio_path))[0]
        
        # Check if it already seems to have a title appended (simple check for multiple underscores)
        # Avoids re-processing files like "ch_001_Prologue" if script is run again.
        if base_name_audio.count('_') > 1: 
             print(f"  Skipping: Filename '{base_name_audio}' seems to already include a title.")
             skip_count += 1
             continue

        # Construct corresponding text file path
        text_file_path = os.path.join(TEXT_DIR, f"{base_name_audio}.txt")

        if not os.path.exists(text_file_path):
            print(f"  Warning: Corresponding text file not found: '{text_file_path}'. Cannot get title.")
            skip_count += 1
            continue

        # Read the first line for the title
        try:
            with open(text_file_path, 'r', encoding='utf-8') as f:
                chapter_title = f.readline().strip() # Read only the first line and strip whitespace
            
            if not chapter_title:
                print(f"  Warning: First line of text file is empty. Using base filename as title.")
                # Create a readable title from filename like ch_001 -> Chapter 001
                try: 
                    chapter_num_str = base_name_audio.split('_')[-1]
                    chapter_title = f"Chapter {int(chapter_num_str):03d}" # Format number e.g., Chapter 001
                except: 
                    chapter_title = base_name_audio # Absolute fallback
                
        except Exception as e:
            print(f"  Error reading title from {text_file_path}: {e}")
            skip_count += 1
            continue

        # Sanitize the extracted title for use in filename
        sanitized_title_part = sanitize_filename(chapter_title)

        if not sanitized_title_part:
            print(f"  Warning: Title '{chapter_title}' resulted in empty sanitized string. Skipping rename.")
            skip_count += 1
            continue

        # Construct the new filename (e.g., "ch_001_Prologue.wav")
        new_base_filename = f"{base_name_audio}_{sanitized_title_part}"
        new_audio_filename = f"{new_base_filename}.{OUTPUT_FORMAT}" # Use OUTPUT_FORMAT from config if needed, default 'wav'
        new_audio_path = os.path.join(AUDIO_DIR, new_audio_filename)

        # Avoid renaming if new name is same as old 
        if old_audio_path == new_audio_path:
            print(f"  Skipping: New name is identical to old name.")
            skip_count += 1
            continue
            
        # Avoid renaming if a file with the new name *already* exists (maybe from previous run)
        if os.path.exists(new_audio_path):
             print(f"  Skipping: File with new name '{new_audio_filename}' already exists.")
             skip_count += 1
             continue

        # Rename the file using shutil.move for safety
        try:
            print(f"  Renaming to: {new_audio_filename}")
            shutil.move(old_audio_path, new_audio_path) 
            rename_count += 1
        except Exception as e:
            print(f"  Error renaming file to {new_audio_filename}: {e}")
            skip_count += 1

    print(f"\n--- Renaming Complete ---")
    print(f"Successfully renamed: {rename_count} files.")
    print(f"Skipped/Errors      : {skip_count} files.")

# --- Main Execution ---
if __name__ == "__main__":
    # Define OUTPUT_FORMAT needed for new filename construction
    OUTPUT_FORMAT = "wav" # Or get from config if used elsewhere
    rename_audio_files_with_titles()
