from dataclasses import dataclass
import os

from dotenv import load_dotenv

# Load variables from a local .env file if present.
# This is convenient for local dev; in Cloud Run you will
# rely on actual environment variables set via gcloud or
# Secret Manager.
load_dotenv()


@dataclass
class Settings:
    """
    Simple container for application settings.
    Values are read once from the process environment.
    """

    # Core GCP configuration
    project_id: str = os.getenv("PROJECT_ID", "")
    bq_sec_dataset: str = os.getenv("BQ_SEC_DATASET", "")

    # External finance API - Finnhub
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")

    # External news API - NewsData.io
    newsdata_api_key: str = os.getenv("NEWSDATA_API_KEY", "")

    # Misc - environment name (dev, prod, etc.)
    environment: str = os.getenv("ENVIRONMENT", "dev")


# Single settings instance to import elsewhere
settings = Settings()