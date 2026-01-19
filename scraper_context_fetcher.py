import os
import requests
import shutil
import sys
import re
from urllib.parse import urlparse
import google.generativeai as genai
from constants import GEMINI_MODEL_NAME

def extract_code_block(response_text):
    """
    Extracts the Python code from Gemini's Markdown response.
    """
    pattern = r"```python\s*(.*?)\s*```"
    match = re.search(pattern, response_text, re.DOTALL)
    if match:
        return match.group(1)
    # Fallback: if no code blocks, assume the whole text is code (rare)
    return response_text

def fetch_and_generate_scraper(target_url, project_root_dir, reference_scraper="scraper_2.py"):
    """
    Fetches HTML context, sends it + reference script to Gemini, 
    and saves the generated adapter script.
    """
    # 1. Setup Directories
    context_dir = os.path.join(project_root_dir, "Scraper_Context")
    if not os.path.exists(context_dir):
        os.makedirs(context_dir)

    print(f"--- 1. Fetching HTML for: {target_url} ---")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    html_content = ""
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text
        
        # Save HTML for debugging/reference
        with open(os.path.join(context_dir, "site_structure.html"), "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception as e:
        print(f"Error fetching URL: {e}")
        return

    print(f"--- 2. Reading Reference Scraper ---")
    reference_code = ""
    if os.path.exists(reference_scraper):
        with open(reference_scraper, "r", encoding="utf-8") as f:
            reference_code = f.read()
    else:
        print(f"Error: Reference scraper '{reference_scraper}' not found.")
        return

    print(f"--- 3. Sending to Gemini ({GEMINI_MODEL_NAME}) ---")
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        return

    genai.configure(api_key=api_key)
    
    # Construct the Prompt
    prompt = f"""
    You are an expert Python web scraping developer.
    
    I need you to write a NEW Python script to scrape a specific web novel.
    
    --- REFERENCE SCRAPER (scraper_2.py) ---
    The following code is a working example of how I want the output formatted. 
    It saves chapters to specific directories and handles logic like 'next chapter' links.
    Reuse the logic for file saving, directory creation (os.getenv calls), and the general loop structure.
    
    {reference_code}
    
    --- TARGET WEBSITE HTML ---
    Here is the HTML source code of the first chapter of the novel I want to scrape.
    Use BeautifulSoup to parse this structure. 
    Find the Title, the Main Content, and the 'Next Chapter' link specific to this HTML.
    
    {html_content[:50000]}  # Truncated to avoid token limits if HTML is massive
    
    --- INSTRUCTIONS ---
    1. Output ONLY the complete, runnable Python code.
    2. Adapt the BeautifulSoup selectors to match the TARGET WEBSITE HTML provided above.
    3. Ensure the script uses `os.getenv('PROJECT_RAW_TEXT_DIR')` for output, just like the reference.
    4. Handle the 'Next Chapter' logic based on the HTML provided.
    """

    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        # Using generate_content method provided by the library
        response = model.generate_content(prompt)
        
        generated_code = extract_code_block(response.text)
        
        # Save the new scraper
        output_scraper_path = os.path.join(project_root_dir, "custom_scraper.py")
        with open(output_scraper_path, "w", encoding="utf-8") as f:
            f.write(generated_code)
            
        print(f"--- SUCCESS! ---")
        print(f"New scraper saved to: {output_scraper_path}")
        print(f"To use it, select this project in the GUI and run 'Run Scraper'.")
        
    except Exception as e:
        print(f"Gemini API Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) > 2:
        fetch_and_generate_scraper(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python scraper_context_fetcher.py <url> <project_dir>")
