import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import subprocess
import threading
import sys
import os
import shutil
from constants import GEMINI_MODEL_NAME

# --- CONFIGURATION ---
NOVELS_ROOT_DIR = "Novels"
SCRIPTS = {
    "Scraper": "scraper_2.py",
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
        self.root.geometry("750x700")
        
        # Ensure Root Novel Directory Exists
        if not os.path.exists(NOVELS_ROOT_DIR):
            os.makedirs(NOVELS_ROOT_DIR)

        self.current_project = tk.StringVar()
        self.pipeline_vars = {
            "scraper": tk.BooleanVar(value=True),
            "translate": tk.BooleanVar(value=False),
            "epub": tk.BooleanVar(value=True),
            "tts": tk.BooleanVar(value=True),
            "convert": tk.BooleanVar(value=True),
            "tag": tk.BooleanVar(value=True),
        }
        self.trans_engine = tk.StringVar(value="Translate (Gemini)")
        self.new_url_var = tk.StringVar()

        self.create_ui()
        self.refresh_project_list()

    def create_ui(self):
        # --- TOP BAR: Project Selection ---
        top_frame = ttk.LabelFrame(self.root, text="Project Management")
        top_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(top_frame, text="Current Novel:").pack(side="left", padx=5)
        self.project_dropdown = ttk.Combobox(top_frame, textvariable=self.current_project, state="readonly", width=30)
        self.project_dropdown.pack(side="left", padx=5)
        self.project_dropdown.bind("<<ComboboxSelected>>", self.on_project_change)

        ttk.Button(top_frame, text="New Project", command=self.create_new_project).pack(side="left", padx=5)
        ttk.Button(top_frame, text="Open Folder", command=self.open_project_folder).pack(side="left", padx=5)

        # --- TABS ---
        tabs = ttk.Notebook(self.root)
        self.tab_run = ttk.Frame(tabs)
        self.tab_adapt = ttk.Frame(tabs)
        tabs.add(self.tab_run, text="Run Pipeline")
        tabs.add(self.tab_adapt, text="Adapt Scraper")
        tabs.pack(expand=True, fill="both", padx=10, pady=5)

        # --- TAB 1: RUN PIPELINE ---
        chk_frame = ttk.LabelFrame(self.tab_run, text="Select Steps")
        chk_frame.pack(fill="x", padx=5, pady=5)

        steps = [
            ("1. Run Scraper", "scraper"),
            ("2. Run Translation (Optional)", "translate"),
            ("3. Create EPUB", "epub"),
            ("4. Generate TTS", "tts"),
            ("5. Convert to Opus", "convert"),
            ("6. Tag Audio", "tag")
        ]

        for i, (text, key) in enumerate(steps):
            row = i // 2
            col = i % 2
            if key == "translate":
                f = ttk.Frame(chk_frame)
                f.grid(row=row, column=col, sticky="w", padx=10, pady=2)
                ttk.Checkbutton(f, text=text, variable=self.pipeline_vars[key]).pack(side="left")
                ttk.Combobox(f, textvariable=self.trans_engine, values=["Translate (Gemini)", "Translate (Grok)"], state="readonly", width=15).pack(side="left", padx=5)
            else:
                ttk.Checkbutton(chk_frame, text=text, variable=self.pipeline_vars[key]).grid(row=row, column=col, sticky="w", padx=10, pady=2)

        self.btn_run = ttk.Button(self.tab_run, text="START PROCESSING", command=self.start_pipeline_thread)
        self.btn_run.pack(pady=10, fill="x", padx=50)

        # Logs
        self.log_area = scrolledtext.ScrolledText(self.tab_run, height=15, state='disabled', font=("Consolas", 9))
        self.log_area.pack(fill="both", expand=True, padx=5, pady=5)

        # --- TAB 2: ADAPT SCRAPER ---
        ttk.Label(self.tab_adapt, text="Adapt scraper for a new website").pack(pady=10)
        ttk.Label(self.tab_adapt, text="Target URL:").pack()
        ttk.Entry(self.tab_adapt, textvariable=self.new_url_var, width=50).pack(pady=5)
        ttk.Button(self.tab_adapt, text="Fetch Context & Create Instructions", command=self.run_adapt_tool).pack(pady=10)
        self.adapt_status = ttk.Label(self.tab_adapt, text="...", foreground="gray")
        self.adapt_status.pack()

    # --- LOGIC ---
    def log(self, msg):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.configure(state='disabled')

    def refresh_project_list(self):
        projects = [d for d in os.listdir(NOVELS_ROOT_DIR) if os.path.isdir(os.path.join(NOVELS_ROOT_DIR, d))]
        self.project_dropdown['values'] = sorted(projects)
        if projects and not self.current_project.get():
            self.current_project.set(projects[0])

    def create_new_project(self):
        name = simpledialog.askstring("New Project", "Enter Novel Name (No special chars):")
        if name:
            safe_name = "".join([c for c in name if c.isalnum() or c in (' ', '_')]).strip().replace(" ", "_")
            path = os.path.join(NOVELS_ROOT_DIR, safe_name)
            if not os.path.exists(path):
                # Create standard folders
                os.makedirs(os.path.join(path, "01_Raw_Text"))
                os.makedirs(os.path.join(path, "02_Translated"))
                os.makedirs(os.path.join(path, "03_Audio_WAV"))
                os.makedirs(os.path.join(path, "04_Audio_Opus"))
                self.log(f"Created project: {safe_name}")
                self.refresh_project_list()
                self.current_project.set(safe_name)
            else:
                messagebox.showerror("Error", "Project already exists.")

    def on_project_change(self, event):
        self.log(f"Selected Project: {self.current_project.get()}")

    def open_project_folder(self):
        proj = self.current_project.get()
        if not proj: return
        path = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
        os.startfile(path) if os.name == 'nt' else subprocess.call(['xdg-open', path])

    def get_env_for_project(self):
        """Sets environment variables so child scripts know where to read/write."""
        proj = self.current_project.get()
        base = os.path.abspath(os.path.join(NOVELS_ROOT_DIR, proj))
        
        # Define paths
        dir_raw = os.path.join(base, "01_Raw_Text")
        dir_trans = os.path.join(base, "02_Translated")
        dir_wav = os.path.join(base, "03_Audio_WAV")
        dir_opus = os.path.join(base, "04_Audio_Opus")
        
        # Decide Input for TTS: Translated if exists/checked, else Raw
        tts_input = dir_trans if self.pipeline_vars["translate"].get() else dir_raw

        env = os.environ.copy()
        
        # -- MAP VARIABLES FOR YOUR SCRIPTS --
        # Scraper Output
        env["PROJECT_RAW_TEXT_DIR"] = dir_raw
        
        # Translator Input/Output
        env["PROJECT_TRANS_INPUT_DIR"] = dir_raw
        env["PROJECT_TRANS_OUTPUT_DIR"] = dir_trans
        
        # TTS Input/Output
        env["PROJECT_INPUT_TEXT_DIR"] = tts_input
        env["PROJECT_AUDIO_WAV_DIR"] = dir_wav
        
        # Converter Input/Output
        env["WAV_AUDIO_DIR"] = dir_wav
        env["OPUS_OUTPUT_DIR"] = dir_opus
        
        # EPUB Config
        env["EPUB_INPUT_DIR"] = tts_input
        env["EPUB_OUTPUT_FILE"] = os.path.join(base, f"{proj}.epub")
        env["EPUB_TITLE"] = proj.replace("_", " ")
        
        return env

    def run_script(self, script_key):
        # 1. Determine which script to run
        script_path = SCRIPTS.get(script_key)
        
        # SPECIAL HANDLING: Logic for Scraper
        # If we are running the Scraper, check if the current project has a custom one.
        if script_key == "Scraper":
            proj = self.current_project.get()
            if proj:
                # Look inside /Novels/ProjectName/custom_scraper.py
                custom_scraper_path = os.path.join(NOVELS_ROOT_DIR, proj, "custom_scraper.py")
                if os.path.exists(custom_scraper_path):
                    script_path = custom_scraper_path
                    self.log(f"--- DETECTED CUSTOM SCRAPER: {script_path} ---")
                else:
                    self.log(f"--- Using Default Scraper (No custom script found) ---")

        # Handle Translation Engine selection
        if script_key.startswith("Translate"):
            script_path = SCRIPTS.get(self.trans_engine.get())

        # 2. Validation
        if not script_path or not os.path.exists(script_path):
            self.log(f"ERROR: Script not found: {script_path}")
            return False

        self.log(f"--- Launching {os.path.basename(script_path)} ---")
        env = self.get_env_for_project()

        # 3. Execution
        try:
            process = subprocess.Popen(
                [sys.executable, script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            for line in process.stdout:
                self.log(line.strip())
            process.wait()
            
            if process.returncode == 0:
                self.log(f"--- {script_key} Completed Successfully ---")
                return True
            else:
                self.log(f"--- {script_key} Failed (Code {process.returncode}) ---")
                return False
        except Exception as e:
            self.log(f"Execution Error: {e}")
            return False

    def start_pipeline_thread(self):
        if not self.current_project.get():
            messagebox.showwarning("Warning", "Select a project first.")
            return
        self.btn_run.config(state="disabled")
        threading.Thread(target=self.run_pipeline).start()

    def run_pipeline(self):
        try:
            if self.pipeline_vars["scraper"].get():
                if not self.run_script("Scraper"): raise Exception("Scraper Failed")
            
            if self.pipeline_vars["translate"].get():
                if not self.run_script("Translate"): raise Exception("Translation Failed")

            if self.pipeline_vars["epub"].get():
                if not self.run_script("EPUB Creator"): raise Exception("EPUB Failed")

            if self.pipeline_vars["tts"].get():
                if not self.run_script("TTS Generator"): raise Exception("TTS Failed")

            if self.pipeline_vars["convert"].get():
                if not self.run_script("Audio Converter"): raise Exception("Converter Failed")

            if self.pipeline_vars["tag"].get():
                if not self.run_script("Tag Audio"): raise Exception("Tagging Failed")

            self.log("=== DONE ===")
        except Exception as e:
            self.log(f"=== PIPELINE STOPPED: {e} ===")
        finally:
            self.btn_run.config(state="normal")

    def run_adapt_tool(self):
        proj = self.current_project.get()
        url = self.new_url_var.get()
        if not proj or not url:
            messagebox.showerror("Error", "Select a project and enter a URL.")
            return
        
        # Check for API Key first
        if not os.environ.get("GEMINI_API_KEY"):
            messagebox.showerror("Error", "GEMINI_API_KEY not found in environment variables.")
            return

        self.adapt_status.config(text=f"Asking {GEMINI_MODEL_NAME} to write code... this may take 30s...", foreground="blue")
        
        def _worker():
            try:
                import scraper_context_fetcher
                proj_dir = os.path.join(NOVELS_ROOT_DIR, proj)
                
                # Call the new function that does everything
                scraper_context_fetcher.fetch_and_generate_scraper(url, proj_dir)
                
                # Check if file was created
                expected_file = os.path.join(proj_dir, "custom_scraper.py")
                if os.path.exists(expected_file):
                    self.root.after(0, lambda: self.adapt_status.config(text="Success! 'custom_scraper.py' created.", foreground="green"))
                    self.root.after(0, lambda: messagebox.showinfo("Done", f"New scraper created at:\n{expected_file}\n\nThe GUI will now use this scraper for this project."))
                    
                    # Update global scripts map to use this new local file for this project
                    # Note: This simple GUI logic assumes standard scraper_2.py unless you override it. 
                    # For a true dynamic switch, you might manually rename 'custom_scraper.py' to 'scraper_2.py' 
                    # inside that folder if you want to replace the default entirely for that project.
                else:
                    self.root.after(0, lambda: self.adapt_status.config(text="Failed to generate file.", foreground="red"))
                    
            except Exception as e:
                self.root.after(0, lambda: self.adapt_status.config(text=f"Error: {e}", foreground="red"))

        threading.Thread(target=_worker).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = PipelineGUI(root)
    root.mainloop()
