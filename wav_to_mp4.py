import os
import glob
import subprocess
import shutil
import platform

# --- Configuration ---
AUDIO_INPUT_DIR = "wav_chapters"  # Directory containing your input .wav files
COVER_IMAGE_PATH = "TAoW.png"    # Path to your cover image (e.g., "cover.jpg" or "album_art.png")
OUTPUT_VIDEO_FILENAME = "The_Art_Of_War_Audiobook.mp4" # Desired output video file name

# Temporary file for concatenated audio (if multiple input WAVs)
TEMP_CONCAT_AUDIO_FILENAME = "_temp_concatenated_audio.wav"

# FFmpeg video settings for YouTube (1080p)
VIDEO_RESOLUTION = "1280x720" # e.g., "1920x1080" for 1080p, "1280x720" for 720p
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "medium" # Slower presets = better quality/smaller size, but longer encoding. Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
VIDEO_CRF = "28" # Constant Rate Factor (quality). 18 (better) to 28 (smaller). 23 is a good default.
AUDIO_CODEC_OUT = "aac"
AUDIO_BITRATE_OUT = "192k" # Audio bitrate for the output video
PIXEL_FORMAT = "yuv420p" # Common pixel format for compatibility
FRAMERATEM_STATIC_IMAGE = "1" # Low framerate for static image video. Can be 1 or 2.
# --- End Configuration ---

