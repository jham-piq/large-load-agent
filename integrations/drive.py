"""
Local file storage — reads and writes CSVs to the data/ folder in the repo.
Files are committed back to GitHub after each run by the Actions workflow.
"""

import logging
import os
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


class DriveClient:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)

    def download_csv(self, file_path):
        """Read CSV from local data/ folder. Returns None if file doesn't exist."""
        if not file_path:
            return None
        path = Path(file_path)
        if not path.exists():
            log.info(f"No existing file at {path} — starting fresh")
            return None
        df = pd.read_csv(path)
        log.info(f"Loaded {len(df)} rows from {path}")
        return df

    def upload_csv(self, df, file_path, filename, folder_id=None):
        """Write CSV to local data/ folder. Returns the file path."""
        if not file_path:
            file_path = str(DATA_DIR / filename)
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)
        log.info(f"Saved {len(df)} rows to {path}")
        return str(path)

    def get_file_url(self, file_path):
        """Return a GitHub URL to the file."""
        repo = os.environ.get("GITHUB_REPOSITORY", "your-org/large-load-agent")
        filename = Path(file_path).name
        return f"https://github.com/{repo}/blob/main/data/{filename}"
