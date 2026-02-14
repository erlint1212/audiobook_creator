import json
import os
import shutil

import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
# The URL of the main page (Novel Info / Table of Contents)
NOVEL_INDEX_URL = "https://www.blleattl.site/story/fairy/"
# ---------------------


def fetch_and_save_metadata(index_url, project_dir):
    print(f"--- Fetching Metadata from: {index_url} ---")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    try:
        response = requests.get(index_url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # --- 1. Extract Metadata using OpenGraph (Most Reliable) ---
        metadata = {
            "title": "Unknown Title",
            "author": "Unknown Author",
            "cover_url": None,
            "description": "",
        }

        # Title
        og_title = soup.find("meta", property="og:title")
        if og_title:
            metadata["title"] = og_title["content"].strip()
        else:
            # Fallback to standard H1
            h1 = soup.find("h1")
            if h1:
                metadata["title"] = h1.get_text(strip=True)

        # Cover Image
        og_image = soup.find("meta", property="og:image")
        if og_image:
            metadata["cover_url"] = og_image["content"]

        # Author (Site specific fallback)
        # Try to find common "Author" labels
        author_el = soup.find(string=lambda t: t and "Author" in t)
        if author_el:
            # Often extracting parent text helps, e.g. <div>Author: Name</div>
            parent_text = author_el.find_parent().get_text(strip=True)
            # Simple cleanup: remove "Author" and colons
            metadata["author"] = (
                parent_text.replace("Author", "").replace(":", "").strip()
            )

        # Description
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            metadata["description"] = og_desc["content"].strip()

        print(
            f"Found Metadata:\n Title: {metadata['title']}\n Author: {metadata['author']}\n Cover: {metadata['cover_url']}"
        )

        # --- 2. Download Cover Image ---
        cover_filename = None
        if metadata["cover_url"]:
            try:
                # Resolve relative URLs if necessary
                if not metadata["cover_url"].startswith("http"):
                    from urllib.parse import urljoin

                    metadata["cover_url"] = urljoin(index_url, metadata["cover_url"])

                print(f"Downloading cover image...")
                img_resp = requests.get(
                    metadata["cover_url"], headers=headers, stream=True
                )
                if img_resp.status_code == 200:
                    ext = os.path.splitext(metadata["cover_url"])[1].split("?")[
                        0
                    ]  # Get .jpg/.png
                    if not ext:
                        ext = ".jpg"

                    cover_filename = f"cover{ext}"
                    cover_path = os.path.join(project_dir, cover_filename)

                    with open(cover_path, "wb") as f:
                        shutil.copyfileobj(img_resp.raw, f)

                    print(f"Cover saved to: {cover_path}")
                    metadata["local_cover_path"] = cover_filename
            except Exception as e:
                print(f"Failed to download cover: {e}")

        # --- 3. Save to JSON ---
        json_path = os.path.join(project_dir, "project_metadata.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=4)

        print(f"--- Success! Metadata saved to {json_path} ---")

    except Exception as e:
        print(f"Error fetching metadata: {e}")


if __name__ == "__main__":
    # Determine base directory dynamically
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # We save metadata in the Project Root (BASE_DIR), not the text folder
    fetch_and_save_metadata(NOVEL_INDEX_URL, BASE_DIR)
