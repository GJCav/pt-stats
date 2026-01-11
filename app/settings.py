from alpenstock.settings import Settings
from pydantic import Field
import dotenv

dotenv.load_dotenv()


def load_settings(file: str) -> "AppSettings":
    """Load application settings from the settings file and environment variables."""
    return AppSettings.from_yaml(file, replace_env_vars=True)


__all__ = ["AppSettings", "load_settings"]


def mb_to_bytes(value: int) -> int:
    """Convert MB to bytes."""
    return value * 1024 * 1024


class AppSettings(Settings):
    db_path: str = Field(
        default="qbt_tasks.db",
        description=(
            "Path to the SQLite database file. "
            "Set to ':memory:' to use an in-memory database for testing purposes."
        ),
    )

    disk_quota_mb: int = Field(
        default=204800,  # 200 GB
        description=(
            "Disk quota for torrents added by this application in MB. "
            "When the total size of the torrents added by this application "
            "exceeds this limit, old torrents will be removed to free up space. "
            "Set to 0 for no limit. Default is 204800 (200 GB)."
        ),
    )

    daemon: "DaemonSettings" = Field(
        default_factory=lambda: DaemonSettings(),
        description="Settings related to the daemon mode behavior.",
    )

    @property
    def disk_quota(self) -> int:
        """Disk quota in bytes."""
        return mb_to_bytes(self.disk_quota_mb)

    qbittorrent: "QBitSettings" = Field(
        default_factory=lambda: QBitSettings(),
        description="Settings related to qBittorrent client.",
    )

    mteam: "MTeamSettings" = Field(
        default_factory=lambda: MTeamSettings(),
        description="Settings related to M-Team.",
    )

    filters: "FilterSettings" = Field(
        default_factory=lambda: FilterSettings(),
        description=("Settings for filtering free torrents before they are added."),
    )


class DaemonSettings(Settings):
    add_free_torrent_interval_hours: float = Field(
        default=6.0,
        description=(
            "Interval in hours between attempts to add new free torrents. "
            "Default is 6.0 hours."
        ),
    )

    sample_stats_interval_minutes: float = Field(
        default=1.0,
        description=(
            "Interval in minutes between sampling qBittorrent statistics. "
            "Default is 1.0 minutes."
        ),
    )


class QBitSettings(Settings):
    api_base: str = Field(
        default="http://localhost:8080",
        description=(
            "The base URL for the qBittorrent Web API. "
            "It is the same as the URL of the qBittorrent Web UI."
        ),
    )

    username: str = Field(
        default="admin", description="Username for qBittorrent Web API authentication."
    )

    password: str = Field(
        default="${QBIT_API_PASS}",
        description=(
            "Password for qBittorrent Web API authentication. "
            "To refrain from hardcoding sensitive information in this file, "
            "set this to '${QBIT_API_PASS}' and define the environment "
            "variable 'QBIT_API_PASS' before running the application. "
        ),
    )

    save_to_category: str | None = Field(
        default=None,
        description=(
            "If set, torrents will be added to this category in qBittorrent. "
            "It will keep the torrents organized. "
            "Make sure the category exists in qBittorrent before adding torrents."
        ),
    )

    upload_speed_limit_mb: int = Field(
        default=0,
        description=(
            "Upload speed limit for added torrents in MB/s. Set to 0 for unlimited."
        ),
    )

    @property
    def upload_speed_limit(self) -> int:
        """Upload speed limit in bytes per second."""
        return mb_to_bytes(self.upload_speed_limit_mb)

    download_speed_limit_mb: int = Field(
        default=0,
        description=(
            "Download speed limit for added torrents in MB/s. Set to 0 for unlimited."
        ),
    )

    @property
    def download_speed_limit(self) -> int:
        """Download speed limit in bytes per second."""
        return mb_to_bytes(self.download_speed_limit_mb)


class MTeamSettings(Settings):
    api_base: str = Field(
        default="https://api.m-team.cc/api",
        description=(
            "Base URL for M-Team API. "
            "The default value is https://api.m-team.cc/api. "
            "Usually, there is no need to change this."
        ),
    )

    api_key: str = Field(
        default="${MTEAM_API_KEY}",
        description=(
            "API key for M-Team API access. "
            "To avoid hardcoding sensitive information in this file, "
            "set this to '${MTEAM_API_KEY}' and define the environment "
            "variable 'MTEAM_API_KEY' before running the application."
        ),
    )

    proxy: str | None = Field(
        default=None,
        description=(
            "Proxy URL for accessing M-Team API. "
            "If your network requires a proxy to access external sites, "
            "set the proxy URL here (e.g., 'http://proxy.example.com:8080'). "
            "Delete this line if no proxy is needed."
        ),
    )


class FilterSettings(Settings):
    max_torrent_size_mb: int = Field(
        default=51200,  # 50 GB
        description=(
            "Maximum allowed torrent content size in MB. "
            "Torrents exceeding this size will be skipped. "
            "Set to 0 for no limit. Default is 51200 (50 GB)."
        ),
    )

    @property
    def max_torrent_size(self) -> int:
        """Maximum torrent size in bytes."""
        return mb_to_bytes(self.max_torrent_size_mb)

    min_torrent_size_mb: int = Field(
        default=128,  # 128 MB
        description=(
            "Minimum required torrent content size in MB. "
            "Torrents smaller than this size will be skipped. "
            "Set to 0 for no minimum. Default is 128 (128 MB)."
        ),
    )

    @property
    def min_torrent_size(self) -> int:
        """Minimum torrent size in bytes."""
        return mb_to_bytes(self.min_torrent_size_mb)

    min_remain_free_hours: float = Field(
        default=4.0,
        description=(
            "Minimum remaining free hours for torrents. "
            "Torrents with less remaining free hours will be skipped. "
            "Default is 4.0 hours."
        ),
    )

    min_seeders: int = Field(
        default=5,
        description=(
            "Minimum number of seeders required for torrents. "
            "Torrents with fewer seeders will be skipped. "
            "Default is 5."
        ),
    )

    min_l2s_ratio: float = Field(
        default=0.8,
        description=(
            "Minimum leech-to-seed ratio required for torrents. "
            "Torrents with a lower ratio will be skipped. "
            "Default is 0.8."
        ),
    )
