import csv
import os
import subprocess
from datetime import datetime


def get_git_hash():
    """Fetches the current short Git commit hash."""
    try:
        # Runs the standard git command to get the short hash
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback if git is not installed or the folder isn't a git repo
        return "unknown-hash"


def log_chapter_translation(novel_dir, filename, model_name, status="Success"):
    """Appends a record to the translation history CSV inside the specific novel folder."""
    # Ensure the target directory exists just in case
    os.makedirs(novel_dir, exist_ok=True)

    log_file = os.path.join(novel_dir, "translation_history.csv")
    file_exists = os.path.exists(log_file)
    git_hash = get_git_hash()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Open the CSV in 'append' mode ('a')
    try:
        with open(log_file, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # Write the header row if the file was just created
            if not file_exists:
                writer.writerow(
                    ["Timestamp", "Filename", "Model", "Git Hash", "Status"]
                )

            # Write the actual log data
            writer.writerow([timestamp, filename, model_name, git_hash, status])
    except IOError as e:
        print(f"  Error writing to log file {log_file}: {e}")
