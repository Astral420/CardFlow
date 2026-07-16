from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://card_tool:card_tool@localhost:5432/card_tool"
    )
    redis_url: str = "redis://localhost:6379/0"
    redis_url1: str = "redis://localhost:6379/1"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "card-tool"
    r2_public_base_url: str = ""
    r2_endpoint_url: str = ""  # override for local dev/testing (e.g. MinIO)

    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24 * 14  # 2 weeks — two known users, low risk
    app_passcode: str = "change-me"

    cors_origins: list[str] = ["http://localhost:5173"]

    # Crop pipeline
    crop_output_width: int = 750
    crop_output_height: int = 1050
    expected_card_aspect_ratio: float = 3.5 / 2.5
    aspect_ratio_tolerance: float = 0.15  # tune empirically, see spec Section 11
    crop_padding_fraction: float = 0.07
    crop_padding_min_pixels: int = 10
    scan_background_threshold: int = 8

    # Duplicate detection (tune empirically, see spec Section 11)
    structural_hash_max_distance: int = 10  # out of 64 bits (pHash)
    color_sig_max_distance: float = 0.2  # normalized histogram distance, 0=identical


settings = Settings()
