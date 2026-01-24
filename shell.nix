# shell.nix for Web Scraper & GUI Env on NixOS 25.05
let
  pkgs = import <nixpkgs> { config.allowUnfree = true; };
  ccLib = pkgs.stdenv.cc.cc;
  
  # Use Python Full which has Tkinter built directly into the base interpreter
  pythonEnv = pkgs.python311Full;
in pkgs.mkShell {
  packages = [
    pythonEnv
    pkgs.uv
    pkgs.gcc
    pkgs.ffmpeg         # Needed for ffmpeg-python / whisper
    pkgs.zlib           # Data compression
    pkgs.bzip2          # Data compression
    pkgs.xz             # Data compression
    pkgs.sqlite         # SQLite database
    pkgs.openssl        # SSL certificates for requests
    pkgs.libffi         # CFFI dependency
    pkgs.tcl            # Backend for Tkinter
    pkgs.tk             # Backend for Tkinter
    pkgs.cudaPackages.cudatoolkit # CUDA toolkit
    ccLib
  ];

  # PREVENT UV FROM DOWNLOADING ITS OWN NON-NIXOS PYTHON
  UV_PYTHON_DOWNLOADS = "never";

  shellHook = ''
    # Expose system libraries so Python packages can find them
    export LD_LIBRARY_PATH=${ccLib.lib}/lib:${pkgs.zlib}/lib:${pkgs.bzip2}/lib:${pkgs.xz}/lib:${pkgs.sqlite.out}/lib:${pkgs.openssl.out}/lib:${pkgs.libffi}/lib:${pkgs.tcl}/lib:${pkgs.tk}/lib:${pkgs.cudaPackages.cudatoolkit}/lib${":$LD_LIBRARY_PATH"}

    # Set up TCL/TK environment variables for Tkinter
    export TCL_LIBRARY="${pkgs.tcl}/lib/tcl8.6"
    export TK_LIBRARY="${pkgs.tk}/lib/tk8.6"

    if [ ! -d ".venv" ]; then
        echo "Creating Python 3.11 virtual environment (.venv) using Nix Python Full..."
        # FORCE uv to use the exact Python binary provided by Nix
        uv venv --python ${pythonEnv}/bin/python
        source .venv/bin/activate
        
        echo "1/2 Installing CUDA-enabled PyTorch 2.5..."
        uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

        echo "2/2 Installing web scraping requirements..."
        uv pip install -r requirements.txt
    else
        source .venv/bin/activate
    fi

    # Customize the terminal prompt
    export PS1="\n\[\033[1;32m\][web_scraper_env:\w]\$\[\033[0m\] "
    
    echo "Welcome to the Web Scraper Environment!"
    echo "Python version: $(python --version)"
  '';
}
