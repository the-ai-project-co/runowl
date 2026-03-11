"""Sandbox execution limits and constants."""

# Maximum reasoning iterations the agent may perform
MAX_ITERATIONS = 20

# Maximum Gemini API calls per review
MAX_LLM_CALLS = 15

# Maximum wall-clock time (seconds) for a single sandbox execution
EXECUTION_TIMEOUT = 60

# Maximum stdout+stderr bytes captured from sandbox
MAX_OUTPUT_BYTES = 256 * 1024  # 256 KB

# Whitelisted tool names the agent script may call
ALLOWED_TOOLS = frozenset({"SEARCH_CODE", "FETCH_FILE", "LIST_DIR"})
