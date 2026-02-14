import glob
import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

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
        self.root.geometry("900x950")

        if not os.path.exists(NOVELS_ROOT_DIR):
            os.makedirs(NOVELS_ROOT_DIR)

        self.current_project = tk.StringVar()
        self.index_url = tk.StringVar()
        self.input_source_var = tk.StringVar(value="Raw")
        self.tts_engine_var = tk.StringVar(value="AllTalk")

        # AllTalk Config Vars
        self.alltalk_path_var = tk.StringVar()
        self.selected_voice_var = tk.StringVar()
        self.selected_rvc_var = tk.StringVar()
        self.alltalk_pitch_var = tk.IntVar(value=0)  # NEW: AllTalk Pitch

        # Qwen+RVC Config Vars
        self.qwen_pth_var = tk.StringVar()
        self.qwen_index_var = tk.StringVar()
        self.qwen_pitch_var = tk.IntVar(value=-2)

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

        ttk.Button(
            top_frame, text="New", command=self.create_new_project, width=5
        ).pack(side="left", padx=2)
        ttk.Button(
            top_frame, text="Folder", command=self.open_project_folder, width=6
        ).pack(side="left", padx=2)

        ttk.Label(top_frame, text=" | Index URL:").pack(side="left", padx=5)
        ttk.Entry(top_frame, textvariable=self.index_url, width=30).pack(
            side="left", padx=5
        )
        ttk.Button(top_frame, text="Get Meta", command=self.run_metadata_fetch).pack(
            side="left", padx=2
        )

        # --- TABS ---
        tabs = ttk.Notebook(self.root)
        self.tab_run = ttk.Frame(tabs)
        self.tab_adapt = ttk.Frame(tabs)
        tabs.add(self.tab_run, text="Run Pipeline")
        tabs.add(self.tab_adapt, text="AI Adapter")
        tabs.pack(expand=True, fill="both", padx=10, pady=5)

        # --- TAB 1: PIPELINE ---
        tts_frame = ttk.LabelFrame(self.tab_run, text="TTS Generation Setup")
        tts_frame.pack(fill="x", padx=10, pady=5)

        # Engine Selector
        eng_sel_frame = ttk.Frame(tts_frame)
        eng_sel_frame.pack(fill="x", padx=5, pady=5)
        ttk.Label(eng_sel_frame, text="Select Engine:").pack(side="left", padx=5)
        ttk.Radiobutton(
            eng_sel_frame,
            text="AllTalk (External API)",
            variable=self.tts_engine_var,
            value="AllTalk",
            command=self.toggle_tts_ui,
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            eng_sel_frame,
            text="Qwen + RVC (Local GPU)",
            variable=self.tts_engine_var,
            value="Qwen",
            command=self.toggle_tts_ui,
        ).pack(side="left", padx=10)

        # 1A. AllTalk Controls
        self.alltalk_frame = ttk.Frame(tts_frame)
        at_path_frame = ttk.Frame(self.alltalk_frame)
        at_path_frame.pack(fill="x", pady=2)
        ttk.Label(at_path_frame, text="AllTalk Root Dir:").pack(side="left", padx=5)
        ttk.Entry(at_path_frame, textvariable=self.alltalk_path_var).pack(
            side="left", padx=5, fill="x", expand=True
        )
        ttk.Button(at_path_frame, text="Browse", command=self.browse_alltalk).pack(
            side="left"
        )
        ttk.Button(
            at_path_frame, text="Scan Voices", command=self.scan_alltalk_content
        ).pack(side="left", padx=5)

        at_opts_frame = ttk.Frame(self.alltalk_frame)
        at_opts_frame.pack(fill="x", pady=2)
        ttk.Label(at_opts_frame, text="XTTS Voice:").pack(side="left", padx=5)
        self.voice_combo = ttk.Combobox(
            at_opts_frame,
            textvariable=self.selected_voice_var,
            state="readonly",
            width=25,
        )
        self.voice_combo.pack(side="left", padx=5)
        ttk.Label(at_opts_frame, text="RVC Model:").pack(side="left", padx=(15, 5))
        self.rvc_combo = ttk.Combobox(
            at_opts_frame,
            textvariable=self.selected_rvc_var,
            state="readonly",
            width=30,
        )
        self.rvc_combo.pack(side="left", padx=5)

        # NEW: AllTalk Pitch Control
        ttk.Label(at_opts_frame, text="Pitch:").pack(side="left", padx=(10, 2))
        ttk.Spinbox(
            at_opts_frame,
            from_=-24,
            to=24,
            textvariable=self.alltalk_pitch_var,
            width=4,
        ).pack(side="left")

        # 1B. Qwen Controls
        self.qwen_frame = ttk.Frame(tts_frame)
        q_pth_frame = ttk.Frame(self.qwen_frame)
        q_pth_frame.pack(fill="x", pady=2)
        ttk.Label(q_pth_frame, text="RVC .pth File:").pack(side="left", padx=5)
        ttk.Entry(q_pth_frame, textvariable=self.qwen_pth_var).pack(
            side="left", padx=5, fill="x", expand=True
        )
        ttk.Button(
            q_pth_frame, text="Browse", command=lambda: self.browse_qwen_file("pth")
        ).pack(side="left", padx=5)

        q_idx_frame = ttk.Frame(self.qwen_frame)
        q_idx_frame.pack(fill="x", pady=2)
        ttk.Label(q_idx_frame, text="RVC .index File:").pack(side="left", padx=5)
        ttk.Entry(q_idx_frame, textvariable=self.qwen_index_var).pack(
            side="left", padx=5, fill="x", expand=True
        )
        ttk.Button(
            q_idx_frame, text="Browse", command=lambda: self.browse_qwen_file("index")
        ).pack(side="left", padx=5)

        q_pitch_frame = ttk.Frame(self.qwen_frame)
        q_pitch_frame.pack(fill="x", pady=2)
        ttk.Label(q_pitch_frame, text="Pitch Shift (-12 to 12):").pack(
            side="left", padx=5
        )
        ttk.Spinbox(
            q_pitch_frame, from_=-24, to=24, textvariable=self.qwen_pitch_var, width=5
        ).pack(side="left", padx=5)

        self.toggle_tts_ui()

        # 2. Source Selection
        source_frame = ttk.LabelFrame(
            self.tab_run, text="Source Content for TTS & EPUB"
        )
        source_frame.pack(fill="x", padx=10, pady=5)
        ttk.Radiobutton(
            source_frame,
            text="Original Scraped Text (01_Raw_Text)",
            variable=self.input_source_var,
            value="Raw",
        ).pack(side="left", padx=20, pady=5)
        ttk.Radiobutton(
            source_frame,
            text="Translated Text (02_Translated)",
            variable=self.input_source_var,
            value="Translated",
        ).pack(side="left", padx=20, pady=5)

        # 3. Steps Selection
        chk_frame = ttk.LabelFrame(self.tab_run, text="Select Steps")
        chk_frame.pack(fill="x", padx=10, pady=5)
        steps = [
            ("1. Scrape Chapters", "scraper"),
            ("2. Translate (Optional)", "translate"),
            ("3. Create EPUB", "epub"),
            ("4. Generate TTS", "tts"),
            ("5. Convert to Opus", "convert"),
            ("6. Tag Audio", "tag"),
        ]
        for i, (text, key) in enumerate(steps):
            row = i // 2
            col = i % 2
            if key == "translate":
                f = ttk.Frame(chk_frame)
                f.grid(row=row, column=col, sticky="w", padx=10, pady=2)
                ttk.Checkbutton(f, text=text, variable=self.pipeline_vars[key]).pack(
                    side="left"
                )
                ttk.Combobox(
                    f,
                    textvariable=self.trans_engine,
                    values=["Translate (Gemini)", "Translate (Grok)"],
                    state="readonly",
                    width=15,
                ).pack(side="left", padx=5)
            else:
                ttk.Checkbutton(
                    chk_frame, text=text, variable=self.pipeline_vars[key]
                ).grid(row=row, column=col, sticky="w", padx=10, pady=2)

        # 4. Controls
        btn_frame = ttk.Frame(self.tab_run)
        btn_frame.pack(pady=10, fill="x", padx=50)
        self.btn_run = ttk.Button(
            btn_frame, text="START PROCESSING", command=self.start_pipeline_thread
        )
        self.btn_run.pack(side="left", fill="x", expand=True, padx=5)
        self.btn_stop = ttk.Button(
            btn_frame,
            text="STOP / TERMINATE",
            command=self.stop_process,
            state="disabled",
        )
        self.btn_stop.pack(side="right", fill="x", expand=True, padx=5)

        # 5. Logs
        log_label_frame = ttk.LabelFrame(self.tab_run, text="Process Logs")
        log_label_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(
            log_label_frame, height=15, state="normal", font=("Consolas", 9)
        )
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)
        self.log_area.bind("<Key>", self.prevent_typing)
        ttk.Button(
            log_label_frame, text="Copy All Logs", command=self.copy_all_logs
        ).pack(pady=2)

        # --- TAB 2: ADAPTER ---
        lbl = ttk.Label(
            self.tab_adapt,
            text="Use AI to write custom scripts for new websites.",
            font=("Arial", 10, "bold"),
        )
        lbl.pack(pady=10)
        adapt_frame = ttk.Frame(self.tab_adapt)
        adapt_frame.pack(pady=5)
        ttk.Label(adapt_frame, text="Target URL:").grid(
            row=0, column=0, padx=5, sticky="e"
        )
        ttk.Entry(adapt_frame, textvariable=self.adapt_url_var, width=50).grid(
            row=0, column=1, padx=5
        )
        ttk.Label(adapt_frame, text="Generate For:").grid(
            row=1, column=0, padx=5, sticky="e"
        )
        ttk.Combobox(
            adapt_frame,
            textvariable=self.adapt_type_var,
            values=["Chapter Scraper", "Metadata Scraper"],
            state="readonly",
        ).grid(row=1, column=1, padx=5, sticky="w")
        ttk.Button(
            self.tab_adapt,
            text="Ask Gemini to Write Script",
            command=self.run_adapt_tool,
        ).pack(pady=15)
        self.adapt_status = ttk.Label(self.tab_adapt, text="Ready", foreground="gray")
        self.adapt_status.pack()

    def toggle_tts_ui(self):
        if self.tts_engine_var.get() == "AllTalk":
            self.qwen_frame.pack_forget()
            self.alltalk_frame.pack(fill="x", padx=5, pady=5)
        else:
            self.alltalk_frame.pack_forget()
            self.qwen_frame.pack(fill="x", padx=5, pady=5)

    def browse_qwen_file(self, file_type):
        ext = "*.pth" if file_type == "pth" else "*.index"
        f = filedialog.askopenfilename(
            title=f"Select RVC {file_type} file",
            filetypes=[(f"RVC {file_type.upper()}", ext)],
        )
        if f:
            if file_type == "pth":
                self.qwen_pth_var.set(f)
            else:
                self.qwen_index_var.set(f)

    def load_config(self):
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    self.alltalk_path_var.set(data.get("alltalk_path", ""))
                    self.alltalk_pitch_var.set(
                        data.get("alltalk_pitch", 0)
                    )  # Load Pitch
                    self.qwen_pth_var.set(data.get("qwen_pth", ""))
                    self.qwen_index_var.set(data.get("qwen_index", ""))
                    self.qwen_pitch_var.set(data.get("qwen_pitch", -2))
        except Exception as e:
            print(f"Config Error: {e}")

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(
                    {
                        "alltalk_path": self.alltalk_path_var.get(),
                        "alltalk_pitch": self.alltalk_pitch_var.get(),  # Save Pitch
                        "qwen_pth": self.qwen_pth_var.get(),
                        "qwen_index": self.qwen_index_var.get(),
                        "qwen_pitch": self.qwen_pitch_var.get(),
                    },
                    f,
                )
        except Exception as e:
            print(f"Config Save Error: {e}")

    def browse_alltalk(self):
        d = filedialog.askdirectory(title="Select AllTalk Root Directory")
        if d:
            self.alltalk_path_var.set(d)
            self.save_config()
            self.scan_alltalk_content()

    def scan_alltalk_content(self):
        base = self.alltalk_path_var.get()
        if not base or not os.path.exists(base):
            return

        voices_dir = os.path.join(base, "voices")
        if os.path.exists(voices_dir):
            wavs = glob.glob(os.path.join(voices_dir, "*.wav"))
            voice_names = [os.path.basename(w) for w in wavs]
            self.voice_combo["values"] = voice_names
            if voice_names:
                self.voice_combo.current(0)
            else:
                self.voice_combo.set("No .wav files found")
        else:
            self.voice_combo.set("Voices dir not found")

        rvc_search_roots = [
            os.path.join(base, "models", "rvc_voices"),
            os.path.join(base, "rvc_models"),
            os.path.join(base, "models", "rvc"),
        ]
        rvc_models_found = ["None"]
        valid_root = next((p for p in rvc_search_roots if os.path.exists(p)), None)
        if valid_root:
            try:
                subdirs = [
                    d
                    for d in os.listdir(valid_root)
                    if os.path.isdir(os.path.join(valid_root, d))
                ]
                for subdir in subdirs:
                    subdir_path = os.path.join(valid_root, subdir)
                    pth_files = glob.glob(os.path.join(subdir_path, "*.pth"))
                    for pth in pth_files:
                        rvc_models_found.append(
                            os.path.join(subdir, os.path.basename(pth))
                        )
            except Exception as e:
                print(f"Error scanning RVC: {e}")
        self.rvc_combo["values"] = rvc_models_found
        self.rvc_combo.current(1 if len(rvc_models_found) > 1 else 0)

    def prevent_typing(self, event):
        if (event.state & 4) and event.keysym.lower() in ["c", "a"]:
            return None
        if event.keysym in [
            "Up",
            "Down",
            "Left",
            "Right",
            "Home",
            "End",
            "Prior",
            "Next",
        ]:
            return None
        return "break"

    def log(self, msg):
        self.root.after(0, lambda: self._log_internal(msg))

    def _log_internal(self, msg):
        print(msg)
        try:
            line_count = int(self.log_area.index("end-1c").split(".")[0])
            if line_count > MAX_LOG_LINES:
                self.log_area.delete("1.0", "501.0")
                self.log_area.insert(tk.END, "\n[Logs truncated...]\n")
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
        except:
            pass

    def copy_all_logs(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.log_area.get("1.0", tk.END))
        messagebox.showinfo("Copied", "Logs copied.")

    def refresh_project_list(self):
        projects = [
            d
            for d in os.listdir(NOVELS_ROOT_DIR)
            if os.path.isdir(os.path.join(NOVELS_ROOT_DIR, d))
        ]
        self.project_dropdown["values"] = sorted(projects)
        if projects and not self.current_project.get():
            self.current_project.set(projects[0])

    def create_new_project(self):
        name = simpledialog.askstring("New Project", "Enter Novel Name:")
        if name:
            safe_name = (
                "".join([c for c in name if c.isalnum() or c in (" ", "_")])
                .strip()
                .replace(" ", "_")
            )
            path = os.path.join(NOVELS_ROOT_DIR, safe_name)
            if not os.path.exists(path):
                for sub in [
                    "01_Raw_Text",
                    "02_Translated",
                    "03_Audio_WAV",
                    "04_Audio_Opus",
                ]:
                    os.makedirs(os.path.join(path, sub))
                self.log(f"Created project: {safe_name}")
                self.refresh_project_list()
                self.current_project.set(safe_name)
            else:
                messagebox.showerror("Error", "Project exists.")

    def on_project_change(self, event):
        self.log(f"Selected: {self.current_project.get()}")

    def open_project_folder(self):
        proj = self.current_project.get()
        if proj:
            path = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
            (
                os.startfile(path)
                if os.name == "nt"
                else subprocess.call(["xdg-open", path])
            )

    def get_env_for_project(self):
        proj = self.current_project.get()
        base = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
        dir_raw = os.path.join(base, "01_Raw_Text")
        dir_trans = os.path.join(base, "02_Translated")
        dir_wav = os.path.join(base, "03_Audio_WAV")
        dir_opus = os.path.join(base, "04_Audio_Opus")
        tts_input = (
            dir_trans if self.input_source_var.get() == "Translated" else dir_raw
        )

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
            try:
                self.current_process.terminate()
            except:
                pass

    def run_script(self, script_key):
        if self.stop_requested:
            return False
        script_path = SCRIPTS.get(script_key)

        if script_key == "Scraper" and self.current_project.get():
            custom_path = os.path.join(
                NOVELS_ROOT_DIR, self.current_project.get(), "custom_scraper.py"
            )
            if os.path.exists(custom_path):
                script_path = custom_path
                self.log(f"--- Using Custom Chapter Scraper ---")

        if script_key.startswith("Translate"):
            script_path = SCRIPTS.get(self.trans_engine.get())
        if script_key == "TTS Generator" and self.tts_engine_var.get() == "Qwen":
            script_path = "qwen_tts_generator.py"

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
                pitch = self.alltalk_pitch_var.get()  # Get Pitch

                if not voice or "No" in voice:
                    self.log("Error: Invalid voice selection.")
                    return False

                cmd.extend(["--voice_filename", voice])
                if rvc and rvc != "None":
                    cmd.extend(
                        ["--rvc_model", rvc, "--pitch", str(pitch)]
                    )  # Pass Pitch
                self.save_config()  # Save AllTalk config too

            else:
                pth = self.qwen_pth_var.get()
                idx = self.qwen_index_var.get()
                pitch = str(self.qwen_pitch_var.get())
                if not os.path.exists(pth) or not os.path.exists(idx):
                    self.log("Error: Qwen RVC paths invalid.")
                    return False
                cmd.extend(
                    ["--rvc_model_path", pth, "--rvc_index_path", idx, "--pitch", pitch]
                )
                self.save_config()

        try:
            self.current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1,
                universal_newlines=True,
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
        finally:
            self.current_process = None

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
                if not self.run_script("Scraper"):
                    raise Exception("Scraping Failed")
            if self.pipeline_vars["translate"].get():
                if not self.run_script("Translate"):
                    raise Exception("Translation Failed")
            if self.pipeline_vars["epub"].get():
                if not self.run_script("EPUB Creator"):
                    raise Exception("EPUB Failed")
            if self.pipeline_vars["tts"].get():
                if not self.run_script("TTS Generator"):
                    raise Exception("TTS Failed")
            if self.pipeline_vars["convert"].get():
                if not self.run_script("Audio Converter"):
                    raise Exception("Conversion Failed")
            if self.pipeline_vars["tag"].get():
                if not self.run_script("Tag Audio"):
                    raise Exception("Tagging Failed")
            self.log("=== COMPLETED ===")
        except Exception as e:
            self.log(f"=== PIPELINE ENDED: {e} ===")
        finally:
            self.btn_run.config(state="normal")
            self.btn_stop.config(state="disabled")

    def run_metadata_fetch(self):
        proj = self.current_project.get()
        url = self.index_url.get().strip()
        if not proj or not url:
            return messagebox.showwarning("Info", "Select Project + URL.")
        self.log(f"--- Fetching Metadata ---")

        def _worker():
            try:
                proj_dir = os.path.join(NOVELS_ROOT_DIR, proj)
                proc = subprocess.Popen(
                    [sys.executable, "-u", SCRIPTS["Metadata"], url, proj_dir],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )
                for line in proc.stdout:
                    self.log(line.strip())
                proc.wait()
                if proc.returncode == 0:
                    self.log("Metadata Fetch Complete.")
            except Exception as e:
                self.log(f"Meta Error: {e}")

        threading.Thread(target=_worker).start()

    def run_adapt_tool(self):
        proj = self.current_project.get()
        url = self.adapt_url_var.get().strip()
        mode = self.adapt_type_var.get()
        if not proj or not url:
            return messagebox.showerror("Error", "Select project + URL.")
        if not os.environ.get("GEMINI_API_KEY"):
            return messagebox.showerror("Error", "GEMINI_API_KEY missing.")
        self.adapt_status.config(
            text=f"Generating {mode}... wait...", foreground="blue"
        )

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
                    self.root.after(
                        0,
                        lambda: self.adapt_status.config(
                            text=f"Success! {target} created.", foreground="green"
                        ),
                    )
                else:
                    self.root.after(
                        0,
                        lambda: self.adapt_status.config(
                            text="Generation failed.", foreground="red"
                        ),
                    )
            except Exception as e:
                err = str(e)
                self.root.after(
                    0,
                    lambda: self.adapt_status.config(
                        text=f"Error: {err}", foreground="red"
                    ),
                )

        threading.Thread(target=_worker).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = PipelineGUI(root)
    root.mainloop()
