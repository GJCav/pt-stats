import httpx
from typing import (
    override, Annotated,
    Literal
)
import attrs
import os
from furl import furl
from datetime import datetime, timedelta
from .base import (
    SiteClient,
    TorrentInfo
)
from .utils import localize2utc, Throttle
from pydantic import (
    Field, 
    AliasPath,
    AfterValidator
)

SITE_NAME = 'MTeam'

class MTeamAPIError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(f"MTEAM API Error {code}: {message}")
        self.code = code
        self.message = message


class MTeamAuthPlugin(httpx.Auth):
    def __init__(self, whitelist: list[str], api_key: str) -> None:
        super().__init__()
        self.whitelist = whitelist
        self.api_key = api_key
    
    @override
    def auth_flow(self, request: httpx.Request):
        if request.url.host in self.whitelist:
            request.headers["x-api-key"] = self.api_key
        yield request


class MTeamTorrentInfoFromSearch(TorrentInfo):
    # inherited properties
    source_site: str = SITE_NAME
    sitewise_id: str = Field(validation_alias="id")
    name: str = Field(validation_alias="name")
    create_date: Annotated[datetime, AfterValidator(localize2utc)] = Field(validation_alias="createdDate")
    size: int = Field(validation_alias="size")
    seeders: int = Field(validation_alias=AliasPath("status", "seeders"))
    leechers: int = Field(validation_alias=AliasPath("status", "leechers"))
    
    # additional properties
    small_descr: str = Field(validation_alias="smallDescr")
    discount: str = Field(validation_alias=AliasPath("status", "discount"))
    discount_end_time: datetime | None = Field(
        validation_alias=AliasPath("status", "discountEndTime")
    )
    
    @property
    def is_free(self) -> bool:
        return self.discount == "FREE"
    
    @property
    def remain_free_duration(self) -> timedelta:
        if not self.is_free:
            return timedelta(0)
        if self.discount_end_time is None:
            return timedelta.max
        now_utc = datetime.now(tz=self.discount_end_time.tzinfo)
        return self.discount_end_time - now_utc


@attrs.define
class MTeamClient(SiteClient):
    api_key: str = attrs.field()
    api_base: furl = attrs.field(converter=furl)
    http_client: httpx.AsyncClient = attrs.field(factory=lambda: httpx.AsyncClient())
    
    throttle: Throttle = attrs.field(
        default=attrs.Factory(lambda: Throttle(rate=2))
    )
    
    def __attrs_post_init__(self):
        # Insert the auth plugin
        self.http_client.auth = MTeamAuthPlugin(
            whitelist=[self.api_base.host], # type: ignore
            api_key=self.api_key
        )
        
        # Force follow redirects
        self.http_client.follow_redirects = True
        
    
    async def search_torrents(
        self, 
        *,
        keyword: str | None = None,
        mode: Literal["adult", "normal", "movie", "tvshow"] = "normal",
        categories: list[str] = [],
        visible: Literal[0, 1, 2] = 1,
        page_number: int = 1,
        page_size: int = 40,
        discount: str | None = None
    ) -> dict:
        """Search torrents on MTeam.
        
        keyword:
            None: no keyword filtering
            str: keyword to search for
        
        mode:
            "normal": General search (adult content excluded)
            "adult": Adult content only search
            "movie": Movie only search
            "tvshow": TV Show only search
        
        categories: Different "mode" has different category IDs. For convenience, 
            leave it an empty list to include all categories.
        
        visible:
            0: all torrents
            1: active torrents only (recommended)
            2: dead torrents only
        
        page_number: Page number (1-based)
        page_size: Number of results per page (max 100)
        
        discount:
            None: no discount filtering
            "FREE": free torrents
            "PERCENT_50": 50% off torrents
            (other possible values not yet known)
        
        """
        await self.throttle()
        
        search_params = {
            'mode': mode,
            'visible': visible,
            'categories': categories,
            'pageSize': page_size,
            'pageNumber': page_number
        }
        if keyword is not None:
            search_params['keyword'] = keyword
        if discount is not None:
            search_params['discount'] = discount
        
        response = await self.http_client.post(
            (self.api_base / "torrent" / "search").url,
            json=search_params
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch latest free torrents from MTeam: {response.status_code} - {response.text}")
        
        data = response.json()
        if data.get('message', '') != 'SUCCESS':
            raise MTeamAPIError(data.get('code', -1), data.get('message', 'Unknown error'))
        
        return data
    
    
    @override
    async def list_latest_free_torrents(self) -> list[MTeamTorrentInfoFromSearch]:
        await self.throttle()
        
        normal_content = await self.search_torrents(
            mode="normal",
            page_number=1,
            page_size=40,
            discount="FREE"
        )
        part_a = normal_content.get('data', {}).get('data', [])
        
        adult_content = await self.search_torrents(
            mode="adult",
            page_number=1,
            page_size=40,
            discount="FREE"
        )
        part_b = adult_content.get('data', {}).get('data', [])
        
        torrents: list[MTeamTorrentInfoFromSearch] = []
        for item in part_a + part_b:
            torrent_info = MTeamTorrentInfoFromSearch.model_validate(item)
            torrents.append(torrent_info)
            
        return torrents
    
    
    @override
    async def download_torrent_metadata(self, sitewise_id: str) -> bytes:
        await self.throttle()
        
        res = await self.http_client.post(
            (self.api_base / "torrent" / "genDlToken").url,
            data={
                "id": sitewise_id
            }
        )
        
        if res.status_code != 200:
            raise Exception(f"Failed to get torrent metadata download link from MTeam: {res.status_code} - {res.text}")
    
        data = res.json()
        if data.get('message', '') != 'SUCCESS':
            raise MTeamAPIError(data.get('code', -1), data.get('message', 'Unknown error'))
        
        dl_link = data.get('data', '')
        
        # Downloading the torrent file
        res = await self.http_client.get(dl_link) # TODO: limit the response body size
        res.raise_for_status()
        
        return res.content
    