# shell.nix: Unified Audio Pipeline (Fixed Fairseq Compilation)
let
  pkgs = import <nixpkgs> { config.allowUnfree = true; };
  ccLib = pkgs.stdenv.cc.cc;
  pythonEnv = pkgs.python310.withPackages (ps: [ ps.tkinter ]);
in pkgs.mkShell {
  packages = [
    pythonEnv
    pkgs.uv
    pkgs.gcc
    pkgs.git
    pkgs.ffmpeg
    pkgs.libsndfile
    pkgs.sox
    pkgs.zlib
    pkgs.tk
    pkgs.tcl
    pkgs.cudaPackages.cudatoolkit
    ccLib
  ];

  UV_PYTHON_DOWNLOADS = "never";

  shellHook = ''
    # 1. SETUP LIBRARY PATHS
    export LD_LIBRARY_PATH=/run/opengl-driver/lib:${ccLib.lib}/lib:${pkgs.libsndfile.out}/lib:${pkgs.zlib}/lib:${pkgs.cudaPackages.cudatoolkit}/lib:${pkgs.tk}/lib:${pkgs.tcl}/lib${":$LD_LIBRARY_PATH"}
    
    # 2. TKINTER VARS
    export TCL_LIBRARY="${pkgs.tcl}/lib/tcl8.6"
    export TK_LIBRARY="${pkgs.tk}/lib/tk8.6"

    if [ ! -d ".venv" ]; then
        echo "Creating Python 3.10 environment..."
        uv venv --python ${pythonEnv}/bin/python --system-site-packages
        source .venv/bin/activate
        
        echo "--- 1/6 Installing PyTorch (CUDA 12.4) ---"
        uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124

        echo "--- 2/6 Installing Flash Attention ---"
        uv pip install https://github.com/Dao-AILab/flash-attention/releases/download/v2.7.2.post1/flash_attn-2.7.2.post1+cu12torch2.5cxx11abiFALSE-cp310-cp310-linux_x86_64.whl

        echo "--- 3/6 Installing Qwen3-TTS ---"
        uv pip install qwen-tts soundfile pydub

        echo "--- 4/6 Installing RVC Prerequisites ---"
        # We MUST install numpy first so we can find its headers
        # We also need Cython and Ninja for compiling Fairseq
        uv pip install "numpy<2.0.0" cython setuptools ninja

        echo "--- 5/6 Compiling Fairseq & RVC ---"
        # Setup headers
        NP_INC=$(python -c 'import numpy; print(numpy.get_include())')
        export CFLAGS="-I$NP_INC"
        export CXXFLAGS="-I$NP_INC"
        export C_INCLUDE_PATH="$NP_INC:$C_INCLUDE_PATH"
        export CPLUS_INCLUDE_PATH="$NP_INC:$CPLUS_INCLUDE_PATH"
        
        # FIX: Install fairseq from GIT to ensure all C++ source files are present
        echo "   -> Installing fairseq from Git..."
        uv pip install git+https://github.com/facebookresearch/fairseq.git@main
        
        # Install rvc-python without deps so it doesn't overwrite our working fairseq
        echo "   -> Installing rvc-python..."
        uv pip install rvc-python --no-deps --no-build-isolation
        # Manually install other rvc-python dependencies that we skipped
        uv pip install "faiss-cpu" "praat-parselmouth" "pyworld" "scipy" "resampy" "torchcrepe" "ffmpeg-python" "av"

        if [ -f requirements.txt ]; then
            echo "--- 6/6 Installing GUI Requirements ---"
            uv pip install -r requirements.txt
        fi
    else
        source .venv/bin/activate
    fi

    export PS1="\n\[\033[1;35m\][AudioPipe_3.10:\w]\$\[\033[0m\] "
    echo "Environment Ready."
  '';
}
