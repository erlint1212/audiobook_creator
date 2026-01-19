import os
import glob
import re
import json
import mimetypes
import base64

# --- Try importing mutagen ---
try:
    import mutagen
    from mutagen.oggopus import OggOpus
    from mutagen.flac import Picture
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("Error: mutagen library not found. Please install it: pip install mutagen")
    MUTAGEN_AVAILABLE = False

# --- Configuration ---
AUDIO_DIR = "generated_audio_MistakenFairy_opus"
TEXT_DIR = "BlleatTL_Novels" 
METADATA_FILE = os.path.join(TEXT_DIR, "chapters.json")
DEFAULT_COVER_ART_PATH = "cover.jpg"

WEB_NOVEL_SERIES_NAME = "Mistaken for a Fairy"
ARTIST = "Mistaken for a Fairy"
ALBUM_ARTIST = "Blleat"
GENRE = "Audiobook"
YEAR = "2026"
# --- End Configuration ---

def get_full_title_from_file(txt_path):
    """
    Reads the text file and returns the first non-empty line 
    which contains 'Chapter X - Title'.
    """
    if not os.path.exists(txt_path):
        return None
    
    try:
        with open(txt_path, 'r', encoding='utf-8') as f:
            for line in f:
                clean_line = line.strip()
                if clean_line:
                    return clean_line
    except Exception as e:
        print(f"   Error reading {txt_path}: {e}")
    return None

def get_track_number(filename):
    match = re.search(r'ch_(\d+)', filename)
    return int(match.group(1)) if match else None

def tag_audio_file(audio_path, track_num, chapter_title, cover_path):
    try:
        audio = OggOpus(audio_path)
        
        # Metadata Tags
        audio.tags['TITLE'] = [chapter_title]
        audio.tags['ALBUM'] = [WEB_NOVEL_SERIES_NAME]
        audio.tags['ARTIST'] = [ARTIST]
        audio.tags['ALBUMARTIST'] = [ALBUM_ARTIST]
        audio.tags['GENRE'] = [GENRE]
        audio.tags['DATE'] = [YEAR]
        audio.tags['TRACKNUMBER'] = [str(track_num)]

        # Embed Cover Art
        if cover_path and os.path.exists(cover_path):
            mime = mimetypes.guess_type(cover_path)[0]
            if mime in ['image/jpeg', 'image/png']:
                pic = Picture()
                pic.type = 3 
                pic.mime = mime
                pic.desc = 'Cover'
                with open(cover_path, 'rb') as f:
                    pic.data = f.read()
                
                pic_data_base64 = base64.b64encode(pic.write()).decode('ascii')
                audio.tags['METADATA_BLOCK_PICTURE'] = [pic_data_base64]

        audio.save()
        return True
    except Exception as e:
        print(f"   Error tagging {os.path.basename(audio_path)}: {e}")
        return False

if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE: exit()

    print(f"--- Starting Precise Opus Tagging ---")
    
    audio_files = sorted(glob.glob(os.path.join(AUDIO_DIR, "ch_*.opus")))

    if not audio_files:
        print(f"No files found in {AUDIO_DIR}")
        exit()

    success_count = 0
    for path in audio_files:
        filename = os.path.basename(path)
        track_num = get_track_number(filename)
        
        if track_num is None: continue

        # 1. Try to get the formatted title directly from the .txt file first
        txt_path = os.path.join(TEXT_DIR, f"ch_{track_num:04d}.txt")
        title = get_full_title_from_file(txt_path)
        
        # 2. Fallback to a generic string if the file read fails
        if not title:
            title = f"Chapter {track_num}"

        print(f"Tagging: {filename} -> {title}")
        if tag_audio_file(path, track_num, title, DEFAULT_COVER_ART_PATH):
            success_count += 1

    print(f"\nSuccessfully tagged {success_count} files with full titles.")
