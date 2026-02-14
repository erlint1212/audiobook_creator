import argparse
import glob
import math
import os
import re
import shutil
import sys
import time

import soundfile as sf
import torch

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import nltk
from nltk.tokenize import sent_tokenize

# --- Import AI Models ---
from qwen_tts import Qwen3TTSModel
from rvc_python.infer import RVCInference

# --- NLTK Setup ---
NLTK_SETUP_SUCCESSFUL = False
try:
    nltk.sent_tokenize("This is a test.")
    NLTK_SETUP_SUCCESSFUL = True
except LookupError:
    nltk.download("punkt", quiet=False)
    NLTK_SETUP_SUCCESSFUL = True

from pydub import AudioSegment

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEXT_FILES_DIR = os.getenv(
    "PROJECT_INPUT_TEXT_DIR", os.path.join(BASE_DIR, "BlleatTL_Novels")
)
AUDIO_OUTPUT_DIR = os.getenv(
    "PROJECT_AUDIO_WAV_DIR", os.path.join(BASE_DIR, "generated_audio_HalfLight")
)
PROJECT_ROOT_DIR = os.path.dirname(os.path.abspath(AUDIO_OUTPUT_DIR))

TEMP_CHUNK_DIR = os.path.join(PROJECT_ROOT_DIR, "temp_audio_chunks")

FALLBACK_TOKEN_LIMIT = 170
AVG_CHARS_PER_TOKEN = 1.9
FALLBACK_CHAR_LIMIT = FALLBACK_TOKEN_LIMIT * AVG_CHARS_PER_TOKEN

OUTPUT_FORMAT = "wav"

# Global Models
qwen_model = None
rvc_model = None

# Tone instruction for "Half Light"
ACTING_PROMPT = "Speak in a very aggressive, threatening, and visceral tone. A raspy, angry whisper-shout."


def concatenate_audio_chunks(chunk_filepaths, final_output_path):
    if not chunk_filepaths:
        return False
    print(f"  Concatenating {len(chunk_filepaths)} chunks...")
    combined = AudioSegment.empty()
    for filepath in sorted(chunk_filepaths):
        combined += AudioSegment.from_wav(filepath)

    if len(combined) > 0:
        combined.export(final_output_path, format=OUTPUT_FORMAT)
        return True
    return False


# ... [KEEP YOUR EXISTING SPLIT FUNCTIONS HERE: _estimate_tokens, _split_by_force_chars, _split_by_sentence_groups, _split_by_line_groups] ...
# (I am omitting them here for brevity, but keep the exact same chunking functions from your previous script)


def process_chapter_file(text_filepath, final_audio_output_path):
    print(f"\n--- Processing: {os.path.basename(text_filepath)} ---")
    base_name = os.path.splitext(os.path.basename(text_filepath))[0]
    sanitized_base = re.sub(r"[^\w_.-]", "_", base_name)

    chapter_temp_dir = os.path.join(TEMP_CHUNK_DIR, sanitized_base)
    os.makedirs(chapter_temp_dir, exist_ok=True)

    with open(text_filepath, "r", encoding="utf-8") as f:
        full_text_content = f.read()

    initial_text_chunks = _split_by_line_groups(
        full_text_content, FALLBACK_TOKEN_LIMIT, AVG_CHARS_PER_TOKEN
    )

    generated_audio_files = []

    for i, text_to_process in enumerate(initial_text_chunks):
        output_suffix = f"l_{i+1:03d}"
        chunk_output_basename = f"{sanitized_base}_{output_suffix}"
        local_chunk_filepath = os.path.join(
            chapter_temp_dir, f"{chunk_output_basename}.{OUTPUT_FORMAT}"
        )

        if os.path.exists(local_chunk_filepath):
            generated_audio_files.append(local_chunk_filepath)
            continue

        try:
            print(f"      [1/2] Qwen Acting for chunk {output_suffix}...")
            # 1. Generate acting with Qwen
            wavs, sr = qwen_model.generate_custom_voice(
                text=text_to_process,
                language="English",
                speaker="Ryan",  # Base male voice, fits well for shifting into Half Light
                instruct=ACTING_PROMPT,
            )

            # Save Qwen audio
            sf.write(local_chunk_filepath, wavs[0], sr)

            print(f"      [2/2] Applying Half Light RVC Skin...")
            # 2. Apply RVC to the generated audio, overwriting the file
            rvc_model.infer_file(
                local_chunk_filepath,
                local_chunk_filepath,  # Save over the original
            )

            generated_audio_files.append(local_chunk_filepath)

        except Exception as e:
            print(f"      [!!] Error: {e}")

    if concatenate_audio_chunks(generated_audio_files, final_audio_output_path):
        shutil.rmtree(chapter_temp_dir)
        return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qwen3-TTS + RVC Generator")
    parser.add_argument(
        "--rvc_model_path", type=str, required=True, help="Path to your .pth file"
    )
    parser.add_argument(
        "--rvc_index_path", type=str, required=True, help="Path to your .index file"
    )
    parser.add_argument(
        "--pitch", type=int, default=-2, help="Pitch shift (try -12 for deep voices)"
    )
    args = parser.parse_args()

    # --- 1. INITIALIZE QWEN ---
    print("Loading Qwen3-TTS CustomVoice Model...")
    qwen_model = Qwen3TTSModel.from_pretrained(
        "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",  # Using CustomVoice for acting control
        device_map="cuda:0",
        dtype=torch.bfloat16,
        attn_implementation="flash_attention_2",
    )

    # --- 2. INITIALIZE RVC ---
    print("Loading Half Light RVC Model...")
    rvc_model = RVCInference(device="cuda:0")
    rvc_model.load_model(args.rvc_model_path)
    rvc_model.set_params(
        f0method="rmvpe",  # Best pitch extraction method
        f0up_key=args.pitch,
        index_file=args.rvc_index_path,
        index_rate=0.75,  # How strongly to enforce the voice print
        filter_radius=3,
        resample_sr=0,
        rms_mix_rate=0.25,
        protect=0.33,
    )

    # --- SETUP DIRECTORIES ---
    if not os.path.exists(TEMP_CHUNK_DIR):
        os.makedirs(TEMP_CHUNK_DIR)
    if not os.path.exists(AUDIO_OUTPUT_DIR):
        os.makedirs(AUDIO_OUTPUT_DIR)

    text_files = sorted(glob.glob(os.path.join(TEXT_FILES_DIR, "*.txt")))
    print(f"Found {len(text_files)} chapters.")

    for text_file_path in text_files:
        base_name = os.path.splitext(os.path.basename(text_file_path))[0]
        out_path = os.path.join(AUDIO_OUTPUT_DIR, f"{base_name}.{OUTPUT_FORMAT}")

        if not os.path.exists(out_path):
            process_chapter_file(text_file_path, out_path)
