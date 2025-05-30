import os
import glob
import re
import shutil
import mimetypes # To guess image mime type
import base64    # For encoding cover art for Opus

# --- Try importing mutagen ---
try:
    import mutagen
    from mutagen.oggopus import OggOpus   # For Opus files
    from mutagen.flac import Picture      # For cover art structure in Ogg containers
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("Error: mutagen library not found. This script cannot tag files.")
    print("Please install it: pip install mutagen")
    MUTAGEN_AVAILABLE = False
# ---------------------------

# --- Configuration ---
# Folder where the generated Opus audio files (e.g., ch_001.opus) are
# UPDATE THIS PATH if your Opus files are in a different directory
AUDIO_DIR = "generated_audio_tileas_worries_opus" # Example: assuming Opus files are here
# Folder where the original text files (e.g., ch_001.txt) with titles are
TEXT_DIR = "scraped_tileas_worries"
# Pattern to find the audio files to tag
FILENAME_PATTERN = "ch_*.opus" # CHANGED to .opus

# --- Optional: Default Cover Art ---
# Used if a volume in VOLUME_CONFIG doesn't specify 'cover_art_file'
# or if a chapter isn't in any defined volume. Set to None if no default.
DEFAULT_COVER_ART_PATH = "cover_art/tileasworries_default.jpg" # Or None

# --- Metadata - Set these values for your audiobook ---
BASE_ALBUM_TITLE = "Tilea's Worries"  # Base title for the audiobook series
ARTIST = "Rina Shito"                 # Author
ALBUM_ARTIST = "Rina Shito"           # Author again
GENRE = "Audiobook"                   # Or "Spoken Word"
YEAR = "2020"                         # Optional: Book's publication year
COMPOSER = "Alltalk TTS - Half Light RVC" # Optional: Narrator/TTS credit

# --- Volume Configuration ---
# 'name_suffix': Text to append to BASE_ALBUM_TITLE (e.g., ", Volume 1").
# 'disc_num': The disc number for this volume (as a string).
# 'start_ch': The first chapter number included in this volume.
# 'end_ch': The last chapter number included in this volume. Use float('inf') for the last.
# 'cover_art_file': Path to the cover art image for this specific volume.
VOLUME_CONFIG = [
    {"name_suffix": "Volume 1", "start_ch": 1, "end_ch": 46, "disc_num": "1", "cover_art_file": "cover_art/tileasworries1.jpg"},
    {"name_suffix": "Volume 2", "start_ch": 47, "end_ch": 78, "disc_num": "2", "cover_art_file": "cover_art/tileasworries2.jpg"},
    {"name_suffix": "Volume 3", "start_ch": 79, "end_ch": float('inf'), "disc_num": "3", "cover_art_file": "cover_art/tileasworries3.jpg"},
]
TOTAL_DISCS_OVERALL = str(len(VOLUME_CONFIG)) if VOLUME_CONFIG else "1"
# --- End Configuration ---

def get_track_number(filename):
    """Extracts track number from filenames like ch_XXX.opus"""
    match = re.search(r'_(\d+)\.(opus|wav|mp3|m4a)$', filename) # Made extension more generic
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def sanitize_tag_text(text):
    """Basic sanitization for tag text."""
    if text:
        return text.replace('\x00', '')
    return text

