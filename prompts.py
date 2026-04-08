"""
prompts.py — Shared prompt templates for all translation engines.

Edit the rules, examples, and categories here once and they apply
to Gemini, Grok, and LM Studio simultaneously.
"""

import json

# ============================================================
# Glossary categories (shared across all engines)
# ============================================================
DEFAULT_GLOSSARY = {
    "characters": {},
    "places": {},
    "organizations": {},
    "items": {},
    "skills": {},
    "species": {},
}

# ============================================================
# Annotation rules (strict — only genuinely obscure stuff)
# ============================================================
ANNOTATION_RULES = """
ANNOTATION RULES — BE EXTREMELY SELECTIVE:
Only use ^[explanation] for things genuinely obscure to a non-Chinese reader.

DO annotate:
- Internet memes or slang with no English equivalent (五五开, 柠檬精, 996, 躺平, 打工人, 内卷)
- Homophonic puns where the humor is completely lost in translation
- References to specific Chinese pop culture, viral moments, or social media trends
- Idioms you kept literal for stylistic reasons where the English is confusing without context

DO NOT annotate:
- Standard idioms you already translated into natural English
- Words whose meaning is clear from context (e.g. "demon race", "knight order", "sword spirit")
- Character names, place names, titles, or ranks
- Common expressions, greetings, farewells, emotional reactions
- Self-explanatory fantasy or cultivation terms
- Anything where the English translation already conveys the full meaning
- General vocabulary or dictionary definitions of Chinese words

When in doubt, DO NOT annotate. A chapter with zero annotations is perfectly normal.
""".strip()

ANNOTATION_EXAMPLES = """
ANNOTATION EXAMPLES:
- 他真是个柠檬精 → He was such a lemon spirit^[Chinese internet slang for someone consumed by jealousy.]
- 这波是五五开 → This was a fifty-fifty^[A gaming meme from Chinese esports, used sarcastically when the odds are clearly not equal.]
- 我太南了 → I'm just too south^[Homophonic pun — "south" (南 nán) sounds like "hard/difficult" (难 nán).]
- Do NOT annotate phrases like "old master", "demonic energy", "broke through to the next realm" — these are self-evident.
""".strip()

# ============================================================
# Translation rules
# ============================================================
TRANSLATION_RULES = """
RULES:
- For names, places, items, organizations, skills, and species, you MUST use the 'english_name' from the glossary if present.
- Pronouns: Chinese frequently omits pronouns. Carefully infer he/she/they from context.
- Titles: Translate relational terms of address (老爷子, 师兄, 兄弟) contextually based on the actual relationship, not literally, unless they are blood relatives.
""".strip()

# ============================================================
# Glossary extraction categories & disambiguation
# ============================================================
GLOSSARY_CATEGORIES = """
CATEGORIES:
- "characters": People, individuals, named beings. Needs "pinyin", "english_name", "pronoun" (he/him, she/her, they/them).
- "places": Cities, regions, named buildings, towers, dungeons. Needs "pinyin", "english_name".
- "organizations": Knight orders, sects, guilds, factions, clans, armies, noble houses. Needs "pinyin", "english_name".
- "items": Named weapons, artifacts, treasures, tools, potions, books, scrolls. Needs "pinyin", "english_name".
- "skills": Named techniques, spells, martial arts moves, formations, arrays. Needs "pinyin", "english_name".
- "species": Races, creature types, monster species, bloodlines, ranked classifications. Needs "pinyin", "english_name".
""".strip()

GLOSSARY_DISAMBIGUATION = """
DISAMBIGUATION:
- 骑士团 (knight order) → ORGANIZATION, not place.
- 城 (city) / 塔 (tower) → PLACE, not organization.
- 剑/杖/named weapon → ITEM, not character or skill.
- 术 (technique) / 阵 (formation) → SKILL, not item.
- 族 (race) / 种 (species) → SPECIES. But 族 as family/clan → ORGANIZATION.
- Can people join/leave it? → ORGANIZATION. Is it a physical location? → PLACE.
""".strip()

# ============================================================
# Few-shot examples
# ============================================================
FEWSHOT_GLOSSARY_USER = "Extract entities from: 兰波带着破妄剑去了清河市的天辉骑士团。"

FEWSHOT_GLOSSARY_ASSISTANT = json.dumps(
    {
        "characters": {
            "兰波": {"pinyin": "Lan Bo", "english_name": "Lan Bo", "pronoun": "he/him"}
        },
        "places": {
            "清河市": {"pinyin": "Qinghe Shi", "english_name": "Qinghe City"}
        },
        "organizations": {
            "天辉骑士团": {
                "pinyin": "Tianhui Qishi Tuan",
                "english_name": "Radiant Knights",
            }
        },
        "items": {
            "破妄剑": {"pinyin": "Po Wang Jian", "english_name": "Delusion Breaker"}
        },
        "skills": {},
        "species": {},
    },
    ensure_ascii=False,
)

