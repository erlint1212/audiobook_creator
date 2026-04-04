import html
import json
import os
import re
import sys
import uuid

from ebooklib import epub

# --- Annotation Pattern ---
# Matches: text^[explanation text here]
# Group 1 = the explanation content inside brackets
ANNOTATION_PATTERN = re.compile(r"\^\[([^\]]+)\]")


def process_annotations(text, chapter_id, footnote_counter_start=1):
    """
    Finds all ^[explanation] markers in text and converts them to EPUB3 footnotes.

    Returns:
        - processed_html: The text with footnote reference links replacing ^[...] markers
        - footnotes_html: HTML block of <aside> footnotes to append at chapter end
        - footnote_count: How many footnotes were created (for numbering across paragraphs)
    """
    footnotes = []
    counter = footnote_counter_start

    def replace_annotation(match):
        nonlocal counter
        note_id = f"{chapter_id}_note_{counter}"
        explanation = html.escape(match.group(1))

        # Superscript reference link (epub:type="noteref" triggers popup in readers)
        ref_html = (
            f'<a epub:type="noteref" href="#{note_id}" id="{note_id}_ref"'
            f' role="doc-noteref"><sup>[{counter}]</sup></a>'
        )

        # The footnote aside block
        footnote_html = (
            f'<aside epub:type="footnote" id="{note_id}" role="doc-footnote">\n'
            f'  <p><a href="#{note_id}_ref">[{counter}]</a> {explanation}</p>\n'
            f"</aside>"
        )
        footnotes.append(footnote_html)
        counter += 1
        return ref_html

    processed_text = ANNOTATION_PATTERN.sub(replace_annotation, text)
    footnotes_html = "\n".join(footnotes)
    return processed_text, footnotes_html, counter


def create_xhtml_chapter(chapter_title, text_content, chapter_file_name_base):
    """
    Converts plain text content to a simple XHTML chapter object.
    Processes ^[annotation] markers into EPUB3 popup footnotes.
    """
    file_name = f"{chapter_file_name_base}.xhtml"
    chapter = epub.EpubHtml(title=chapter_title, file_name=file_name, lang="en")

    # We need the EPUB3 namespace for epub:type attributes
    chapter.properties = []

    # Create HTML content
    escaped_title = html.escape(chapter_title)
    xhtml_content_parts = [f"<h1>{escaped_title}</h1>"]

    # Split by blank lines to form paragraphs
    paragraphs = re.split(r"\n\s*\n+", text_content.strip())

    all_footnotes = []
    footnote_counter = 1
    chapter_id = chapter_file_name_base  # e.g., "chapter_0001"

    for para_text in paragraphs:
        cleaned_para = para_text.strip()
        if not cleaned_para:
            continue

        # First: extract annotations BEFORE html-escaping the main text,
        # because annotations contain special chars we need to handle carefully.
        # Strategy: find annotations, replace with placeholders, escape, restore.
        annotations_found = []
        placeholder_map = {}

        def extract_and_placeholder(match):
            placeholder = f"__ANNOT_{len(annotations_found)}__"
            annotations_found.append(match.group(0))  # full ^[...] match
            placeholder_map[placeholder] = match.group(0)
            return placeholder

        para_with_placeholders = ANNOTATION_PATTERN.sub(
            extract_and_placeholder, cleaned_para
        )

        # Now HTML-escape the main text (placeholders are safe ASCII)
        escaped_para = html.escape(para_with_placeholders)

        # Preserve internal line breaks
        escaped_para = escaped_para.replace("\r\n", "<br />\n").replace(
            "\n", "<br />\n"
        )

        # Restore annotation markers so we can process them into footnote HTML
        for placeholder, original in placeholder_map.items():
            escaped_para = escaped_para.replace(placeholder, original)

        # Now convert ^[...] to footnote references
        processed_para, footnotes_html, footnote_counter = process_annotations(
            escaped_para, chapter_id, footnote_counter
        )

        xhtml_content_parts.append(f"<p>{processed_para}</p>")
        if footnotes_html:
            all_footnotes.append(footnotes_html)

    # Append footnotes section at the end of the chapter
    if all_footnotes:
        xhtml_content_parts.append('<hr class="footnote-separator" />')
        xhtml_content_parts.append('<section class="footnotes" epub:type="footnotes">')
        xhtml_content_parts.extend(all_footnotes)
        xhtml_content_parts.append("</section>")

    # Build final XHTML with proper namespace
    body_content = "\n".join(xhtml_content_parts)
    full_xhtml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml"'
        ' xmlns:epub="http://www.idpf.org/2007/ops">\n'
        "<head>\n"
        f"  <title>{escaped_title}</title>\n"
        '  <link rel="stylesheet" type="text/css" href="style/default.css" />\n'
        "</head>\n"
        "<body>\n"
        f"{body_content}\n"
        "</body>\n"
        "</html>"
    )

    chapter.content = full_xhtml.encode("utf-8")
    # Mark as having the full XHTML (ebooklib won't wrap it again)
    chapter.is_chapter = True

    return chapter


