import requests
import time
import json
from pprint import pprint

class AllTalkAPI:
    """
    A class to interact with the AllTalk API.
    This class provides methods to initialize the connection, fetch server information,
    and perform various operations like generating TTS, switching models, etc.
    """

    def __init__(self, config_file='config.json'):
        """
        Initialize the AllTalkAPI class.
        Loads configuration from a file or uses default values.
        Sets up the base URL for API requests and initializes variables for storing server data.
        """
        # Default configuration
        default_config = {
            "api_alltalk_protocol": "http://",
            "api_alltalk_ip_port": "127.0.0.1:7851",
            "api_connection_timeout": 5
        }
        
        # Try to load configuration from JSON file, use defaults if file not found
        try:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"Config file '{config_file}' not found. Using default configuration.")
            self.config = default_config
        
        # Construct the base URL for API requests
        self.base_url = f"{self.config['api_alltalk_protocol']}{self.config['api_alltalk_ip_port']}"
        
        # Initialize variables to store API data
        self.current_settings = None
        self.available_voices = None
        self.available_rvc_voices = None

    def check_server_ready(self):
        """
        Check if the AllTalk server is ready to accept requests.
        Attempts to connect to the server within the specified timeout period.
        Returns True if the server is ready, False otherwise.
        """
        timeout = time.time() + self.config['api_connection_timeout']
        while time.time() < timeout:
            try:
                response = requests.get(f"{self.base_url}/api/ready", timeout=1)
                if response.text == "Ready":
                    return True
            except requests.RequestException:
                pass
            time.sleep(0.5)
        return False

    def initialize(self):
        """
        Perform initial setup by fetching current settings and available voices.
        This method should be called after creating an instance of AllTalkAPI.
        Returns True if initialization is successful, False otherwise.
        """
        if not self.check_server_ready():
            print("Server is offline or not responding.")
            return False

        self.current_settings = self.get_current_settings()
        self.available_voices = self.get_available_voices()
        self.available_rvc_voices = self.get_available_rvc_voices()
        return True

    def get_current_settings(self):
        """
        Fetch current settings from the AllTalk server.
        Returns a dictionary of server settings or None if the request fails.
        """
        try:
            response = requests.get(f"{self.base_url}/api/currentsettings")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Error fetching current settings: {e}")
            return None

    def get_available_voices(self):
        """
        Fetch available voices from the AllTalk server.
        Returns a list of available voices or None if the request fails.
        """
        try:
            response = requests.get(f"{self.base_url}/api/voices")
            response.raise_for_status()
            data = response.json()
            return data.get('voices', [])
        except requests.RequestException as e:
            print(f"Error fetching available voices: {e}")
            return None

    def get_available_rvc_voices(self):
        """
        Fetch available RVC voices from the AllTalk server.
        RVC (Retrieval-based Voice Conversion) voices are used for voice cloning.
        Returns a list of available RVC voices or None if the request fails.
        """
        try:
            response = requests.get(f"{self.base_url}/api/rvcvoices")
            response.raise_for_status()
            data = response.json()
            return data.get('rvcvoices', [])
        except requests.RequestException as e:
            print(f"Error fetching available RVC voices: {e}")
            return None

    def reload_config(self):
        """
        Reload the AllTalk server configuration.
        This method triggers a config reload on the server and then re-initializes the local data.
        Returns True if the reload is successful, False otherwise.
        """
        response = requests.get(f"{self.base_url}/api/reload_config")
        if response.status_code == 200:
            # Re-fetch settings and voices after reloading config
            self.initialize()
            return True
        return False

    def generate_tts(self, text, character_voice, narrator_voice=None, **kwargs):
        """
        Generate text-to-speech audio using the AllTalk server.
        
        Args:
            text (str): The text to convert to speech.
            character_voice (str): The voice to use for the character.
            narrator_voice (str, optional): The voice to use for the narrator, if applicable.
            **kwargs: Additional parameters for TTS generation (e.g., language, output_file_name).
        
        Returns:
            dict: A dictionary containing information about the generated audio, or None if generation fails.
        """
        data = {
            "text_input": text,
            "character_voice_gen": character_voice,
            "narrator_enabled": "true" if narrator_voice else "false",
            "narrator_voice_gen": narrator_voice,
            **kwargs
        }
        response = requests.post(f"{self.base_url}/api/tts-generate", data=data)
        return response.json() if response.status_code == 200 else None

    def stop_generation(self):
        """
        Stop the current TTS generation process.
        Returns the server's response as a dictionary, or None if the request fails.
        """
        response = requests.put(f"{self.base_url}/api/stop-generation")
        return response.json() if response.status_code == 200 else None

    def switch_model(self, model_name):
        """
        Switch to a different TTS model.
        
        Args:
            model_name (str): The name of the model to switch to.
        
        Returns:
            dict: The server's response as a dictionary if successful, None if the request fails.
        """
        try:
            response = requests.post(f"{self.base_url}/api/reload", params={"tts_method": model_name})
            response.raise_for_status()  # This will raise an exception for HTTP errors
            return response.json()
        except requests.RequestException as e:
            print(f"Error switching model: {e}")
            if response.status_code == 404:
                print(f"Model '{model_name}' not found on the server.")
            elif response.status_code == 500:
                print("Server encountered an error while switching models.")
            else:
                print(f"Unexpected error occurred. Status code: {response.status_code}")
            return None

    def set_deepspeed(self, enabled):
        """
        Enable or disable DeepSpeed mode.
        DeepSpeed is an optimization library for large-scale models.
        
        Args:
            enabled (bool): True to enable DeepSpeed, False to disable.
        
        Returns:
            dict: The server's response as a dictionary, or None if the request fails.
        """
        response = requests.post(f"{self.base_url}/api/deepspeed", params={"new_deepspeed_value": str(enabled).lower()})
        return response.json() if response.status_code == 200 else None

    def set_low_vram(self, enabled):
        """
        Enable or disable Low VRAM mode.
        Low VRAM mode optimizes memory usage for systems with limited GPU memory.
        
        Args:
            enabled (bool): True to enable Low VRAM mode, False to disable.
        
        Returns:
            dict: The server's response as a dictionary, or None if the request fails.
        """
        response = requests.post(f"{self.base_url}/api/lowvramsetting", params={"new_low_vram_value": str(enabled).lower()})
        return response.json() if response.status_code == 200 else None

    def display_server_info(self):
        """
        Display all information pulled from the AllTalk server.
        This includes current settings, available voices, RVC voices, and server capabilities.
        """
        print("=== AllTalk Server Information ===")
        
        print(f"\nServer URL: {self.base_url}")
        
        print("\n--- Current Settings ---")
        pprint(self.current_settings)
        
        print("\n--- Available Voices ---")
        pprint(self.available_voices)
        
        print("\n--- Available RVC Voices ---")
        pprint(self.available_rvc_voices)
        
        print("\n--- Server Capabilities ---")
        if self.current_settings:
            capabilities = {
                "DeepSpeed Capable": self.current_settings.get('deepspeed_capable', False),
                "DeepSpeed Enabled": self.current_settings.get('deepspeed_enabled', False),
                "Low VRAM Capable": self.current_settings.get('lowvram_capable', False),
                "Low VRAM Enabled": self.current_settings.get('lowvram_enabled', False),
                "Generation Speed Capable": self.current_settings.get('generationspeed_capable', False),
                "Current Generation Speed": self.current_settings.get('generationspeed_set', 'N/A'),
                "Pitch Capable": self.current_settings.get('pitch_capable', False),
                "Current Pitch": self.current_settings.get('pitch_set', 'N/A'),
                "Temperature Capable": self.current_settings.get('temperature_capable', False),
                "Current Temperature": self.current_settings.get('temperature_set', 'N/A'),
                "Streaming Capable": self.current_settings.get('streaming_capable', False),
                "Multi-voice Capable": self.current_settings.get('multivoice_capable', False),
                "Multi-model Capable": self.current_settings.get('multimodel_capable', False),
                "Languages Capable": self.current_settings.get('languages_capable', False)
            }
            pprint(capabilities)
        else:
            print("Server settings not available. Make sure the server is running and accessible.")

