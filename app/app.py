import httpx
import peewee
from pt_stats.pt_sites.mteam import MTeamTorrentInfoFromSearch
from settings import load_settings, AppSettings
import sys
import cyclopts
from cyclopts import App as CliApp, Parameter
from typing import Annotated, Any, Literal, Protocol
import attrs
from qbittorrentapi import Client as QbtClient
import qbittorrentapi as qbt_types
import torf
import asyncio as aio
from pt_stats.pt_sites import MTeamClient
from datetime import timedelta, datetime, timezone
import pt_stats.db as db
import pt_stats.db.models as db_schemas
from utils import naturalsize, shorten, utc_now
from rich.table import Table as RichTable
from rich.console import Console
from rich.progress import track
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pendulum

cli = CliApp("pt-stats")

cli_setting = CliApp("settings", help="Manage application settings")
cli.command(cli_setting)

cli_report = CliApp("report", help="Report statistics about the torrents")
cli.command(cli_report)

@cli.default
def print_help():
    cli.help_print()


@cli.command
def add_free(
    dry_run: Annotated[bool, Parameter(name=["--dry-run", '-d'], help="Dry run mode, do not actually add torrents")] = False
):
    """Add free torrents from MTeam to qBittorrent."""
    settings = load_settings("settings.yaml")
    app = App.create(settings)
    
    aio.run(app.add_free_torrents(dry_run=dry_run))


@cli.command
def sample_stats():
    """Sample torrent stats from qBittorrent and store them in the database."""
    settings = load_settings("settings.yaml")
    app = App.create(settings)
    
    aio.run(app.qbt_sample_stats())


@cli.command
def daemon(
    dry_run: Annotated[bool, Parameter(name=["--dry-run", '-d'], help="Dry run mode, do not actually add torrents")] = False
):
    """Run the application in daemon mode."""
    settings = load_settings("settings.yaml")
    app = App.create(settings)
    
    async def job_add_free_torrents():
        print("\n=== Adding Free Torrents Job Started ===")
        print(f"Time: {datetime.now().isoformat()}")
        await app.add_free_torrents(dry_run=dry_run)
        
    async def job_sample_stats():
        # print("\n=== Sampling Torrent Stats Job Started ===")
        # print(f"Time: {datetime.now().isoformat()}")
        await app.qbt_sample_stats(quiet=True)
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        job_add_free_torrents,
        'interval',
        hours=settings.daemon.add_free_torrent_interval_hours,
        next_run_time=datetime.now() + timedelta(seconds=10)
    )
    scheduler.add_job(
        job_sample_stats,
        'interval',
        minutes=settings.daemon.sample_stats_interval_minutes,
        next_run_time=datetime.now()
    )
    
    async def main():
        scheduler.start()
        
        # Keep the main thread alive.
        try:
            await aio.Event().wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            scheduler.shutdown()
            
    aio.run(main())


@cli.command
def prune(
    space_to_free: Annotated[float, Parameter(name=["--space-to-free", '-s'], help="Space to free in GiB")] = 0,
    dry_run: Annotated[bool, Parameter(name=["--dry-run", '-d'], help="Dry run mode, do not actually remove torrents")] = False
):
    """Prune torrents from qBittorrent to comply with disk quota."""
    settings = load_settings("settings.yaml")
    app = App.create(settings)
    
    aio.run(app.qbt_prune(reserve_space=int(space_to_free * 1024**3), dry_run=dry_run))


@cli_setting.command()
def template(
    no_comments: Annotated[bool, Parameter(name=["--no-comments", '-n'], help="Do not include comments in the generated template")] = False,
    output: Annotated[str | None, Parameter(name=["--output", '-o'], help="Output file path")] = None,
    theme: Annotated[
        Literal['auto', 'dark', 'light'], 
        Parameter(name=["--theme", '-t'], help="Syntax highlighting theme to use")
    ] = "auto"
):
    """Generate the settings template to stdout."""
    
    template = AppSettings()
    # Output to file if specified
    if output:
        with open(output, "w") as f:
            template.to_yaml(f, fill_default_comments=not no_comments)
        return
    
    # Output to stdout with syntax highlighting
    import io
    from rich.syntax import Syntax
    import darkdetect
    
    buf = io.StringIO()
    template.to_yaml(buf, fill_default_comments=not no_comments)
    
    if theme == "auto":
        theme = "dark" if darkdetect.isDark() else "light"
    
    if theme == "dark":
        theme = "github-dark" # type: ignore
    elif theme == "light":
        theme = "staroffice" # type: ignore
    
    syntax = Syntax(buf.getvalue(), "yaml", theme=theme)
    
    console = Console()
    console.print(syntax)


