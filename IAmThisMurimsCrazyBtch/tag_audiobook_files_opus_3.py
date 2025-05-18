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
AUDIO_DIR = "generated_audio_IATMCB_opus"
TEXT_DIR = "scraped_IATMCB_celsetial_pavilion" # Or "scraped_tileas_worries_mystic" - where ch_XXX.txt files are
FILENAME_PATTERN = "ch_*.opus"
DEFAULT_COVER_ART_PATH = "cover_art/tileasworries_default.jpg"

WEB_NOVEL_SERIES_NAME = "I Am This Murim’s Crazy Bitch"
BASE_ALBUM_TITLE = "I Am This Murim’s Crazy Bitch"
ARTIST = "ILikeTraditionalMartialArtsNovels/정통무협조와요"
ALBUM_ARTIST = "ILikeTraditionalMartialArtsNovels/정통무협조와요"
GENRE = "Audiobook"
YEAR = "2025"
COMPOSER = "Alltalk TTS - Half Light RVC"

# =====================================================================================
# !!! IMPORTANT: YOU NEED TO UPDATE THE start_ch, end_ch, and cover_art_file FOR THESE VOLUMES !!!
# The chapter ranges below are EXAMPLES based on common splits and your previous config.
# =====================================================================================
VOLUME_CONFIG = [
    {
        "name_suffix": "I Am This Murim’s Crazy Bitch",
        "start_ch": 1,    # Example: Please verify
        "end_ch": float('inf'),     # Example: Please verify
        "disc_num": "1",
        "cover_art_file": "cover_art/I-Am-This-Murims-Crazy-Btch2.jpg"
    },
]
TOTAL_DISCS_OVERALL = str(len(VOLUME_CONFIG)) if VOLUME_CONFIG else "1"
# --- End Configuration ---


def get_track_number(filename):
    """Extracts track number from filenames like ch_XXX.opus"""
    match = re.search(r'_(\d+)\.(opus|wav|mp3|m4a)$', filename, re.IGNORECASE)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None

def sanitize_tag_text(text):
    """Basic sanitization for tag text."""
    if text:
        return text.replace('\x00', '') # Remove null characters
    return text

def tag_audio_file(audio_filepath, text_filepath, track_num, total_tracks_in_album,
                   current_album_title, current_disc_number, current_total_discs,
                   series_name,
                   current_cover_art_path):
    print(f"\nProcessing: {os.path.basename(audio_filepath)}")

    if not os.path.exists(text_filepath):
        print(f"  Warning: Corresponding text file not found: '{text_filepath}'. Skipping title from file.")
        chapter_title = f"Chapter {track_num:03d}" # Fallback title
    else:
        try:
            with open(text_filepath, 'r', encoding='utf-8') as f:
                chapter_title = f.readline().strip()
            if not chapter_title:
                print(f"  Warning: First line of text file '{text_filepath}' is empty. Using fallback title.")
                chapter_title = f"Chapter {track_num:03d}"
            chapter_title = sanitize_tag_text(chapter_title)
            print(f"  Title from file: '{chapter_title}'")
        except Exception as e:
            print(f"  Error reading title from '{text_filepath}': {e}. Using fallback title.")
            chapter_title = f"Chapter {track_num:03d}"

    try:
        audio = OggOpus(audio_filepath)

        audio.tags['TITLE'] = [chapter_title]
        audio.tags['ALBUM'] = [current_album_title]
        audio.tags['ARTIST'] = [ARTIST]
        if ALBUM_ARTIST: audio.tags['ALBUMARTIST'] = [ALBUM_ARTIST]
        if GENRE: audio.tags['GENRE'] = [GENRE]
        if YEAR: audio.tags['DATE'] = [YEAR]
        if COMPOSER: audio.tags['COMPOSER'] = [COMPOSER]
        audio.tags['TRACKNUMBER'] = [str(track_num)]
        audio.tags['TRACKTOTAL'] = [str(total_tracks_in_album)]

        if current_disc_number:
            audio.tags['DISCNUMBER'] = [str(current_disc_number)]
            if current_total_discs:
                audio.tags['DISCTOTAL'] = [str(current_total_discs)]

        if series_name:
            audio.tags['SERIES'] = [series_name]
            audio.tags['GROUPING'] = [series_name]
            print(f"  Series/Grouping: '{series_name}'")

        if current_cover_art_path and os.path.exists(current_cover_art_path):
            try:
                mime = mimetypes.guess_type(current_cover_art_path)[0]
                if mime in ['image/jpeg', 'image/png']:
                    pic = Picture()
                    pic.type = 3
                    pic.mime = mime
                    pic.desc = ''
                    with open(current_cover_art_path, 'rb') as f:
                        pic.data = f.read()
                    pic_data_binary = pic.write()
                    pic_data_base64 = base64.b64encode(pic_data_binary).decode('ascii')
                    audio.tags['METADATA_BLOCK_PICTURE'] = [pic_data_base64]
                    print(f"  Added cover art from: {os.path.basename(current_cover_art_path)}")
                else:
                    print(f"  Warning: Unsupported cover art MIME type '{mime}' for {current_cover_art_path}. Skipping cover.")
            except Exception as e:
                print(f"  Error adding cover art: {e}")
        elif current_cover_art_path:
            print(f"  Warning: Cover art file not found at: {current_cover_art_path}")

        audio.save()
        print(f"  Successfully tagged.")
        return True
    except Exception as e:
        print(f"  Error tagging file '{audio_filepath}': {e}")
        return False

