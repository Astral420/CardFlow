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

    # Already-cropped input detection (spec Section 6.2 addendum). Some
    # intake sources (e.g. a scanner that auto-crops on-device) hand us
    # images that are already tight to the card/sleeve, with little or no
    # near-black scan bed left around them. Contour-detecting against a
    # background that isn't really there just finds the frame itself, which
    # (a) can't be cropped any further and (b) has no business being graded
    # against the raw-scan aspect-ratio tolerance below. We detect that case
    # by checking how much of the image's own border is background-colored:
    # a real raw scan is bordered almost entirely by the near-black bed, an
    # already-cropped image mostly isn't. This is the "tolerance" for that
    # detection -- the max fraction of background pixels still allowed
    # around the border before we trust it's a raw, uncropped scan.
    precropped_perimeter_bg_max_fraction: float = 0.8
    # Aspect-ratio tolerance applied instead of aspect_ratio_tolerance when
    # an image is judged already-cropped. We didn't do the cropping, so we
    # can't correct it -- only sanity-check it. Pre-cropped sources commonly
    # include a bit of toploader/sleeve margin (or a slightly loose device
    # crop), which pushes the measured ratio further from the bare-card
    # ideal than our own contour-based crops ever would. Wider than
    # aspect_ratio_tolerance on purpose; tune empirically, see spec Section 11.
    precropped_aspect_ratio_tolerance: float = 0.35

    # Duplicate detection (tune empirically, see spec Section 11)
    structural_hash_max_distance: int = 10  # out of 64 bits (pHash)
    color_sig_max_distance: float = 0.2  # normalized histogram distance, 0=identical


settings = Settings()
