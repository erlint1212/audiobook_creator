# Audiobook pipeline

I wanted to make audiobooks of some novels I like to read, for use when I go hiking or excercising in general.

## Pipeline process

* Crawl all chapters of a web novel and put them into `.txt` files. Done by `gem_4.py`
* (Optional) Use Gemini API to transelate the text (done in `dragon_princess` folder)
* Use Alltalk V2 API running locally to send requests for TTS. `alltalk_tts_generator_chunky_4.py`
* Transform and clean (Normalize -20dB) the `.wav` files into less space intensive `.opus` files. `convert_audio_to_opus_2.py`
* Tag the files properly as audiobooks so that audio players can recognize it. Done by `tag_audiobook_files_opus.py`.

## TODO

* Actually make a fully automated pipeline. Just need to input the first chapter website.
* Write tests

## Install

Requires Alltalk V2 to work: [https://github.com/erew123/alltalk_tts/tree/alltalkbeta](https://github.com/erew123/alltalk_tts/tree/alltalkbeta)
1. Clone this folder
2. Install ffmpeg
3. `conda env create -f environment.yml`