def check_ffmpeg_installed():
    """Checks if ffmpeg is installed and accessible."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, shell=(platform.system() == 'Windows'))
        print("FFmpeg found.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: ffmpeg not found. Please install ffmpeg and ensure it's in your system's PATH.")
        print("Download from: https://ffmpeg.org/download.html")
        return False

def concatenate_wav_files(wav_files_list, output_concat_path):
    """
    Concatenates a list of WAV files into a single WAV file using ffmpeg.
    Returns True on success, False on failure.
    """
    if not wav_files_list:
        print("No WAV files provided for concatenation.")
        return False
    if len(wav_files_list) == 1:
        print("Only one WAV file found, no concatenation needed. Using original file.")
        # Copy the single file to the expected output_concat_path for consistent workflow
        try:
            shutil.copyfile(wav_files_list[0], output_concat_path)
            return True
        except Exception as e:
            print(f"Error copying single WAV file: {e}")
            return False

    print(f"Concatenating {len(wav_files_list)} WAV files into '{output_concat_path}'...")
    
    # Create a temporary file list for ffmpeg's concat demuxer
    list_file_path = "_temp_ffmpeg_filelist.txt"
    with open(list_file_path, 'w', encoding='utf-8') as f:
        for wav_file in wav_files_list:
            # FFmpeg's concat demuxer requires paths to be escaped or very clean.
            # For simplicity, we're writing them directly. Ensure no problematic characters.
            # Using absolute paths can be safer.
            abs_wav_file = os.path.abspath(wav_file)
            # On Windows, ffmpeg's concat demuxer can be tricky with backslashes in file list.
            # It's often safer to use forward slashes or escape backslashes.
            # Or, ensure paths are quoted if they contain spaces.
            # For file list, simple 'file path' syntax.
            # Let's try with paths as they are, then adjust if needed.
            # Ensure no single quotes are in the filename itself.
            # A common way to handle paths in the list file:
            f.write(f"file '{abs_wav_file.replace(os.sep, '/')}'\n")


    ffmpeg_concat_command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0", # Allows unsafe file paths (use with caution, ensure paths are correct)
        "-i", list_file_path,
        "-c", "copy", # Copy codec since inputs are WAV, output is WAV
        output_concat_path,
        "-y" # Overwrite output file if it exists
    ]

    try:
        print(f"Running ffmpeg concat command: {' '.join(ffmpeg_concat_command)}")
        process = subprocess.run(ffmpeg_concat_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, shell=(platform.system() == 'Windows'))
        print("Concatenation successful.")
        return True
    except subprocess.CalledProcessError as e:
        print("Error during ffmpeg concatenation:")
        print("Stdout:", e.stdout.decode(errors='ignore'))
        print("Stderr:", e.stderr.decode(errors='ignore'))
        return False
    except FileNotFoundError:
        # This outer try-except for FileNotFoundError is for ffmpeg itself
        print("Error: ffmpeg command not found during concatenation. Is it installed and in PATH?")
        return False
    finally:
        if os.path.exists(list_file_path):
            os.remove(list_file_path)

def create_video_from_audio_and_image(audio_path, image_path, video_output_path):
    """
    Creates a video from a static image and an audio file using ffmpeg.
    """
    if not os.path.exists(audio_path):
        print(f"Error: Audio input file not found: {audio_path}")
        return False
    if not os.path.exists(image_path):
        print(f"Error: Cover image file not found: {image_path}")
        return False

    print(f"Creating video '{video_output_path}' from image '{image_path}' and audio '{audio_path}'...")

    # Scale and pad filter to fit image into video_resolution (e.g., 1920x1080)
    # while maintaining aspect ratio and padding with black.
    vf_filter = (
        f"scale={VIDEO_RESOLUTION}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_RESOLUTION}:(ow-iw)/2:(oh-ih)/2,"
        f"format={PIXEL_FORMAT}"
    )
    
    ffmpeg_video_command = [
        "ffmpeg",
        "-loop", "1",                      # Loop the image
        "-framerate", FRAMERATEM_STATIC_IMAGE, # Low framerate for static image
        "-i", image_path,                  # Input image
        "-i", audio_path,                  # Input audio
        "-c:v", VIDEO_CODEC,               # Video codec (e.g., libx264)
        "-preset", VIDEO_PRESET,           # Encoding preset
        "-tune", "stillimage",             # Optimize for static image
        "-crf", VIDEO_CRF,                 # Constant Rate Factor (quality)
        "-c:a", AUDIO_CODEC_OUT,           # Audio codec (e.g., aac)
        "-b:a", AUDIO_BITRATE_OUT,         # Audio bitrate
        "-pix_fmt", PIXEL_FORMAT,          # Pixel format for compatibility
        "-vf", vf_filter,                  # Video filter for scaling and padding
        "-shortest",                       # Finish encoding when the shortest input stream ends (the audio)
        video_output_path,
        "-y" # Overwrite output file if it exists
    ]

    try:
        print(f"Running ffmpeg video creation command: {' '.join(ffmpeg_video_command)}")
        process = subprocess.run(ffmpeg_video_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, shell=(platform.system() == 'Windows'))
        print("Video creation successful!")
        return True
    except subprocess.CalledProcessError as e:
        print("Error during ffmpeg video creation:")
        print("Stdout:", e.stdout.decode(errors='ignore'))
        print("Stderr:", e.stderr.decode(errors='ignore'))
        return False
    except FileNotFoundError:
        print("Error: ffmpeg command not found during video creation. Is it installed and in PATH?")
        return False

if __name__ == "__main__":
    print("--- Starting Video Generation Script ---")

    if not check_ffmpeg_installed():
        exit(1)

    if not os.path.isdir(AUDIO_INPUT_DIR):
        print(f"Error: Audio input directory '{AUDIO_INPUT_DIR}' not found.")
        exit(1)
    
    if not os.path.exists(COVER_IMAGE_PATH):
        print(f"Error: Cover image file '{COVER_IMAGE_PATH}' not found.")
        exit(1)

    # Find and sort WAV files
    wav_files = sorted(glob.glob(os.path.join(AUDIO_INPUT_DIR, "*.wav")))

    if not wav_files:
        print(f"No .wav files found in '{AUDIO_INPUT_DIR}'.")
        exit(1)

    print(f"Found {len(wav_files)} .wav file(s) in '{AUDIO_INPUT_DIR}'.")

    # Define path for the (potentially temporary) concatenated audio
    # Place it in the current directory or a specific temp location
    current_working_dir = os.getcwd()
    final_audio_for_video = os.path.join(current_working_dir, TEMP_CONCAT_AUDIO_FILENAME)
    
    audio_ready = False
    if len(wav_files) == 1:
        print("Single audio file found. Using it directly for the video.")
        # For a single file, we can use its original path directly if shutil.copy is not preferred,
        # but for workflow consistency, we'll "prepare" it like the concat output.
        try:
            shutil.copyfile(wav_files[0], final_audio_for_video)
            print(f"Copied '{wav_files[0]}' to '{final_audio_for_video}' for processing.")
            audio_ready = True
        except Exception as e:
            print(f"Error preparing single audio file: {e}")
            audio_ready = False
            
    else: # Multiple WAV files, need to concatenate
        if concatenate_wav_files(wav_files, final_audio_for_video):
            audio_ready = True
        else:
            print("Failed to concatenate audio files.")
            audio_ready = False

    if audio_ready:
        if create_video_from_audio_and_image(final_audio_for_video, COVER_IMAGE_PATH, OUTPUT_VIDEO_FILENAME):
            print(f"\nVideo successfully generated: {OUTPUT_VIDEO_FILENAME}")
        else:
            print("\nVideo generation failed.")
    else:
        print("\nAudio preparation failed, cannot proceed with video generation.")

    # Clean up temporary concatenated audio file
    if os.path.exists(final_audio_for_video) and len(wav_files) > 1 : # Only remove if it was a temp concat file
         # Or always remove if TEMP_CONCAT_AUDIO_FILENAME was created by copy
        try:
            print(f"Cleaning up temporary audio file: {final_audio_for_video}")
            os.remove(final_audio_for_video)
        except Exception as e:
            print(f"Warning: Could not remove temporary audio file {final_audio_for_video}: {e}")
    elif os.path.exists(final_audio_for_video) and len(wav_files) == 1:
        # If it was a single file copied, we can also remove this temp copy.
        try:
            print(f"Cleaning up temporary copy of single audio file: {final_audio_for_video}")
            os.remove(final_audio_for_video)
        except Exception as e:
            print(f"Warning: Could not remove temporary audio file {final_audio_for_video}: {e}")


    print("--- Video Generation Script Finished ---")
