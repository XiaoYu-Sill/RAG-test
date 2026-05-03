import os
from dotenv import load_dotenv

load_dotenv()

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY", "")
EMBEDDING_MODEL = "embedding-3"
LLM_MODEL = "glm-4-flash"
VECTOR_STORE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "vector_store")
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 5
