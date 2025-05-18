import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin # <<< --- Required for handling relative links
import time                 # <<< --- Required for pausing between requests

def scrape_novel_chapter(url, output_filename="novel_chapter.txt"):
    """
    Scrapes the chapter title and text from a single chapter on mystictranslations.com,
    saves it to a file, and returns the BeautifulSoup soup object of the page.
    """
    print(f"Attempting to fetch content from: {url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    page_soup = None

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        # Use utf-8 encoding as it's specified in the meta tag
        response.encoding = 'utf-8'
        print("Content fetched successfully.")
        page_soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return None

    if not page_soup:
        print("Soup object not created.")
        return None

    # --- Extract Chapter Title (Updated Selector) ---
    chapter_title_str = "Unknown Chapter Title" # Default
    try:
        h2_element = page_soup.find('h1', class_='gh-article-title is-title')
        if h2_element:
            extracted_title = h2_element.get_text(strip=True)
            if extracted_title:
                chapter_title_str = extracted_title
            else:
                print("  Warning: Found H2 title tag, but it contained no text.")
        else:
             print("  Warning: Could not find H2 tag with class 'mud-typography-h4' inside 'div.chapter-background'.")

        print(f"  Chapter Title: {chapter_title_str}")
    except Exception as e:
        print(f"  Error extracting chapter title: {e}")

    # --- Extract Main Content (Updated Selector and Logic) ---
    novel_text = ""
    try:
        # Find the specific div containing the chapter text
        content_element = page_soup.find('section', class_='gh-content gh-canvas is-body')

        if not content_element:
            print(f"Could not find the main content element ('div#chapter-text') for {url}.")
            novel_text = "[Main content element 'div#chapter-text' not found on page]"
        else:
            # Find all paragraph tags within the content div
            paragraphs = content_element.find_all('p')
            if not paragraphs:
                print(f"Found no paragraphs (<p>) in 'div#chapter-text' for {url}.")
                # Fallback: Get all text from the content div if no <p> tags found
                novel_text = content_element.get_text(separator='\n\n', strip=True)
                if not novel_text:
                     novel_text = "[No paragraph tags found, and content element has no direct text]"
                else:
                    print("  Warning: No <p> tags found, using all text from content div.")
            else:
                novel_text_parts = []
                # Iterate through ALL paragraphs, not skipping the first one anymore
                for p in paragraphs:
                    paragraph_text = p.get_text(separator=' ', strip=True)
                    # Optional: filter out empty paragraphs that might just contain <br>
                    if paragraph_text:
                        novel_text_parts.append(paragraph_text)
                novel_text = "\n\n".join(novel_text_parts)

    except Exception as e:
         print(f"  Error extracting main content: {e}")
         novel_text = f"[Error during content extraction: {e}]"


    if not novel_text.strip() and not novel_text.startswith("["): # Avoid overwriting error messages
        print(f"Failed to extract any text from paragraphs for {url}.")
        novel_text = "[No text extracted from paragraphs]"

    # --- Combine Title and Content, then Save ---
    final_text_to_save = f"{chapter_title_str}\n\n\n{novel_text.strip()}"

    try:
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_text_to_save)
        print(f"Novel text (with title) saved to: {output_filename}")
    except IOError as e:
        print(f"Could not write to file: {e}")

    return page_soup

# (The main crawler loop, updated start URL and next link selector)
if __name__ == "__main__":
    # --- Updated Start URL ---
    start_url = "https://www.celestial-pavilion.com/iatmcb-0/"
    current_url = start_url

    page_counter = 0

    # --- Define Output Directory ---
    output_dir = "scraped_IATMCB_celsetial_pavilion" # Changed directory name slightly
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    while current_url:
        page_counter += 1
        print(f"\n--- Processing page {page_counter}: {current_url} ---")

        # Sanitize URL slightly for filename (replace slashes, colons)
        # safe_part = current_url.split('/')[-1] or current_url.split('/')[-2] # Get last part of URL
        filename = os.path.join(output_dir, f"ch_{page_counter:03d}.txt") # Use chapter number in filename

        page_soup = scrape_novel_chapter(current_url, filename)

        if not page_soup:
            print(f"Failed to get page content for {current_url}. Stopping crawl.")
            break

        # --- Find Next Chapter Link (Updated Selector) ---
        next_url_to_visit = f"https://www.celestial-pavilion.com/iatmcb-{page_counter}/"

        current_url = next_url_to_visit

        if current_url:
            delay_seconds = 2 # Keep a polite delay
            print(f"Pausing for {delay_seconds} seconds before fetching next page...")
            time.sleep(delay_seconds)
        else:
            print("\n--- End of crawling ---")
