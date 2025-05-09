import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import time

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
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8' # sfacg.com uses UTF-8
        print("Content fetched successfully.")
        page_soup = BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return None

    if not page_soup:
        print("Soup object not created.")
        return None

    # --- Extract Chapter Title ---
    chapter_title_str = "Unknown Chapter Title" # Default value
    try:
        title_element = page_soup.find('h1', class_='article-title')
        if title_element:
            chapter_title_str = title_element.get_text(strip=True)
        else:
            print("  Warning: Could not find chapter title element with class 'article-title'. Using default title.")
        
        print(f"  Chapter Title: {chapter_title_str}")
    except Exception as e:
        print(f"  Error extracting chapter title: {e}")

    # --- Extract Main Content ---
    novel_text = "" 
    try:
        content_element = page_soup.find('div', id='ChapterBody')

        if not content_element:
            print("Could not find the main content element with id 'ChapterBody'.")
            novel_text = "[Main content element not found on page]"
        else:
            paragraphs = content_element.find_all('p')
            if not paragraphs:
                print(f"Found no paragraphs (<p>) in the content element of {url}.")
                novel_text = content_element.get_text(separator='\n\n', strip=True) # Fallback
                if not novel_text.strip():
                     novel_text = "[No text found in content element, even without <p> tags]"
            else:
                novel_text_parts = [p.get_text(separator=' ', strip=True) for p in paragraphs if p.get_text(strip=True)]
                novel_text = "\n\n".join(novel_text_parts)
    except Exception as e:
        print(f"  Error extracting chapter text: {e}")
        novel_text = "[Error extracting chapter text]"

    if not novel_text.strip() and not novel_text.startswith("["):
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

if __name__ == "__main__":
    start_url = "https://book.sfacg.com/Novel/680378/894591/8176590/" 
    current_url = start_url
    
    page_counter = 0 
    
    output_dir = "scraped_sfacg_novel" 
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    while current_url:
        page_counter += 1
        print(f"\n--- Processing page {page_counter}: {current_url} ---")
        
        filename = os.path.join(output_dir, f"chapter_{page_counter:03d}.txt")
        
        page_soup = scrape_novel_chapter(current_url, filename)

        if not page_soup:
            print(f"Failed to get page content for {current_url}. Stopping crawl.")
            break

        # Find the link to the next chapter based on the provided HTML structure
        # It's an <a> tag with text "下一章" and classes "btn" and "normal"
        next_link_element = page_soup.find('a', string='下一章', class_='btn normal')
        
        # A more robust way could be to locate the specific "fn-btn" div first, if necessary:
        # nav_buttons_div = page_soup.find('div', class_='fn-btn') # This might need refinement if multiple divs have this class
        # if nav_buttons_div:
        #    next_link_element = nav_buttons_div.find('a', string='下一章', class_='btn normal')
        # else:
        #    next_link_element = None
            
        next_url_to_visit = None 
        if next_link_element and next_link_element.get('href'):
            next_href = next_link_element['href']
            potential_next_url = urljoin(current_url, next_href) # Handles relative URLs correctly
            
            if potential_next_url != current_url and next_href not in ["#", "javascript:void(0);", ""]:
                # Ensure the link is for a novel chapter on the same site
                if "book.sfacg.com/Novel/" in potential_next_url or next_href.startswith("/Novel/"):
                    next_url_to_visit = potential_next_url
                    print(f"Found next chapter link: {next_url_to_visit}")
                else:
                    print(f"Potential next link ({potential_next_url}) does not seem to be a valid chapter link for this novel. Stopping.")
            else:
                print(f"Next link found ({potential_next_url}) but it appears to be the same page or invalid. Stopping.")
        else:
            print("No 'next chapter' link found with text '下一章' and class 'btn normal'. Presumed end of novel.")

        current_url = next_url_to_visit 

        if current_url:
            delay_seconds = 3 
            print(f"Pausing for {delay_seconds} seconds before fetching next page...")
            time.sleep(delay_seconds) 
        else:
            print("\n--- End of crawling ---")