@cli_setting.command()
def show(
    path: Annotated[str, Parameter(name=["--path", '-p'], help="Path to the settings file")] = "settings.yaml",
    comments: Annotated[bool, Parameter(name=["--comments", '-c'], help="Include comments in the output")] = False
):
    """Show the current application settings."""
    settings = load_settings(path)
    settings.to_yaml(sys.stdout, enable_comments=comments)


@cli_report.command()
def transfer(
    minutes: Annotated[
        int,
        Parameter(
            name=["--minutes", '-m'],
            help="Number of minutes to look back for transfer calculation",
            group="Lookback"
        ),
    ] = 0,
    hours: Annotated[
        int,
        Parameter(
            name=["--hours", '-H'],
            help="Number of hours to look back for transfer calculation",
            group="Lookback"
        ),
    ] = 0,
    days: Annotated[
        int, 
        Parameter(
            name=["--days", '-d'], 
            help="Number of days to look back for transfer calculation",
            group="Lookback"
        ),
    ] = 0,
    
    start: Annotated[
        datetime,
        Parameter(
            name=["--start", '-s'],
            help="Start datetime for transfer calculation",
            group="Duration",
        ),
    ] = utc_now() - timedelta(days=1),
    end: Annotated[
        datetime,
        Parameter(
            name=["--end", '-e'],
            help="End datetime for transfer calculation",
            group="Duration",
        ),
    ] = utc_now(),
):
    settings = load_settings("settings.yaml")
    app = App.create(settings)
    
    if minutes > 0 or hours > 0 or days > 0:
        delta = timedelta(days=days, hours=hours, minutes=minutes)
        end = utc_now()
        start = end - delta
        
    if start.tzinfo is None:
        start = start.replace(tzinfo=pendulum.local_timezone())
    if end.tzinfo is None:
        end = end.replace(tzinfo=pendulum.local_timezone())
    
    print("Calculating transfer deltas from:")
    print(f"Start:    {start.astimezone(pendulum.local_timezone()).isoformat()}")
    print(f"End:      {end.astimezone(pendulum.local_timezone()).isoformat()}")
    print(f"Duration: {end - start}")
    
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    
    result = app.calc_transfer_deltas(start=start, end=end)
    
    table = RichTable(
        title="Transfer Statistics for Torrents",
    )
    table.add_column("Hash", overflow='ellipsis', max_width=12, no_wrap=True)
    table.add_column("Down")
    table.add_column("Up")
    table.add_column("Ratio")
    table.add_column("Name", overflow='ellipsis', max_width=48, no_wrap=True)
    
    for t in result:
        down = t.downloaded_delta
        up = t.uploaded_delta
        ratio = (up / down) if down > 0 else (float('inf') if up > 0 else 0.0)
        
        table.add_row(
            t.torrent_hash,
            naturalsize(down),
            naturalsize(up),
            f"{ratio:.1f}" if ratio != float('inf') else "∞",
            t.name
        )
    console = Console()
    console.print(table)
    
    accu_down = sum(t.downloaded_delta for t in result)
    accu_up = sum(t.uploaded_delta for t in result)
    accu_ratio = (accu_up / accu_down) if accu_down > 0 else (float('inf') if accu_up > 0 else 0.0)
    print("\n=== Accumulated Transfer Statistics ===")
    print(f"Total Downloaded: {naturalsize(accu_down)}")
    print(f"Total Uploaded:   {naturalsize(accu_up)}")
    print(f"Overall Ratio:    {accu_ratio:.1f}")

#####

