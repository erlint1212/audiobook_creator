import argparse
import json
import os
import re
import statistics

# --- Configuration & Thresholds ---
LOWER_BOUND_RATIO = 0.45  # Flag if smaller than 45% of median (Severe Cutoff)
UPPER_BOUND_RATIO = 2.50  # Flag if larger than 250% of median (Thinking dump)
ABSOLUTE_MIN_CHARS = 1000  # Anything under this is functionally empty
MIN_EXPECTED_RATIO = 2.0  # English text must be >= 2.0x the Chinese length

OUTPUT_FILENAME = "early_cutoff_chapters.json"


def strip_for_counting(text):
    """Strips annotations and excess whitespace in-memory to get a true character count."""
    if not text:
        return ""
    # Remove the translator annotations: ^[explanation]
    clean = re.sub(r"\^\[.*?\]", "", text, flags=re.DOTALL)
    # Remove standard brackets if the LLM hallucinated notes
    clean = re.sub(
        r"\[(?:Note|Translation|TL|Editor).*?\]",
        "",
        clean,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return clean.strip()


def analyze_chapter_ending(text):
    """
    Returns True if the chapter seems to end abruptly.
    A valid ending MUST have terminal punctuation (. ! ? ~ … —) optionally followed by quotes.
    """
    clean_text = text.strip()
    if not clean_text:
        return True, ""

    if clean_text.endswith("..."):
        return False, "..."

    # Regex Explanation:
    # [.!?~…—*] -> Must contain at least one terminal punctuation mark.
    # [\"\'”’\)\]]*$ -> Can optionally be followed by closing quotes or brackets at the very end of the string.
    match = re.search(r"[.!?~…—*][\"\'”’\)\]]*$", clean_text)

    if match:
        return False, clean_text[-1]

    # If no terminal punctuation is found at the end, it's an abrupt cutoff (e.g., ends in a letter, comma, or stray apostrophe)
    return True, clean_text[-1]


def process_novel_directory(novel_dir):
    raw_dir = os.path.join(novel_dir, "01_Raw_Text")
    trans_dir = os.path.join(novel_dir, "02_Translated")

    if not os.path.exists(trans_dir):
        print(f"  [Error] Directory '{trans_dir}' does not exist.")
        return

    txt_files = sorted([f for f in os.listdir(trans_dir) if f.endswith(".txt")])
    if not txt_files:
        print(f"  [Skip] No text files found in '{trans_dir}'.")
        return

    print(f"\nScanning '{os.path.basename(novel_dir)}' ({len(txt_files)} chapters)...")

    file_data = {}
    trans_lengths = []

    for filename in txt_files:
        trans_path = os.path.join(trans_dir, filename)
        raw_path = os.path.join(raw_dir, filename)

        try:
            with open(trans_path, "r", encoding="utf-8") as f:
                trans_content = f.read()

            stripped_trans = strip_for_counting(trans_content)
            trans_len = len(stripped_trans)

            raw_len = 0
            if os.path.exists(raw_path):
                with open(raw_path, "r", encoding="utf-8") as f:
                    raw_len = len(f.read().strip())

            file_data[filename] = {
                "trans_content": trans_content,
                "trans_len": trans_len,
                "raw_len": raw_len,
            }

            if trans_len > 0:
                trans_lengths.append(trans_len)

        except Exception as e:
            print(f"  Error reading {filename}: {e}")

    if not trans_lengths:
        return

    median_len = statistics.median(trans_lengths)
    lower_limit = int(median_len * LOWER_BOUND_RATIO)
    upper_limit = int(median_len * UPPER_BOUND_RATIO)

    print(f"  -> Median English Chapter: {median_len} chars")

    flagged_chapters = {}

    for filename, data in file_data.items():
        reasons = []
        trans_len = data["trans_len"]
        raw_len = data["raw_len"]
        original_content = data["trans_content"]

        # 1. Absolute limits
        if trans_len < ABSOLUTE_MIN_CHARS:
            reasons.append(f"Severely truncated ({trans_len} chars)")

        # 2. Statistical Bounds
        elif trans_len < lower_limit:
            reasons.append(f"Statistically too short ({trans_len} chars)")
        elif trans_len > upper_limit:
            reasons.append(
                f"Statistically too long / Thinking dump ({trans_len} chars)"
            )

        # 3. Translation Ratio
        if raw_len > 0:
            ratio = trans_len / raw_len
            if ratio < MIN_EXPECTED_RATIO:
                reasons.append(
                    f"Low translation ratio: {ratio:.2f}x (Raw: {raw_len}, Trans: {trans_len})"
                )

        # 4. Abrupt Ending - NOW STRICT AND INDEPENDENT OF LENGTH
        is_abrupt, last_char = analyze_chapter_ending(original_content)
        if is_abrupt and trans_len > 0:
            # We explicitly mention what character it failed on to help with debugging
            reasons.append(
                f"Abrupt ending detected (ends with '{last_char}' lacking terminal punctuation)"
            )

        if reasons:
            snippet_end = (
                original_content.strip()[-60:].replace("\n", " ")
                if trans_len > 0
                else ""
            )
            flagged_chapters[filename] = {
                "stripped_length": trans_len,
                "raw_length": raw_len,
                "reasons": reasons,
                "snippet_end": f"...{snippet_end}",
            }

    output_path = os.path.join(novel_dir, OUTPUT_FILENAME)

    if flagged_chapters:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(flagged_chapters, f, indent=4, ensure_ascii=False)
        print(f"\n  ⚠️ Found {len(flagged_chapters)} anomalous chapters!")
        print(f"  💾 Saved target list to: {output_path}")
    else:
        if os.path.exists(output_path):
            os.remove(output_path)
        print("\n  ✅ All chapters passed length, ratio, and punctuation checks!")


def main():
    parser = argparse.ArgumentParser(description="Find malformed translated chapters.")
    parser.add_argument("novel", type=str, help="The exact folder name of the novel")
    parser.add_argument(
        "--base", type=str, default="Novels", help="Base directory (default: 'Novels')"
    )

    args = parser.parse_args()
    novel_path = os.path.join(args.base, args.novel)

    if not os.path.exists(novel_path):
        print(f"Error: Novel directory '{novel_path}' does not exist.")
        return

    process_novel_directory(novel_path)


if __name__ == "__main__":
    main()
