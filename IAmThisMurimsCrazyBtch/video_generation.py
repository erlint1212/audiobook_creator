import ffmpeg
import os

# --- Configuration ---
IMAGE_PATH = "Portrait_half-light.png"
SRT_PATH = "generated_audio_IATMCB_opus/ch_001.srt"
WAV_PATH = "generated_audio_IATMCB/ch_001.wav"
OUTPUT_PATH = "videos/ch_001.mp4"

SUBTITLE_FONT_NAME = "Libre Baskerville"
SUBTITLE_FONT_SIZE = "24" # Keep as string for f-string formatting
# Vertical margin for subtitles, adjusted to be below the page title
SUBTITLE_MARGIN_V = 60 # Increased from 10

PAGE_COLOR = "0x1E1E1E"  # Background color for the text pane
SUBTITLE_FONT_COLOR = "&H00E0E0E0&"  # ASS format &HAABBGGRR

# --- Page Title Overlay Configuration ---
PAGE_TITLE_TEXT = "Chapter 0 - Gaming, A Fundamental Skill for Factory Workers"
# PAGE_TITLE_DURATION = 7 # No longer needed as title will be static

PAGE_TITLE_FONT_FILE = "C:/Windows/Fonts/BASKVILL.TTF" # Ensure this path is correct
PAGE_TITLE_FONT_SIZE = 30
PAGE_TITLE_FONT_COLOR_HEX = "E0E0E0"  # RRGGBB hex format
PAGE_TITLE_Y_POSITION = 20  # Position from the top of the text pane (244px wide)

def main():
    # --- Prepare Page Title Text by escaping special characters for FFmpeg drawtext ---
    escaped_page_title_text = PAGE_TITLE_TEXT
    escaped_page_title_text = escaped_page_title_text.replace('\\', '\\\\')
    escaped_page_title_text = escaped_page_title_text.replace("'", "\\'")
    escaped_page_title_text = escaped_page_title_text.replace(":", "\\:")
    escaped_page_title_text = escaped_page_title_text.replace("%", "\\%")

    # --- Ensure the output directory exists ---
    output_directory = os.path.dirname(OUTPUT_PATH)
    if output_directory and not os.path.exists(output_directory):
        os.makedirs(output_directory)
        print(f"Created output directory: {output_directory}")

    print("Starting FFmpeg process...")

    try:
        input_image = ffmpeg.input(IMAGE_PATH, loop=1, framerate=25)
        input_audio = ffmpeg.input(WAV_PATH)
        # Corrected size for text_pane_bg to 244x720
        input_text_bg = ffmpeg.input(f"color=c={PAGE_COLOR}:s=762x720", format='lavfi', r=25)

        img_pane = input_image['v'].filter('scale', width=518, height=720).filter('setpts', 'PTS-STARTPTS')
        txt_pane_bg = input_text_bg['v'].filter('setpts', 'PTS-STARTPTS')

        subtitle_force_style = (
            f"FontName={SUBTITLE_FONT_NAME},"
            f"PrimaryColour={SUBTITLE_FONT_COLOR},"
            f"FontSize={SUBTITLE_FONT_SIZE},Alignment=5,MarginL=10,MarginV={SUBTITLE_MARGIN_V}" # Using new SUBTITLE_MARGIN_V
        )
        txt_pane_with_subs = txt_pane_bg.filter('subtitles', filename=SRT_PATH, force_style=subtitle_force_style)

        # Drawtext for the static page title
        # Removed 'enable' option to make it static
        txt_pane_final = txt_pane_with_subs.drawtext(
            text=escaped_page_title_text,
            fontfile=PAGE_TITLE_FONT_FILE,
            fontsize=PAGE_TITLE_FONT_SIZE,
            fontcolor=PAGE_TITLE_FONT_COLOR_HEX,
            x='(w-text_w)/2', # Centered horizontally in the 244px text pane
            y=str(PAGE_TITLE_Y_POSITION)
        )

        video_content = ffmpeg.filter([img_pane, txt_pane_final], 'hstack', inputs=2)

        process = (
            ffmpeg
            .output(
                video_content,
                input_audio['a'],
                OUTPUT_PATH,
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

        print("FFmpeg command to be executed:")
        print(' '.join(process.compile()))

        stdout, stderr = process.run(capture_stdout=True, capture_stderr=True)

        print(f"Video processing complete. Output at: {OUTPUT_PATH}")
        if stderr:
            print("FFmpeg messages (stderr):")
            print(stderr.decode('utf-8', errors='ignore'))

    except ffmpeg.Error as e:
        print("An error occurred with FFmpeg:")
        print("STDOUT:", e.stdout.decode('utf-8', errors='ignore') if e.stdout else 'N/A')
        print("STDERR:", e.stderr.decode('utf-8', errors='ignore') if e.stderr else 'N/A')
    except Exception as e_gen:
        print(f"An unexpected Python error occurred: {e_gen}")

if __name__ == '__main__':
    main()
