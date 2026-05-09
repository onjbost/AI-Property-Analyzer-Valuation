"""
Configurazione centralizzata dell'applicazione.
Tutte le variabili di configurazione vengono caricate dall'ambiente (.env).
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Applicazione ---
    app_name: str = "AI Property Analyzer & Valuation"
    app_version: str = "1.2.0"
    app_env: str = "development"
    log_level: str = "INFO"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # --- Moonshot AI (Kimi) ---
    moonshot_api_key: str = ""
    moonshot_base_url: str = "https://api.moonshot.ai/v1"
    moonshot_model: str = "moonshot-v1-8k"

    # --- NVIDIA Build ---
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-4-maverick-17b-128e-instruct"

    # --- Playwright ---
    playwright_timeout: int = 30000  # ms
    playwright_headless: bool = True

    # --- Anti-Bot Proxy (ScrapingBee) ---
    scrapingbee_api_key: str = ""

    # --- OMI ---
    omi_csv_path: str = "app/data/omi_full.csv"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache()
def get_settings() -> Settings:
    """Restituisce l'istanza singleton della configurazione (cached)."""
    return Settings()
