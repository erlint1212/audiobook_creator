import ffmpeg
import os

# --- Iteration Configuration ---
START_CHAPTER = 2
END_CHAPTER = 6  # Set this to your desired last chapter number

# --- Base Path Configuration (Uses your folder structure) ---
IMAGE_PATH = "Portrait_half-light.png" # Assumed static for all chapters
BASE_SRT_DIR = "generated_audio_IATMCB_opus"
BASE_WAV_DIR = "generated_audio_IATMCB"
BASE_OUTPUT_DIR = "videos"
BASE_TITLE_TEXT_DIR = "scraped_IATMCB_celsetial_pavilion" # Directory for title text files

# --- Static Video Configuration (applied to all chapters) ---
FRAME_RATE = 25
SUBTITLE_FONT_NAME = "Libre Baskerville"
SUBTITLE_FONT_SIZE = "24"
SUBTITLE_MARGIN_V = 60 # Vertical margin for subtitles, below the page title
PAGE_COLOR = "0x1E1E1E"  # Background color for the text pane (244px wide)
SUBTITLE_FONT_COLOR = "&H00E0E0E0&"  # ASS format &HAABBGGRR

# Page Title Overlay Configuration (Static parts)
PAGE_TITLE_FONT_FILE = "C:/Windows/Fonts/BASKVILL.TTF" # Ensure this path is correct
PAGE_TITLE_FONT_SIZE = 30
PAGE_TITLE_FONT_COLOR_HEX = "E0E0E0"
PAGE_TITLE_Y_POSITION = 20

# --- Audio Normalization Configuration ---
TARGET_INTEGRATED_LOUDNESS = -20.0  # LUFS
TARGET_TRUE_PEAK = -1.5             # dBTP
TARGET_LOUDNESS_RANGE = 11.0        # LU

