import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True, parents=True)

WAREHOUSE_DB_PATH = DATA_DIR / "university_warehouse.db"
NEO4J_EXPORT_PATH = DATA_DIR / "neo4j_graph_export.cypher"

# Load local .env if present
env_path = BASE_DIR / ".env"
if env_path.exists():
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
    except Exception:
        pass

# Groq API Configuration (Loaded securely from environment or .env)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_DEFAULT_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Entity Resolution Weights & Thresholds
SIMILARITY_WEIGHTS = {
    "name": 0.35,
    "email": 0.25,
    "dob": 0.20,
    "phone": 0.10,
    "identifier": 0.10,
}

THRESHOLD_AUTO_MERGE = 0.82
THRESHOLD_BORDERLINE = 0.62

# Server Configuration
HOST = "127.0.0.1"
PORT = 8000
