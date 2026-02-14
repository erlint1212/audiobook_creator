import argparse
import glob
import json
import math
import os
import re
import shutil
import sys
import time
import traceback

import requests

# --- 1. WINDOWS UNICODE FIX ---
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import nltk
from nltk.tokenize import sent_tokenize

# --- NLTK Setup ---
NLTK_SETUP_SUCCESSFUL = False
try:
    nltk.sent_tokenize("This is a test.")
    NLTK_SETUP_SUCCESSFUL = True
except LookupError:
    print("NLTK tokenizer missing. Attempting to download resources...")
    try:
        nltk.download("punkt", quiet=False)
        nltk.download("punkt_tab", quiet=False)
        nltk.sent_tokenize("This is a test.")
        print("NLTK resources available.")
        NLTK_SETUP_SUCCESSFUL = True
    except Exception as download_e:
        print(f"NLTK Error: {download_e}")

if not NLTK_SETUP_SUCCESSFUL:
    print("\nNLTK setup failed. Run: python -m nltk.downloader punkt_tab")
    exit(1)

# --- Pydub Setup ---
try:
    from pydub import AudioSegment
    from pydub.exceptions import CouldntDecodeError

    PYDUB_AVAILABLE = True
except ImportError:
    print("Warning: pydub library not found. Audio concatenation will not work.")
    PYDUB_AVAILABLE = False

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALLTALK_API_URL = "http://127.0.0.1:7851/api/tts-generate"
ALLTALK_BASE_URL = "http://127.0.0.1:7851"

TEXT_FILES_DIR = os.getenv(
    "PROJECT_INPUT_TEXT_DIR", os.path.join(BASE_DIR, "BlleatTL_Novels")
)
AUDIO_OUTPUT_DIR = os.getenv(
    "PROJECT_AUDIO_WAV_DIR", os.path.join(BASE_DIR, "generated_audio")
)
PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(AUDIO_OUTPUT_DIR))

TEMP_CHUNK_DIR = os.path.join(PROJECT_ROOT_DIR, "temp_audio_chunks")
LOG_FILE = os.path.join(PROJECT_ROOT_DIR, "failed_chunks.log")

# --- PAUSE SETTINGS ---
CHUNK_PAUSE_MS = (
    450  # milliseconds of silence between chunks (Adjust this if too long/short)
)

CHAPTER_STOP = 0
FALLBACK_TOKEN_LIMIT = 170
AVG_CHARS_PER_TOKEN = 1.9
FALLBACK_CHAR_LIMIT = FALLBACK_TOKEN_LIMIT * AVG_CHARS_PER_TOKEN

# Global Settings (Will be set by args)
XTTS_SPEAKER_WAV = None
XTTS_LANGUAGE = "en"
RVC_ENABLE = False
RVC_MODEL_NAME_FOR_API = None
RVC_PITCH = 0
SPEED = 1.0
OUTPUT_FORMAT = "wav"


def _estimate_tokens(text, avg_chars_per_token=AVG_CHARS_PER_TOKEN):
    if not text:
        return 0
    return math.ceil(len(text) / max(1.0, avg_chars_per_token))


