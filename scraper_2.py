import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
DELAY_BETWEEN_REQUESTS = 0.01
# ---------------------

def get_with_retries(session, url, headers, retries=3):
    for i in range(retries):
        try:
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException:
            time.sleep(1 * (i + 1))
    return None

def extract_and_clean_chapter_data(content_el, ch_num):
    if not content_el:
        return "Unknown Title", ""

    for junk in content_el.find_all(['script', 'style', 'title', 'div'], 
                                   class_=['paragraph-tools', 'chapter__actions']):
        junk.decompose()

    paragraphs = content_el.find_all('p')
    story_title = f"Chapter {ch_num}" 
    
    for p in paragraphs[:10]:
        text = p.get_text(strip=True)
        bracket_match = re.search(r'\[(.*?)\]', text)
        if bracket_match:
            story_title = bracket_match.group(1)
            p.decompose()
            continue
            
        if re.search(rf'fairy\s*ch\s*{ch_num}', text, re.IGNORECASE):
            p.decompose()
            continue

    cleaned_body = content_el.get_text(separator='\n\n', strip=True)
    final_header = f"Chapter {ch_num} - {story_title}"
    return final_header, cleaned_body

def parse_chapter_number(raw_title):
    match = re.search(r'(?:ch|chapter|c)\.?\s*(\d+)', raw_title, re.IGNORECASE)
    return int(match.group(1)) if match else 0

def scrape_and_save_chapters(start_url, save_directory="BlleatTL_Novels"):
    if not os.path.exists(save_directory):
        os.makedirs(save_directory)

    json_path = os.path.join(save_directory, "chapters.json")
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.blleattl.site/'
    }

    # --- LOAD HISTORY ---
    # This map helps us jump to the last known URL quickly
    url_history_map = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
                for entry in history_data:
                    url_history_map[entry['url']] = entry.get('next_url')
        except:
            print("Could not load history JSON. Proceeding normally.")

    current_url = start_url

    try:
        while current_url:
            # 1. Determine Chapter Number from URL if possible, or check if we've seen this URL
            # To be safe, we perform a quick check: Do we already have a record for this URL?
            # If so, and we have the 'next_url', we can skip the request entirely.
            if current_url in url_history_map and url_history_map[current_url]:
                # Logic: We already processed this URL, just move to the next one
                next_link = url_history_map[current_url]
                
                # Check if the file actually exists on disk
                # We extract the expected filename based on the URL index usually
                # But since filenames depend on content, we'll do a light check
                print(f"Skipping (already in history): {current_url}")
                current_url = next_link
                continue

            print(f"Processing: {current_url}")
            response = get_with_retries(session, current_url, headers)
            if not response: break

            soup = BeautifulSoup(response.content, 'html.parser')
            title_el = soup.select_one('h1.chapter__title')
            content_el = soup.select_one('#chapter-content')
            next_el = soup.select_one('a._navigation._next')

            if not title_el or not content_el:
                print("Content missing. Stopping.")
                break

            raw_h1 = title_el.get_text(strip=True)
            ch_num = parse_chapter_number(raw_h1)
            filename = f"ch_{ch_num:04d}.txt"
            filepath = os.path.join(save_directory, filename)

            # --- FILE CHECK ---
            if os.path.exists(filepath):
                print(f"   -> File {filename} already exists. Skipping save.")
            else:
                full_header, cleaned_body = extract_and_clean_chapter_data(content_el, ch_num)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"{full_header}\n\n{cleaned_body}")
                print(f"   -> Saved: {full_header}")

            # Update JSON History
            next_url = next_el['href'] if next_el else None
            
            # Save progress so we can skip next time
            history_entry = {"url": current_url, "next_url": next_url, "file": filename}
            
            # Add or update history
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            else:
                data = []
            
            # Simple check to avoid duplicates in JSON
            if not any(d['url'] == current_url for d in data):
                data.append(history_entry)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)

            current_url = next_url
            time.sleep(DELAY_BETWEEN_REQUESTS)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    start_link = 'https://www.blleattl.site/story/fairy/fairy-ch1/'
    save_directory = os.getenv("PROJECT_RAW_TEXT_DIR", "BlleatTL_Novels")
    scrape_and_save_chapters(start_link, save_directory)