def process_chapter(chapter_num):
    """
    Generates a video for a specific chapter, fetching the title dynamically and normalizing audio.
    """
    chapter_num_str = f"{chapter_num:03d}"

    current_srt_path = os.path.join(BASE_SRT_DIR, f"ch_{chapter_num_str}.srt")
    current_wav_path = os.path.join(BASE_WAV_DIR, f"ch_{chapter_num_str}.wav")
    current_output_path = os.path.join(BASE_OUTPUT_DIR, f"ch_{chapter_num_str}.mp4")
    title_text_file_path = os.path.join(BASE_TITLE_TEXT_DIR, f"ch_{chapter_num_str}.txt")

    if not os.path.exists(current_srt_path):
        print(f"SRT file not found for chapter {chapter_num}: {current_srt_path}. Skipping.")
        return
    if not os.path.exists(current_wav_path):
        print(f"WAV file not found for chapter {chapter_num}: {current_wav_path}. Skipping.")
        return

    raw_page_title = f"Chapter {chapter_num}"
    if os.path.exists(title_text_file_path):
        try:
            with open(title_text_file_path, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
            if first_line:
                raw_page_title = first_line
            else:
                print(f"Warning: Title file {title_text_file_path} is empty. Using default title: '{raw_page_title}'.")
        except Exception as e:
            print(f"Warning: Could not read title file {title_text_file_path}: {e}. Using default title: '{raw_page_title}'.")
    else:
        print(f"Warning: Title file not found: {title_text_file_path}. Using default title: '{raw_page_title}'.")

    cleaned_page_title_text = raw_page_title.replace(":", " - ")
    escaped_page_title_text = cleaned_page_title_text
    escaped_page_title_text = escaped_page_title_text.replace('\\', '\\\\')
    escaped_page_title_text = escaped_page_title_text.replace("'", "\\'")
    escaped_page_title_text = escaped_page_title_text.replace("%", "\\%")

    output_directory = os.path.dirname(current_output_path)
    if output_directory and not os.path.exists(output_directory):
        os.makedirs(output_directory)

    print(f"Starting FFmpeg process for Chapter {chapter_num} -> {current_output_path} ...")
    print(f"Using Title: \"{cleaned_page_title_text}\"")

    try:
        input_image = ffmpeg.input(IMAGE_PATH, loop=1, framerate=FRAME_RATE)
        input_audio_stream = ffmpeg.input(current_wav_path)['a'] # Select audio stream directly
        input_text_bg = ffmpeg.input(f"color=c={PAGE_COLOR}:s=762x720:r={FRAME_RATE}", format='lavfi')

        # Apply loudness normalization to the audio stream
        normalized_audio_stream = input_audio_stream.filter(
            'loudnorm',
            I=TARGET_INTEGRATED_LOUDNESS,
            LRA=TARGET_LOUDNESS_RANGE,
            tp=TARGET_TRUE_PEAK,
            print_format='summary' # This will print normalization details to stderr
        )

        img_pane = input_image['v'].filter('scale', width=518, height=720).filter('setpts', 'PTS-STARTPTS')
        txt_pane_bg = input_text_bg['v'].filter('setpts', 'PTS-STARTPTS')

        subtitle_force_style = (
            f"FontName={SUBTITLE_FONT_NAME},"
            f"PrimaryColour={SUBTITLE_FONT_COLOR},"
            f"FontSize={SUBTITLE_FONT_SIZE},Alignment=5,MarginL=10,MarginV={SUBTITLE_MARGIN_V}"
        )
        txt_pane_with_subs = txt_pane_bg.filter('subtitles', filename=current_srt_path, force_style=subtitle_force_style)

        txt_pane_final = txt_pane_with_subs.drawtext(
            text=escaped_page_title_text,
            fontfile=PAGE_TITLE_FONT_FILE,
            fontsize=PAGE_TITLE_FONT_SIZE,
            fontcolor=PAGE_TITLE_FONT_COLOR_HEX,
            x='(w-text_w)/2',
            y=str(PAGE_TITLE_Y_POSITION)
        )

        video_content = ffmpeg.filter([img_pane, txt_pane_final], 'hstack', inputs=2)

        process = (
            ffmpeg
            .output(
                video_content,             # Video stream
                normalized_audio_stream,   # Use the normalized audio stream
                current_output_path,
                **{'c:v': 'libx264'},
                preset='medium',
                crf=23,
                pix_fmt='yuv420p',
                **{'c:a': 'aac'},
                **{'b:a': '192k'},
                shortest=None,
            )
            .overwrite_output()
        )

        # print(f"FFmpeg command for Chapter {chapter_num}:")
        # print(' '.join(process.compile()))

        stdout, stderr = process.run(capture_stdout=True, capture_stderr=True)

        print(f"Chapter {chapter_num} processing complete. Output at: {current_output_path}")
        if stderr:
            print(f"FFmpeg messages for Chapter {chapter_num} (stderr):")
            print(stderr.decode('utf-8', errors='ignore'))

    except ffmpeg.Error as e:
        print(f"An FFmpeg error occurred for Chapter {chapter_num}:")
        print("STDERR:", e.stderr.decode('utf-8', errors='ignore') if e.stderr else 'N/A')
    except Exception as e_gen:
        print(f"An unexpected Python error occurred for Chapter {chapter_num}: {e_gen}")

def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"Error: Static image file not found: {IMAGE_PATH}. Exiting.")
        return
    
    if BASE_OUTPUT_DIR and not os.path.exists(BASE_OUTPUT_DIR):
        os.makedirs(BASE_OUTPUT_DIR)
        print(f"Created base output directory: {BASE_OUTPUT_DIR}")

    for chapter_num in range(START_CHAPTER, END_CHAPTER + 1):
        print(f"\n--- Preparing to Process Chapter {chapter_num} ---")
        process_chapter(chapter_num)
    
    print("\n--- All chapter processing finished. ---")

if __name__ == '__main__':
    main()
