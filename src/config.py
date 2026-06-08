import os
from dataclasses import dataclass


@dataclass
class Settings:
    download_dir: str = "/tmp/downloads"
    max_concurrent_downloads: int = 3
    max_video_duration: int = 3600
    default_quality: int = 1080
    file_ttl_minutes: int = 60
    api_port: int = 6060
    pot_provider_url: str = "http://bgutil-provider:4416"
    cookies_file: str | None = None
    yt_proxy: str | None = None

    def __post_init__(self):
        self.download_dir = os.getenv("DOWNLOAD_DIR", self.download_dir)
        self.max_concurrent_downloads = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", self.max_concurrent_downloads))
        self.max_video_duration = int(os.getenv("MAX_VIDEO_DURATION", self.max_video_duration))
        self.default_quality = int(os.getenv("DEFAULT_QUALITY", self.default_quality))
        self.file_ttl_minutes = int(os.getenv("FILE_TTL_MINUTES", self.file_ttl_minutes))
        self.api_port = int(os.getenv("API_PORT", self.api_port))
        self.pot_provider_url = os.getenv("POT_PROVIDER_URL", self.pot_provider_url)
        self.cookies_file = os.getenv("COOKIES_FILE") or None
        self.yt_proxy = os.getenv("YT_PROXY") or None

    def validate(self):
        if not os.path.isabs(self.download_dir):
            raise ValueError("DOWNLOAD_DIR must be an absolute path")