def create_epub_project():
    # --- CRITICAL FIX FOR WINDOWS UNICODE ERROR ---
    # Forces the console output to use UTF-8 instead of the default Windows cp1252
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    print("--- Starting EPUB Creation ---")

    # --- 1. Setup Paths ---
    # The GUI passes 'EPUB_INPUT_DIR' (e.g., Novels/MyBook/01_Raw_Text)
    # The GUI passes 'EPUB_OUTPUT_FILE' (e.g., Novels/MyBook/MyBook.epub)

    TEXT_INPUT_DIR = os.getenv("EPUB_INPUT_DIR")
    OUTPUT_FILE = os.getenv("EPUB_OUTPUT_FILE")

    # Standalone fallback (for testing without GUI)
    if not TEXT_INPUT_DIR:
        print("Warning: Running standalone. Using default relative paths.")
        TEXT_INPUT_DIR = "BlleatTL_Novels"
        OUTPUT_FILE = "Output.epub"

    if not os.path.exists(TEXT_INPUT_DIR):
        print(f"Error: Input directory not found: {TEXT_INPUT_DIR}")
        return

    # Determine Project Root (One level up from text dir)
    # If text dir is ".../Novels/Title/01_Raw_Text", root is ".../Novels/Title"
    PROJECT_ROOT = os.path.dirname(os.path.abspath(TEXT_INPUT_DIR))

    METADATA_JSON = os.path.join(PROJECT_ROOT, "metadata.json")
    COVER_IMAGE = os.path.join(PROJECT_ROOT, "cover.jpg")
    CHAPTERS_JSON = os.path.join(TEXT_INPUT_DIR, "chapters.json")

    # --- 2. Load Metadata ---
    # Default values
    book_meta = {
        "title": os.getenv("EPUB_TITLE", "Unknown Title"),
        "author": "Unknown Author",
        "description": "Generated by Auto-Audiobook Pipeline",
    }

    # Override with metadata.json if exists
    if os.path.exists(METADATA_JSON):
        print(f"Loading metadata from: {METADATA_JSON}")
        try:
            with open(METADATA_JSON, "r", encoding="utf-8") as f:
                loaded_meta = json.load(f)
                # Only update keys that contain data
                if loaded_meta.get("title"):
                    book_meta["title"] = loaded_meta["title"]
                if loaded_meta.get("author"):
                    book_meta["author"] = loaded_meta["author"]
                if loaded_meta.get("description"):
                    book_meta["description"] = loaded_meta["description"]
        except Exception as e:
            print(f"Warning: Failed to parse metadata.json: {e}")

    # Safe Print to avoid crash if reconfigure fails for some reason
    try:
        print(f"Book Title: {book_meta['title']}")
        print(f"Book Author: {book_meta['author']}")
    except UnicodeEncodeError:
        print(f"Book Author: [Complex Characters Hidden]")

    # --- 3. Setup EPUB Book Object ---
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(book_meta["title"])
    book.set_language("en")
    book.add_author(book_meta["author"])

    if book_meta["description"]:
        book.add_metadata("DC", "description", book_meta["description"])

    # Handle Cover
    if os.path.exists(COVER_IMAGE):
        try:
            with open(COVER_IMAGE, "rb") as f:
                book.set_cover("cover.jpg", f.read())
            print(f"Attached cover image: {COVER_IMAGE}")
        except Exception as e:
            print(f"Error attaching cover: {e}")
    else:
        print("No cover.jpg found in project root.")

    # --- 4. Load Chapter Order ---
    chapter_entries = []

    # Try loading strictly ordered list from scraper
    if os.path.exists(CHAPTERS_JSON):
        try:
            with open(CHAPTERS_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                chapter_entries = [entry for entry in data if entry.get("file")]
            print(f"Loaded order from chapters.json ({len(chapter_entries)} chapters)")
        except Exception as e:
            print(f"Error loading chapters.json: {e}")

    # Fallback: Alphabetical sort of text files
    if not chapter_entries:
        print("Falling back to alphabetical file sort.")
        txt_files = sorted(
            [f for f in os.listdir(TEXT_INPUT_DIR) if f.lower().endswith(".txt")]
        )
        chapter_entries = [{"file": f} for f in txt_files]

    if not chapter_entries:
        print("No .txt files found to compile.")
        return

    # --- 5. Process Chapters ---
    epub_chapters = []
    toc_links = []
    total_annotations = 0

    print(f"Processing text files...")
    for i, entry in enumerate(chapter_entries):
        txt_filename = entry["file"]
        txt_filepath = os.path.join(TEXT_INPUT_DIR, txt_filename)

        if not os.path.exists(txt_filepath):
            print(f"  [Skipped] Missing file: {txt_filename}")
            continue

        try:
            with open(txt_filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
                if not lines:
                    continue

                # Heuristic: The first line is often the Title (saved by scraper)
                # If the first line is very short, treat it as title. Otherwise default.
                first_line = lines[0].strip()
                if len(first_line) < 200:
                    final_title = first_line
                    body_content = "".join(lines[1:]).strip()
                else:
                    final_title = f"Chapter {i+1}"
                    body_content = "".join(lines).strip()

            # Count annotations for logging
            annotation_count = len(ANNOTATION_PATTERN.findall(body_content))
            total_annotations += annotation_count
            if annotation_count > 0:
                print(f"  [{txt_filename}] Found {annotation_count} annotation(s)")

            # Create XHTML Chapter Object
            chapter_obj = create_xhtml_chapter(
                final_title, body_content, f"chapter_{i+1:04d}"
            )
            book.add_item(chapter_obj)
            epub_chapters.append(chapter_obj)
            toc_links.append(
                epub.Link(chapter_obj.file_name, final_title, f"chapter_{i+1:04d}")
            )

        except Exception as e:
            print(f"  [Error] Failed to process {txt_filename}: {e}")

    # --- 6. Finalize EPUB ---
    book.toc = tuple(toc_links)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # CSS Styling (includes footnote styles)
    css = """
    body { margin: 5%; font-family: serif; font-size: 1.1em; line-height: 1.6; }
    h1 { text-align: center; margin-top: 2em; margin-bottom: 1em; font-weight: bold; border-bottom: 1px solid #ddd; padding-bottom: 0.5em;}
    p { text-indent: 1.5em; margin-bottom: 0.5em; text-align: justify; }

    /* Footnote reference styling */
    a[epub|type~="noteref"] { text-decoration: none; color: #4f46e5; }
    a[epub|type~="noteref"] sup { font-size: 0.75em; vertical-align: super; }

    /* Footnotes section at end of chapter */
    hr.footnote-separator { margin-top: 2em; border: none; border-top: 1px solid #ccc; }
    section.footnotes { margin-top: 1em; font-size: 0.9em; color: #555; }
    section.footnotes aside { margin-bottom: 0.5em; }
    section.footnotes aside p { text-indent: 0; margin-bottom: 0.3em; }
    section.footnotes a { color: #4f46e5; text-decoration: none; }
    """
    style_item = epub.EpubItem(
        uid="style_default",
        file_name="style/default.css",
        media_type="text/css",
        content=css,
    )
    book.add_item(style_item)

    book.spine = ["nav"] + epub_chapters
    for ch in epub_chapters:
        ch.add_item(style_item)

    # Write file
    try:
        epub.write_epub(OUTPUT_FILE, book, {})
        print(f"SUCCESS! EPUB saved to: {OUTPUT_FILE}")
        print(f"Total cultural annotations converted to footnotes: {total_annotations}")
    except Exception as e:
        print(f"Error saving EPUB file: {e}")


if __name__ == "__main__":
    create_epub_project()