def tag_audio_file(audio_filepath, text_filepath, track_num, total_tracks_in_book,
                   current_album_title, current_disc_number, current_total_discs,
                   current_cover_art_path):
    """Reads title from text file and applies Vorbis comment tags to the Opus audio file."""
    print(f"\nProcessing: {os.path.basename(audio_filepath)}")

    # --- Get Title ---
    if not os.path.exists(text_filepath):
        print(f"  Warning: Corresponding text file not found: '{text_filepath}'. Skipping.")
        return False
    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            chapter_title = f.readline().strip()
        if not chapter_title:
            print(f"  Warning: First line of text file is empty. Using fallback title.")
            chapter_title = f"Chapter {track_num:03d}"
        chapter_title = sanitize_tag_text(chapter_title)
        print(f"  Title: '{chapter_title}'")
    except Exception as e:
        print(f"  Error reading title from '{text_filepath}': {e}")
        return False

    # --- Apply Tags using Mutagen for Opus ---
    try:
        audio = OggOpus(audio_filepath) # Open Opus file

        # Vorbis comments are stored as a list of strings for each key.
        audio.tags['TITLE'] = [chapter_title]
        audio.tags['ALBUM'] = [current_album_title]
        audio.tags['ARTIST'] = [ARTIST]
        if ALBUM_ARTIST: audio.tags['ALBUMARTIST'] = [ALBUM_ARTIST] # ALBUMARTIST is common
        if GENRE: audio.tags['GENRE'] = [GENRE]
        if YEAR: audio.tags['DATE'] = [YEAR] # DATE is standard for year YYYY or YYYY-MM-DD
        if COMPOSER: audio.tags['COMPOSER'] = [COMPOSER] # Or PERFORMER for narrator

        audio.tags['TRACKNUMBER'] = [str(track_num)]
        audio.tags['TRACKTOTAL'] = [str(total_tracks_in_book)] # Standard Vorbis comment

        if current_disc_number:
            audio.tags['DISCNUMBER'] = [str(current_disc_number)]
            if current_total_discs:
                audio.tags['DISCTOTAL'] = [str(current_total_discs)] # Standard Vorbis comment
            
        # --- Add Cover Art (METADATA_BLOCK_PICTURE) ---
        if current_cover_art_path and os.path.exists(current_cover_art_path):
            try:
                mime = mimetypes.guess_type(current_cover_art_path)[0]
                if mime in ['image/jpeg', 'image/png']:
                    pic = Picture()
                    pic.type = 3  # 3 means 'Cover (front)'
                    pic.mime = mime
                    pic.desc = '' # Description for the picture
                    with open(current_cover_art_path, 'rb') as f:
                        pic.data = f.read()
                    
                    # For Ogg Opus, the picture block is base64 encoded and stored.
                    # Mutagen's Picture.write() gives the binary picture block.
                    pic_data_binary = pic.write()
                    pic_data_base64 = base64.b64encode(pic_data_binary).decode('ascii')
                    
                    # The METADATA_BLOCK_PICTURE tag expects a list containing this one base64 string.
                    audio.tags['METADATA_BLOCK_PICTURE'] = [pic_data_base64]
                    
                    print(f"  Added cover art from: {os.path.basename(current_cover_art_path)}")
                else:
                    print(f"  Warning: Unsupported cover art MIME type '{mime}' for {current_cover_art_path}. Skipping cover.")
            except Exception as e:
                print(f"  Error adding cover art: {e}")
        elif current_cover_art_path: # Path was given but file not found
            print(f"  Warning: Cover art file not found at: {current_cover_art_path}")
        else: # No cover art path was applicable or provided for this track
            print(f"  Info: No specific cover art path for this track.")
        # --------------------------------

        audio.save()
        print(f"  Successfully tagged.")
        return True

    except Exception as e:
        print(f"  Error tagging file '{audio_filepath}': {e}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE:
        exit()

    print(f"--- Starting Opus Audiobook Tagger ---") # Updated title
    print(f"Audio Directory (Opus files): {os.path.abspath(AUDIO_DIR)}")
    print(f"Text Directory : {os.path.abspath(TEXT_DIR)}")

    if DEFAULT_COVER_ART_PATH and os.path.exists(DEFAULT_COVER_ART_PATH):
        print(f"Default Cover Art File: {os.path.abspath(DEFAULT_COVER_ART_PATH)}")
    elif DEFAULT_COVER_ART_PATH:
        print(f"Warning: Default cover art file specified but not found: {DEFAULT_COVER_ART_PATH}")
    else:
        print("No default cover art path specified. Volume-specific covers will be used if defined in VOLUME_CONFIG.")
    if VOLUME_CONFIG:
        print("VOLUME_CONFIG found and will be used for volume-specific metadata.")

    if not os.path.isdir(AUDIO_DIR): print(f"Error: Audio directory '{AUDIO_DIR}' not found."); exit()
    if not os.path.isdir(TEXT_DIR): print(f"Error: Text directory '{TEXT_DIR}' not found."); exit()

    audio_files = glob.glob(os.path.join(AUDIO_DIR, FILENAME_PATTERN))
    if not audio_files: print(f"No audio files matching '{FILENAME_PATTERN}' found in '{AUDIO_DIR}'."); exit()

    audio_files_sorted = sorted(audio_files, key=lambda x: get_track_number(os.path.basename(x)) or float('inf'))
    total_files_in_book = len(audio_files_sorted)

    print(f"\nFound {total_files_in_book} audio files to process.")
    
    success_count = 0
    fail_count = 0

    for idx, audio_path in enumerate(audio_files_sorted):
        base_name_audio = os.path.splitext(os.path.basename(audio_path))[0]
        text_path = os.path.join(TEXT_DIR, f"{base_name_audio}.txt")
        
        track_num = get_track_number(os.path.basename(audio_path))
        if track_num is None:
            print(f"\nSkipping {os.path.basename(audio_path)} - could not determine track number.")
            fail_count += 1
            continue

        # --- Determine volume-specific metadata ---
        album_title_for_tag = BASE_ALBUM_TITLE
        disc_number_for_tag = "1"
        total_discs_for_tag = "1"
        cover_art_path_for_tag = DEFAULT_COVER_ART_PATH

        current_volume_details = None

        if VOLUME_CONFIG:
            total_discs_for_tag = TOTAL_DISCS_OVERALL
            for vol_info_entry in VOLUME_CONFIG:
                if vol_info_entry["start_ch"] <= track_num <= vol_info_entry["end_ch"]:
                    current_volume_details = vol_info_entry
                    break
            
            if current_volume_details:
                album_title_for_tag = f"{BASE_ALBUM_TITLE}, {current_volume_details['name_suffix']}"
                disc_number_for_tag = str(current_volume_details['disc_num'])
                if 'cover_art_file' in current_volume_details and current_volume_details['cover_art_file']:
                    cover_art_path_for_tag = current_volume_details['cover_art_file']
                elif DEFAULT_COVER_ART_PATH:
                    print(f"  Info: Track {track_num} in '{current_volume_details['name_suffix']}' using default cover art (no specific cover defined for this volume).")
                    # cover_art_path_for_tag remains DEFAULT_COVER_ART_PATH
                else:
                    print(f"  Info: Track {track_num} in '{current_volume_details['name_suffix']}' - no specific or default cover art will be applied.")
                    cover_art_path_for_tag = None
            else: # Track not in any defined volume range
                print(f"  Warning: Track {track_num} (file: {os.path.basename(audio_path)}) not in any VOLUME_CONFIG range.")
                print(f"           Using default album ('{album_title_for_tag}'), disc 1/{total_discs_for_tag}, and default cover art (if any).")
                disc_number_for_tag = "1" # Fallback to disc 1
                # cover_art_path_for_tag remains DEFAULT_COVER_ART_PATH
        else: # No VOLUME_CONFIG provided
            print(f"  Info: VOLUME_CONFIG is not defined. Using single volume scheme for track {track_num}.")

        # Call the tag_audio_file function
        if tag_audio_file(audio_path, text_path, track_num, total_files_in_book,
                          album_title_for_tag,
                          disc_number_for_tag,
                          total_discs_for_tag,
                          cover_art_path_for_tag):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n--- Tagging Complete ---")
    print(f"Successfully tagged: {success_count} files.")
    print(f"Failed/Skipped   : {fail_count} files.")
