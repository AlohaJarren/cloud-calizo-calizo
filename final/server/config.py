import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# Load environment variables from final/server/.env if present.
# - We point directly at the directory this file lives in.
# - override=False so real env vars win over .env if you ever set them.
ENV_DIR = Path(__file__).parent
ENV_PATH = ENV_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=False)


@dataclass
class Settings:
    """
    Central configuration for the MCP server.

    Values are loaded from environment variables. For local development,
    you can provide them in final/server/.env (do not commit that file).
    """

    # Core GCP project configuration
    project_id: str | None = os.getenv("PROJECT_ID")

    # BigQuery fundamentals source
    # BQ_SEC_DATASET: optional logical name for your SEC-related dataset.
    # BQ_SEC_TABLE_FQN: fully-qualified table or view name:
    #   project.dataset.table
    bq_sec_dataset: str | None = os.getenv("BQ_SEC_DATASET")
    bq_sec_table_fqn: str | None = os.getenv("BQ_SEC_TABLE_FQN")

    # External APIs
    finnhub_api_key: str | None = os.getenv("FINNHUB_API_KEY")
    newsdata_api_key: str | None = os.getenv("NEWSDATA_API_KEY")
    alpha_vantage_api_key: str | None = os.getenv("ALPHA_VANTAGE_API_KEY")

    # Misc environment flag (dev, prod, test, etc.)
    environment: str = os.getenv("ENVIRONMENT", "dev")


settings = Settings()