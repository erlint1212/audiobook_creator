import os
import glob
import re
import difflib
import math

# --- SRT Helper Functions ---
def time_to_seconds(time_str):
    """Converts HH:MM:SS,mmm SRT time string to seconds."""
    parts = re.split(r'[:,]', time_str)
    h, m, s, ms = map(int, parts)
    return h * 3600 + m * 60 + s + ms / 1000.0

def seconds_to_srt_time(seconds_float):
    """Converts seconds (float) to HH:MM:SS,mmm SRT time string."""
    hours = int(seconds_float // 3600)
    seconds_float %= 3600
    minutes = int(seconds_float // 60)
    seconds_float %= 60
    seconds = int(seconds_float // 1)
    milliseconds = int(round((seconds_float % 1) * 1000))
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

def parse_srt_file(filepath):
    """
    Parses an SRT file.
    Returns a list of dictionaries:
    [{'index': int, 'start_time': float, 'end_time': float, 
      'start_srt': str, 'end_srt': str, 'text': str}, ...]
    """
    segments = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        raw_segments = content.split('\n\n')
        for raw_segment in raw_segments:
            if not raw_segment.strip():
                continue
            lines = raw_segment.split('\n')
            if len(lines) < 3: # Index, Time, Text (at least)
                # print(f"  Warning: Malformed segment in {filepath}: {lines}")
                continue
            
            index = int(lines[0])
            time_match = re.match(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', lines[1])
            if not time_match:
                # print(f"  Warning: Malformed time string in {filepath}: {lines[1]}")
                continue
                
            start_srt, end_srt = time_match.groups()
            text_lines = lines[2:]
            text = "\n".join(text_lines).strip()
            
            segments.append({
                'index': index,
                'start_time': time_to_seconds(start_srt),
                'end_time': time_to_seconds(end_srt),
                'start_srt': start_srt,
                'end_srt': end_srt,
                'text': text
            })
    except Exception as e:
        print(f"  Error parsing SRT file {filepath}: {e}")
    return segments

def write_srt_file(segments, filepath):
    """
    Writes a list of segment dictionaries to an SRT file.
    Expects segments like: {'start_srt': str, 'end_srt': str, 'text': str}
    """
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments):
                f.write(f"{i + 1}\n")
                f.write(f"{segment['start_srt']} --> {segment['end_srt']}\n")
                f.write(f"{segment['text']}\n\n")
        print(f"  Successfully wrote corrected SRT: {filepath}")
    except Exception as e:
        print(f"  Error writing SRT file {filepath}: {e}")

# --- Core Correction Logic ---
def generate_corrected_full_text(whisper_text_cleaned, original_text_cleaned, original_text_raw):
    """
    Generates a 'corrected' version of the full text by aligning whisper_text_cleaned
    with original_text_cleaned and preferring content from original_text_raw.
    """
    matcher = difflib.SequenceMatcher(None, whisper_text_cleaned, original_text_cleaned, autojunk=False)
    corrected_chunks = []
    
    # Pointers for the raw original text to extract actual content
    original_raw_ptr = 0
    
    # This requires careful mapping of cleaned indices back to raw indices if there were significant changes.
    # For simplicity in this version, we'll use the cleaned original text for reconstruction,
    # assuming it's good enough or that the user will use the raw original if they adapt this.
    # A more robust way would be to align based on cleaned, but pull from raw using character offset mapping.
    # For now, let's assume original_text_raw is used when pulling 'equal' or 'replace' from original_text_cleaned.
    # This is complex. Let's simplify: reconstruct based on original_text_cleaned, assuming it's "the truth".
    # If user wants precise casing/punctuation from original_text_raw, they'd need a more sophisticated alignment.

    # We will rebuild the text primarily from the original_text_cleaned side of the alignment.
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            corrected_chunks.append(original_text_cleaned[j1:j2])
        elif tag == 'replace':
            corrected_chunks.append(original_text_cleaned[j1:j2]) # Prefer original text
        elif tag == 'delete': # Text in Whisper, not in original (so omit Whisper's part)
            pass
        elif tag == 'insert': # Text in original, not in Whisper (so insert original's part)
            corrected_chunks.append(original_text_cleaned[j1:j2])
            
    return "".join(corrected_chunks)


def correct_srt_file(input_srt_path, original_text_path, output_srt_path):
    """
    Corrects the text in an SRT file using an original text manuscript.
    """
    print(f"\nProcessing to correct: {os.path.basename(input_srt_path)}")
    print(f"  Using original text: {os.path.basename(original_text_path)}")

    srt_segments = parse_srt_file(input_srt_path)
    if not srt_segments:
        print(f"  No segments found or error parsing SRT: {input_srt_path}. Skipping.")
        return

    try:
        with open(original_text_path, 'r', encoding='utf-8') as f:
            original_text_raw = f.read()
    except Exception as e:
        print(f"  Error reading original text file {original_text_path}: {e}. Skipping.")
        return

    if not original_text_raw.strip():
        print(f"  Original text file {original_text_path} is empty. Skipping.")
        return

    # 1. Get all text from Whisper SRT and its structure
    whisper_segment_texts_raw = [seg['text'] for seg in srt_segments]
    
    # 2. Prepare texts for alignment (simple cleaning: join, normalize spaces)
    #    We need the lengths of the *cleaned* whisper segments to do proportional distribution later.
    def clean_text_for_alignment(text):
        return ' '.join(text.lower().split())

    cleaned_whisper_segment_texts = [clean_text_for_alignment(text) for text in whisper_segment_texts_raw]
    cleaned_whisper_full_text = " ".join(cleaned_whisper_segment_texts) # Use a space as a pseudo-separator
                                                                       # This helps difflib a bit but isn't perfect.
    
    cleaned_original_full_text = clean_text_for_alignment(original_text_raw)

    if not cleaned_whisper_full_text:
        print(f"  Whisper SRT {os.path.basename(input_srt_path)} contains no text after cleaning. Skipping.")
        return

    # 3. Generate the 'corrected' full text stream based on alignment
    #    This text will be sourced from original_text_raw, guided by alignment.
    #    For this version, we construct `corrected_text_stream` from `original_text_raw` by following opcodes.
    
    matcher = difflib.SequenceMatcher(None, cleaned_whisper_full_text, cleaned_original_full_text, autojunk=False)
    
    # Reconstruct the corrected text, taking characters from the *raw original text*
    # This requires mapping cleaned indices (from opcodes) back to raw indices, which is hard.
    # Simplification: we will build the corrected_text_stream from original_text_raw
    # based on what parts of original_text_CLEANED were kept by the opcodes.
    # This is still an approximation.
    
    corrected_text_stream_parts = []
    # Pointers for raw text extraction (this is tricky due to cleaning)
    # A truly robust solution needs more advanced tokenization and alignment.
    # For now, let's use the cleaned original text for forming the stream, and the user
    # can refine if exact casing/punctuation from raw is needed (which means a much more complex char mapping).
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal' or tag == 'replace': # take from original
            corrected_text_stream_parts.append(cleaned_original_full_text[j1:j2])
        elif tag == 'insert': # text in original not in whisper
            corrected_text_stream_parts.append(cleaned_original_full_text[j1:j2])
        # 'delete' (text in whisper not in original) is implicitly handled by not adding from whisper_text
        
    corrected_full_text_aligned = "".join(corrected_text_stream_parts)
    # This ^ text is now aligned to whisper_full_text's structure but with original content.
    # We need to distribute *this* proportionally. The cleaning might have removed spaces used as separators.
    # Let's use a more direct approach: build the corrected text using original_text_raw for "equal" and "replace".

    corrected_full_text_raw_pieces = []
    ptr_original_raw = 0
    ptr_whisper_clean = 0
    ptr_original_clean = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        len_whisper_clean_segment = i2 - i1
        len_original_clean_segment = j2 - j1

        if tag == 'equal' or tag == 'replace':
            # Attempt to extract corresponding raw segment from original_text_raw
            # This is an approximation: assumes cleaning doesn't drastically change lengths/offsets
            # A proper solution would involve token-level alignment or careful char mapping
            start_raw_approx = original_text_raw.lower().find(cleaned_original_full_text[j1:j1+10], ptr_original_raw) # find start of segment
            if start_raw_approx != -1:
                 # Try to find a reasonable end point
                rough_end_raw_approx = start_raw_approx + len(cleaned_original_full_text[j1:j2]) * 2 # give some buffer
                # This is still very heuristic. True character mapping is needed for perfection.
                # For this script, we'll simplify and just use the cleaned original text, as pulling from raw
                # perfectly based on cleaned alignment is beyond a simple script.
                corrected_full_text_raw_pieces.append(cleaned_original_full_text[j1:j2]) # Use cleaned original as proxy
            else: # fallback if find fails
                 corrected_full_text_raw_pieces.append(cleaned_original_full_text[j1:j2])
            ptr_original_raw = start_raw_approx + len(cleaned_original_full_text[j1:j2]) if start_raw_approx !=-1 else ptr_original_raw + len_original_clean_segment

        elif tag == 'insert': # text in original not in whisper
            corrected_full_text_raw_pieces.append(cleaned_original_full_text[j1:j2])
            # ptr_original_raw advances similarly
            start_raw_approx = original_text_raw.lower().find(cleaned_original_full_text[j1:j1+10], ptr_original_raw)
            ptr_original_raw = start_raw_approx + len(cleaned_original_full_text[j1:j2]) if start_raw_approx !=-1 else ptr_original_raw + len_original_clean_segment

        # For 'delete', we add nothing from whisper, and original_raw_ptr doesn't move based on original text for this block

    corrected_text_to_distribute = " ".join(" ".join(corrected_full_text_raw_pieces).split()) # Normalize spaces


    # 4. Distribute the corrected_text_to_distribute into new SRT segments
    #    maintaining original timings and segment count.
    new_srt_segments = []
    total_cleaned_whisper_len = sum(len(s) for s in cleaned_whisper_segment_texts)
    if total_cleaned_whisper_len == 0: # Avoid division by zero if whisper SRT was empty
        print(f"  Cleaned Whisper text for {os.path.basename(input_srt_path)} is empty. Cannot perform proportional distribution.")
        # Create SRT with original timings but empty text or placeholder
        for i, seg_info in enumerate(srt_segments):
            new_srt_segments.append({
                'index': i + 1,
                'start_srt': seg_info['start_srt'],
                'end_srt': seg_info['end_srt'],
                'text': "[Correction failed: Whisper text empty]"
            })
        write_srt_file(new_srt_segments, output_srt_path)
        return

    current_pos_in_corrected_text = 0
    total_len_corrected_text = len(corrected_text_to_distribute)

    for i, seg_info in enumerate(srt_segments):
        original_cleaned_segment_len = len(cleaned_whisper_segment_texts[i])
        proportion = original_cleaned_segment_len / total_cleaned_whisper_len if total_cleaned_whisper_len > 0 else 0
        
        chars_to_take = math.ceil(proportion * total_len_corrected_text) # Use math.ceil to try and use up all text
        
        # Ensure we don't overshoot, especially for the last segment
        if i == len(srt_segments) - 1: # Last segment takes the rest
            new_text_for_segment = corrected_text_to_distribute[current_pos_in_corrected_text:]
        else:
            end_slice = min(current_pos_in_corrected_text + chars_to_take, total_len_corrected_text)
            new_text_for_segment = corrected_text_to_distribute[current_pos_in_corrected_text:end_slice]
        
        current_pos_in_corrected_text += len(new_text_for_segment) #  Use actual length of slice taken

        new_srt_segments.append({
            'index': i + 1, # Keep original index from parsing if needed, or re-index
            'start_srt': seg_info['start_srt'],
            'end_srt': seg_info['end_srt'],
            'text': new_text_for_segment.strip() if new_text_for_segment else seg_info['text'] # Fallback if new text is empty
        })

    write_srt_file(new_srt_segments, output_srt_path)


if __name__ == "__main__":
    # --- Configuration ---
    # Directory containing the Whisper-generated .srt files
    # Example: generated_audio_tileas_worries_opus/
    SRT_INPUT_DIR = "generated_audio_tileas_worries_opus"  # <--- !!! UPDATE THIS !!!

    # Directory containing the original .txt manuscript files
    # Example: scraped_tileas_worries/
    ORIGINAL_TEXT_DIR = "scraped_tileas_worries"  # <--- !!! UPDATE THIS !!!

    # Directory where the corrected .srt files will be saved
    CORRECTED_SRT_OUTPUT_DIR = "generated_audio_tileas_worries_opus_corrected_srt" # <--- !!! UPDATE THIS !!!
    
    # File pattern for SRT files
    SRT_FILENAME_PATTERN = "ch_*.srt" # Example: "*.srt" or "ch_*.srt"
    # ---------------------

    print("--- Starting SRT Correction Process ---")
    print(f"Input SRT Directory: {os.path.abspath(SRT_INPUT_DIR)}")
    print(f"Original Text Directory: {os.path.abspath(ORIGINAL_TEXT_DIR)}")
    print(f"Corrected SRT Output Directory: {os.path.abspath(CORRECTED_SRT_OUTPUT_DIR)}")
    print(f"SRT Filename Pattern: {SRT_FILENAME_PATTERN}")
    print("-" * 70)

    if not os.path.isdir(SRT_INPUT_DIR):
        print(f"Error: SRT input directory '{SRT_INPUT_DIR}' not found.")
        exit()
    if not os.path.isdir(ORIGINAL_TEXT_DIR):
        print(f"Error: Original text directory '{ORIGINAL_TEXT_DIR}' not found.")
        exit()

    if not os.path.exists(CORRECTED_SRT_OUTPUT_DIR):
        try:
            os.makedirs(CORRECTED_SRT_OUTPUT_DIR)
            print(f"Created output directory: {CORRECTED_SRT_OUTPUT_DIR}")
        except OSError as e:
            print(f"Error creating output directory '{CORRECTED_SRT_OUTPUT_DIR}': {e}")
            exit()

    srt_files_to_process = glob.glob(os.path.join(SRT_INPUT_DIR, SRT_FILENAME_PATTERN))
    srt_files_to_process.sort()

    if not srt_files_to_process:
        print(f"No SRT files matching pattern '{SRT_FILENAME_PATTERN}' found in '{SRT_INPUT_DIR}'.")
        exit()

    print(f"Found {len(srt_files_to_process)} SRT files to process.\n")
    
    success_count = 0
    fail_count = 0

    for srt_path in srt_files_to_process:
        srt_basename = os.path.basename(srt_path)
        text_filename = os.path.splitext(srt_basename)[0] + ".txt"
        original_text_path = os.path.join(ORIGINAL_TEXT_DIR, text_filename)
        
        output_srt_path = os.path.join(CORRECTED_SRT_OUTPUT_DIR, srt_basename)

        if not os.path.exists(original_text_path):
            print(f"Warning: Original text file not found for {srt_basename} (expected at {original_text_path}). Skipping.")
            fail_count +=1
            continue
        
        try:
            correct_srt_file(srt_path, original_text_path, output_srt_path)
            success_count +=1
        except Exception as e:
            print(f"  UNEXPECTED CRITICAL ERROR processing {srt_basename}: {e}")
            fail_count +=1


    print("\n" + "-" * 70)
    print("--- SRT Correction Process Complete ---")
    print(f"Successfully processed (or attempted): {success_count} files.")
    print(f"Failed or skipped: {fail_count} files.")
    print(f"Corrected SRT files should be in: {os.path.abspath(CORRECTED_SRT_OUTPUT_DIR)}")
