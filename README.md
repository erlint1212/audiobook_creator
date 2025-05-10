# Audiobook pipeline

I wanted to make audiobooks of some novels I like to read, for use when I go hiking or exercising in general.

## Pipeline process

* Crawl all chapters of a web novel and put them into `.txt` files. Done by `gem_4.py`
* (Optional) Use Gemini API to translate the text (done in `dragon_princess` folder)
* Use Alltalk V2 API running locally to send requests for TTS. `alltalk_tts_generator_chunky_4.py`
* Transform and clean (Normalize -20dB) the `.wav` files into less space intensive `.opus` files. `convert_audio_to_opus_2.py`
* Create `.srt` subtitle files using `opeai-whisper`. Using `generate_wav_to_opusfolder_srt.py`.
* Verifying the `.srt` files against the true text. Using `correct_srt_text.py`. **Currently very bad, don't use**
* Tag the files properly as audiobooks so that audio players can recognize it. Done by `tag_audiobook_files_opus.py`.

**OPS:** `generate_wav_to_opusfolder_srt.py` runs on multiprocessing with whispers `medium.en` model, this will require around 10GB VRAM, I have 12GB so it's fine for me but it might break if you have less, reduce the number of workers or choose a smaller model according to your VRAM.

**OPS 2:** multi threading `whisper` was very very slow, it might just be me using a laptop GPU therefore not fully utilizing it (46W/153W).

## TODO

* Actually make a fully automated pipeline. Just need to input the first chapter website.
* Write unit tests that work
* Make the `.srt` correction work properly

## Install

Requires Alltalk V2 to work: [https://github.com/erew123/alltalk_tts/tree/alltalkbeta](https://github.com/erew123/alltalk_tts/tree/alltalkbeta)

For Gemini API calls to work:
`export GEMINI_API_KEY=your_api_key`

1. Clone this folder
2. Install ffmpeg
3. `conda env create -f environment.yml`
