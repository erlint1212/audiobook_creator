#!/bin/bash

IMAGE_PATH="Portrait_half-light.png"
SRT_PATH="generated_audio_IATMCB_opus/ch_001.srt"
WAV_PATH="generated_audio_IATMCB/ch_001.wav"
OUTPUT_PATH="videos/ch_001.mp4"
FONT_STYLE="Libre Baskerville"
PAGE_COLOR="0x1E1E1E"
FONT_COLOR="&H00E0E0E0&"

# --- Page Title Overlay Configuration ---
PAGE_TITLE_TEXT="Chapter 0: Gaming: A Fundamental Skill for Factory Workers"   # Your desired title text
PAGE_TITLE_DURATION=7                # How long the title stays on screen (seconds)
PAGE_TITLE_FONT_STYLE="Anton"
PAGE_TITLE_FONT_SIZE=30
PAGE_TITLE_FONT_COLOR_HEX="D1D1D1"   # A slightly different off-white for the title
PAGE_TITLE_Y_POSITION=25             # Vertical position from the top of the text pane

# Ensure the output directory exists
mkdir -p "$(dirname "$OUTPUT_PATH")"

ffmpeg \
-loop 1 -i "$IMAGE_PATH" \
-i "$WAV_PATH" \
-f lavfi -i color=c=$PAGE_COLOR:s=244x720 \
-filter_complex \
"[0:v]scale=518:720,setpts=PTS-STARTPTS[img_pane]; \
[2:v]setpts=PTS-STARTPTS[txt_pane_bg]; \
[txt_pane_bg]subtitles=filename='${SRT_PATH}':force_style=\"FontName=${FONT_STYLE},PrimaryColour=${FONT_COLOR},FontSize=24,Alignment=5,MarginL=10,MarginV=10\"[txt_pane_with_subs]; \
[txt_pane_with_subs]drawtext=text='${PAGE_TITLE_TEXT}':font='${PAGE_TITLE_FONT_STYLE}':fontsize=${PAGE_TITLE_FONT_SIZE}:fontcolor=${PAGE_TITLE_FONT_COLOR_HEX}:x=(w-text_w)/2:y=${PAGE_TITLE_Y_POSITION}:enable='between(t,0,${PAGE_TITLE_DURATION})'[txt_pane_final]; \
[img_pane][txt_pane_final]hstack=inputs=2[output_v]" \
-map "[output_v]" \
-map 1:a \
-c:v libx264 -preset medium -crf 23 \
-c:a aac -b:a 192k \
-shortest \
"$OUTPUT_PATH"

echo "Video processing complete with overlay title. Output at: $OUTPUT_PATH"
