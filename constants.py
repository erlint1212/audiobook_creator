GEMINI_MODEL_NAME = "gemini-3-flash-preview"
CONFIG_FILE = "alltalk_path_config.json"

# --- Context Window Budget (LM Studio / Local LLM) ---
CONTEXT_LIMIT = 36970          # Total context length configured in LM Studio
AVG_CHARS_PER_TOKEN_ZH = 1.5   # Chinese text: ~1.5 chars per token
AVG_CHARS_PER_TOKEN_EN = 4.0   # English text: ~4 chars per token
PROMPT_OVERHEAD_TOKENS = 1500  # System prompt + rules + few-shot + formatting
OUTPUT_RATIO = 2.5             # EN translation is ~2-2.5x longer than ZH in chars
SAFETY_MARGIN = 0.90           # Leave 10% headroom

# --- Thinking Dump Detection ---
THINKING_DUMP_CJK_THRESHOLD = 20     # CJK chars in output = source text leak
THINKING_DUMP_INDICATOR_THRESHOLD = 3 # Number of reasoning indicators to trigger retry
