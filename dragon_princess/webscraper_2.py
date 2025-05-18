import requests
from bs4 import BeautifulSoup
import os
from urllib.parse import urljoin
import time
from typing import Optional, Tuple

def scrape_syosetu_chapter(url: str, output_filename: str = "novel_chapter.txt") -> Optional[BeautifulSoup]:
    """
    Scrapes the chapter title and text from a single Syosetu chapter, saves it to a file,
    and returns the BeautifulSoup soup object of the page.

    Args:
        url (str): The URL of the novel chapter to scrape.
        output_filename (str): The name of the file to save the chapter content to.

    Returns:
        Optional[BeautifulSoup]: The BeautifulSoup object of the page if successful, None otherwise.
    """
    print(f"Attempting to fetch content from: {url}")

    headers: dict[str, str] = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    page_soup: Optional[BeautifulSoup] = None

    try:
        response: requests.Response = requests.get(url, headers=headers, timeout=15)
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

    chapter_title_str: str = "Unknown Chapter Title"
    try:
        title_element: Optional[BeautifulSoup] = page_soup.find('h1', class_='p-novel__title')
        if title_element:
            chapter_title_str = title_element.get_text(strip=True)
        else:
            head_title_element: Optional[BeautifulSoup] = page_soup.find('title')
            if head_title_element:
                full_title: str = head_title_element.get_text(strip=True)
                parts: list[str] = full_title.split(' - ', 1)
                if len(parts) > 1:
                    chapter_title_str = parts[1]
                else:
                    chapter_title_str = full_title
                    print("  Warning: Could not find chapter title element with class 'p-novel__title'. Used <title> tag instead, but couldn't split series and chapter.")
            else:
                print("  Warning: Could not find chapter title element with class 'p-novel__title' or <title> tag in <head>. Using default title.")
        print(f"  Chapter Title: {chapter_title_str}")
    except Exception as e:
        print(f"  Error extracting chapter title: {e}")

    novel_text: str = ""
    try:
        content_element: Optional[BeautifulSoup] = page_soup.find('div', class_='js-novel-text')
        if not content_element:
            content_element = page_soup.find('div', id='novel_honbun')
            if not content_element:
                 content_element = page_soup.find('div', class_='p-novel__body')

        if not content_element:
            print(f"Could not find the main content element for {url}.")
            novel_text = "[Main content element not found on page]"
        else:
            paragraphs: list[BeautifulSoup] = content_element.find_all('p')
            if not paragraphs:
                print(f"Found no paragraphs (<p>) in the content element of {url}.")
                novel_text = content_element.get_text(separator='\n\n', strip=True)
                if not novel_text.strip():
                    novel_text = "[No text found in content element, even without <p> tags]"
            else:
                novel_text_parts: list[str] = [p.get_text(separator=' ', strip=True) for p in paragraphs if p.get_text(strip=True)]
                novel_text = "\n\n".join(novel_text_parts)
    except Exception as e:
        print(f"  Error extracting chapter text: {e}")
        novel_text = "[Error extracting chapter text]"

    if not novel_text.strip() and not novel_text.startswith("["):
        print(f"Failed to extract any text from paragraphs for {url}.")
        novel_text = "[No text extracted from paragraphs]"

    final_text_to_save: str = f"{chapter_title_str}\n\n\n{novel_text.strip()}"

    try:
        output_dir: str = os.path.dirname(output_filename)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        with open(output_filename, 'w', encoding='utf-8') as f:
            f.write(final_text_to_save)
        print(f"Novel text (with title) saved to: {output_filename}")
    except IOError as e:
        print(f"Could not write to file: {e}")
    return page_soup

