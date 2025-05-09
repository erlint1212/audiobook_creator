import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin # For constructing absolute URLs
import time                 # For adding delays

# This is your existing function, with a modification to return `soup` or `None`
def scrape_novel_chapter(url, output_filename="novel_chapter.txt"):
    """
    Scrapes the text from a single chapter of a web novel, saves it to a file,
    and returns the BeautifulSoup soup object of the page.

    Args:
        url (str): The URL of the chapter to scrape.
        output_filename (str): The name of the file the text should be saved in.

    Returns:
        BeautifulSoup object if successful, None otherwise.
    """
    print(f"Attempting to fetch content from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    page_soup = None # Initialize page_soup to None

    try:
        response = requests.get(url, headers=headers, timeout=15) # Increased timeout slightly
        response.raise_for_status()
        # Try to use apparent encoding for text, fallback to utf-8
        response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
        print("Content fetched successfully.")
        page_soup = BeautifulSoup(response.text, 'html.parser') # Use response.text after setting encoding
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return None # Return None if fetching fails

    # Ensure page_soup is available before proceeding
    if not page_soup:
        print("Soup object not created, cannot scrape.")
        return None

    content_element = page_soup.find('div', class_='prose-inner')

    if not content_element:
        content_element = page_soup.find('article') 
        if not content_element:
            print("Could not find the main content element ('div.prose-inner' or 'article').")
            return page_soup # Return soup anyway, maybe next link is still findable, or signals an issue
    
    paragraphs = content_element.find_all('p')
    
    if not paragraphs:
        print(f"Found no paragraphs (<p>) in the content element of {url}.")
        # Optional: If no <p> tags, you could try to get all text from content_element directly
        # novel_text = content_element.get_text(separator='\n\n', strip=True)
        # For now, we'll assume this means no primary text content to save in the usual format.
        # We still return the soup for next link finding.
        # Create an empty file or a file with a notice.
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(f"[No paragraph content found on {url}]")
            print(f"Notice file saved to: {output_filename}")
        except IOError as e:
            print(f"Could not write notice file: {e}")
        return page_soup 

    novel_text_parts = []
    # Your fix: Skip the first paragraph if it's consistently a header
    for p in paragraphs[1:]: 
        paragraph_text = p.get_text(separator=' ', strip=True)
        if paragraph_text:
            novel_text_parts.append(paragraph_text)
    
    # Simple fix: if the *last* paragraph from the original list (before slicing)
    # is the navigation link, we might want to remove it from our collected text if it got included.
    # The `paragraphs[1:]` already handles the header. If the footer is the very last p tag,
    # `paragraphs[1:]` will include it if it's not also the first tag.
    # For now, this simplified version will include the "Next => Index" if it's the last <p> tag.
    # This can be refined later if that text in the file is an issue.
    
    novel_text = "\n\n".join(novel_text_parts)

    if not novel_text.strip():
        print(f"Failed to extract any text from paragraphs for {url}.")
        # Create an empty file or a file with a notice.
        try:
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(f"[No text extracted from paragraphs on {url}]")
            print(f"Notice file saved to: {output_filename}")
        except IOError as e:
            print(f"Could not write notice file: {e}")
        return page_soup # Still return soup

    try:
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(novel_text)
        print(f"Novel text saved to: {output_filename}")
    except IOError as e:
        print(f"Could not write to file: {e}")
    
    return page_soup # Crucial: return the soup object

if __name__ == "__main__":
    # Initial URL for the first page to scrape (e.g., prologue or chapter 1)
    start_url = "https://re-library.com/translations/tileas-worries/volume-1/prologue/"
    current_url = start_url
    
    page_counter = 0 # To number the output files sequentially
    
    # Directory to save the novel chapters
    output_dir = "scraped_tileas_worries"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    while current_url:
        page_counter += 1
        print(f"\n--- Processing page {page_counter}: {current_url} ---")
        
        # Generate a filename for the current chapter
        # Using a simple numbered scheme for reliability.
        # You can create more descriptive names based on URL slugs if desired.
        # Example slug: current_url.strip('/').split('/')[-1].replace('#content', '')
        filename = os.path.join(output_dir, f"page_{page_counter:03d}.txt")
        
        # Scrape the current chapter and get the soup object for the page
        page_soup = scrape_novel_chapter(current_url, filename)

        if not page_soup:
            print(f"Failed to get page content for {current_url}. Stopping crawl.")
            break

        # Find the "Next" link: <div class="nextPageLink PageLink"><a href="..." ...>Next ⇒</a></div>
        # To find a div that has BOTH classes, we can use a CSS selector or string search for class attribute.
        # Using find with the exact string value for the class attribute:
        next_link_div = page_soup.find('div', class_="nextPageLink PageLink")
        
        # Alternative using CSS selector (often more robust for multiple classes):
        # next_link_div = page_soup.select_one('div.nextPageLink.PageLink')

        next_url_to_visit = None # Reset for this iteration
        if next_link_div:
            a_tag = next_link_div.find('a', href=True) # Find 'a' tag with an 'href' attribute
            if a_tag:
                next_href = a_tag['href']
                # Construct full URL (handles relative paths like "/translations/...")
                potential_next_url = urljoin(current_url, next_href)
                
                # Check if the new URL is genuinely different from the current one (ignoring fragments)
                base_current_url = current_url.split('#')[0]
                base_potential_next_url = potential_next_url.split('#')[0]

                if base_potential_next_url != base_current_url and potential_next_url != start_url : # also check if it's not looping back to start_url immediately for some reason
                    next_url_to_visit = potential_next_url
                    print(f"Found next chapter link: {next_url_to_visit}")
                else:
                    print(f"Next link found ({potential_next_url}) but it seems to be the same page or leads back to start. Stopping.")
            else:
                print("Found 'nextPageLink PageLink' div, but no valid 'a' tag with href inside.")
        else:
            print("No 'nextPageLink PageLink' div found. Presumed end of chapters.")

        current_url = next_url_to_visit # Update current_url for the next loop iteration

        if current_url:
            # Be polite to the server: add a small delay between requests
            delay_seconds = 2
            print(f"Pausing for {delay_seconds} seconds before fetching next page...")
            time.sleep(delay_seconds)
        else:
            print("\n--- End of crawling ---")
