import os
import re
import json
import uuid
import html
from ebooklib import epub

def create_xhtml_chapter(chapter_title, text_content, chapter_file_name_base):
    """
    Converts plain text content to a simple XHTML chapter object.
    """
    file_name = f"{chapter_file_name_base}.xhtml"
    chapter = epub.EpubHtml(title=chapter_title, file_name=file_name, lang='en')

    # Create HTML content
    escaped_title = html.escape(chapter_title)
    xhtml_content_parts = [f"<h1>{escaped_title}</h1>"]
    
    # Split by blank lines to form paragraphs
    paragraphs = re.split(r'\n\s*\n+', text_content.strip())
    
    for para_text in paragraphs:
        cleaned_para = para_text.strip()
        if cleaned_para: 
            escaped_para = html.escape(cleaned_para)
            escaped_para = escaped_para.replace('\r\n', '<br />\n').replace('\n', '<br />\n')
            xhtml_content_parts.append(f"<p>{escaped_para}</p>")
            
    chapter.content = "\n".join(xhtml_content_parts)
    return chapter

def create_epub_from_txt_directory(input_directory, 
                                   json_metadata_path, 
                                   output_epub_name, 
                                   book_title_meta, 
                                   book_author_meta, 
                                   book_language_meta='en',
                                   book_uid_meta=None,
                                   cover_image_path=None):
    
    if not os.path.isdir(input_directory):
        print(f"Error: Input directory '{input_directory}' not found.")
        return

    # --- 1. Load Order from JSON ---
    # Using the JSON allows us to follow the "Next" link sequence correctly
    chapter_order = []
    if os.path.exists(json_metadata_path):
        try:
            with open(json_metadata_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Filter to only include chapters that actually have a saved file
                chapter_order = [entry for entry in data if entry.get('file')]
            print(f"Loaded sequence for {len(chapter_order)} chapters from JSON.")
        except Exception as e:
            print(f"Warning: Could not load JSON: {e}. Falling back to filename sort.")
    
    # Fallback if JSON is missing or empty
    if not chapter_order:
        txt_files = sorted([f for f in os.listdir(input_directory) if f.lower().endswith('.txt')])
        chapter_order = [{'file': f} for f in txt_files]

    # --- 2. Setup EPUB ---
    book = epub.EpubBook()
    if book_uid_meta is None: book_uid_meta = str(uuid.uuid4())
    book.set_identifier(book_uid_meta)
    book.set_title(book_title_meta)
    book.set_language(book_language_meta)
    book.add_author(book_author_meta)

    # Handle Cover
    if cover_image_path and os.path.exists(cover_image_path):
        img_ext = os.path.splitext(cover_image_path)[1].lower()
        with open(cover_image_path, 'rb') as f:
            book.set_cover(f"cover{img_ext}", f.read())

    # --- 3. Process Chapters ---
    epub_chapters = []
    toc_links = []      

    for i, entry in enumerate(chapter_order):
        txt_filename = entry['file']
        txt_filepath = os.path.join(input_directory, txt_filename)
        
        if not os.path.exists(txt_filepath):
            print(f"  Skipping missing file: {txt_filename}")
            continue

        # Read file: First line is the Title, rest is Body
        with open(txt_filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if not lines: continue
            
            # Line 1: "Chapter 1 - The Fairy of the Martial World"
            final_title = lines[0].strip() 
            body_content = "".join(lines[1:]).strip() 

        print(f"  Adding: {final_title}")
        
        # Create XHTML Chapter Object
        chapter_obj = create_xhtml_chapter(final_title, body_content, f"chapter_{i+1:04d}")
        book.add_item(chapter_obj)
        epub_chapters.append(chapter_obj)
        toc_links.append(epub.Link(chapter_obj.file_name, final_title, f"chapter_{i+1:04d}"))

    # --- 4. Finalize ---
    book.toc = tuple(toc_links) 
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    # High-Readability CSS
    css = '''
    body { margin: 5%; font-size: 1.1em; line-height: 1.6; }
    h1 { text-align: center; margin-top: 2em; margin-bottom: 1em; font-weight: bold; }
    p { text-indent: 1.5em; margin-bottom: 0.5em; text-align: justify; }
    '''
    
    style_item = epub.EpubItem(uid="style_default", file_name="style/default.css", media_type="text/css", content=css)
    book.add_item(style_item)
    book.spine = ['nav'] + epub_chapters
    for ch in epub_chapters: ch.add_item(style_item)

    epub.write_epub(output_epub_name, book, {})
    print(f"\nSuccess! Created: {output_epub_name}")

if __name__ == "__main__":
    # --- CONFIGURATION ---
    input_dir = "BlleatTL_Novels" # Matches your latest scraper folder
    json_path = os.path.join(input_dir, "chapters.json") 
    epub_file = "MistakenForAFairy.epub"
    
    create_epub_from_txt_directory(
        input_directory=input_dir,
        json_metadata_path=json_path,
        output_epub_name=epub_file,
        book_title_meta="Mistaken for a Fairy",
        book_author_meta="햇빤" # Set your preferred author name
    )
