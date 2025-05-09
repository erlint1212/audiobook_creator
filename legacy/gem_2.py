import requests
from bs4 import BeautifulSoup
import os

def scrape_novel_chapter(url, output_filename="novel_chapter.txt"):
    """
    Scrapes the text from a single chapter of a web novel, cleans it,
    and saves it to a file.

    Args:
        url (str): The URL of the chapter to scrape.
        output_filename (str): The name of the file to save the text to.
    """
    print(f"Attempting to fetch content from: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        print("Content fetched successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Could not fetch the URL: {e}")
        return

    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the main content element
    # Based on previous findings, 'div.prose-inner' is a good candidate for re-library.com
    content_element = soup.find('div', class_='prose-inner')

    if not content_element:
        # Fallback if 'prose-inner' is not found
        content_element = soup.find('article') 
        if not content_element:
            print("Could not find the main content element ('div.prose-inner' or 'article'). Please inspect the page and update the selector.")
            return
    
    # --- 1. Decompose known non-story wrapper DIVs ---
    # These are common class names for plugins. You might need to inspect the specific
    # page to find the exact classes for sharing buttons, like buttons, or related posts if they are included.
    selectors_to_decompose = [
        'div.sharedaddy',           # Common class for WordPress sharing plugins
        'div.sd-sharing',           # Another common sharing class
        'div.wpulike',              # Common class for "Like" plugins (WP ULike)
        'div.wp_ulike_div',         # Another class for WP ULike
        'div.jp-relatedposts',      # Jetpack related posts section
        'div#jp-post-flair',        # Jetpack flair, often contains sharing buttons
        # Add other selectors for distinct blocks you want to remove entirely
        # Example: if "Leave a comment" is wrapped in its own div like <div class="comments-link">
    ]

    print("Attempting to remove known non-story blocks...")
    for selector in selectors_to_decompose:
        # This basic parsing handles "tag.class", "tag#id", ".class", "#id"
        # For more complex CSS selectors, BeautifulSoup's select() method is more powerful.
        tag_name = None
        attrs = {}
        
        if '#' in selector:
            parts = selector.split('#', 1)
            tag_name = parts[0] if parts[0] else None
            attrs['id'] = parts[1]
        elif '.' in selector:
            parts = selector.split('.', 1)
            tag_name = parts[0] if parts[0] else None
            attrs['class_'] = parts[1]
        else: # Assumed to be a tag name
            tag_name = selector
            
        elements_to_remove = content_element.find_all(tag_name, **attrs)
        for el in elements_to_remove:
            print(f"  Removing element: <{el.name} id='{el.get('id', '')}' class='{' '.join(el.get('class', []))}'>")
            el.decompose() # Removes the element from the tree

    # --- 2. Extract and filter paragraphs ---
    # Get all <p> tags that are likely story content.
    # Using recursive=True to find all <p> tags within content_element.
    # If you only want direct children <p> tags, set recursive=False.
    paragraphs = content_element.find_all('p', recursive=True)
    
    if not paragraphs:
        print("No <p> tags found in the content element after decomposition. Trying to get all text directly.")
        # Fallback: get all text from content_element. This might need further string cleaning.
        novel_text = content_element.get_text(separator='\n\n', strip=True)
        # Manual string cleaning could be added here if this fallback is used
    else:
        story_text_parts = []
        
        # Keywords/phrases that indicate a paragraph is NOT part of the story
        # Order matters for some checks (e.g., checking for specific long headers first)
        unwanted_paragraph_content = [
            "Leave a comment Next ⇒ ⌈ Index ⌋ Author :", # Very specific header
            "Author :", "Translator :", "Editor(s) :", "Original Source :", # Individual meta items
            "Share this:", "Click to share on Facebook (Opens in new window)", # Sharing prompts
            "Like this:", "Loading...", # Like button text
            "Next ⇒ ⌈ Index ⌋" # Common navigation link text
        ]

        for i, p_tag in enumerate(paragraphs):
            p_text = p_tag.get_text(strip=True)

            if not p_text: # Skip empty paragraphs
                continue

            is_unwanted = False
            
            # Check if the paragraph is the specific long header string
            if "Leave a comment" in p_text and "Author :" in p_text and "Editor(s) :" in p_text:
                is_unwanted = True
            # Check for other unwanted content patterns
            else:
                for unwanted_pattern in unwanted_paragraph_content:
                    if unwanted_pattern in p_text:
                        # Make it more robust: if it's short and contains the pattern, it's more likely unwanted.
                        # Or if the pattern is quite unique to utility text.
                        if len(p_text) < 150 or unwanted_pattern == "Click to share on Facebook (Opens in new window)":
                            is_unwanted = True
                            break
            
            if is_unwanted:
                print(f"  Skipping paragraph: \"{p_text[:70]}...\"")
            else:
                story_text_parts.append(p_text)
        
        # Re-check the very first and last collected paragraphs if they are simple nav links
        if story_text_parts:
            if "Next ⇒" in story_text_parts[0] and "Index" in story_text_parts[0] and len(story_text_parts[0]) < 50:
                print(f"  Removing detected leading navigation: \"{story_text_parts.pop(0)[:70]}...\"")
        if story_text_parts: # Check again in case list became empty
            if "Next ⇒" in story_text_parts[-1] and "Index" in story_text_parts[-1] and len(story_text_parts[-1]) < 50:
                 print(f"  Removing detected trailing navigation: \"{story_text_parts.pop(-1)[:70]}...\"")


        if not story_text_parts:
            print("After filtering, no story paragraphs remained. The original content might have been all filtered out.")
            novel_text = "Error: No content found after filtering. Please check scraper logic."
        else:
            novel_text = "\n\n".join(story_text_parts)

    # Save the cleaned text
    try:
        output_dir = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir): # Create directory if it doesn't exist
            os.makedirs(output_dir)
            
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(novel_text)
        print(f"Cleaned novel text saved to: {output_filename}")
    except IOError as e:
        print(f"Could not write to file: {e}")

# --- How to use the script ---
if __name__ == "__main__":
    target_url = "https://re-library.com/translations/tileas-worries/volume-1/prologue/"
    # Using a new filename to avoid overwriting previous attempts immediately
    file_name = "tileas_worries_prologue_cleaned.txt" 
    
    scrape_novel_chapter(target_url, file_name)
