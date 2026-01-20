import os
import sys
import json
import requests
import re
import shutil
import subprocess
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Try to import constants, fallback if missing
try:
    import google.generativeai as genai
    from constants import GEMINI_MODEL_NAME
except ImportError:
    GEMINI_MODEL_NAME = "gemini-3-flash-preview"

# --- HELPER: Image Downloader ---
def download_cover(img_url, save_dir):
    if not img_url: return
    try:
        clean_url = img_url.split('?')[0] # Remove WP resize params
        save_path = os.path.join(save_dir, "cover.jpg")
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(img_url, headers=headers, stream=True, timeout=10)
        if r.status_code == 200:
            with open(save_path, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
            print(f"    [Cover] Saved to: {save_path}")
    except Exception as e:
        print(f"    [Error] Cover download failed: {e}")

# --- 1. DEFAULT EXTRACTION LOGIC ---
def default_metadata_extraction(html, url):
    """
    Standard scraper trying OpenGraph and common HTML tags.
    """
    soup = BeautifulSoup(html, 'html.parser')
    data = {"title": "Unknown Title", "author": "Unknown Author", "description": "", "cover_url": ""}

    # Title
    og_title = soup.find("meta", property="og:title")
    if og_title: 
        data["title"] = og_title.get("content", "").replace("– Dobytranslations", "").strip()
    else:
        h1 = soup.select_one("h1.entry-title")
        if h1: data["title"] = h1.get_text(strip=True)

    # Cover
    # Doby specific
    thumb = soup.select_one(".sertothumb img")
    if thumb:
        data["cover_url"] = thumb.get("src", "") or thumb.get("data-src", "")
    else:
        og_image = soup.find("meta", property="og:image")
        if og_image: data["cover_url"] = og_image.get("content", "")

    # Description
    # Doby specific
    desc_div = soup.select_one(".sersys.entry-content") 
    if not desc_div: desc_div = soup.select_one(".entry-content[itemprop='description']")
    
    if desc_div:
        # Cleanup Doby junk (New Free unlock...)
        for junk in desc_div.find_all(['h4', 'strong']):
            if "unlock" in junk.get_text().lower(): junk.decompose()
        data["description"] = desc_div.get_text(separator="\n", strip=True)
    else:
        og_desc = soup.find("meta", property="og:description")
        if og_desc: data["description"] = og_desc.get("content", "")

    # Author
    # Fixed the specific error you saw previously (argument conflict)
    author_meta = soup.find("meta", attrs={"name": "author"})
    if author_meta:
        data["author"] = author_meta.get("content", "")
    else:
        for label in soup.find_all(string=re.compile(r"Author", re.I)):
            parent = label.parent
            if parent:
                text = parent.get_text(strip=True).replace("Author", "").replace(":", "").strip()
                if 1 < len(text) < 50:
                    data["author"] = text
                    break
    
    return data

# --- 2. AI GENERATOR LOGIC ---
def fetch_and_generate_metadata_scraper(index_url, project_dir):
    """
    Fetches HTML -> Sends to Gemini -> Writes custom_metadata_scraper.py
    """
    context_dir = os.path.join(project_dir, "Scraper_Context")
    if not os.path.exists(context_dir): os.makedirs(context_dir)

    print(f"    [AI] Fetching HTML source to analyze...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(index_url, headers=headers, timeout=15)
        html_content = response.text
        # Save for reference
        with open(os.path.join(context_dir, "index_structure.html"), "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception as e:
        print(f"    [AI] Error fetching URL: {e}")
        return False

    print(f"    [AI] Asking Gemini ({GEMINI_MODEL_NAME}) to write a custom scraper...")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("    [Error] GEMINI_API_KEY not set.")
        return False

    genai.configure(api_key=api_key)
    
    prompt = f"""
    You are an expert Python web scraping developer.
    
    The default scraping method FAILED for this website.
    I need a robust script to extract Novel Metadata from the HTML below.
    
    --- TARGET HTML (Index Page) ---
    {html_content[:55000]} 
    
    --- INSTRUCTIONS ---
    1. Write a Python script using `BeautifulSoup`.
    2. Extract: **Title**, **Author**, **Description**, **Cover Image URL**.
    3. **CRITICAL OUTPUT**:
       - Save the data to `metadata.json` in `os.getenv('SAVE_DIR')`.
       - Download the cover image to `cover.jpg` in `os.getenv('SAVE_DIR')`.
    4. Handle `data-src` or `loading="lazy"` if present for images.
    5. Use `requests` to download the image.
    
    Output ONLY the valid Python code.
    """

    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        response = model.generate_content(prompt)
        
        # Extract code block
        code = response.text
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0]
        elif "```" in code:
            code = code.split("```")[1]
        
        output_path = os.path.join(project_dir, "custom_metadata_scraper.py")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(code)
            
        print(f"    [AI] Success! Generated: {output_path}")
        return True
        
    except Exception as e:
        print(f"    [AI] Gemini API Error: {e}")
        return False

# --- 3. MAIN CONTROLLER ---
def run_metadata_fetch(index_url, project_dir):
    print(f"--- Fetching Metadata for: {os.path.basename(project_dir)} ---")
    
    # A. Check for EXISTING custom script first
    custom_script = os.path.join(project_dir, "custom_metadata_scraper.py")
    if os.path.exists(custom_script):
        print(f"--- Found Custom Script. Executing... ---")
        run_custom_script(custom_script, index_url, project_dir)
        return

    # B. Try Default Method
    try:
        print("    [1] Trying Default Extraction...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(index_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = default_metadata_extraction(response.text, index_url)
        
        # Validate critical data
        if not data['title'] or data['title'] == "Unknown Title":
            raise Exception("Default extractor failed to find a valid title.")

        # Save success
        json_path = os.path.join(project_dir, "metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"    [Meta] Success! Title: {data['title']}")
        
        if data["cover_url"]:
            download_cover(data["cover_url"], project_dir)

    except Exception as e:
        # C. FAILOVER: Trigger AI
        print(f"    [!] Default Method Failed: {e}")
        print(f"    [2] FAILOVER: Initializing AI Auto-Correction...")
        
        success = fetch_and_generate_metadata_scraper(index_url, project_dir)
        
        if success and os.path.exists(custom_script):
            print(f"    [3] Executing newly generated AI script...")
            run_custom_script(custom_script, index_url, project_dir)
        else:
            print("    [Error] AI Adaptation failed.")

def run_custom_script(script_path, url, save_dir):
    """Executes the custom script in a subprocess"""
    try:
        env = os.environ.copy()
        env["TARGET_URL"] = url
        env["SAVE_DIR"] = save_dir
        
        result = subprocess.run(
            [sys.executable, script_path], 
            env=env, 
            capture_output=True, 
            text=True
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"    [Script Error] {result.stderr}")
    except Exception as e:
        print(f"    [Exec Error] {e}")

if __name__ == "__main__":
    if len(sys.argv) > 3:
        u = sys.argv[1]
        d = sys.argv[2]
        mode = sys.argv[3]
        if mode == "adapt":
            fetch_and_generate_metadata_scraper(u, d)
        else:
            run_metadata_fetch(u, d)
    elif len(sys.argv) > 2:
        run_metadata_fetch(sys.argv[1], sys.argv[2])