# Example usage
if __name__ == "__main__":
    # Create an instance of the AllTalkAPI
    api = AllTalkAPI()
    
    # Initialize the API and fetch server information
    if api.initialize():
        print("AllTalk API initialized successfully.")
        
        # Display all server information
        api.display_server_info()
        
        # Generate TTS
        result = api.generate_tts(
            "Hello, this is a test.",
            character_voice="female_01.wav",
            language="en",
            output_file_name="test_output"
        )
        if result:
            print(f"\nTTS generated: {result['output_file_url']}")
        else:
            print("Failed to generate TTS.")
        
        # Switch to a different TTS model
        print("\nAttempting to switch TTS model...")
        available_models = api.current_settings.get('models_available', [])
        if available_models:
            target_model = available_models[0]['name']  # Choose the first available model
            if api.switch_model(target_model):
                print(f"Model switched successfully to {target_model}.")
            else:
                print(f"Failed to switch to model {target_model}.")
        else:
            print("No available models found. Cannot switch model.")
        
        # Enable DeepSpeed for optimized performance
        if api.set_deepspeed(True):
            print("DeepSpeed enabled.")
        else:
            print("Failed to enable DeepSpeed.")
        
        # Reload config and display updated information
        if api.reload_config():
            print("\nConfiguration reloaded. Updated server information:")
            api.display_server_info()
        else:
            print("Failed to reload configuration.")
    else:
        print("Failed to initialize AllTalk API.")
