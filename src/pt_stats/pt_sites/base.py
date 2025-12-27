from abc import ABC
import attrs
from typing import Any
from pydantic import BaseModel
from datetime import datetime


class TorrentInfo(BaseModel):
    source_site: str        # The name of the source site, e.g., "MTeam"
    sitewise_id: Any        # The unique ID of the torrent on the site
    name: str
    create_date: datetime
    size: int               # Size in bytes
    seeders: int            # Number of seeders (uploaders)
    leechers: int           # Number of leechers (downloaders)


@attrs.define
class SiteClient(ABC):
    async def list_latest_free_torrents(self) -> list[TorrentInfo]:
        """
        List the latest free torrents from the site.
        """
        ...
        
    async def download_torrent_metadata(self, sitewise_id: Any) -> bytes:
        """
        Download the torrent metadata file (.torrent) for the given sitewise ID.
        
        According to the implementation, this method may impose a file size limit
        on the downloaded metadata file.
        """
        ...
