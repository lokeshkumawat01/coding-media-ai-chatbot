"""
Application configuration loaded from environment variables.
Uses pydantic-settings so all env vars are validated and typed.

LLM provider: Groq only (no fallback provider at this stage).
Embeddings: HuggingFace Inference API (hosted, free tier - no self-hosted model).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_env: str = "development"
    app_debug: bool = True
    allowed_origins: str = "http://localhost:3000"

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # LLM provider (Groq only)
    groq_api_key: str
    groq_model: str = "openai/gpt-oss-120b"

    # Embeddings (HuggingFace Inference API)
    hf_api_key: str
    hf_embedding_model: str = (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )

    # ChromaDB
    chroma_persist_dir: str = "./chroma_data"
    chroma_collection_name: str = "agency_knowledge"

    # Google Calendar
    google_calendar_credentials_path: str = "./credentials/google_calendar_service_account.json"
    google_calendar_credentials_json: str = ""

    # WhatsApp Cloud API
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""

    # JWT
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Encryption
    field_encryption_key: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 15
    max_daily_chat_messages: int = 150

    # Admin panel (Phase 1: single admin account)
    admin_username: str = "admin"
    admin_password_hash: str

    # Notifications
    notify_whatsapp_number: str = ""
    notify_email: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @property
    def allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
