import os
import wave # Standard Python library for WAV files
import struct # For handling potential errors when reading WAV headers

def hollow_out_wav_files(directory):
    """
    Finds all files with the .wav extension in the specified directory,
    reads their audio parameters, and overwrites them with valid, empty
    (0 audio frames) WAV files using the original parameters.

    Args:
        directory (str): The path to the directory containing .wav files.
    """
    found_files = False
    processed_files = 0
    failed_files = []
    skipped_files = []

    # Standard default parameters in case original can't be read
    default_n_channels = 1
    default_samp_width = 2  # Bytes per sample (e.g., 2 for 16-bit audio)
    default_frame_rate = 44100

    if not os.path.isdir(directory):
        print(f"Error: Directory not found at '{directory}'")
        return

    print(f"Scanning directory: '{directory}' for .wav files...")

    for filename in os.listdir(directory):
        if filename.lower().endswith(".wav"):
            found_files = True
            filepath = os.path.join(directory, filename)

            if not os.path.isfile(filepath):
                print(f"Skipping '{filename}', as it is not a file.")
                skipped_files.append(f"{filename} (not a file)")
                continue

            n_channels = default_n_channels
            samp_width = default_samp_width
            frame_rate = default_frame_rate
            original_params_read = False

            try:
                # Attempt to read parameters from the original WAV file
                with wave.open(filepath, 'rb') as wf_orig:
                    n_channels = wf_orig.getnchannels()
                    samp_width = wf_orig.getsampwidth()
                    frame_rate = wf_orig.getframerate()
                    original_params_read = True
            except (wave.Error, EOFError, struct.error) as e:
                print(f"Warning: Could not read parameters from '{filename}' (possibly corrupt or not a standard WAV): {e}. Using default parameters to create an empty WAV.")
            except Exception as e:
                print(f"An unexpected error occurred while trying to read '{filename}': {e}. Using default parameters.")


            try:
                # Overwrite the file with an empty WAV using determined parameters
                with wave.open(filepath, 'wb') as wf_new:
                    wf_new.setnchannels(n_channels)
                    wf_new.setsampwidth(samp_width)
                    wf_new.setframerate(frame_rate)
                    wf_new.setnframes(0) # Critically, set 0 frames
                    # No need to writeframes('') as setnframes(0) handles it for an empty file.
                                        # The header will be written correctly upon close.

                if original_params_read:
                    print(f"Successfully hollowed out '{filename}' (preserving original parameters).")
                else:
                    print(f"Successfully hollowed out '{filename}' (using default parameters).")
                processed_files += 1
            except Exception as e:
                print(f"Error processing file '{filename}': {e}")
                failed_files.append(filename)

    if not found_files:
        print("No .wav files found in the specified directory.")
    else:
        print(f"\nProcessing complete.")
        print(f"Successfully hollowed out {processed_files} WAV file(s).")
        if skipped_files:
            print(f"Skipped {len(skipped_files)} item(s): {', '.join(skipped_files)}")
        if failed_files:
            print(f"Failed to process {len(failed_files)} file(s): {', '.join(failed_files)}")

if __name__ == "__main__":
    target_directory = "generated_audio_tileas_worries"
    hollow_out_wav_files(target_directory)