def find_next_chapter_url(page_soup: BeautifulSoup, current_url: str) -> Optional[str]:
    """
    Finds the URL for the next chapter on a Syosetu page.

    Args:
        page_soup (BeautifulSoup): The parsed HTML of the current chapter page.
        current_url (str): The URL of the current chapter.

    Returns:
        Optional[str]: The URL of the next chapter if found, otherwise None.
    """
    next_link_element: Optional[BeautifulSoup] = page_soup.find('a', class_='c-pager__item--next')
    if next_link_element and next_link_element.get('href'):
        next_href: str = next_link_element['href']
        potential_next_url: str = urljoin(current_url, next_href)
        if potential_next_url != current_url and next_href not in ["#", "javascript:void(0);", ""]:
            if "/n" in potential_next_url and potential_next_url.count('/') >= 2 :
                return potential_next_url
            else:
                print(f"Potential next link ({potential_next_url}) does not seem to be a valid Syosetu chapter link. Stopping.")
        else:
            print(f"Next link found ({potential_next_url}) but it appears to be the same page or invalid. Stopping.")
    else:
        # This is the normal condition for the end of the novel (no "next" button)
        print("No 'next chapter' link found with class 'c-pager__item--next'. Presumed end of novel.")
    return None

if __name__ == "__main__":
    start_url: str = "https://ncode.syosetu.com/n9045bm/232/" # The chapter you provided
    current_url: Optional[str] = start_url
    page_counter: int = 0
    # max_chapters_to_scrape: int = 5 # Optional: uncomment to limit chapters per run for testing

    ncode: str = ""
    try:
        path_parts: list[str] = start_url.split('/')
        if len(path_parts) > 3 and path_parts[3].startswith('n'):
            ncode = path_parts[3]
    except Exception:
        pass

    output_folder_name: str = f"scraped_syosetu_{ncode}" if ncode else "scraped_syosetu_novel"
    if not os.path.exists(output_folder_name):
        os.makedirs(output_folder_name)
        print(f"Created directory: {output_folder_name}")

    # while current_url and page_counter < max_chapters_to_scrape: # Use this line if max_chapters_to_scrape is active
    while current_url: # Loop until no next URL is found
        page_counter += 1
        print(f"\n--- Processing chapter attempt {page_counter}: {current_url} ---")

        chapter_number_str: str = "unknown_chapter"
        try:
            url_parts: list[str] = current_url.strip('/').split('/')
            if url_parts[-1].isdigit():
                chapter_number_str = url_parts[-1]
        except Exception as e:
            print(f"Could not extract chapter number from URL {current_url}: {e}")

        filename_base: str = f"{ncode}_{chapter_number_str}.txt" if ncode else f"chapter_{page_counter:03d}.txt"
        output_path: str = os.path.join(output_folder_name, filename_base)

        page_soup_result: Optional[BeautifulSoup] = None

        if os.path.exists(output_path):
            print(f"Chapter file already exists: {output_path}. Skipping download.")
            # Need to fetch page to find next link even if skipping download
            try:
                print(f"Fetching page content for {current_url} to find next chapter link (even though skipping download).")
                headers: dict[str, str] = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response: requests.Response = requests.get(current_url, headers=headers, timeout=15)
                response.raise_for_status()
                response.encoding = response.apparent_encoding if response.apparent_encoding else 'utf-8'
                page_soup_result = BeautifulSoup(response.text, 'html.parser')
            except requests.exceptions.RequestException as e:
                print(f"Could not fetch {current_url} to find next link (even after skipping download): {e}")
                # Decide if you want to break here or try to continue if possible (e.g., if you have a list of URLs)
                # For now, we'll break as we rely on the current page for the next link.
                break
        else:
            page_soup_result = scrape_syosetu_chapter(current_url, output_path)

        if not page_soup_result:
            print(f"Failed to get page content for {current_url}. Stopping crawl.")
            break

        current_url = find_next_chapter_url(page_soup_result, current_url)

        if current_url:
            delay_seconds: int = 0.1
            print(f"Pausing for {delay_seconds} seconds before fetching next page...")
            time.sleep(delay_seconds)
        else:
            print("\n--- End of crawling (no next chapter found) ---")

    # if page_counter >= max_chapters_to_scrape: # Use this line if max_chapters_to_scrape is active
    #     print(f"\n--- Reached max chapters to scrape ({max_chapters_to_scrape}). Stopping. ---")