if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE:
        exit()

    print(f"--- Starting Opus Audiobook Tagger ---")
    print(f"Audio Directory (Opus files): {os.path.abspath(AUDIO_DIR)}")
    print(f"Text Directory (for titles): {os.path.abspath(TEXT_DIR)}")
    print(f"Series Name to be applied: '{WEB_NOVEL_SERIES_NAME}'")

    if DEFAULT_COVER_ART_PATH and os.path.exists(DEFAULT_COVER_ART_PATH):
        print(f"Default Cover Art File: {os.path.abspath(DEFAULT_COVER_ART_PATH)}")
    elif DEFAULT_COVER_ART_PATH:
        print(f"Warning: Default cover art file specified but not found: {DEFAULT_COVER_ART_PATH}")

    if not os.path.isdir(AUDIO_DIR): print(f"Error: Audio directory '{AUDIO_DIR}' not found."); exit()
    if not os.path.isdir(TEXT_DIR): print(f"Error: Text directory '{TEXT_DIR}' not found."); exit()

    audio_files = glob.glob(os.path.join(AUDIO_DIR, FILENAME_PATTERN))
    if not audio_files: print(f"No audio files matching '{FILENAME_PATTERN}' found in '{AUDIO_DIR}'."); exit()

    audio_files_sorted = sorted(audio_files, key=lambda x: get_track_number(os.path.basename(x)) or float('inf'))
    total_tracks_overall = len(audio_files_sorted)
    print(f"\nFound {total_tracks_overall} audio files to process.")
    
    success_count = 0
    fail_count = 0

    for idx, audio_path in enumerate(audio_files_sorted):
        base_name_audio = os.path.splitext(os.path.basename(audio_path))[0]
        text_path = os.path.join(TEXT_DIR, f"{base_name_audio}.txt")
        track_num_overall = get_track_number(os.path.basename(audio_path))

        if track_num_overall is None:
            print(f"\nSkipping {os.path.basename(audio_path)} - could not determine track number.")
            fail_count += 1
            continue

        album_title_for_tag = f"{BASE_ALBUM_TITLE}"
        disc_number_for_tag = "1"
        total_discs_for_tag = TOTAL_DISCS_OVERALL
        cover_art_path_for_tag = DEFAULT_COVER_ART_PATH
        current_volume_details = None

        if VOLUME_CONFIG:
            for vol_info_entry in VOLUME_CONFIG:
                if vol_info_entry["start_ch"] <= track_num_overall <= vol_info_entry["end_ch"]:
                    current_volume_details = vol_info_entry
                    break
            
            if current_volume_details:
                album_title_for_tag = f"{BASE_ALBUM_TITLE}, {current_volume_details['name_suffix']}" # This now includes the arc name
                disc_number_for_tag = str(current_volume_details['disc_num'])
                if 'cover_art_file' in current_volume_details and current_volume_details['cover_art_file']:
                    cover_art_path_for_tag = current_volume_details['cover_art_file']
            else:
                print(f"  Warning: Track {track_num_overall} (file: {os.path.basename(audio_path)}) not in any VOLUME_CONFIG range.")
        else:
            print(f"  Info: VOLUME_CONFIG is not defined. Using single volume scheme for track {track_num_overall}.")

        track_num_for_tag = track_num_overall

        if tag_audio_file(audio_path, text_path, track_num_for_tag, total_tracks_overall,
                          album_title_for_tag,
                          disc_number_for_tag,
                          total_discs_for_tag,
                          WEB_NOVEL_SERIES_NAME,
                          cover_art_path_for_tag):
            success_count += 1
        else:
            fail_count += 1

    print(f"\n--- Tagging Complete ---")
    print(f"Successfully tagged: {success_count} files.")
    print(f"Failed/Skipped   : {fail_count} files.")
