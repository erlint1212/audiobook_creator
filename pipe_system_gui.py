import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

# --- OPTIONAL: Pillow for Image Previews ---
try:
    from PIL import Image, ImageTk
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Warning: Pillow not installed. Image previews will be disabled. (pip install Pillow)")

# --- CONFIGURATION ---
NOVELS_ROOT_DIR = "Novels"
CONFIG_FILE = "alltalk_path_config.json"
MAX_LOG_LINES = 5000

try:
    from constants import GEMINI_MODEL_NAME
except ImportError:
    GEMINI_MODEL_NAME = "gemini-3-flash-preview"

SCRIPTS = {
    "Scraper": "scraper_2.py",
    "Metadata": "metadata_fetcher.py",
    "Translate (Gemini)": "gemini_transelate_4.py",
    "Translate (Grok)": "grok_transelate.py",
    "TTS Generator": "alltalk_tts_generator_chunky_17.py",
    "Audio Converter": "convert_audio_to_opus_3.py",
    "Tag Audio": "tag_audiobook_files_opus_3.py",
    "EPUB Creator": "txt_to_epub.py",
}

class PipelineGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audiobook Pipe System")
        self.root.geometry("950x950")

        # --- THEME SETUP ---
        self.style = ttk.Style()
        self.setup_dark_theme()
        self.root.configure(bg="#2e2e2e")

        # --- ICON SETUP ---
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
            if os.path.exists(icon_path):
                icon_img = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon_img)
        except Exception:
            pass

        if not os.path.exists(NOVELS_ROOT_DIR):
            os.makedirs(NOVELS_ROOT_DIR)

        # Variables
        self.current_project = tk.StringVar()
        self.index_url = tk.StringVar()
        self.input_source_var = tk.StringVar(value="Raw")
        self.tts_engine_var = tk.StringVar(value="AllTalk")

        # AllTalk Config Vars
        self.alltalk_path_var = tk.StringVar()
        self.selected_voice_var = tk.StringVar()
        self.selected_rvc_var = tk.StringVar()
        self.alltalk_pitch_var = tk.IntVar(value=0)

        # Qwen+RVC Config Vars
        self.qwen_pth_var = tk.StringVar()
        self.qwen_index_var = tk.StringVar()
        self.qwen_pitch_var = tk.IntVar(value=-2)

        # Metadata Tab Vars
        self.meta_title = tk.StringVar()
        self.meta_author = tk.StringVar()
        self.meta_year = tk.StringVar(value="2025")
        self.meta_genre = tk.StringVar(value="Audiobook")
        self.meta_composer = tk.StringVar(value="AI TTS")
        self.cover_image_ref = None # Keep reference to prevent GC

        self.pipeline_vars = {
            "scraper": tk.BooleanVar(value=True),
            "translate": tk.BooleanVar(value=False),
            "epub": tk.BooleanVar(value=True),
            "tts": tk.BooleanVar(value=True),
            "convert": tk.BooleanVar(value=True),
            "tag": tk.BooleanVar(value=True),
        }
        self.trans_engine = tk.StringVar(value="Translate (Gemini)")

        self.adapt_url_var = tk.StringVar()
        self.adapt_type_var = tk.StringVar(value="Chapter Scraper")

        self.current_process = None
        self.stop_requested = False

        self.load_config()
        self.create_ui()
        self.refresh_project_list()

        if self.alltalk_path_var.get():
            self.scan_alltalk_content()

    def setup_dark_theme(self):
        """Applies a custom dark theme to ttk widgets."""
        self.style.theme_use('clam') # 'clam' supports custom colors better than 'vista'
        
        bg_color = "#2e2e2e"
        fg_color = "#ffffff"
        darker_bg = "#252525"
        entry_bg = "#404040"
        accent_color = "#4f46e5" 
        active_color = "#4338ca"
        hover_bg = "#505050" # A lighter gray for hover, instead of system white

        # General
        self.style.configure(".", background=bg_color, foreground=fg_color, borderwidth=0)
        
        # Frames & Labels
        self.style.configure("TFrame", background=bg_color)
        self.style.configure("TLabelframe", background=bg_color, foreground=fg_color, borderwidth=1, relief="solid")
        self.style.configure("TLabelframe.Label", background=bg_color, foreground=accent_color, font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabel", background=bg_color, foreground=fg_color)
        
        # Buttons
        self.style.configure("TButton", 
                             background="#3f3f3f", 
                             foreground=fg_color, 
                             borderwidth=0, 
                             padding=6)
        self.style.map("TButton", 
                       background=[("active", accent_color), ("pressed", active_color)],
                       foreground=[("disabled", "#888888")])

        # Accent Button Style
        self.style.configure("Accent.TButton", background=accent_color, font=("Segoe UI", 9, "bold"))
        self.style.map("Accent.TButton", background=[("active", "#6366f1")])

        # Inputs (Entry)
        self.style.configure("TEntry", fieldbackground=entry_bg, foreground=fg_color, insertcolor="white", borderwidth=1)
        
        # --- FIXED COMBOBOX STYLING ---
        self.style.configure("TCombobox", 
                             fieldbackground=entry_bg, 
                             background=entry_bg, 
                             foreground=fg_color, 
                             arrowcolor="white",
                             borderwidth=1)
        
        # This map ensures the background stays dark even when hovering or active
        self.style.map("TCombobox", 
                       fieldbackground=[("readonly", entry_bg), ("active", entry_bg)],
                       background=[("active", hover_bg), ("pressed", accent_color)],
                       foreground=[("readonly", fg_color), ("active", fg_color)],
                       selectbackground=[("readonly", entry_bg)], # Prevents blue highlight on text selection
                       selectforeground=[("readonly", fg_color)])
        # ------------------------------

        self.style.configure("TSpinbox", fieldbackground=entry_bg, foreground=fg_color, arrowcolor="white")

        # Tabs
        self.style.configure("TNotebook", background=bg_color, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=darker_bg, foreground=fg_color, padding=[15, 8], font=("Segoe UI", 9))
        self.style.map("TNotebook.Tab", background=[("selected", bg_color), ("active", "#3a3a3a")], foreground=[("selected", accent_color)])

    def create_ui(self):
        # --- TOP BAR ---
        top_frame = ttk.LabelFrame(self.root, text="Project Management")
        top_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(top_frame, text="Project:").pack(side="left", padx=5)
        self.project_dropdown = ttk.Combobox(
            top_frame, textvariable=self.current_project, state="readonly", width=25
        )
        self.project_dropdown.pack(side="left", padx=5)
        self.project_dropdown.bind("<<ComboboxSelected>>", self.on_project_change)

        ttk.Button(top_frame, text="New", command=self.create_new_project, width=6).pack(side="left", padx=2)
        ttk.Button(top_frame, text="Folder", command=self.open_project_folder, width=6).pack(side="left", padx=2)

        ttk.Label(top_frame, text=" | Index URL:").pack(side="left", padx=5)
        ttk.Entry(top_frame, textvariable=self.index_url, width=30).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(top_frame, text="Get Meta", command=self.run_metadata_fetch).pack(side="left", padx=2)

        # --- TABS ---
        tabs = ttk.Notebook(self.root)
        self.tab_run = ttk.Frame(tabs)
        self.tab_meta = ttk.Frame(tabs) # NEW TAB
        self.tab_adapt = ttk.Frame(tabs)
        
        tabs.add(self.tab_run, text="  Run Pipeline  ")
        tabs.add(self.tab_meta, text="  Metadata & Cover  ")
        tabs.add(self.tab_adapt, text="  AI Adapter  ")
        tabs.pack(expand=True, fill="both", padx=10, pady=5)

        # ==========================
        # === TAB 1: RUN PIPELINE ===
        # ==========================
        
        # 1. TTS Setup
        tts_frame = ttk.LabelFrame(self.tab_run, text="TTS Generation Setup")
        tts_frame.pack(fill="x", padx=10, pady=5)

        eng_sel_frame = ttk.Frame(tts_frame)
        eng_sel_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(eng_sel_frame, text="Select Engine:").pack(side="left", padx=5)
        ttk.Radiobutton(eng_sel_frame, text="AllTalk (External API)", variable=self.tts_engine_var, value="AllTalk", command=self.toggle_tts_ui).pack(side="left", padx=10)
        ttk.Radiobutton(eng_sel_frame, text="Qwen + RVC (Local GPU)", variable=self.tts_engine_var, value="Qwen", command=self.toggle_tts_ui).pack(side="left", padx=10)

        # AllTalk UI
        self.alltalk_frame = ttk.Frame(tts_frame)
        at_path_frame = ttk.Frame(self.alltalk_frame)
        at_path_frame.pack(fill="x", pady=2)
        ttk.Label(at_path_frame, text="AllTalk Root Dir:").pack(side="left", padx=5)
        ttk.Entry(at_path_frame, textvariable=self.alltalk_path_var).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(at_path_frame, text="Browse", command=self.browse_alltalk).pack(side="left")
        ttk.Button(at_path_frame, text="Scan Voices", command=self.scan_alltalk_content).pack(side="left", padx=5)

        at_opts_frame = ttk.Frame(self.alltalk_frame)
        at_opts_frame.pack(fill="x", pady=2)
        ttk.Label(at_opts_frame, text="XTTS Voice:").pack(side="left", padx=5)
        self.voice_combo = ttk.Combobox(at_opts_frame, textvariable=self.selected_voice_var, state="readonly", width=25)
        self.voice_combo.pack(side="left", padx=5)
        ttk.Label(at_opts_frame, text="RVC Model:").pack(side="left", padx=(15, 5))
        self.rvc_combo = ttk.Combobox(at_opts_frame, textvariable=self.selected_rvc_var, state="readonly", width=30)
        self.rvc_combo.pack(side="left", padx=5)
        ttk.Label(at_opts_frame, text="Pitch:").pack(side="left", padx=(10, 2))
        ttk.Spinbox(at_opts_frame, from_=-24, to=24, textvariable=self.alltalk_pitch_var, width=4).pack(side="left")

        # Qwen UI
        self.qwen_frame = ttk.Frame(tts_frame)
        q_pth_frame = ttk.Frame(self.qwen_frame)
        q_pth_frame.pack(fill="x", pady=2)
        ttk.Label(q_pth_frame, text="RVC .pth:").pack(side="left", padx=5)
        ttk.Entry(q_pth_frame, textvariable=self.qwen_pth_var).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(q_pth_frame, text="Browse", command=lambda: self.browse_qwen_file("pth")).pack(side="left", padx=5)
        q_idx_frame = ttk.Frame(self.qwen_frame)
        q_idx_frame.pack(fill="x", pady=2)
        ttk.Label(q_idx_frame, text="RVC .index:").pack(side="left", padx=5)
        ttk.Entry(q_idx_frame, textvariable=self.qwen_index_var).pack(side="left", padx=5, fill="x", expand=True)
        ttk.Button(q_idx_frame, text="Browse", command=lambda: self.browse_qwen_file("index")).pack(side="left", padx=5)
        q_pitch_frame = ttk.Frame(self.qwen_frame)
        q_pitch_frame.pack(fill="x", pady=2)
        ttk.Label(q_pitch_frame, text="Pitch Shift:").pack(side="left", padx=5)
        ttk.Spinbox(q_pitch_frame, from_=-24, to=24, textvariable=self.qwen_pitch_var, width=5).pack(side="left", padx=5)

        self.toggle_tts_ui()

        # Source & Steps
        mid_frame = ttk.Frame(self.tab_run)
        mid_frame.pack(fill="x", padx=10, pady=5)
        
        # Source
        source_frame = ttk.LabelFrame(mid_frame, text="Input Source")
        source_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        ttk.Radiobutton(source_frame, text="Raw Scraped Text", variable=self.input_source_var, value="Raw").pack(anchor="w", padx=10, pady=5)
        ttk.Radiobutton(source_frame, text="Translated Text", variable=self.input_source_var, value="Translated").pack(anchor="w", padx=10, pady=5)

        # Steps
        chk_frame = ttk.LabelFrame(mid_frame, text="Processing Steps")
        chk_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        steps = [
            ("1. Scrape", "scraper"), ("2. Translate", "translate"),
            ("3. EPUB", "epub"), ("4. TTS Gen", "tts"),
            ("5. Opus Conv", "convert"), ("6. Tag Audio", "tag")
        ]
        for i, (text, key) in enumerate(steps):
            r, c = divmod(i, 2)
            if key == "translate":
                f = ttk.Frame(chk_frame)
                f.grid(row=r, column=c, sticky="w", padx=5, pady=2)
                ttk.Checkbutton(f, text=text, variable=self.pipeline_vars[key]).pack(side="left")
                ttk.Combobox(f, textvariable=self.trans_engine, values=["Translate (Gemini)", "Translate (Grok)"], state="readonly", width=12).pack(side="left", padx=2)
            else:
                ttk.Checkbutton(chk_frame, text=text, variable=self.pipeline_vars[key]).grid(row=r, column=c, sticky="w", padx=5, pady=2)

        # Action Buttons
        btn_frame = ttk.Frame(self.tab_run)
        btn_frame.pack(pady=15, fill="x", padx=50)
        self.btn_run = ttk.Button(btn_frame, text="START PROCESSING", command=self.start_pipeline_thread, style="Accent.TButton")
        self.btn_run.pack(side="left", fill="x", expand=True, padx=5)
        self.btn_stop = ttk.Button(btn_frame, text="STOP", command=self.stop_process, state="disabled")
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=5)

        # Logs
        log_frame = ttk.LabelFrame(self.tab_run, text="System Logs")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=12, state="normal", font=("Consolas", 9), bg="#1e1e1e", fg="#e0e0e0", insertbackground="white")
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_area.bind("<Key>", self.prevent_typing)
        ttk.Button(log_frame, text="Copy Logs", command=self.copy_all_logs).pack(pady=2)

        # ==============================
        # === TAB 2: METADATA EDITOR ===
        # ==============================
        self.create_metadata_ui()

        # ==============================
        # === TAB 3: AI ADAPTER ===
        # ==============================
        lbl = ttk.Label(self.tab_adapt, text="AI Scraper Generator", font=("Segoe UI", 12, "bold"))
        lbl.pack(pady=20)
        
        adapt_frame = ttk.Frame(self.tab_adapt)
        adapt_frame.pack(pady=10)
        
        ttk.Label(adapt_frame, text="Target URL:").grid(row=0, column=0, padx=5, sticky="e")
        ttk.Entry(adapt_frame, textvariable=self.adapt_url_var, width=50).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(adapt_frame, text="Mode:").grid(row=1, column=0, padx=5, sticky="e")
        ttk.Combobox(adapt_frame, textvariable=self.adapt_type_var, values=["Chapter Scraper", "Metadata Scraper"], state="readonly").grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        ttk.Button(self.tab_adapt, text="Generate Script with Gemini", command=self.run_adapt_tool, style="Accent.TButton").pack(pady=20)
        self.adapt_status = ttk.Label(self.tab_adapt, text="Ready", foreground="#888888")
        self.adapt_status.pack()

    def create_metadata_ui(self):
        """Builds the Metadata Tab UI."""
        main_meta = ttk.Frame(self.tab_meta)
        main_meta.pack(fill="both", expand=True, padx=20, pady=20)

        # Left Column: Inputs
        left_col = ttk.Frame(main_meta)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 20))

        # Fields
        fields = [
            ("Series Title:", self.meta_title),
            ("Author:", self.meta_author),
            ("Year:", self.meta_year),
            ("Genre:", self.meta_genre),
            ("Composer/Voice:", self.meta_composer)
        ]

        for label, var in fields:
            f = ttk.Frame(left_col)
            f.pack(fill="x", pady=5)
            ttk.Label(f, text=label, width=15).pack(side="left")
            ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True)

        # Buttons
        btn_box = ttk.Frame(left_col)
        btn_box.pack(fill="x", pady=20)
        ttk.Button(btn_box, text="Save Metadata.json", command=self.save_project_metadata, style="Accent.TButton").pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(btn_box, text="Reload from File", command=self.load_project_metadata).pack(side="left", fill="x", expand=True, padx=5)

        # Right Column: Image Preview
        right_col = ttk.LabelFrame(main_meta, text="Cover Art")
        right_col.pack(side="right", fill="both", expand=False, padx=5)

        self.lbl_cover_preview = ttk.Label(right_col, text="No Image", anchor="center", background="#1e1e1e")
        self.lbl_cover_preview.pack(padx=10, pady=10, fill="both", expand=True)
        # Fixed size container
        self.lbl_cover_preview.configure(width=30) # approx chars

        ttk.Button(right_col, text="Select Cover Image...", command=self.select_cover_image).pack(pady=10, padx=10, fill="x")


    # --- METADATA LOGIC ---
    def on_project_change(self, event):
        self.log(f"Selected: {self.current_project.get()}")
        self.load_project_metadata() # Auto-load when project changes

    def get_project_path(self):
        proj = self.current_project.get()
        if not proj: return None
        return os.path.join(NOVELS_ROOT_DIR, proj)

    def load_project_metadata(self):
        path = self.get_project_path()
        if not path: return

        json_file = os.path.join(path, "metadata.json")
        cover_file = os.path.join(path, "cover.jpg")

        # 1. Load JSON
        if os.path.exists(json_file):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.meta_title.set(data.get("title", ""))
                    self.meta_author.set(data.get("author", ""))
                    self.meta_year.set(data.get("year", "2025"))
                    self.meta_genre.set(data.get("genre", "Audiobook"))
                    self.meta_composer.set(data.get("composer", "AI TTS"))
            except Exception as e:
                self.log(f"Error loading metadata: {e}")
        else:
            # Clear fields if no file
            self.meta_title.set("")
            self.meta_author.set("")
            self.meta_year.set("2025")

        # 2. Load Cover
        if PILLOW_AVAILABLE and os.path.exists(cover_file):
            try:
                img = Image.open(cover_file)
                # Resize for preview (keep aspect ratio, max height 300)
                img.thumbnail((250, 350)) 
                self.cover_image_ref = ImageTk.PhotoImage(img)
                self.lbl_cover_preview.configure(image=self.cover_image_ref, text="")
            except Exception as e:
                self.lbl_cover_preview.configure(image="", text=f"Error loading image")
        else:
            self.lbl_cover_preview.configure(image="", text="No cover.jpg found")

    def save_project_metadata(self):
        path = self.get_project_path()
        if not path: 
            messagebox.showerror("Error", "No project selected")
            return

        data = {
            "title": self.meta_title.get(),
            "author": self.meta_author.get(),
            "year": self.meta_year.get(),
            "genre": self.meta_genre.get(),
            "composer": self.meta_composer.get()
        }

        try:
            with open(os.path.join(path, "metadata.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            self.log("Metadata saved successfully.")
            messagebox.showinfo("Success", "Metadata saved to metadata.json")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def select_cover_image(self):
        path = self.get_project_path()
        if not path: return

        file_path = filedialog.askopenfilename(
            title="Select Cover Image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.webp")]
        )

        if file_path:
            try:
                if PILLOW_AVAILABLE:
                    # Convert to JPG and resize if massive
                    img = Image.open(file_path)
                    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                    
                    target_path = os.path.join(path, "cover.jpg")
                    img.save(target_path, "JPEG", quality=90)
                    
                    self.load_project_metadata() # Refresh UI
                    self.log(f"Cover image updated: {target_path}")
                else:
                    # Simple copy if no Pillow
                    target_path = os.path.join(path, "cover.jpg")
                    shutil.copy(file_path, target_path)
                    self.log("Cover image copied (install Pillow for preview).")

            except Exception as e:
                messagebox.showerror("Error", f"Failed to process image: {e}")

    # --- EXISTING LOGIC ---
    def toggle_tts_ui(self):
        if self.tts_engine_var.get() == "AllTalk":
            self.qwen_frame.pack_forget()
            self.alltalk_frame.pack(fill="x", padx=5, pady=5)
        else:
            self.alltalk_frame.pack_forget()
            self.qwen_frame.pack(fill="x", padx=5, pady=5)

    def browse_qwen_file(self, file_type):
        ext = "*.pth" if file_type == "pth" else "*.index"
        f = filedialog.askopenfilename(title=f"Select RVC {file_type} file", filetypes=[(f"RVC {file_type.upper()}", ext)])
        if f:
            if file_type == "pth": self.qwen_pth_var.set(f)
            else: self.qwen_index_var.set(f)

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.alltalk_path_var.set(data.get("alltalk_path", ""))
                    self.alltalk_pitch_var.set(data.get("alltalk_pitch", 0))
                    self.qwen_pth_var.set(data.get("qwen_pth", ""))
                    self.qwen_index_var.set(data.get("qwen_index", ""))
                    self.qwen_pitch_var.set(data.get("qwen_pitch", -2))
        except Exception as e: print(f"Config Error: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({
                    "alltalk_path": self.alltalk_path_var.get(),
                    "alltalk_pitch": self.alltalk_pitch_var.get(),
                    "qwen_pth": self.qwen_pth_var.get(),
                    "qwen_index": self.qwen_index_var.get(),
                    "qwen_pitch": self.qwen_pitch_var.get(),
                }, f)
        except Exception as e: print(f"Config Save Error: {e}")

    def browse_alltalk(self):
        d = filedialog.askdirectory(title="Select AllTalk Root Directory")
        if d:
            self.alltalk_path_var.set(d)
            self.save_config()
            self.scan_alltalk_content()

    def scan_alltalk_content(self):
        base = self.alltalk_path_var.get()
        if not base or not os.path.exists(base): return

        voices_dir = os.path.join(base, "voices")
        if os.path.exists(voices_dir):
            wavs = glob.glob(os.path.join(voices_dir, "*.wav"))
            voice_names = [os.path.basename(w) for w in wavs]
            self.voice_combo["values"] = voice_names
            if voice_names: self.voice_combo.current(0)
            else: self.voice_combo.set("No .wav files found")
        else: self.voice_combo.set("Voices dir not found")

        rvc_search_roots = [
            os.path.join(base, "models", "rvc_voices"),
            os.path.join(base, "rvc_models"),
            os.path.join(base, "models", "rvc"),
        ]
        rvc_models_found = ["None"]
        valid_root = next((p for p in rvc_search_roots if os.path.exists(p)), None)
        if valid_root:
            try:
                subdirs = [d for d in os.listdir(valid_root) if os.path.isdir(os.path.join(valid_root, d))]
                for subdir in subdirs:
                    subdir_path = os.path.join(valid_root, subdir)
                    pth_files = glob.glob(os.path.join(subdir_path, "*.pth"))
                    for pth in pth_files:
                        rvc_models_found.append(os.path.join(subdir, os.path.basename(pth)))
            except Exception as e: print(f"Error scanning RVC: {e}")
        self.rvc_combo["values"] = rvc_models_found
        self.rvc_combo.current(1 if len(rvc_models_found) > 1 else 0)

    def prevent_typing(self, event):
        if (event.state & 4) and event.keysym.lower() in ["c", "a"]: return None
        if event.keysym in ["Up", "Down", "Left", "Right", "Home", "End", "Prior", "Next"]: return None
        return "break"

    def log(self, msg):
        self.root.after(0, lambda: self._log_internal(msg))

    def _log_internal(self, msg):
        print(msg)
        try:
            line_count = int(self.log_area.index('end-1c').split('.')[0])
            if line_count > MAX_LOG_LINES:
                self.log_area.delete("1.0", "501.0")
                self.log_area.insert(tk.END, "\n[Logs truncated...]\n")
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
        except: pass

    def copy_all_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_area.get("1.0", tk.END))
        messagebox.showinfo("Copied", "Logs copied.")

    def refresh_project_list(self):
        projects = [d for d in os.listdir(NOVELS_ROOT_DIR) if os.path.isdir(os.path.join(NOVELS_ROOT_DIR, d))]
        self.project_dropdown["values"] = sorted(projects)
        if projects and not self.current_project.get(): 
            self.current_project.set(projects[0])
            self.load_project_metadata() # Load first project meta

    def create_new_project(self):
        name = simpledialog.askstring("New Project", "Enter Novel Name:")
        if name:
            safe_name = "".join([c for c in name if c.isalnum() or c in (" ", "_")]).strip().replace(" ", "_")
            path = os.path.join(NOVELS_ROOT_DIR, safe_name)
            if not os.path.exists(path):
                for sub in ["01_Raw_Text", "02_Translated", "03_Audio_WAV", "04_Audio_Opus"]:
                    os.makedirs(os.path.join(path, sub))
                self.log(f"Created project: {safe_name}")
                self.refresh_project_list()
                self.current_project.set(safe_name)
                self.load_project_metadata()
            else: messagebox.showerror("Error", "Project exists.")

    def open_project_folder(self):
        proj = self.current_project.get()
        if proj:
            path = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
            os.startfile(path) if os.name == "nt" else subprocess.call(["xdg-open", path])

    def get_env_for_project(self):
        proj = self.current_project.get()
        base = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
        dir_raw = os.path.join(base, "01_Raw_Text")
        dir_trans = os.path.join(base, "02_Translated")
        dir_wav = os.path.join(base, "03_Audio_WAV")
        dir_opus = os.path.join(base, "04_Audio_Opus")
        tts_input = dir_trans if self.input_source_var.get() == "Translated" else dir_raw

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PROJECT_RAW_TEXT_DIR"] = dir_raw
        env["PROJECT_TRANS_INPUT_DIR"] = dir_raw
        env["PROJECT_TRANS_OUTPUT_DIR"] = dir_trans
        env["PROJECT_INPUT_TEXT_DIR"] = tts_input
        env["PROJECT_AUDIO_WAV_DIR"] = dir_wav
        env["WAV_AUDIO_DIR"] = dir_wav
        env["OPUS_OUTPUT_DIR"] = dir_opus
        env["EPUB_INPUT_DIR"] = tts_input
        env["EPUB_OUTPUT_FILE"] = os.path.join(base, f"{proj}.epub")
        env["EPUB_TITLE"] = proj.replace("_", " ")
        return env

    def stop_process(self):
        if self.current_process and self.current_process.poll() is None:
            self.stop_requested = True
            self.log("\n!!! STOPPING PROCESS... !!!")
            try: self.current_process.terminate()
            except: pass

    def run_script(self, script_key):
        if self.stop_requested: return False
        script_path = SCRIPTS.get(script_key)

        if script_key == "Scraper" and self.current_project.get():
            custom_path = os.path.join(NOVELS_ROOT_DIR, self.current_project.get(), "custom_scraper.py")
            if os.path.exists(custom_path):
                script_path = custom_path
                self.log(f"--- Using Custom Chapter Scraper ---")

        if script_key.startswith("Translate"): script_path = SCRIPTS.get(self.trans_engine.get())
        if script_key == "TTS Generator" and self.tts_engine_var.get() == "Qwen": script_path = "qwen_tts_generator.py"

        if not script_path or not os.path.exists(script_path):
            self.log(f"Error: {script_path} not found.")
            return False

        self.log(f"--- Running {os.path.basename(script_path)} ---")
        env = self.get_env_for_project()
        cmd = [sys.executable, "-u", script_path]

        if script_key == "TTS Generator":
            if self.tts_engine_var.get() == "AllTalk":
                voice = os.path.basename(self.selected_voice_var.get())
                rvc = self.selected_rvc_var.get()
                pitch = self.alltalk_pitch_var.get()

                if not voice or "No" in voice:
                    self.log("Error: Invalid voice selection.")
                    return False

                cmd.extend(["--voice_filename", voice])
                if rvc and rvc != "None":
                    cmd.extend(["--rvc_model", rvc, "--pitch", str(pitch)])
                self.save_config()

            else:
                pth = self.qwen_pth_var.get()
                idx = self.qwen_index_var.get()
                pitch = str(self.qwen_pitch_var.get())
                if not os.path.exists(pth) or not os.path.exists(idx):
                    self.log("Error: Qwen RVC paths invalid.")
                    return False
                cmd.extend(["--rvc_model_path", pth, "--rvc_index_path", idx, "--pitch", pitch])
                self.save_config()

        try:
            self.current_process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True, bufsize=1, universal_newlines=True
            )
            for line in self.current_process.stdout:
                if self.stop_requested:
                    self.current_process.terminate()
                    break
                self.log(line.strip())
            self.current_process.wait()
            if self.stop_requested:
                self.log("--- STOPPED ---")
                return False
            return self.current_process.returncode == 0
        except Exception as e:
            self.log(f"Error: {e}")
            return False
        finally: self.current_process = None

    def start_pipeline_thread(self):
        if not self.current_project.get():
            messagebox.showwarning("Warning", "Select a project.")
            return
        self.stop_requested = False
        self.btn_run.config(state="disabled")
        self.btn_stop.config(state="normal")
        threading.Thread(target=self.run_pipeline).start()

    def run_pipeline(self):
        try:
            if self.pipeline_vars["scraper"].get():
                if not self.run_script("Scraper"): raise Exception("Scraping Failed")
            if self.pipeline_vars["translate"].get():
                if not self.run_script("Translate"): raise Exception("Translation Failed")
            if self.pipeline_vars["epub"].get():
                if not self.run_script("EPUB Creator"): raise Exception("EPUB Failed")
            if self.pipeline_vars["tts"].get():
                if not self.run_script("TTS Generator"): raise Exception("TTS Failed")
            if self.pipeline_vars["convert"].get():
                if not self.run_script("Audio Converter"): raise Exception("Conversion Failed")
            if self.pipeline_vars["tag"].get():
                if not self.run_script("Tag Audio"): raise Exception("Tagging Failed")
            self.log("=== COMPLETED ===")
        except Exception as e: self.log(f"=== PIPELINE ENDED: {e} ===")
        finally:
            self.btn_run.config(state="normal")
            self.btn_stop.config(state="disabled")

    def run_metadata_fetch(self):
        proj = self.current_project.get()
        url = self.index_url.get().strip()
        if not proj or not url: return messagebox.showwarning("Info", "Select Project + URL.")
        self.log(f"--- Fetching Metadata ---")
        def _worker():
            try:
                proj_dir = os.path.join(NOVELS_ROOT_DIR, proj)
                proc = subprocess.Popen([sys.executable, "-u", SCRIPTS["Metadata"], url, proj_dir], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
                for line in proc.stdout: self.log(line.strip())
                proc.wait()
                if proc.returncode == 0: 
                    self.log("Metadata Fetch Complete.")
                    self.root.after(0, self.load_project_metadata) # Refresh UI with new data
            except Exception as e: self.log(f"Meta Error: {e}")
        threading.Thread(target=_worker).start()

    def run_adapt_tool(self):
        proj = self.current_project.get()
        url = self.adapt_url_var.get().strip()
        mode = self.adapt_type_var.get()
        if not proj or not url: return messagebox.showerror("Error", "Select project + URL.")
        if not os.environ.get("GEMINI_API_KEY"): return messagebox.showerror("Error", "GEMINI_API_KEY missing.")
        self.adapt_status.config(text=f"Generating {mode}... wait...", foreground="#6366f1")
        def _worker():
            try:
                proj_dir = os.path.join(NOVELS_ROOT_DIR, proj)
                if mode == "Chapter Scraper":
                    import scraper_context_fetcher
                    scraper_context_fetcher.fetch_and_generate_scraper(url, proj_dir)
                    target = "custom_scraper.py"
                else:
                    import metadata_fetcher
                    metadata_fetcher.fetch_and_generate_metadata_scraper(url, proj_dir)
                    target = "custom_metadata_scraper.py"
                if os.path.exists(os.path.join(proj_dir, target)):
                    self.root.after(0, lambda: self.adapt_status.config(text=f"Success! {target} created.", foreground="green"))
                else:
                    self.root.after(0, lambda: self.adapt_status.config(text="Generation failed.", foreground="red"))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda: self.adapt_status.config(text=f"Error: {err}", foreground="red"))
        threading.Thread(target=_worker).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = PipelineGUI(root)
    root.mainloop()
