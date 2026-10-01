"""Settings. Each one can be changed with an environment variable."""

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://fightlens:fightlens@localhost:5432/fightlens"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Where the UFC data comes from: a web address or a folder with the CSV files.
DATASET_URL = os.getenv(
    "DATASET_URL", "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"
)

# New fights are written to this Redis Stream, so other services can pick them up.
STREAM = os.getenv("STREAM", "fightlens:fights")

# Password for POST /api/v1/import. If it is empty, importing through the API is turned off.
IMPORT_TOKEN = os.getenv("IMPORT_TOKEN", "")
