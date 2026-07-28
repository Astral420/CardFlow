from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = (
        "postgresql+psycopg2://card_tool:card_tool@localhost:5432/card_tool"
    )
    redis_url: str = "redis://localhost:6379/0"
    # Celery result backend (separate DB index from the broker above so
    # results don't collide with queued task messages).
    redis_result_backend_url: str = "redis://localhost:6379/1"
    # Auth session state (access-token revocation markers, refresh-token
    # family registry -- see app.token_store). Its own DB index for the
    # same reason as the result backend: independent of Celery's traffic,
    # so flushing/inspecting one doesn't touch the others.
    redis_auth_url: str = "redis://localhost:6379/2"

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = "card-tool"
    r2_public_base_url: str = ""
    r2_endpoint_url: str = ""  # override for local dev/testing (e.g. MinIO)

    secret_key: str = _INSECURE_DEFAULT
    jwt_algorithm: str = "HS256"
    # Short-lived on purpose -- this is what limits how long a revoked
    # user's outstanding access token stays technically valid if the
    # Redis revocation check were ever bypassed. The refresh token (below)
    # is what makes a short access-token life tolerable for the user.
    access_token_expires_minutes: int = 15
    refresh_token_expires_days: int = 30
    app_passcode: str = _INSECURE_DEFAULT

    # Refresh token is delivered as an httpOnly cookie rather than JSON
    # (unlike the access token) so it's never reachable from JS -- an XSS
    # bug can steal the short-lived access token out of localStorage, but
    # not the refresh token, which is what actually grants long-term
    # access. The frontend is deployed separately from the API (Vercel +
    # Cloudflare Tunnel), so this cookie is genuinely cross-site: SameSite
    # "none" + Secure aren't just best practice here, browsers require
    # both before they'll accept a cross-site cookie at all. For local
    # dev, Vite's /api proxy (vite.config.ts) makes requests same-origin,
    # so these defaults work locally too *except* that "Secure" requires
    # HTTPS -- if your browser drops the cookie in local dev, override
    # REFRESH_COOKIE_SECURE=false and REFRESH_COOKIE_SAMESITE=lax in
    # backend/.env.
    refresh_cookie_name: str = "cardflow_refresh"
    refresh_cookie_secure: bool = True
    refresh_cookie_samesite: str = "none"
    refresh_cookie_domain: str | None = None

    cors_origins: list[str] = ["http://localhost:5173"]

    def insecure_defaults(self) -> list[str]:
        """Names of settings still at their placeholder value. Used to fail
        loudly on startup instead of silently running with a guessable JWT
        signing key / login passcode (see app.main's startup check)."""
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
