import os
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./certificates.db")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./generated_certificates"))
MAX_RECIPIENTS_PER_JOB = int(os.getenv("MAX_RECIPIENTS_PER_JOB", "1000"))
