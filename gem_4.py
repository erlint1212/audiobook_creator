import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin # <<< --- Ensure this import is present and uncommented
import time                 # <<< --- Ensure this import is present and uncommented

# This is an update to the scrape_novel_chapter function you are using
# (based on your version that skips the first paragraph with paragraphs[1:])
def scrape_novel_chapter(url, output_filename="novel_chapter.txt"):
    """
    Scrapes the chapter title and text from a single chapter, saves it to a file,
    and returns the BeautifulSoup soup object of the page.
    """
    print(f"Attempting to fetch content from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    page_soup = None

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
        print("Content fetched successfully.")
        page_soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return None

    if not page_soup:
        print("Soup object not created.")
        return None

    # --- Extract Chapter Title ---
    chapter_title_str = "Unknown Chapter Title" # Default
    try:
        header_element = page_soup.find('header', class_='entry-header')
        if header_element:
            h1_element = header_element.find('h1', class_='entry-title')
            if h1_element:
                temp_h1_soup = BeautifulSoup(str(h1_element), 'html.parser')
                temp_h1_tag = temp_h1_soup.find('h1') 

                if temp_h1_tag:
                    div_to_remove = temp_h1_tag.find('div', class_='code-block')
                    if div_to_remove:
                        div_to_remove.decompose() 
                    
                    extracted_title = temp_h1_tag.get_text(strip=True)
                    if extracted_title:
                        chapter_title_str = extracted_title
                    else: 
                        all_strings_original_h1 = list(h1_element.stripped_strings)
                        if len(all_strings_original_h1) > 1 and "tilea’s worries" in all_strings_original_h1[0].lower():
                            chapter_title_str = all_strings_original_h1[1] 
                        elif all_strings_original_h1: 
                            chapter_title_str = all_strings_original_h1[-1]
                else:
                    print("  Warning: Could not effectively parse the H1 tag for title extraction.")
        
        print(f"  Chapter Title: {chapter_title_str}")
    except Exception as e:
        print(f"  Error extracting chapter title: {e}")

    # --- Extract Main Content (your existing logic) ---
    content_element = page_soup.find('div', class_='prose-inner')
    novel_text = "" 

    if not content_element:
        content_element = page_soup.find('article') 
        if not content_element:
            print("Could not find the main content element ('div.prose-inner' or 'article').")
            novel_text = "[Main content element not found on page]"
    
    if content_element: 
        paragraphs = content_element.find_all('p')
        if not paragraphs:
            print(f"Found no paragraphs (<p>) in the content element of {url}.")
            novel_text = "[No paragraph content found in content element]"
        else:
            novel_text_parts = []
            for p in paragraphs[1:]: 
                paragraph_text = p.get_text(separator=' ', strip=True)
                if paragraph_text:
                    novel_text_parts.append(paragraph_text)
            novel_text = "\n\n".join(novel_text_parts)

    if not novel_text.strip() and "[No paragraph content found" not in novel_text and "[Main content element not found" not in novel_text:
        print(f"Failed to extract any text from paragraphs for {url}.")
        novel_text = "[No text extracted from paragraphs]"
        if content_element and not paragraphs : 
            novel_text = content_element.get_text(separator='\n\n', strip=True)
            print(f"  Fell back to full text of content_element for {url}")

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

# (The main crawler loop from your script)
if __name__ == "__main__":
    start_url = "https://re-library.com/translations/tileas-worries/volume-1/prologue/"
    current_url = start_url
    
    page_counter = 0 
    
    output_dir = "scraped_tileas_worries"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    while current_url:
        page_counter += 1
        print(f"\n--- Processing page {page_counter}: {current_url} ---")
        
        filename = os.path.join(output_dir, f"page_{page_counter:03d}.txt")
        
        page_soup = scrape_novel_chapter(current_url, filename)

        if not page_soup:
            print(f"Failed to get page content for {current_url}. Stopping crawl.")
            break

        next_link_div = page_soup.find('div', class_="nextPageLink PageLink")
        
        next_url_to_visit = None 
        if next_link_div:
            a_tag = next_link_div.find('a', href=True) 
            if a_tag:
                next_href = a_tag['href']
                # ---- This is where urljoin is called ----
                potential_next_url = urljoin(current_url, next_href) 
                
                base_current_url = current_url.split('#')[0]
                base_potential_next_url = potential_next_url.split('#')[0]

                # Updated check to prevent stopping if it's genuinely a new chapter even if it's the start URL (e.g. single page novel)
                # However, for multi-chapter, we want to avoid an immediate loop to start.
                # The original check: potential_next_url != start_url
                # If start_url is "prologue" and next is "chapter-1", this is fine.
                # If start_url is "chapter-1" and next is "chapter-2", also fine.
                # The main issue is if next_href is empty or points to the exact same page.
                if base_potential_next_url != base_current_url:
                    next_url_to_visit = potential_next_url
                    print(f"Found next chapter link: {next_url_to_visit}")
                # Added a check: what if the site links back to the first page from the last page?
                elif base_potential_next_url == start_url.split('#')[0] and page_counter > 1:
                     print(f"Next link found ({potential_next_url}) but it leads back to the start URL from a later page. Stopping.")
                     next_url_to_visit = None # Stop if it loops back to the very first page
                else:
                    print(f"Next link found ({potential_next_url}) but it appears to be the same page. Stopping.")
                    next_url_to_visit = None # Stop if it's the same page
            else:
                print("Found 'nextPageLink PageLink' div, but no valid 'a' tag with href inside.")
        else:
            print("No 'nextPageLink PageLink' div found. Presumed end of chapters.")

        current_url = next_url_to_visit 

        if current_url:
            delay_seconds = 2
            print(f"Pausing for {delay_seconds} seconds before fetching next page...")
            # ---- This is where time.sleep is called ----
            time.sleep(delay_seconds) 
        else:
            print("\n--- End of crawling ---")
