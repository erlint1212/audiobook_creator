import os
import re
import sys
from urllib.parse import urlparse

import requests

# --- FIX 1: Safer Import Handling ---
try:
    import google.generativeai as genai

    from constants import GEMINI_MODEL_NAME

    GENAI_AVAILABLE = True
except ImportError:
    GEMINI_MODEL_NAME = "gemini-3-flash-preview"
    GENAI_AVAILABLE = False


def extract_code_block(response_text):
    pattern = r"```python\s*(.*?)\s*```"
    match = re.search(pattern, response_text, re.DOTALL)
    if match:
        return match.group(1)
    return response_text


def fetch_and_generate_scraper(
    target_url, project_root_dir, reference_scraper="scraper_2.py"
):
    # Guard check for API availability
    if not GENAI_AVAILABLE:
        raise Exception(
            "Google Generative AI package is not installed. Please run: pip install google-generativeai"
        )

    context_dir = os.path.join(project_root_dir, "Scraper_Context")
    if not os.path.exists(context_dir):
        os.makedirs(context_dir)

    print(f"--- 1. Fetching HTML for: {target_url} ---")
    headers = {"User-Agent": "Mozilla/5.0"}

    html_content = ""
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.raise_for_status()
        html_content = response.text
        with open(
            os.path.join(context_dir, "site_structure.html"), "w", encoding="utf-8"
        ) as f:
            f.write(html_content)
    except Exception as e:
        raise Exception(f"Error fetching URL: {e}")

    print(f"--- 2. Reading Reference Scraper ---")
    reference_code = ""
    if os.path.exists(reference_scraper):
        with open(reference_scraper, "r", encoding="utf-8") as f:
            reference_code = f.read()
    else:
        raise Exception(f"Reference scraper '{reference_scraper}' not found.")

    print(f"--- 3. Sending to Gemini ({GEMINI_MODEL_NAME}) ---")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise Exception("GEMINI_API_KEY environment variable not set.")

    genai.configure(api_key=api_key)

    prompt = f"""
    You are an expert Python web scraping developer.
    
    I need you to write a NEW Python script to scrape a specific web novel.
    
    --- REFERENCE SCRAPER (scraper_2.py) ---
    The following code is a working example. Reuse the file saving, os.getenv logic, and loop structure.
    
    {reference_code}
    
    --- TARGET WEBSITE HTML ---
    Here is the HTML source code of the first chapter. 
    Use BeautifulSoup to parse this structure. 
    
    {html_content[:55000]}
    
    --- CRITICAL INSTRUCTIONS ---
    1. **CLEAN CONTENT:** The text saved to the .txt file MUST ONLY contain the Chapter Header and the Story Body.
       - **Remove** "Previous/Next" text, "Read at..." watermarks, and social media buttons from the body.
    
    2. **DEDUPLICATION:** - Check if the first line of the body content matches the Chapter Title.
       - **If it matches, remove it** from the body content to avoid duplication in the output file.
    
    3. **STRICT FORMAT:** `f.write(f"{{full_header}}\\n\\n{{cleaned_body}}")`
    
    4. **NEXT CHAPTER LOGIC (Crucial):**
       - **Priority 1:** Look for `<a href="..." rel="next">`. This is the most reliable method.
       - **Priority 2:** Look for an `<a>` tag inside a "nav" or "pager" div that contains the text "Next".
       - Ensure the loop breaks cleanly if no next link is found.

    5. Output ONLY the complete, runnable Python code.
    """

    try:
        model = genai.GenerativeModel(GEMINI_MODEL_NAME)
        # --- FIX 2: Added 120-second timeout to prevent infinite hanging ---
        response = model.generate_content(prompt, request_options={"timeout": 120})

        generated_code = extract_code_block(response.text)

        output_scraper_path = os.path.join(project_root_dir, "custom_scraper.py")
        with open(output_scraper_path, "w", encoding="utf-8") as f:
            f.write(generated_code)

        print(f"--- SUCCESS! ---")
        print(f"New scraper saved to: {output_scraper_path}")

    except Exception as e:
        # Re-raise the exception so the GUI background thread catches it
        raise Exception(f"Gemini API Error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        try:
            fetch_and_generate_scraper(sys.argv[1], sys.argv[2])
        except Exception as e:
            print(f"Fatal Error: {e}")
    else:
        print("Usage: python scraper_context_fetcher.py <url> <project_dir>")