def normalize_text(text):
    # Ensure standard quotes
    replacements = {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
        "—": "-",
        "–": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # Force space after periods to prevent "sentence.sentence" rushing
    text = text.replace(".", ". ")
    text = re.sub(r"\s+", " ", text)  # Clean up double spaces
    return text


def _split_by_force_chars(text_content, char_limit):
    if len(text_content) <= char_limit:
        return [text_content]
    chunks = []
    current_chunk_start = 0
    while current_chunk_start < len(text_content):
        end_index = min(current_chunk_start + int(char_limit), len(text_content))
        if end_index < len(text_content):
            space_index = text_content.rfind(" ", current_chunk_start, end_index)
            if space_index != -1 and space_index > current_chunk_start:
                end_index = space_index
        chunk = text_content[current_chunk_start:end_index].strip()
        if chunk:
            chunks.append(chunk)
        current_chunk_start = end_index + 1
    return chunks


def _split_by_sentence_groups(text_content, token_limit, avg_chars_token_est):
    final_tts_chunks = []
    char_limit = token_limit * avg_chars_token_est
    try:
        sentences = sent_tokenize(text_content)
    except Exception as e:
        print(f"      [!] NLTK error: {e}. Fallback Lvl 3.")
        return _split_by_force_chars(text_content, char_limit)

    if not sentences:
        return []
    current_chunk_sentences_list = []
    current_chunk_tokens = 0

    for sentence_text in sentences:
        sentence_text = sentence_text.strip()
        if not sentence_text:
            continue
        estimated_sentence_tokens = _estimate_tokens(sentence_text, avg_chars_token_est)

        if estimated_sentence_tokens > token_limit:
            if current_chunk_sentences_list:
                final_tts_chunks.append(" ".join(current_chunk_sentences_list))
                current_chunk_sentences_list = []
                current_chunk_tokens = 0
            final_tts_chunks.extend(_split_by_force_chars(sentence_text, char_limit))
        elif current_chunk_tokens + estimated_sentence_tokens <= token_limit:
            current_chunk_sentences_list.append(sentence_text)
            current_chunk_tokens += estimated_sentence_tokens
        else:
            if current_chunk_sentences_list:
                final_tts_chunks.append(" ".join(current_chunk_sentences_list))
            current_chunk_sentences_list = [sentence_text]
            current_chunk_tokens = estimated_sentence_tokens

    if current_chunk_sentences_list:
        final_tts_chunks.append(" ".join(current_chunk_sentences_list))
    return [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]


def _split_by_line_groups(text_content, token_limit, avg_chars_token_est):
    final_tts_chunks = []
    if not text_content or not text_content.strip():
        return final_tts_chunks
    lines = [line.strip() for line in text_content.split("\n") if line.strip()]
    if not lines:
        return []

    current_chunk_lines_list = []
    current_chunk_tokens = 0

    for line_text in lines:
        estimated_line_tokens = _estimate_tokens(line_text, avg_chars_token_est)
        if estimated_line_tokens > token_limit:
            if current_chunk_lines_list:
                final_tts_chunks.append("\n".join(current_chunk_lines_list))
                current_chunk_lines_list = []
                current_chunk_tokens = 0
            final_tts_chunks.extend(
                _split_by_sentence_groups(line_text, token_limit, avg_chars_token_est)
            )
        elif current_chunk_tokens + estimated_line_tokens <= token_limit:
            current_chunk_lines_list.append(line_text)
            current_chunk_tokens += estimated_line_tokens
        else:
            if current_chunk_lines_list:
                final_tts_chunks.append("\n".join(current_chunk_lines_list))
            current_chunk_lines_list = [line_text]
            current_chunk_tokens = estimated_line_tokens

    if current_chunk_lines_list:
        final_tts_chunks.append("\n".join(current_chunk_lines_list))
    return [chunk for chunk in final_tts_chunks if chunk and chunk.strip()]


def download_audio_chunk(server_base_url, relative_audio_url, local_temp_path):
    try:
        full_url = server_base_url.rstrip("/") + "/" + relative_audio_url.lstrip("/")
        response = requests.get(full_url, stream=True, timeout=300)
        response.raise_for_status()
        with open(local_temp_path, "wb") as f:
            shutil.copyfileobj(response.raw, f)
        if os.path.exists(local_temp_path) and os.path.getsize(local_temp_path) > 100:
            return True
        return False
    except Exception as e:
        print(f"      Error downloading: {e}")
        return False


# --- IMPROVED CONCATENATION WITH SILENCE ---
def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    if not PYDUB_AVAILABLE or not chunk_filepaths:
        return False
    print(f"  Concatenating {len(chunk_filepaths)} chunks...")

    combined = AudioSegment.empty()
    # Create a silence segment
    silence = AudioSegment.silent(duration=CHUNK_PAUSE_MS)

    for i, filepath in enumerate(sorted(chunk_filepaths)):
        try:
            segment = AudioSegment.from_wav(filepath)
            combined += segment

            # Add silence after every chunk except the very last one
            if i < len(chunk_filepaths) - 1:
                combined += silence

        except CouldntDecodeError:
            print(f"      Error: Corrupt chunk {filepath}. Skipping.")

    if len(combined) > 0:
        combined.export(final_output_path, format=OUTPUT_FORMAT)
        print(f"  Saved to: {final_output_path}")
        return True
    return False


def process_chapter_file(text_filepath, final_audio_output_path):
    if not XTTS_SPEAKER_WAV:
        print("[Error] XTTS_SPEAKER_WAV is not set.")
        return False

    print(f"\n--- Processing: {os.path.basename(text_filepath)} ---")
    base_filename_no_ext = os.path.splitext(os.path.basename(text_filepath))[0]
    sanitized_base = re.sub(r"[^\w_.-]", "_", base_filename_no_ext)
    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, sanitized_base)
    os.makedirs(chapter_temp_dir, exist_ok=True)

    try:
        with open(text_filepath, "r", encoding="utf-8") as f:
            full_text_content = normalize_text(f.read())  # Added normalization
        if not full_text_content.strip():
            return True
    except Exception as e:
        print(f"  Error reading file: {e}")
        return False

    initial_text_chunks = _split_by_line_groups(
        full_text_content, FALLBACK_TOKEN_LIMIT, AVG_CHARS_PER_TOKEN
    )
    pending_jobs = [
        {"text": t, "output_suffix": f"l_{i+1:03d}", "fallback_level": 1}
        for i, t in enumerate(initial_text_chunks)
    ]

    generated_audio_files = []
    any_chunk_failed = False
    job_idx = 0

    while job_idx < len(pending_jobs):
        current_job = pending_jobs[job_idx]
        text_to_process = current_job["text"]
        output_suffix = current_job["output_suffix"]
        fallback_level = current_job.get("fallback_level", 1)

        chunk_basename = f"{sanitized_base}_{output_suffix}"
        local_filepath = os.path.join(
            chapter_temp_dir, f"{chunk_basename}.{OUTPUT_FORMAT}"
        )

        if os.path.exists(local_filepath) and os.path.getsize(local_filepath) > 100:
            generated_audio_files.append(local_filepath)
            job_idx += 1
            continue

        payload = {
            "text_input": text_to_process,
            "character_voice_gen": XTTS_SPEAKER_WAV,
            "language": XTTS_LANGUAGE,
            "output_file_name": chunk_basename,
            "rvccharacter_voice_gen": RVC_MODEL_NAME_FOR_API if RVC_ENABLE else "",
            "rvccharacter_pitch": RVC_PITCH,
            "speed": SPEED,
        }

        try:
            response = requests.post(ALLTALK_API_URL, data=payload, timeout=720)
            response.raise_for_status()
            response_data = response.json()

            if response_data.get("output_file_url"):
                if download_audio_chunk(
                    ALLTALK_BASE_URL, response_data["output_file_url"], local_filepath
                ):
                    generated_audio_files.append(local_filepath)
                else:
                    raise Exception("Download failed.")
            else:
                print(f"[!] API Error. Payload: {json.dumps(payload)}")
                raise Exception(f"API Error: {response_data.get('error')}")

            job_idx += 1
            time.sleep(0.1)

        except Exception as e:
            print(f"      [!!] Error: {e}")
            time.sleep(2)

            # Fallback Logic
            new_sub_jobs = []
            if fallback_level == 1:
                print(f"      -> Fallback Lvl 2 (Sentence Split)")
                chunks = _split_by_sentence_groups(
                    text_to_process, FALLBACK_TOKEN_LIMIT, AVG_CHARS_PER_TOKEN
                )
                for i, c in enumerate(chunks):
                    new_sub_jobs.append(
                        {
                            "text": c,
                            "output_suffix": f"{output_suffix}_s_{i+1:02d}",
                            "fallback_level": 2,
                        }
                    )
            elif fallback_level == 2:
                print(f"      -> Fallback Lvl 3 (Force Split)")
                chunks = _split_by_force_chars(text_to_process, FALLBACK_CHAR_LIMIT)
                for i, c in enumerate(chunks):
                    new_sub_jobs.append(
                        {
                            "text": c,
                            "output_suffix": f"{output_suffix}_f_{i+1:02d}",
                            "fallback_level": 3,
                        }
                    )

            if new_sub_jobs:
                pending_jobs = (
                    pending_jobs[:job_idx] + new_sub_jobs + pending_jobs[job_idx + 1 :]
                )
                continue
            else:
                print(f"      [Fail] Skipping chunk.")
                any_chunk_failed = True
                with open(LOG_FILE, "a", encoding="utf-8") as log_f:
                    log_f.write(f"FAILED: {output_suffix}\nText: {text_to_process}\n\n")
                job_idx += 1

    if not generated_audio_files:
        return False

    if concatenate_audio_chunks(generated_audio_files, final_audio_output_path):
        if not any_chunk_failed:
            try:
                shutil.rmtree(chapter_temp_dir)
            except:
                pass
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--voice_filename", type=str, required=True, help="XTTS WAV filename"
    )
    parser.add_argument("--rvc_model", type=str, default=None, help="RVC Model Name")
    parser.add_argument(
        "--pitch", type=int, default=0, help="RVC Pitch Shift (Semitones)"
    )

    args = parser.parse_args()

    XTTS_SPEAKER_WAV = os.path.basename(args.voice_filename)

    if args.rvc_model and args.rvc_model.lower() != "none" and args.rvc_model != "":
        RVC_ENABLE = True
        RVC_MODEL_NAME_FOR_API = args.rvc_model
        RVC_PITCH = args.pitch
        print(f"[Config] RVC Enabled: {RVC_MODEL_NAME_FOR_API} | Pitch: {RVC_PITCH}")
    else:
        RVC_ENABLE = False
        print("[Config] RVC Disabled")

    if not os.path.exists(TEMP_CHUNK_DIR):
        os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.exists(AUDIO_OUTPUT_DIR):
        os.makedirs(AUDIO_OUTPUT_DIR)

    text_files = sorted(glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt")))
    if not text_files:
        print(f"No .txt files found in {TEXT_FILES_DIR}")
        exit(1)

    print(f"Found {len(text_files)} files.")
    succeeded = 0
    for idx, text_file_path in enumerate(text_files):
        base_name = os.path.splitext(os.path.basename(text_file_path))[0]
        clean_name = re.sub(r"[^\w_.-]", "_", base_name)
        out_path = os.path.join(AUDIO_OUTPUT_DIR, f"{clean_name}.{OUTPUT_FORMAT}")

        if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
            print(f"Skipping {clean_name} (Exists)")
            succeeded += 1
            continue

        if process_chapter_file(text_file_path, out_path):
            succeeded += 1