@attrs.define
class App:
    settings: AppSettings
    qbt: QbtClient
    mteam: MTeamClient
    db_ok: bool
    
    _mteam_site: db_schemas.Sites = attrs.field(default=None, init=False)
    
    @staticmethod
    def create(settings: AppSettings) -> "App":
        # Initialize qBittorrent client
        qbt = QbtClient(
            host=settings.qbittorrent.api_base,
            username=settings.qbittorrent.username,
            password=settings.qbittorrent.password,
        )
        try:
            qbt.auth_log_in()
        except Exception as e:
            print(f"Failed to connect to qBittorrent Web API: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Initialize MTeam client
        mteam = MTeamClient(
            api_base=settings.mteam.api_base,
            api_key=settings.mteam.api_key,
            http_client=httpx.AsyncClient(proxy=settings.mteam.proxy)
        )
        
        # Initialize database
        db.initialize(settings.db_path)
        db.conn.create_tables([
            db_schemas.Sites,
            db_schemas.Torrents,
            db_schemas.TorrentStats,
        ])
        
        db_schemas.StatsComputed.create_view()
        db_schemas.TorrentsComputed.create_view()
        
        return App(
            settings=settings,
            qbt=qbt,
            mteam=mteam,
            db_ok=True
        )
    
    
    async def add_free_torrents(self, dry_run: bool = False):
        free_torrents = await self.mteam.list_latest_free_torrents()
        print(f"Found {len(free_torrents)} free torrents on MTeam.")
        
        # Filtering
        filtered: list[MTeamTorrentInfoFromSearch] = []
        cfg = self.settings.filters
        for t in free_torrents:
            # filter by size
            if t.size > cfg.max_torrent_size:
                continue
            if t.size < cfg.min_torrent_size:
                continue
            # filter by free duration
            if t.remain_free_duration < timedelta(hours=cfg.min_remain_free_hours):
                continue
            # filter by seeders & leechers
            if t.seeders < cfg.min_seeders:
                continue
            if t.leechers / t.seeders < cfg.min_l2s_ratio:
                continue
            # filter by existing records
            if self.get_mteam_torrent(t.sitewise_id) is not None:
                # already added
                continue
            # if disk quota exceeded, skip
            if self.settings.disk_quota > 0 and t.size > self.settings.disk_quota:
                continue
            
            filtered.append(t)
        
        # select top first N torrents that fit in the disk quota
        if self.settings.disk_quota > 0:
            selected: list[MTeamTorrentInfoFromSearch] = []
            accumulated_size = 0
            for t in filtered:
                if accumulated_size + t.size > self.settings.disk_quota:
                    break
                selected.append(t)
                accumulated_size += t.size
            filtered = selected
        
        
        table = RichTable(
            title="Torrents to be Added", 
        )
        table.add_column("ID", justify="right")
        table.add_column("Size")  # size
        table.add_column("Accu.Sz.")  # accumulated size
        table.add_column("▲")  # seeders
        table.add_column("▼")  # leechers
        table.add_column("Free")
        table.add_column("Name", overflow='ellipsis', max_width=48, no_wrap=True)
        _acc = 0
        for t in filtered:
            _acc += t.size
            table.add_row(
                t.sitewise_id,
                naturalsize(t.size),
                naturalsize(_acc),
                str(t.seeders),
                str(t.leechers),
                f"{t.remain_free_duration.total_seconds() / 3600:.1f} hrs",
                t.name
            )
        console = Console()
        console.print(table)
        
        required_space = sum(t.size for t in filtered)
        await self.qbt_prune(reserve_space=required_space, dry_run=dry_run)
        
        if dry_run:
            print("Dry run mode, not actually adding torrents.")
            return
        
        # Adding torrents
        for t in track(filtered, description="Adding torrents...", transient=True):
            try:
                torrent_meta = await self.mteam.download_torrent_metadata(t.sitewise_id)
                torrent = torf.Torrent.read_stream(torrent_meta)
                torrent_hash = torrent.infohash
                
                with db.conn.atomic() as txn:
                    await self.qbt_add_torrent_and_verify(
                        torrent_meta_bytes=torrent_meta, 
                        torrent_hash=torrent_hash, 
                        # qBittorrent may get a different name from the .torrent
                        # file, so we use the original name here.
                        name=t.name
                    )
                    # Record in database
                    db_schemas.Torrents.create(
                        torrent_hash=torrent_hash,
                        name=t.name,
                        site=self.site_mteam,
                        sitewise_id=t.sitewise_id,
                        # MTeam use different hosts for different regions,
                        # so we just use a relative URL here.
                        url="/detail/" + t.sitewise_id, 
                        size_bytes=t.size,
                    )
                    # print(f"Succeed. Record ID: {record.record_id}")
                
            except Exception as e:
                print(f"Failed to add torrent {t.sitewise_id}: {e}")
                continue
    
    
    async def qbt_add_torrent_and_verify(self, *, torrent_meta_bytes: bytes, torrent_hash: str, name: str, timeout=20):
        """
        `client.torrents_add` returns `Ok` even for failed additions, so 
        we need to verify if the torrent was actually added.
        
        If failed, an exception is raised.
        """
        if not torrent_meta_bytes:
            raise ValueError("Empty torrent metadata bytes provided.")
        
        if not torrent_hash:
            raise ValueError("Empty torrent hash provided.")
        
        qbt = self.qbt
        res = qbt.torrents_add(
            torrent_files=torrent_meta_bytes,
            rename=name,
            upload_limit=self.settings.qbittorrent.upload_speed_limit,
            download_limit=self.settings.qbittorrent.download_speed_limit,
            category=self.settings.qbittorrent.save_to_category
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

    
    async def qbt_sample_stats(self, quiet: bool = False):
        """
        Sample torrent stats from qBittorrent and store them in the database.
        """
        alive_torrents = {
            t.torrent_hash: t 
            for t in list(db_schemas.Torrents.select().where(
                db_schemas.Torrents.delete_time.is_null()
            ))
        }        
        
        torrent_info_list: qbt_types.TorrentInfoList = [] # type: ignore
        sample_times = []
        
        batch_size = 32
        torrent_hashes = list(alive_torrents.keys())
        for i in (
            (lambda x: x) if quiet else
            (lambda x: track(x, description="Sampling torrent stats...", transient=True))
        )(range(0, len(torrent_hashes), batch_size)):
            batch_hashes = torrent_hashes[i:i+batch_size]
            infos = self.qbt.torrents_info(torrent_hashes=batch_hashes)
            torrent_info_list.extend(infos)
            sample_times.extend([utc_now()] * len(infos))
        
        with db.conn.atomic():
            for info, sample_time in zip(torrent_info_list, sample_times):
                t = alive_torrents[info.hash]
                
                db_schemas.TorrentStats.create(
                    torrent=t,
                    recorded_time=sample_time,
                    connected_seeders=info.num_seeds,
                    swarm_seeders=info.num_complete,
                    connected_leechers=info.num_leechs,
                    swarm_leechers=info.num_incomplete,
                    uploaded_bytes=info.uploaded,
                    downloaded_bytes=info.downloaded
                )
    
    
    async def qbt_prune(self, reserve_space: int, dry_run: bool = False):
        """
        Prune torrents from qBittorrent to free up the specified space (in bytes).
        """
        if self.settings.disk_quota <= 0:
            # No disk quota set
            return
        
        total_used = self.get_total_used_space()
        print(f"Disk quota: {naturalsize(self.settings.disk_quota)}, "
              f"currently used: {naturalsize(total_used)}, "
              f"need to reserve: {naturalsize(reserve_space)}")
        
        if total_used + reserve_space <= self.settings.disk_quota:
            # No need to prune
            print("No need to prune torrents.")
            return
        
        to_free = (total_used + reserve_space) - self.settings.disk_quota
        
        candidate_torrents = list(
            db_schemas.Torrents.select(
                db_schemas.Torrents,
                db_schemas.TorrentsComputed.popularity,
                db_schemas.TorrentsComputed.ratio,
            )
            .join(db_schemas.TorrentsComputed, attr='computed')
            .where(db_schemas.Torrents.delete_time.is_null())
            .order_by(db_schemas.TorrentsComputed.popularity.asc())
        )
        
        accumulated_freed = 0
        for idx, t in enumerate(candidate_torrents):
            if accumulated_freed >= to_free:
                break
            
            accumulated_freed += t.size_bytes
            
        to_prune = candidate_torrents[:idx+1]
        
        print(f"The following {len(to_prune)} torrents will be pruned to free up {naturalsize(accumulated_freed)}:")
        table = RichTable(
            title="Torrents to be Pruned",
        )
        table.add_column("Popularity", justify="right")
        table.add_column("Ratio")
        table.add_column("Size")
        table.add_column("Accu.Sz.")
        table.add_column("Hash", overflow='ellipsis', max_width=12, no_wrap=True)
        table.add_column("Name", overflow='ellipsis', max_width=48, no_wrap=True)
        
        _acc = 0
        for t in to_prune:
            _acc += t.size_bytes
            table.add_row(
                f"{t.computed.popularity:.1f}",
                f"{t.computed.ratio:.1f}",
                naturalsize(t.size_bytes),
                naturalsize(_acc),
                t.torrent_hash,
                t.name
            )
        console = Console()
        console.print(table)
        
        if dry_run:
            print("\nDry run mode, not actually removing torrents.")
            return
        
        for t in track(to_prune, description="Pruning torrents...", transient=True):
            with db.conn.atomic():
                # Remove from qBittorrent
                try:
                    self.qbt.torrents_delete(
                        torrent_hashes=t.torrent_hash,
                        delete_files=True
                    )
                    # Mark as deleted in database
                    t.delete_time = utc_now()
                    t.save()
                except Exception as e:
                    print(f"Failed to prune torrent {t.torrent_hash} | {shorten(t.name, 48)}: {e}")
                    continue
        

    @property
    def site_mteam(self) -> db_schemas.Sites:
        if self._mteam_site is not None:
            return self._mteam_site
        
        self._mteam_site, created = db_schemas.Sites.get_or_create(
            name="MTeam",
            url="https://m-team.cc/"
        )
        return self._mteam_site
    
    
    def get_mteam_torrent(self, sitewise_id: str) -> db_schemas.Torrents | None:
        torrent = db_schemas.Torrents.get_or_none(
            (db_schemas.Torrents.site == self.site_mteam) &
            (db_schemas.Torrents.sitewise_id == sitewise_id)
        )
        return torrent
    
    
    def get_total_used_space(self) -> int:
        """
        Get the total used space occupied by all torrents.
        """
        total = db_schemas.Torrents.select(
            peewee.fn.SUM(db_schemas.Torrents.size_bytes)
        ).where(
            db_schemas.Torrents.delete_time.is_null()
        ).scalar()
        return total or 0
    
    
    def calc_transfer_deltas(self, start: datetime, end: datetime) -> list[Any]:
        """
        Calculate the transfer deltas (uploaded and downloaded bytes) for
        torrents between the given start and end times.
        
        Returns a list of Torrents with additional attributes:
            - uploaded_delta: int
            - downloaded_delta: int
        
        Raises ValueError if start or end datetime does not have tzinfo set.
        """
        
        # start, end should be UTC timestamps or 
        # have tzinfo set to be converted to UTC.
        def normalize_dt(dt: datetime, name: str) -> datetime:
            if dt.tzinfo is None:
                raise ValueError(f"Datetime '{name}' must have tzinfo set.")
            return dt.astimezone(tz=timezone.utc)

        start = normalize_dt(start, "start")
        end = normalize_dt(end, "end")
        
        # Magical SQL query to compute deltas
        TorrentStats = db_schemas.TorrentStats
        Torrents = db_schemas.Torrents
        fn = peewee.fn
        
        StartStats = TorrentStats.alias()
        EndStats = TorrentStats.alias()
        
        boundary = (
            TorrentStats
            .select(
                TorrentStats.torrent,
                fn.MIN(TorrentStats.recorded_time).alias('min_ts'),
                fn.MAX(TorrentStats.recorded_time).alias('max_ts')
            )
            .where(
                (TorrentStats.recorded_time >= start) &
                (TorrentStats.recorded_time <= end)
            )
            .group_by(TorrentStats.torrent)
            .cte('boundary')
        )
        
        query = (
            Torrents
            .select(
                Torrents,
                # deltas
                (EndStats.uploaded_bytes - StartStats.uploaded_bytes).alias('uploaded_delta'),
                (EndStats.downloaded_bytes - StartStats.downloaded_bytes).alias('downloaded_delta'),
            )
            # Torrents -> boundary
            .join(boundary, on=(Torrents.id == boundary.c.torrent_id))
            # boundary -> StartStats
            .join(
                StartStats,
                on=(
                    (StartStats.torrent == boundary.c.torrent_id) &
                    (StartStats.recorded_time == boundary.c.min_ts)
                )
            )
            # boundary -> EndStats
            .join(
                EndStats,
                on=(
                    (EndStats.torrent == boundary.c.torrent_id) &
                    (EndStats.recorded_time == boundary.c.max_ts)
                )
            )
            .with_cte(boundary)
        )
        
        results = list(query)
        return results
        


if __name__ == "__main__":
    cli()
