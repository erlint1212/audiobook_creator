import requests
from bs4 import BeautifulSoup
import os # Used for robustly handling file paths

def scrape_novel_chapter(url, output_filename="novel_chapter.txt"):
    """
    Scrapes the text from a single chapter of a web novel and saves it to a file.

    Args:
        url (str): The URL of the chapter to scrape.
        output_filename (str): The name of the file to save the text to.
    """
    print(f"Attempting to fetch content from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    } # Some websites block requests without a valid User-Agent

    try:
        response = requests.get(url, headers=headers, timeout=10) # Timeout after 10 seconds
        response.raise_for_status() # Checks for HTTP errors (e.g., 404, 500)
        print("Content fetched successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # --- IMPORTANT: Identifying the correct content element ---
    # You need to inspect the HTML source of the webpage to find the exact tag
    # and class (or ID) that contains the novel text.
    #
    # How to do it:
    # 1. Open the URL in your web browser (e.g., Chrome, Firefox).
    # 2. Right-click on the text you want to extract.
    # 3. Select "Inspect" or "Inspect Element".
    # 4. Look for an enclosing element (often a <div> or <article>)
    #    that seems to contain all the novel text. Note its tag (e.g., 'div')
    #    and its 'class' or 'id' attribute.
    #
    # Example: If the text is in <div class="entry-content">
    # content_element = soup.find('div', class_='entry-content')
    #
    # For re-library.com, after a quick look (this might change),
    # the content might be inside a div with a class like 'prose-inner' or similar,
    # or the paragraphs might be directly under a specific main div.
    #
    # Based on the specific URL https://re-library.com/translations/tileas-worries/volume-1/prologue/
    # it appears the content is within <div class="prose-inner">
    content_element = soup.find('div', class_='prose-inner')

    if not content_element:
        # Fallback: Sometimes it's an <article> tag
        content_element = soup.find('article') 
        if not content_element:
            print("Could not find the main content element. Check the HTML structure and update the script.")
            # You can print parts of the soup here for debugging, e.g.:
            # print(soup.prettify()[:2000]) # Prints the first 2000 characters of the HTML
            return

    # Extract all text from <p> (paragraph) tags within the content_element
    paragraphs = content_element.find_all('p')
    
    if not paragraphs:
        print("Found no paragraphs (<p>) in the identified content element.")
        # If the text is not in <p> tags, you'll need to identify which tags it is in.
        # Perhaps all text is directly in content_element?
        # novel_text = content_element.get_text(separator='\n\n', strip=True)
        return

    novel_text = ""
    for p in paragraphs[1:]:
        # .get_text() extracts all text from a tag and its children
        # 'separator' adds a space between text pieces if there are e.g. <br> tags inside <p>
        # 'strip=True' removes unnecessary whitespace from the start and end
        paragraph_text = p.get_text(separator=' ', strip=True)
        if paragraph_text: # Only add if there's actual text
            novel_text += paragraph_text + "\n\n" # Add two newlines for readability

    if not novel_text.strip():
        print("Failed to extract any text. Check the selectors for the content element and paragraphs.")
        return

    # Save the text to a file
    try:
        # Ensure the directory for the output file exists (if output_filename includes directories)
        output_filename = f"chapters/{output_filename}"
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(novel_text)
        print(f"Novel text saved to: {output_filename}")
    except IOError as e:
        print(f"Could not write to file: {e}")

# --- How to use the script ---
if __name__ == "__main__":
    target_url = "https://re-library.com/translations/tileas-worries/volume-1/prologue/"
    # You can change the filename or add a path, e.g., "output/tileas_prologue.txt"
    file_name = "tileas_worries_prologue.txt" 
    scrape_novel_chapter(target_url, file_name)

    # To scrape another chapter, change target_url and file_name:
    # target_url_ch1 = "URL_TO_CHAPTER_1"
    # file_name_ch1 = "tileas_worries_chapter1.txt"
    # scrape_novel_chapter(target_url_ch1, file_name_ch1)
