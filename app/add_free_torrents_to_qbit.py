import httpx
import peewee
from peewee import SqliteDatabase
from dotenv import load_dotenv
import os
from qbittorrentapi import Client as QbtClient
import torf
import asyncio as aio
from pt_stats.pt_sites import MTeamClient
from datetime import timedelta
from argparse import ArgumentParser

from pt_stats.pt_sites.mteam import MTeamTorrentInfoFromSearch

load_dotenv()

def must_have(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Environment variable '{name}' must be set.")
    return value

# Config priority:
#   1. Environment variable
#   2. '.env' file
#   3. Default value

DB_PATH = os.getenv("DB_PATH") or "qbt_tasks.db"

QBIT_API_URL = must_have("QBIT_API_URL")
QBIT_API_USERNAME = must_have("QBIT_API_USERNAME")
QBIT_API_PASS = os.getenv("QBIT_API_PASS") or ""
QBIT_UPLOAD_LIMIT = int(os.getenv("QBIT_UPLOAD_LIMIT") or "0") * 1024 * 1024      # in MB/s, 0 means unlimited
QBIT_DOWNLOAD_LIMIT = int(os.getenv("QBIT_DOWNLOAD_LIMIT") or "0") * 1024 * 1024  # in MB/s, 0 means unlimited
QBIT_SET_CATEGORY = os.getenv("QBIT_SET_CATEGORY")  # save to this category if set

MTEAM_API_BASE = os.getenv("MTEAM_API_BASE") or "https://api.m-team.cc/api"
MTEAM_API_KEY = must_have("MTEAM_API_KEY")
MTEAM_PROXY = os.getenv("MTEAM_PROXY")

MAX_TORRENT_CONTENT_SIZE = int(
    os.getenv("MAX_TORRENT_CONTENT_SIZE") or "51200" # in MB, 0 means unlimited, default to 50 GB
) * 1024 * 1024  
MIN_TORRENT_CONTENT_SIZE = int(
    os.getenv("MIN_TORRENT_CONTENT_SIZE") or "128"   # in MB, 0 means no minimum, default to 128 MB
) * 1024 * 1024  
MIN_REMAIN_FREE_HOURS = float(
    os.getenv("MIN_REMAIN_FREE_HOURS") or "4"    # in hours, default to 4 hours
)
MIN_SEEDERS = int(os.getenv("MIN_SEEDERS") or "5")  # minimum number of seeders, default to 5
MIN_L2S_RATIO = float(
    os.getenv("MIN_L2S_RATIO") or "0.8"           # minimum leech-to-seed ratio, default to 1.0
)

##################################
# Database part
db = SqliteDatabase(DB_PATH, pragmas={
    "journal_mode": "wal",
})

class DatabaseModel(peewee.Model):
    class Meta:
        database = db


class TorrentRecord(DatabaseModel):
    record_id = peewee.AutoField()
    torrent_hash = peewee.CharField(unique=True)
    mteam_id = peewee.CharField(unique=True)
    
    @staticmethod
    def get_by_hash(torrent_hash: str) -> 'TorrentRecord | None':
        try:
            return TorrentRecord.get(TorrentRecord.torrent_hash == torrent_hash)
        except peewee.DoesNotExist:
            return None
    
    @staticmethod
    def get_by_mteam_id(mteam_id: str) -> 'TorrentRecord | None':
        try:
            return TorrentRecord.get(TorrentRecord.mteam_id == mteam_id)
        except peewee.DoesNotExist:
            return None


db.create_tables([TorrentRecord])

##################################
# Qbittorrent client

qbt = QbtClient(
    host=QBIT_API_URL,
    username=QBIT_API_USERNAME,
    password=QBIT_API_PASS,
)

try:
    qbt.auth_log_in()
except Exception as e:
    print(f"Failed to log in to qBittorrent: {e}")
    raise e


async def add_torrent_and_verify(torrent_meta_bytes: bytes, torrent_hash: str, timeout=5):
    """
    `client.torrents_add` returns `Ok` even for failed additions, so 
    we need to verify if the torrent was actually added.
    
    If failed, an exception is raised.
    """
    if not torrent_meta_bytes:
        raise ValueError("Empty torrent metadata bytes provided.")
    
    if not torrent_hash:
        raise ValueError("Empty torrent hash provided.")
    
    res = qbt.torrents_add(
        torrent_files=torrent_meta_bytes,
        upload_limit=QBIT_UPLOAD_LIMIT,
        download_limit=QBIT_DOWNLOAD_LIMIT,
        category=QBIT_SET_CATEGORY
    )
    ## The API may return 'Fails.' even when it actually succeeds.
    ## So we comment out this check and verify by querying the torrent list instead.
    # if res != 'Ok.':
    #     raise RuntimeError(f"qbt.torrents_add failed, error message: {res}")
    
    elapsed = 0
    while elapsed < timeout:
        # Verify if the torrent is added
        torrents = qbt.torrents_info(torrent_hashes=torrent_hash)
        if not torrents:
            # Not added yet, wait and retry
            elapsed += 1
            await aio.sleep(1)
            continue
        else:
            # Successfully added
            return
    
    raise TimeoutError(f"Failed to add torrent with hash {torrent_hash} within {timeout} seconds.")


######################
# MTeam client

mteam = MTeamClient(
    api_key=MTEAM_API_KEY,
    api_base=MTEAM_API_BASE,
    http_client=httpx.AsyncClient(proxy=MTEAM_PROXY)
)


async def main(dry_run: bool = False):
    free_torrents = await mteam.list_latest_free_torrents()
    print(f"Found {len(free_torrents)} free torrents on MTeam.")
    
    # Some filtering logic here to select the "test" torrent
    filtered: list[MTeamTorrentInfoFromSearch] = []
    for t in free_torrents:
        # filter by size
        if t.size > MAX_TORRENT_CONTENT_SIZE:
            continue
        if t.size < MIN_TORRENT_CONTENT_SIZE:
            continue
        if t.remain_free_duration < timedelta(hours=MIN_REMAIN_FREE_HOURS):
            continue
        if t.seeders < MIN_SEEDERS:
            continue
        if t.leechers / t.seeders < MIN_L2S_RATIO:
            continue
        if TorrentRecord.get_by_mteam_id(t.sitewise_id) is not None:
            # already added
            continue
        
        filtered.append(t)
    
    print(f"{len(filtered)} torrents passed the filtering criteria.")
    
    for t in filtered:
        print(f"{t.sitewise_id} | {t.name} | Size: {t.size / (1024*1024):.1f} MB | Seeders: {t.seeders} | Leechers: {t.leechers}")
    
    # Now add the filtered torrents to qBittorrent
    for t in filtered: # TODO: test only
        print(f"Adding torrent {t.sitewise_id} - {t.name[:8]} {t.small_descr[:16]} ...")
        try:
            torrent_meta = await mteam.download_torrent_metadata(t.sitewise_id)
            torrent = torf.Torrent.read_stream(torrent_meta)
            torrent_hash = torrent.infohash
            
            if not dry_run:
                with db.atomic() as txn:
                    try:
                        await add_torrent_and_verify(torrent_meta, torrent_hash)
                        # Record in database
                        record = TorrentRecord.create(
                            torrent_hash=torrent_hash,
                            mteam_id=t.sitewise_id
                        )
                        # print(f"Succeed. Record ID: {record.record_id}")
                    except:
                        txn.rollback()
                        raise
            else:
                print(f"Dry run mode, not actually adding torrent {t.sitewise_id}.")
            
        except Exception as e:
            print(f"Failed to add torrent {t.sitewise_id}: {e}")
            continue


if __name__ == "__main__":
    parser = ArgumentParser(description="Add free torrents from MTeam to qBittorrent.")
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="If set, do not actually add torrents, just simulate the process."
    )
    
    args = parser.parse_args()
    
    aio.run(main(dry_run=args.dry_run))