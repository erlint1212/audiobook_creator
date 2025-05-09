import os
import glob
import re
import shutil 
import mimetypes # To guess image mime type

# --- Try importing mutagen ---
try:
    import mutagen
    from mutagen.wave import WAVE # Specifically for WAV files
    # We will add ID3 tags to the WAV files for better compatibility
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TPOS, TCON, TDRC, TCOM, APIC, ID3NoHeaderError 
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("Error: mutagen library not found. This script cannot tag files.")
    print("Please install it: pip install mutagen")
    MUTAGEN_AVAILABLE = False
# ---------------------------

# --- Configuration ---
# Folder where the generated audio files (e.g., ch_001.wav) are
AUDIO_DIR = "generated_audio_tileas_worries"
# Folder where the original text files (e.g., ch_001.txt) with titles are
TEXT_DIR = "scraped_tileas_worries"
# Pattern to find the audio files to tag
FILENAME_PATTERN = "ch_*.wav"

# --- Optional: Default Cover Art ---
# This will be used if a volume in VOLUME_CONFIG doesn't specify its own 'cover_art_file'
# or if a chapter doesn't fall into any defined volume.
# Set to None if you don't want any default cover art in those cases.
DEFAULT_COVER_ART_PATH = "cover_art/tileasworries_default.jpg" # Or None

# --- Metadata - Set these values for your audiobook ---
BASE_ALBUM_TITLE = "Tilea's Worries"  # Base title for the audiobook series
ARTIST = "Rina Shito"                 # Author
ALBUM_ARTIST = "Rina Shito"           # Author again
GENRE = "Audiobook"                   # Or "Spoken Word"
YEAR = "2020"                         # Optional: Book's publication year
COMPOSER = "Alltalk TTS - Half Light RVC" # Optional: Narrator/TTS credit

# --- New Volume Configuration ---
# Define your volumes here.
# 'name_suffix': Text to append to BASE_ALBUM_TITLE (e.g., ", Volume 1").
# 'disc_num': The disc number for this volume (as a string).
# 'start_ch': The first chapter number included in this volume.
# 'end_ch': The last chapter number included in this volume. Use float('inf') for the last volume.
# 'cover_art_file': Path to the cover art image for this specific volume.
VOLUME_CONFIG = [
    {"name_suffix": "Volume 1", "start_ch": 1, "end_ch": 46, "disc_num": "1", "cover_art_file": "cover_art/tileasworries1.jpg"},
    {"name_suffix": "Volume 2", "start_ch": 47, "end_ch": 100, "disc_num": "2", "cover_art_file": "cover_art/tileasworries2.jpg"},
    # Example for a third volume:
    # {"name_suffix": "Volume 3", "start_ch": 101, "end_ch": float('inf'), "disc_num": "3", "cover_art_file": "cover_art/tileasworries3.jpg"},
]

TOTAL_DISCS_OVERALL = str(len(VOLUME_CONFIG)) if VOLUME_CONFIG else "1"

# --- Comment out or remove old static COVER_ART_PATH ---
# COVER_ART_PATH = "cover_art/tileasworries_1500x1500.jpg" # OLD - Now dynamic or default

# --- End Configuration ---

def get_track_number(filename):
    """Extracts track number from filenames like ch_XXX.wav"""
    # Extracts digits after the last underscore
    match = re.search(r'_(\d+)\.wav$', filename)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def sanitize_tag_text(text):
    """Basic sanitization for tag text if needed (e.g., removing null chars)"""
    if text:
        return text.replace('\x00', '') # Remove null characters
    return text

