from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://card_tool:card_tool@localhost:5432/card_tool"
    )
    redis_url: str = "redis://localhost:6379/0"
    redis_result_backend_url: str = "redis://localhost:6379/1"
    redis_auth_url: str = "redis://localhost:6379/2"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "card-tool"
    r2_public_base_url: str = ""
    r2_endpoint_url: str = ""  # override for local dev/testing (e.g. MinIO)

    secret_key: str = _INSECURE_DEFAULT
    jwt_algorithm: str = "HS256"

    access_token_expires_minutes: int = 15
    refresh_token_expires_days: int = 30
    app_passcode: str = _INSECURE_DEFAULT

    refresh_cookie_name: str = "cardflow_refresh"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: str = "none"
    refresh_cookie_domain: str | None = None

    cors_origins: list[str] = ["http://localhost:5173"]
    cors_origin_regex: str = ""

    
    environment: str = "development"
    log_level: str = "INFO"
    ops_dashboard_token: str = ""
    alert_webhook_url: str = ""
    
    alert_webhook_url: str = ""

    def insecure_defaults(self) -> list[str]:
        insecure = []
        if self.secret_key == _INSECURE_DEFAULT:
            insecure.append("SECRET_KEY")
        if self.app_passcode == _INSECURE_DEFAULT:
            insecure.append("APP_PASSCODE")
        return insecure

    # Crop pipeline
    crop_output_width: int = 750
    crop_output_height: int = 1050
    expected_card_aspect_ratio: float = 3.5 / 2.5
    aspect_ratio_tolerance: float = 0.15  
    crop_padding_fraction: float = 0.04
    crop_padding_min_pixels: int = 5
    scan_background_threshold: int = 8


    crop_refine_enabled: bool = True
    # Pixels darker than this (0-255, grayscale) are treated as residual
    # scan-bed / toploader-margin background to trim. Tuned above scan-bed
    # noise (0-5) and below even the darkest real card borders seen in
    # inventory so far (15-30+).
    crop_refine_bg_threshold: int = 12
    # Safety cap: never trim more than this fraction of a dimension from
    # any single edge, regardless of what the border scan finds. Guards
    # against a pathological input (e.g. a mostly-black photo) eating the
    # card itself.
    crop_refine_max_trim_fraction: float = 0.15


    precropped_perimeter_bg_max_fraction: float = 0.8
    
    precropped_aspect_ratio_tolerance: float = 0.35
 
    contour_full_frame_area_fraction: float = 0.97

    # Duplicate detection (tune empirically, see spec Section 11)
    structural_hash_max_distance: int = 10  # out of 64 bits (pHash)
    color_sig_max_distance: float = 0.2  # normalized histogram distance, 0=identical


settings = Settings()