FEWSHOT_TRANSLATE_USER = (
    "Translate into English. Output ONLY the translation.\n\n"
    "--- CHINESE TEXT ---\n"
    "那个叫姬白的骑士挥舞着破妄剑，说道：\"这波是五五开，你们先撤。\"\n"
    "老骑士点了点头，转身离开。\n"
    "--- END ---"
)

FEWSHOT_TRANSLATE_ASSISTANT = (
    'The knight named Ji Bai swung the Delusion Breaker and said, '
    '"This is a fifty-fifty^[A gaming meme from Chinese esports meaning an even '
    "split, often used sarcastically when the odds are clearly not equal.], "
    'you all retreat first."\n'
    "The old knight nodded and turned to leave."
)


# ============================================================
# System prompts
# ============================================================
SYSTEM_TRANSLATION = (
    "You are a professional translation engine. Output ONLY the final English translation. "
    "No reasoning, no chain of thought, no meta-commentary. "
    "Start immediately with the translated text."
)

SYSTEM_GLOSSARY = (
    "You are a data extractor. Output ONLY valid JSON. "
    "No markdown fences, no explanation — just the JSON object."
)

SYSTEM_COMBINED = "You are a helpful assistant that follows instructions precisely."


# ============================================================
# Prompt builders
# ============================================================
def build_translation_prompt(text_to_translate, glossary_json_str, target_language="English"):
    """
    Builds the translation-only prompt (used by LM Studio Pass 2).
    Returns the user prompt string.
    """
    return (
        f"You are an expert Chinese-to-English translator.\n"
        f"Translate the Chinese text below into high-quality, natural-sounding {target_language}.\n\n"
        f"{TRANSLATION_RULES}\n\n"
        f"{ANNOTATION_RULES}\n\n"
        f"{ANNOTATION_EXAMPLES}\n\n"
        f"GLOSSARY:\n{glossary_json_str}\n\n"
        f"--- CHINESE TEXT ---\n{text_to_translate}\n--- END ---\n\n"
        f"Output ONLY the translated text. No reasoning, no commentary."
    )


def build_glossary_prompt(original_chinese):
    """
    Builds the glossary extraction prompt (used by LM Studio Pass 1).
    Returns the user prompt string.
    """
    return (
        f"You are a named entity extraction assistant for Chinese fantasy/web novels.\n"
        f"Given the Chinese text below, extract ALL named entities and provide English translations.\n\n"
        f"{GLOSSARY_CATEGORIES}\n\n"
        f"{GLOSSARY_DISAMBIGUATION}\n\n"
        f"Return JSON with all six keys. Empty objects for empty categories.\n"
        f"ONLY the JSON. No markdown, no explanation.\n\n"
        f"--- CHINESE TEXT ---\n{original_chinese}\n--- END ---"
    )


def build_combined_prompt(text_to_translate, glossary_json_str, target_language="English"):
    """
    Builds the combined translation+glossary prompt (used by Gemini and Grok).
    The LLM does everything in one call, separated by ---JSON---.
    Returns the user prompt string.
    """
    return (
        f"You are an expert Chinese-to-English translator and data extractor.\n"
        f"Your task has three parts:\n"
        f"1. Translate the Chinese text into high-quality, natural-sounding {target_language}.\n"
        f"   {TRANSLATION_RULES}\n"
        f"2. Identify new named entities (characters, places, organizations, items, skills, species) "
        f"NOT already in the glossary, and extract their details.\n"
        f"3. Annotate cultural references where needed.\n\n"
        f"{ANNOTATION_RULES}\n\n"
        f"{ANNOTATION_EXAMPLES}\n\n"
        f"--- RELEVANT GLOSSARY ---\n{glossary_json_str}\n\n"
        f"--- RESPONSE FORMATTING RULES ---\n"
        f"- Your response MUST have two parts separated by '---JSON---'.\n"
        f"- PART 1 (Translation): ONLY the final {target_language.upper()} translation "
        f"(with any ^[annotation] markers inline).\n"
        f"- PART 2 (Data): A JSON object of NEW entities (not already in the glossary).\n\n"
        f"{GLOSSARY_CATEGORIES}\n\n"
        f"{GLOSSARY_DISAMBIGUATION}\n\n"
        f"- Use empty objects for categories with no new entities.\n"
        f'- Example: {{"characters": {{"兰波": {{"pinyin": "Lan Bo", "english_name": "Lan Bo", "pronoun": "he/him"}}}}, '
        f'"places": {{}}, "organizations": {{}}, "items": {{}}, "skills": {{}}, "species": {{}}}}\n\n'
        f"--- CHINESE TEXT TO PROCESS ---\n{text_to_translate}\n--- END OF TEXT ---\n\n"
        f"Provide your response following all rules."
    )
