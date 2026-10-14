"""Load this project's private settings before DB/security modules are imported."""

from pathlib import Path
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(ENV_FILE, override=False, interpolate=False)
