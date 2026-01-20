import os
import glob
import re
import json
import mimetypes
import base64
import sys

# --- 1. WINDOWS UNICODE FIX ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# --- Try importing mutagen ---
try:
    import mutagen
    from mutagen.oggopus import OggOpus
    from mutagen.flac import Picture
    MUTAGEN_AVAILABLE = True
except ImportError:
    print("Error: mutagen library not found. Please install it: pip install mutagen")
    MUTAGEN_AVAILABLE = False

# --- Configuration & Paths ---
# 1. Inputs from GUI (Environment Variables)
AUDIO_DIR = os.getenv("OPUS_OUTPUT_DIR")
TEXT_DIR = os.getenv("PROJECT_INPUT_TEXT_DIR")

# Fallbacks for standalone testing
if not AUDIO_DIR: 
    print("Warning: Running standalone. Using default paths.")
    AUDIO_DIR = "generated_audio_MistakenFairy_opus"
    TEXT_DIR = "BlleatTL_Novels"

# 2. Determine Project Root (One level up from text/audio dirs)
# Structure: /Novels/Title/01_Raw_Text  -> Root is /Novels/Title
if TEXT_DIR and os.path.exists(TEXT_DIR):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(TEXT_DIR))
else:
    PROJECT_ROOT = os.getcwd()

METADATA_JSON = os.path.join(PROJECT_ROOT, "metadata.json")
COVER_ART_PATH = os.path.join(PROJECT_ROOT, "cover.jpg")

# 3. Default Metadata (Overwritten if metadata.json exists)
ALBUM_META = {
    "title": "Unknown Series",
    "author": "Unknown Author",
    "year": "2026",
    "genre": "Audiobook"
}

# --- Helper Functions ---

def load_global_metadata():
    """Loads the Series Title and Author from the project's metadata.json"""
    if os.path.exists(METADATA_JSON):
        try:
            with open(METADATA_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get("title"): ALBUM_META["title"] = data["title"]
                if data.get("author"): ALBUM_META["author"] = data["author"]
            print(f"Loaded Global Metadata: {ALBUM_META['title']} by {ALBUM_META['author']}")
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")
    else:
        print("Warning: metadata.json not found. Using defaults.")

def get_chapter_title_from_text(track_num):
    """
    Reads the specific text file for this track number.
    The first line is assumed to be the Chapter Title (header).
    """
    if not TEXT_DIR or not os.path.exists(TEXT_DIR):
        return None

    # Try formatted name first (ch_0001.txt)
    txt_path = os.path.join(TEXT_DIR, f"ch_{track_num:04d}.txt")
    
    # Fallback to loose matching if exact file doesn't exist
    if not os.path.exists(txt_path):
        candidates = glob.glob(os.path.join(TEXT_DIR, f"*_{track_num:04d}.txt"))
        if candidates: txt_path = candidates[0]

    if os.path.exists(txt_path):
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                if first_line:
                    return first_line
        except Exception:
            pass
            
    return None

def get_track_number(filename):
    # Extracts '1' from 'ch_0001.opus' or 'Mistaken_Fairy_l_001.opus'
    # Looks for the last sequence of digits
    matches = re.findall(r'(\d+)', filename)
    if matches:
        return int(matches[-1]) # Return the last number found (usually the chapter index)
    return None

def tag_audio_file(audio_path, track_num, chapter_title):
    try:
        audio = OggOpus(audio_path)
        
        # 1. Standard Tags
        audio.tags['TITLE'] = [chapter_title]
        audio.tags['ALBUM'] = [ALBUM_META['title']]
        audio.tags['ARTIST'] = [ALBUM_META['author']]
        audio.tags['ALBUMARTIST'] = ["AI Narrator"] # Or use Author again
        audio.tags['GENRE'] = [ALBUM_META['genre']]
        audio.tags['DATE'] = [ALBUM_META['year']]
        audio.tags['TRACKNUMBER'] = [str(track_num)]

        # 2. Embed Cover Art (Opus uses METADATA_BLOCK_PICTURE)
        if os.path.exists(COVER_ART_PATH):
            mime = mimetypes.guess_type(COVER_ART_PATH)[0] or 'image/jpeg'
            
            pic = Picture()
            with open(COVER_ART_PATH, 'rb') as f:
                pic.data = f.read()
            
            pic.type = 3 # Cover (front)
            pic.mime = mime
            pic.desc = 'Cover'
            
            # OggOpus requires base64 encoded picture block
            pic_data = pic.write()
            encoded_data = base64.b64encode(pic_data).decode('ascii')
            audio.tags['METADATA_BLOCK_PICTURE'] = [encoded_data]

        audio.save()
        return True
    except Exception as e:
        print(f"   Error tagging {os.path.basename(audio_path)}: {e}")
        return False

# --- Main Execution ---
if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE:
        print("Mutagen is required. Install via: pip install mutagen")
        sys.exit(1)

    print(f"--- Audio Tagging ---")
    print(f"Audio Source: {AUDIO_DIR}")
    print(f"Text Source:  {TEXT_DIR}")
    
    if not AUDIO_DIR or not os.path.exists(AUDIO_DIR):
        print("Error: Audio directory not found.")
        sys.exit(1)

    load_global_metadata()
    
    # Process Opus files
    audio_files = sorted(glob.glob(os.path.join(AUDIO_DIR, "*.opus")))
    
    if not audio_files:
        print(f"No .opus files found in {AUDIO_DIR}")
        sys.exit(0)

    print(f"Found {len(audio_files)} files to tag.")
    
    success_count = 0
    for path in audio_files:
        filename = os.path.basename(path)
        track_num = get_track_number(filename)
        
        if track_num is None:
            print(f"   Skipping {filename} (Could not determine track number)")
            continue

        # 1. Get Specific Chapter Title
        title = get_chapter_title_from_text(track_num)
        if not title:
            title = f"Chapter {track_num}" # Fallback
        
        # 2. Apply Tags
        if tag_audio_file(path, track_num, title):
            print(f"   Tagged: [{track_num}] {title}")
            success_count += 1
    
    print(f"\nDone. Successfully tagged {success_count} files.")
