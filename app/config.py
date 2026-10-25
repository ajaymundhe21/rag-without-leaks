import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app:app@localhost:5432/rag")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
IDENTITY_FILE = os.getenv("IDENTITY_FILE", os.path.join(os.path.dirname(__file__), "..", "data", "identity.json"))

TOP_K = 50                 # chunks from each search
ANSWER_CHUNKS = 5          # chunks the model gets
EF_SEARCH = int(os.getenv("EF_SEARCH", "100"))            # HNSW: higher finds more of the true closest, a bit slower
SMALL_GROUP_ROWS = int(os.getenv("SMALL_GROUP_ROWS", "20000"))  # below this, search exactly without the vector index
CACHE_SECONDS = int(os.getenv("CACHE_SECONDS", "300"))

# Optional language model (any OpenAI-compatible API). Without it, /ask returns the best chunk with its source.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
