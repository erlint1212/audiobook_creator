import base64
import glob
import json
import mimetypes
import os
import re
import sys

# --- 1. WINDOWS UNICODE FIX ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# --- Try importing mutagen ---
try:
    import mutagen
    from mutagen.flac import Picture
    from mutagen.oggopus import OggOpus

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
if TEXT_DIR and os.path.exists(TEXT_DIR):
    PROJECT_ROOT = os.path.dirname(os.path.abspath(TEXT_DIR))
else:
    PROJECT_ROOT = os.getcwd()

METADATA_JSON = os.path.join(PROJECT_ROOT, "metadata.json")
COVER_ART_PATH = os.path.join(PROJECT_ROOT, "cover.jpg")

# 3. Default Metadata
ALBUM_META = {
    "title": "Unknown Series",
    "author": "Unknown Author",
    "year": "2025",
    "genre": "Audiobook",
    "composer": "AI TTS",  # Default for 'Composer' field
}


# --- Helper Functions ---
def load_global_metadata():
    """Loads the Series Title, Author, and other fields from metadata.json"""
    if os.path.exists(METADATA_JSON):
        try:
            with open(METADATA_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Standard Fields
            if data.get("title"):
                ALBUM_META["title"] = data["title"]
            if data.get("author"):
                ALBUM_META["author"] = data["author"]

            # Optional Overrides
            if data.get("year"):
                ALBUM_META["year"] = str(data["year"])
            if data.get("genre"):
                ALBUM_META["genre"] = data["genre"]
            if data.get("composer"):
                ALBUM_META["composer"] = data["composer"]

            print(f"Loaded Metadata: {ALBUM_META['title']} by {ALBUM_META['author']}")
        except Exception as e:
            print(f"Warning: Could not read metadata.json: {e}")
    else:
        print("Warning: metadata.json not found. Using defaults.")


def get_chapter_title_from_text(track_num):
    """Reads the first line of the corresponding text file to use as the Title."""
    if not TEXT_DIR or not os.path.exists(TEXT_DIR):
        return None

    # Try formatted name first (ch_0001.txt)
    txt_path = os.path.join(TEXT_DIR, f"ch_{track_num:04d}.txt")

    # Fallback to loose matching
    if not os.path.exists(txt_path):
        candidates = glob.glob(os.path.join(TEXT_DIR, f"*_{track_num:04d}.txt"))
        if candidates:
            txt_path = candidates[0]

    if os.path.exists(txt_path):
        try:
            with open(txt_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    return first_line
        except Exception:
            pass

    return None


def get_track_number(filename):
    """Extracts the track number from the filename."""
    matches = re.findall(r"(\d+)", filename)
    if matches:
        return int(matches[-1])
    return None


def tag_audio_file(audio_path, track_num, chapter_title, total_tracks):
    try:
        audio = OggOpus(audio_path)

        # --- 1. Standard Tags ---
        audio.tags["TITLE"] = [chapter_title]
        audio.tags["ARTIST"] = [ALBUM_META["author"]]
        audio.tags["ALBUM"] = [ALBUM_META["title"]]
        audio.tags["DATE"] = [ALBUM_META["year"]]
        audio.tags["GENRE"] = [ALBUM_META["genre"]]

        # --- 2. Enhanced Audiobooks Tags ---
        # Album Artist should usually be the Author for Audiobooks
        audio.tags["ALBUMARTIST"] = [ALBUM_META["author"]]

        # Track / Disc info
        audio.tags["TRACKNUMBER"] = [str(track_num)]
        audio.tags["TRACKTOTAL"] = [str(total_tracks)]
        audio.tags["DISCNUMBER"] = ["1"]
        audio.tags["DISCTOTAL"] = ["1"]

        # Grouping & Series (Good for players that support series)
        audio.tags["GROUPING"] = [ALBUM_META["title"]]
        audio.tags["SERIES"] = [ALBUM_META["title"]]

        # Composer -> Often used for the Narrator/Voice Model
        audio.tags["COMPOSER"] = [ALBUM_META["composer"]]

        # --- 3. Embed Cover Art ---
        if os.path.exists(COVER_ART_PATH):
            mime = mimetypes.guess_type(COVER_ART_PATH)[0] or "image/jpeg"

            pic = Picture()
            with open(COVER_ART_PATH, "rb") as f:
                pic.data = f.read()

            pic.type = 3  # Cover (front)
            pic.mime = mime
            pic.desc = "Cover"

            # OggOpus requires base64 encoded picture block
            pic_data = pic.write()
            encoded_data = base64.b64encode(pic_data).decode("ascii")
            audio.tags["METADATA_BLOCK_PICTURE"] = [encoded_data]

        audio.save()
        return True
    except Exception as e:
        print(f"   Error tagging {os.path.basename(audio_path)}: {e}")
        return False


# --- Main Execution ---
if __name__ == "__main__":
    if not MUTAGEN_AVAILABLE:
        print("Mutagen is required. Please install it: pip install mutagen")
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
    total_tracks = len(audio_files)

    if not audio_files:
        print(f"No .opus files found in {AUDIO_DIR}")
        sys.exit(0)

    print(f"Found {total_tracks} files to tag.")

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
            title = f"Chapter {track_num}"  # Fallback

        # 2. Apply Tags
        if tag_audio_file(path, track_num, title, total_tracks):
            print(f"   Tagged: [{track_num}/{total_tracks}] {title}")
            success_count += 1

    print(f"\nDone. Successfully tagged {success_count} files.")