def tag_audio_file(audio_filepath, text_filepath, track_num, total_tracks_in_book,
                   current_album_title, current_disc_number, current_total_discs,
                   current_cover_art_path): # ADDED current_cover_art_path
    """Reads title from text file and applies ID3 tags to the WAV audio file."""
    print(f"\nProcessing: {os.path.basename(audio_filepath)}")

    # --- Get Title --- (This part remains the same)
    # ... (copy the existing Get Title section here) ...
    if not os.path.exists(text_filepath):
        print(f"  Warning: Corresponding text file not found: '{text_filepath}'. Skipping.")
        return False
    try:
        with open(text_filepath, 'r', encoding='utf-8') as f:
            chapter_title = f.readline().strip()
        if not chapter_title:
            print(f"  Warning: First line of text file is empty. Using fallback title.")
            chapter_title = f"Chapter {track_num:03d}"
        chapter_title = sanitize_tag_text(chapter_title) # Sanitize before tagging
        print(f"  Title: '{chapter_title}'")
    except Exception as e:
        print(f"  Error reading title from '{text_filepath}': {e}")
        return False

    # --- Apply Tags using Mutagen ---
    try:
        audio = WAVE(audio_filepath)
        if audio.tags is None:
            audio.add_tags()

        # --- Set ID3 Tags ---
        # ... (TRCK, TIT2, TALB, TPE1, TPE2, TCON, TDRC, TCOM, TPOS tags remain as in the previous update) ...
        # Track Number / Total Tracks (TRCK frame)
        track_str = f"{track_num}/{total_tracks_in_book}"
        audio.tags.add(TRCK(encoding=3, text=track_str))
        # Title (TIT2 frame)
        audio.tags.add(TIT2(encoding=3, text=chapter_title))
        # Album (TALB frame)
        audio.tags.add(TALB(encoding=3, text=current_album_title))
        # Artist (TPE1 frame)
        audio.tags.add(TPE1(encoding=3, text=ARTIST))
        # Album Artist (TPE2 frame)
        if ALBUM_ARTIST: audio.tags.add(mutagen.id3.TPE2(encoding=3, text=ALBUM_ARTIST))
        # Genre (TCON frame)
        if GENRE: audio.tags.add(TCON(encoding=3, text=GENRE))
        # Year/Date (TDRC frame)
        if YEAR and re.match(r'^\d{4}$', YEAR):
            audio.tags.add(TDRC(encoding=3, text=YEAR))
        elif YEAR:
            audio.tags.add(TDRC(encoding=3, text=YEAR))
        # Composer (TCOM frame)
        if COMPOSER: audio.tags.add(TCOM(encoding=3, text=COMPOSER))
        # Disc Number / Total Discs (TPOS frame)
        if current_disc_number:
            disc_str = str(current_disc_number)
            if current_total_discs: disc_str += f"/{str(current_total_discs)}"
            audio.tags.add(TPOS(encoding=3, text=disc_str))

        # --- Add Cover Art (APIC frame) --- MODIFIED SECTION ---
        if current_cover_art_path and os.path.exists(current_cover_art_path):
            try:
                mime = mimetypes.guess_type(current_cover_art_path)[0]
                if mime in ['image/jpeg', 'image/png']:
                    with open(current_cover_art_path, 'rb') as art:
                        audio.tags.add(
                            APIC(
                                encoding=0, # For image data description (often '' for cover art)
                                mime=mime,
                                type=3, # 3 means 'Cover (front)'
                                desc='', # Description
                                data=art.read()
                            )
                        )
                    print(f"  Added cover art from: {os.path.basename(current_cover_art_path)}")
                else:
                    print(f"  Warning: Unsupported cover art MIME type '{mime}' for {current_cover_art_path}. Skipping cover.")
            except Exception as e:
                print(f"  Error adding cover art: {e}")
        elif current_cover_art_path: # Path was given but file not found
            print(f"  Warning: Cover art file not found at: {current_cover_art_path}")
        else: # No cover art path was applicable or provided for this track
            print(f"  Info: No specific cover art path for this track.")
        # --- END MODIFIED SECTION ---

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

    print(f"--- Starting Audiobook Tagger ---")
    print(f"Audio Directory: {os.path.abspath(AUDIO_DIR)}")
    print(f"Text Directory : {os.path.abspath(TEXT_DIR)}")
    # MODIFIED Cover Art Info Print
    if DEFAULT_COVER_ART_PATH and os.path.exists(DEFAULT_COVER_ART_PATH):
        print(f"Default Cover Art File: {os.path.abspath(DEFAULT_COVER_ART_PATH)}")
    elif DEFAULT_COVER_ART_PATH: # Specified but not found
        print(f"Warning: Default cover art file specified but not found: {DEFAULT_COVER_ART_PATH}")
    else: # No default specified
        print("No default cover art path specified. Volume-specific covers will be used if defined.")
    if VOLUME_CONFIG:
        print("VOLUME_CONFIG found and will be used for volume-specific metadata (album, disc #, cover art).")
    # END MODIFIED Print

    # ... (directory checks remain the same) ...
    if not os.path.isdir(AUDIO_DIR): print(f"Error: Audio directory not found."); exit()
    if not os.path.isdir(TEXT_DIR): print(f"Error: Text directory not found."); exit()


    audio_files = glob.glob(os.path.join(AUDIO_DIR, FILENAME_PATTERN))
    if not audio_files: print(f"No audio files matching '{FILENAME_PATTERN}' found."); exit()

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

        # --- Determine volume-specific metadata --- MODIFIED SECTION ---
        album_title_for_tag = BASE_ALBUM_TITLE
        disc_number_for_tag = "1"
        total_discs_for_tag = "1"
        cover_art_path_for_tag = DEFAULT_COVER_ART_PATH # Start with default

        current_volume_details = None # To store the matched vol_info from VOLUME_CONFIG

        if VOLUME_CONFIG:
            total_discs_for_tag = TOTAL_DISCS_OVERALL # Use actual total if config exists
            for vol_info_entry in VOLUME_CONFIG:
                if vol_info_entry["start_ch"] <= track_num <= vol_info_entry["end_ch"]:
                    current_volume_details = vol_info_entry
                    break # Found the matching volume
            
            if current_volume_details:
                album_title_for_tag = f"{BASE_ALBUM_TITLE}, {current_volume_details['name_suffix']}"
                disc_number_for_tag = str(current_volume_details['disc_num'])
                # Get volume-specific cover art if defined, otherwise it remains default
                if 'cover_art_file' in current_volume_details and current_volume_details['cover_art_file']:
                    cover_art_path_for_tag = current_volume_details['cover_art_file']
                # If 'cover_art_file' is not in current_volume_details, cover_art_path_for_tag will keep DEFAULT_COVER_ART_PATH value
                elif DEFAULT_COVER_ART_PATH:
                     print(f"  Info: Track {track_num} in '{current_volume_details['name_suffix']}' using default cover art as no specific cover defined for this volume.")
                else: # No specific cover for this volume and no default path set
                     print(f"  Info: Track {track_num} in '{current_volume_details['name_suffix']}' - no specific or default cover art will be applied.")
                     cover_art_path_for_tag = None


            elif not current_volume_details: # Track not in any defined volume range
                print(f"  Warning: Track {track_num} (file: {os.path.basename(audio_path)}) not in any defined volume range in VOLUME_CONFIG.")
                print(f"           Using default album title ('{album_title_for_tag}'), disc 1/{total_discs_for_tag}, and default cover art (if any).")
                disc_number_for_tag = "1" # Fallback to disc 1
                # cover_art_path_for_tag remains DEFAULT_COVER_ART_PATH
        else: # No VOLUME_CONFIG provided
            print(f"  Info: VOLUME_CONFIG is not defined. Defaulting to single volume scheme for track {track_num}.")
            # All parameters (album_title_for_tag, disc_number_for_tag, total_discs_for_tag, cover_art_path_for_tag)
            # will retain their initial default values set above.
        # --- END MODIFIED SECTION ---

        # Call the modified tag_audio_file function
        if tag_audio_file(audio_path, text_path, track_num, total_files_in_book,
                          album_title_for_tag,
                          disc_number_for_tag,
                          total_discs_for_tag,
                          cover_art_path_for_tag): # ADDED cover_art_path_for_tag
            success_count += 1
        else:
            fail_count += 1

    print(f"\n--- Tagging Complete ---")
    print(f"Successfully tagged: {success_count} files.")
    print(f"Failed/Skipped   : {fail_count} files.")
