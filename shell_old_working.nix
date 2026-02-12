# shell.nix for Web Scraper & GUI Env on NixOS
let
  pkgs = import <nixpkgs> { config.allowUnfree = true; };
  ccLib = pkgs.stdenv.cc.cc;
  
  # Create a Python environment that ALREADY has tkinter
  pythonEnv = pkgs.python311.withPackages (ps: [ ps.tkinter ]);
  
in pkgs.mkShell {
  packages = [
    pythonEnv
    pkgs.uv
    pkgs.gcc
    pkgs.ffmpeg
    pkgs.zlib
    pkgs.bzip2
    pkgs.xz
    pkgs.sqlite
    pkgs.openssl
    pkgs.libffi
    pkgs.tcl
    pkgs.tk
    pkgs.cudaPackages.cudatoolkit
    ccLib
  ];

  # PREVENT UV FROM DOWNLOADING ITS OWN NON-NIXOS PYTHON
  UV_PYTHON_DOWNLOADS = "never";

  shellHook = ''
    # 1. LINK SYSTEM LIBRARIES (Crucial for _tkinter.so to find libtk/libtcl)
    export LD_LIBRARY_PATH=${ccLib.lib}/lib:${pkgs.zlib}/lib:${pkgs.bzip2}/lib:${pkgs.xz}/lib:${pkgs.sqlite.out}/lib:${pkgs.openssl.out}/lib:${pkgs.libffi}/lib:${pkgs.tcl}/lib:${pkgs.tk}/lib:${pkgs.cudaPackages.cudatoolkit}/lib${":$LD_LIBRARY_PATH"}

    # 2. SET TK/TCL ENVIRONMENT VARIABLES
    export TCL_LIBRARY="${pkgs.tcl}/lib/tcl8.6"
    export TK_LIBRARY="${pkgs.tk}/lib/tk8.6"

    # 3. SETUP VIRTUAL ENV
    if [ ! -d ".venv" ]; then
        echo "Creating Python virtual environment..."
        # CRITICAL FIX: --system-site-packages lets the venv see the Nix-installed 'tkinter'
        uv venv --python ${pythonEnv}/bin/python --system-site-packages
        
        source .venv/bin/activate
        
        echo "Installing PyTorch..."
        uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
        
        if [ -f requirements.txt ]; then
            echo "Installing requirements..."
            uv pip install -r requirements.txt
        fi
    else
        source .venv/bin/activate
    fi

    export PS1="\n\[\033[1;32m\][web_scraper_env:\w]\$\[\033[0m\] "
    echo "Environment Ready. Python: $(python --version)"
  '';
}
