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
# Path to your cover art image file
COVER_ART_PATH = "cover_art/tileasworries_1500x1500.jpg" 

# Metadata - Set these values for your audiobook
ALBUM_TITLE = "Tilea's Worries, Volume 1"  # Or just "Tilea's Worries"
ARTIST = "Rina Shito"                 # Author
ALBUM_ARTIST = "Rina Shito"                 # Author again
GENRE = "Audiobook"                     # Or "Spoken Word"
YEAR = "2020"                               # Optional: Book's publication year as string (e.g., "2020")
COMPOSER = "Alltalk TTS - Half Light RVC" # Optional: Narrator/TTS credit
DISC_NUMBER = "1"                         # Optional: Volume number
TOTAL_DISCS = "5"                          # Optional: Total volumes
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

def tag_audio_file(audio_filepath, text_filepath, track_num, total_tracks):
    """Reads title from text file and applies ID3 tags to the WAV audio file."""
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
        chapter_title = sanitize_tag_text(chapter_title) # Sanitize before tagging
        print(f"  Title: '{chapter_title}'")
    except Exception as e:
        print(f"  Error reading title from '{text_filepath}': {e}")
        return False

    # --- Apply Tags using Mutagen ---
    try:
        # Open the WAV file
        audio = WAVE(audio_filepath)

        # Add ID3 tag frame if it doesn't exist. 
        # mutagen handles WAVE files that might already have ID3 or need a new header.
        if audio.tags is None:
             audio.add_tags() # Initializes the ID3 tag structure

        # --- Set ID3 Tags ---
        # We use ID3 frames directly as mutagen doesn't have an "Easy" interface for WAV.
        # Encoding=3 specifies UTF-8 text encoding.

        # Track Number / Total Tracks (TRCK frame) - Format "N/M"
        track_str = f"{track_num}/{total_tracks}"
        audio.tags.add(TRCK(encoding=3, text=track_str))

        # Title (TIT2 frame)
        audio.tags.add(TIT2(encoding=3, text=chapter_title))

        # Album (TALB frame)
        audio.tags.add(TALB(encoding=3, text=ALBUM_TITLE))

        # Artist (TPE1 frame - Lead performer/soloist)
        audio.tags.add(TPE1(encoding=3, text=ARTIST)) 

        # Album Artist (TPE2 frame) - Often the same as Artist for audiobooks
        if ALBUM_ARTIST: audio.tags.add(mutagen.id3.TPE2(encoding=3, text=ALBUM_ARTIST))

        # Genre (TCON frame)
        if GENRE: audio.tags.add(TCON(encoding=3, text=GENRE))

        # Year/Date (TDRC frame - YYYY format)
        if YEAR and re.match(r'^\d{4}$', YEAR): 
            audio.tags.add(TDRC(encoding=3, text=YEAR))
        elif YEAR:
             print(f"  Warning: Year '{YEAR}' is not in YYYY format. Saving anyway.")
             audio.tags.add(TDRC(encoding=3, text=YEAR)) # Save non-standard year if provided

        # Composer (TCOM frame) - For TTS voice/narrator
        if COMPOSER: audio.tags.add(TCOM(encoding=3, text=COMPOSER))

        # Disc Number / Total Discs (TPOS frame) - Format "N/M"
        if DISC_NUMBER:
            disc_str = DISC_NUMBER
            if TOTAL_DISCS: disc_str += f"/{TOTAL_DISCS}"
            audio.tags.add(TPOS(encoding=3, text=disc_str))
            
        # --- Add Cover Art (APIC frame) ---
        if COVER_ART_PATH and os.path.exists(COVER_ART_PATH):
             try:
                 mime = mimetypes.guess_type(COVER_ART_PATH)[0] # Guess MIME type (e.g., 'image/jpeg')
                 if mime in ['image/jpeg', 'image/png']:
                      with open(COVER_ART_PATH, 'rb') as art:
                         # Add the APIC frame for front cover
                         audio.tags.add(
                              APIC(
                                   encoding=0, # 3 is UTF-8, but 0 is recommended for image data description by spec? Using 0 for desc=''. Data is binary.
                                   mime=mime,
                                   type=3, # 3 means 'Cover (front)'
                                   desc='', # Description - can be empty
                                   data=art.read()
                              )
                         )
                      print(f"  Added cover art from: {os.path.basename(COVER_ART_PATH)}")
                 else:
                      print(f"  Warning: Unsupported cover art MIME type '{mime}' for {COVER_ART_PATH}. Skipping cover.")
             except Exception as e:
                  print(f"  Error adding cover art: {e}")
        elif COVER_ART_PATH:
             print(f"  Warning: Cover art file not found at: {COVER_ART_PATH}")
        # --------------------------------

        # Save the changes back to the WAV file
        audio.save()
        print(f"  Successfully tagged.")
        return True

    except Exception as e:
        print(f"  Error tagging file '{audio_filepath}': {e}")
        return False


# --- Main Execution ---
if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE: 
        exit() # Exit if mutagen couldn't be imported

    print(f"--- Starting Audiobook Tagger ---")
    print(f"Audio Directory: {os.path.abspath(AUDIO_DIR)}")
    print(f"Text Directory : {os.path.abspath(TEXT_DIR)}")
    if COVER_ART_PATH and os.path.exists(COVER_ART_PATH):
        print(f"Cover Art File: {os.path.abspath(COVER_ART_PATH)}")
    elif COVER_ART_PATH:
        print(f"Warning: Cover art file specified but not found: {COVER_ART_PATH}")
    else:
        print("No cover art path specified.")

    if not os.path.isdir(AUDIO_DIR): print(f"Error: Audio directory not found."); exit()
    if not os.path.isdir(TEXT_DIR): print(f"Error: Text directory not found."); exit()

    # Find audio files matching the pattern
    audio_files = glob.glob(os.path.join(AUDIO_DIR, FILENAME_PATTERN))
    if not audio_files: print(f"No audio files matching '{FILENAME_PATTERN}' found."); exit()

    # Sort files based on extracted track number to process in order
    audio_files_sorted = sorted(audio_files, key=lambda x: get_track_number(os.path.basename(x)) or float('inf'))
    total_files = len(audio_files_sorted)

    print(f"\nFound {total_files} audio files to process.")
    
    success_count = 0
    fail_count = 0

    for idx, audio_path in enumerate(audio_files_sorted):
        # Get base name (e.g., "ch_001") to find text file
        base_name_audio = os.path.splitext(os.path.basename(audio_path))[0]
        text_path = os.path.join(TEXT_DIR, f"{base_name_audio}.txt")
        
        # Get track number again for tagging
        track_num = get_track_number(os.path.basename(audio_path))
        if track_num is None:
            print(f"\nSkipping {os.path.basename(audio_path)} - could not determine track number.")
            fail_count += 1
            continue

        if tag_audio_file(audio_path, text_path, track_num, total_files):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n--- Tagging Complete ---")
    print(f"Successfully tagged: {success_count} files.")
    print(f"Failed/Skipped   : {fail_count} files.")
