import unittest
from unittest.mock import patch, MagicMock
import sys # <--- ADD THIS
import os  # <--- ADD THIS

# --- ADD THESE LINES TO ADJUST SYS.PATH ---
# Get the directory of the current test file (e.g., .../tests/)
_current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (e.g., .../web_scraping/)
_project_root = os.path.abspath(os.path.join(_current_dir, '..'))
# Add the project root to the start of the Python path
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
# --- END OF SYS.PATH ADJUSTMENT ---

# Assuming your script is convert_audio_to_opus.py
from convert_audio_to_opus_2 import convert_wav_to_opus, normalize_audio

# Mock pydub's AudioSegment
class MockAudioSegment:
    def __init__(self, data=None, frame_rate=None, sample_width=None, channels=None):
        self.channels = channels if channels is not None else 1
        self.dBFS = -25.0 # Default mock value
        self.data = data

    @classmethod
    def from_wav(cls, file):
        # print(f"MockAudioSegment.from_wav called with {file}")
        return cls(channels=1) # Assume mono for simplicity in mock

    def set_channels(self, channels):
        # print(f"MockAudioSegment.set_channels called with {channels}")
        self.channels = channels
        return self # Return self for chaining

    def apply_gain(self, gain):
        # print(f"MockAudioSegment.apply_gain called with {gain}")
        # Simulate gain application, doesn't need to be accurate for mock
        self.dBFS += gain 
        return self

    def export(self, out_f, format, parameters=None, bitrate=None):
        # print(f"MockAudioSegment.export called: out_f={out_f}, format={format}, params={parameters}, bitrate={bitrate}")
        # You could simulate file creation if needed for more complex tests
        with open(out_f, 'wb') as f: # Create a dummy output file
            f.write(b"opus_data")
        pass

class TestAudioConverter(unittest.TestCase):

    # Test normalize_audio if it's a standalone part of your convert script
    @patch('convert_audio_to_opus.AudioSegment', MockAudioSegment)
    def test_normalize_audio_logic(self):
        # This tests the logic of your normalize_audio function, not pydub itself
        if hasattr(__import__('convert_audio_to_opus'), 'normalize_audio'):
            from convert_audio_to_opus import normalize_audio
            mock_sound = MockAudioSegment()
            mock_sound.dBFS = -30.0
            normalized_sound = normalize_audio(mock_sound, target_dbfs=-20.0)
            # apply_gain would have been called with +10dB
            # We'd need to check the gain applied, or that dBFS is now -20.0 if apply_gain sets it.
            # For this mock, let's assume apply_gain correctly modifies dBFS conceptually.
            # The mock apply_gain does self.dBFS += gain.
            # So, expected_dbfs_after_gain = -30.0 + ( -20.0 - (-30.0) ) = -30.0 + 10.0 = -20.0
            self.assertEqual(normalized_sound.dBFS, -20.0)

            mock_silent_sound = MockAudioSegment()
            mock_silent_sound.dBFS = float('-inf')
            normalized_silent = normalize_audio(mock_silent_sound, target_dbfs=-20.0)
            self.assertEqual(normalized_silent.dBFS, float('-inf')) # Should remain silent


    @patch('convert_audio_to_opus.AudioSegment', MockAudioSegment)
    @patch('convert_audio_to_opus.os.path.exists') # if used within function
    @patch('convert_audio_to_opus.os.remove') # if used
    def test_convert_wav_to_opus_calls(self, mock_os_remove, mock_os_exists):
        mock_os_exists.return_value = True # Assume input wav exists

        # Create dummy input and output paths for the test
        dummy_wav_path = "dummy_input.wav"
        dummy_opus_path = "dummy_output.opus"
        
        # Create a dummy wav file for AudioSegment.from_wav to "find"
        with open(dummy_wav_path, 'wb') as f:
            f.write(b"fake_wav_data")

        result = convert_wav_to_opus(dummy_wav_path, dummy_opus_path, bitrate="48k", apply_normalization=False)
        self.assertTrue(result)
        # Check if export was called with correct parameters (requires more advanced mock assertion)
        # For now, check if the dummy output file was created by the mock export
        self.assertTrue(os.path.exists(dummy_opus_path))

        # Test with normalization enabled
        result_norm = convert_wav_to_opus(dummy_wav_path, dummy_opus_path, bitrate="64k", apply_normalization=True, target_dbfs=-18.0)
        self.assertTrue(result_norm)

        # Clean up dummy files
        if os.path.exists(dummy_wav_path): os.remove(dummy_wav_path)
        if os.path.exists(dummy_opus_path): os.remove(dummy_opus_path)

    # Add tests for:
    # - Non-existent input WAV
    # - Handling of stereo to mono conversion if explicitly tested
    # - Deletion of original WAV if flag is True
