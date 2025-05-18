#Requires -Version 5.0

# --- Configuration ---
$IMAGE_PATH = "Portrait_half-light.png"
$SRT_PATH = "generated_audio_IATMCB_opus/ch_001.srt"
$WAV_PATH = "generated_audio_IATMCB/ch_001.wav"
$OUTPUT_PATH = "videos/ch_001.mp4"

$FONT_NAME_FOR_SUBTITLES = "Libre Baskerville" # Used in force_style
$PAGE_COLOR = "0x1E1E1E"
$FONT_COLOR_FOR_SUBTITLES = "&H00E0E0E0&" # ASS format for subtitles

# --- Page Title Overlay Configuration ---
$PAGE_TITLE_TEXT = "Chapter 0 - Gaming, A Fundamental Skill for Factory Workers"
$PAGE_TITLE_DURATION = 7

# IMPORTANT: Specify the FULL PATH to your .ttf or .otf font file here
# Adjust this path to where your Libre Baskerville font file actually is.
# Common locations are C:\Windows\Fonts or a local project folder.
# Using forward slashes in the path is generally safer for FFmpeg.
$PAGE_TITLE_FONT_FILE = "C:/Windows/Fonts/LibreBaskerville-Regular.ttf"
# If LibreBaskerville-Regular.ttf is not the exact filename, change it.
# (e.g., it might be Libre_Baskerville/LibreBaskerville-Regular.ttf if you downloaded from Google Fonts and extracted)
# You can also try just "LibreBaskerville-Regular.ttf" if the font is in the same directory as ffmpeg.exe or a system font directory.

$PAGE_TITLE_FONT_SIZE = 30
$PAGE_TITLE_FONT_COLOR_HEX = "E0E0E0"
$PAGE_TITLE_Y_POSITION = 25

# --- Prepare Page Title Text by escaping special characters for FFmpeg drawtext ---
$EscapedPageTitleText = $PAGE_TITLE_TEXT
$EscapedPageTitleText = $EscapedPageTitleText -replace '\\', '\\\\'
$EscapedPageTitleText = $EscapedPageTitleText -replace "'", "\'"
$EscapedPageTitleText = $EscapedPageTitleText -replace ":", "\:"
$EscapedPageTitleText = $EscapedPageTitleText -replace "%", "\%"

# --- Ensure the output directory exists ---
$OutputDirectory = Split-Path -Path $OUTPUT_PATH -Parent
if (-not (Test-Path -Path $OutputDirectory)) {
    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    Write-Host "Created output directory: $OutputDirectory"
}

# --- Construct the FFmpeg filter_complex argument ---
$FilterComplex = "[0:v]scale=518:720,setpts=PTS-STARTPTS[img_pane];" `
                + "[2:v]setpts=PTS-STARTPTS[txt_pane_bg];" `
                + "[txt_pane_bg]subtitles=filename='$(<span class="math-inline">SRT\_PATH\)'\:force\_style\='FontName\=</span>(<span class="math-inline">FONT\_NAME\_FOR\_SUBTITLES\),PrimaryColour\=</span>($FONT_COLOR_FOR_SUBTITLES),FontSize=24,Alignment=5,MarginL=10,MarginV=10'[txt_pane_with_subs];" `
                + "[txt_pane_with_subs]drawtext=text='$($EscapedPageTitleText)':fontfile='$($PAGE_TITLE_FONT_FILE)':fontsize=$($PAGE_TITLE_FONT_SIZE):fontcolor=$($PAGE_TITLE_FONT_COLOR_HEX):x=(w-text_w)/2:y=$($PAGE_TITLE_Y_POSITION):enable='between(t,0,$($PAGE_TITLE_DURATION))'[txt_pane_final];" `
                + "[img_pane][txt_pane_final]hstack=inputs=2[output_v]"

Write-Host "Starting FFmpeg process..."
Write-Host "Using Filter Complex: <span class="math-inline">FilterComplex" \# For debugging
\# \-\-\- Execute FFmpeg \-\-\-
try \{
& ffmpeg \-y \-loop 1 \-i "</span>($IMAGE_PATH)" `
        -i "$($WAV_PATH)" `
        -f lavfi -i "color=c=$($PAGE_COLOR):s=244x720" `
        -filter_complex $FilterComplex `
        -map "[output_v]" `
        -map "1:a" `
        -c:v libx264 -preset medium -crf 23 `
        -c:a aac -b:a 192k `
        -shortest `
        "$($OUTPUT_PATH)"

    if ($LASTEXITCODE -eq 0) {
        Write-Host "Video processing complete. Output at: $($OUTPUT_PATH)" -ForegroundColor Green
    } else {
        Write-Error "FFmpeg process likely failed. Exit code: $LASTEXITCODE. Review FFmpeg output above."
    }
}
catch {
    Write-Error "An error occurred while trying to run FFmpeg: $($_.Exception.Message)"
}
