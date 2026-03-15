import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
DELAY_BETWEEN_REQUESTS = 1.0  # Seconds
# ---------------------


def get_with_retries(session, url, headers, retries=3):
    for i in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            print(f"   [!] Error fetching {url}: {e}. Retrying ({i+1}/{retries})...")
            time.sleep(2 * (i + 1))
    return None


def parse_chapter_title(raw_title):
    """
    Parses a raw page title like:
      "Volume 1, Chapter 0 – Prologue: A Clumsy Transmigration"
    into:
      "Chapter 0 - Prologue: A Clumsy Transmigration"
    Falls back to the cleaned string if parsing fails.
    """
    # Strip zero-width characters
    raw_title = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", raw_title)

    # Strip optional "Volume X, " prefix
    stripped = re.sub(r"(?i)^volume\s+\d+\s*,\s*", "", raw_title).strip()

    # Try to match "Chapter <num> – <subtitle>"
    m = re.match(r"(?i)^chapter\s+(\d+)\s*[–—\-:]\s*(.+)$", stripped)
    if m:
        return f"Chapter {m.group(1)} - {m.group(2).strip()}"

    # If only "Chapter <num>" with no subtitle
    m2 = re.match(r"(?i)^chapter\s+(\d+)\s*$", stripped)
    if m2:
        return f"Chapter {m2.group(1)}"

    # Fallback
    return stripped


def clean_body_text(text):
    """
    Strips zero-width characters, watermarks, and trailing credit lines
    from chapter body text.
    """
    # Strip zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

    # Remove common watermarks
    text = re.sub(r"(?i)read\s+(at|on)\s+\w+\.com", "", text)
    text = re.sub(r"(?i)translated by.*?\n", "", text)

    # Remove short trailing credit/watermark lines
    lines = text.rstrip().split("\n")
    while lines:
        last = lines[-1].strip()
        if not last or (len(last) < 40 and not any(c in last for c in ".?!,;:")):
            lines.pop()
        else:
            break

    return "\n".join(lines).strip()


def extract_and_clean_chapter_data(content_el, soup, ch_num):
    """
    Targets the main content area, removes scripts, styles, and unwanted
    interactive elements like glossaries or ads.
    Uses the page's own title instead of the internal counter for the header.
    """
    if not content_el:
        return f"Chapter {ch_num}", ""

    # Extract the page title for use in the header
    page_title_el = soup.select_one("h1.entry-title")
    extracted_title = (
        page_title_el.get_text(strip=True) if page_title_el else f"Chapter {ch_num}"
    )

    # 1. Remove script, style, and known junk classes
    for junk in content_el.find_all(
        ["script", "style", "div", "section", "button"],
        class_=[
            "paragraph-tools",
            "chapter__actions",
            "social-share",
            "sharedaddy",
            "navigation",
        ],
    ):
        junk.decompose()

    # 2. Remove Glossary Tooltips (common in translation sites)
    for tooltip in content_el.find_all(class_="dg-tooltip-box"):
        tooltip.decompose()

    # 3. Get text content
    cleaned_body = content_el.get_text(separator="\n\n", strip=True)

    # --- TITLE DEDUPLICATION ---
    lines = cleaned_body.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)

    if lines:
        first_line = lines[0].strip()
        if (
            (extracted_title.lower() in first_line.lower())
            or (first_line.lower() in extracted_title.lower())
            or (len(first_line) < 100 and "chapter" in first_line.lower())
        ):
            extracted_title = first_line
            cleaned_body = "\n".join(lines[1:]).strip()

    # Clean body text (watermarks, credits, zero-width chars)
    cleaned_body = clean_body_text(cleaned_body)

    # Parse the title (strip "Volume X,", extract real chapter number)
    final_header = parse_chapter_title(extracted_title)

    return final_header, cleaned_body


def scrape_and_save_chapters(start_url, save_directory="BlleatTL_Novels"):
    save_directory = os.getenv("PROJECT_RAW_TEXT_DIR", save_directory)

    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    json_path = os.path.join(save_directory, "chapters.json")
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    # --- LOAD HISTORY & SET COUNTER ---
    url_history_map = {}
    history_data = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                history_data = json.load(f)
                for entry in history_data:
                    url_history_map[entry["url"]] = entry.get("next_url")
        except:
            pass

    ch_counter = len(history_data) + 1
    current_url = start_url

    try:
        while current_url:
            if current_url in url_history_map and url_history_map[current_url]:
                next_link = url_history_map[current_url]
                print(f"Skipping (history): {current_url}")
                current_url = next_link
                continue

            print(f"Processing: {current_url}")
            response = get_with_retries(session, current_url, headers)
            if not response:
                break

            soup = BeautifulSoup(response.content, "html.parser")

            # Extract basic info
            content_el = soup.select_one(".entry-content") or soup.find("article")

            # Find Next Link
            next_el = None
            for a in soup.find_all("a", href=True):
                if "next" in a.get_text(strip=True).lower():
                    next_el = a
                    break

            if not content_el:
                print("Content not found.")
                break

            # Use internal counter for FILENAME only
            filename = f"ch_{ch_counter:04d}.txt"
            filepath = os.path.join(save_directory, filename)

            if os.path.exists(filepath):
                print(f"   -> Exists: {filename}")
            else:
                full_header, cleaned_body = extract_and_clean_chapter_data(
                    content_el, soup, ch_counter
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"{full_header}\n\n{cleaned_body}")
                print(f"   -> Saved: {full_header}")

            next_url = next_el["href"] if next_el else None

            # Save History
            history_entry = {"url": current_url, "next_url": next_url, "file": filename}
            history_data.append(history_entry)
            with open(json_path, "w") as f:
                json.dump(history_data, f, indent=4)

            ch_counter += 1

            if not next_url:
                break
            current_url = next_url
            time.sleep(DELAY_BETWEEN_REQUESTS)

    except Exception as e:
        print(f"Critical Error: {e}")


if __name__ == "__main__":
    pass
