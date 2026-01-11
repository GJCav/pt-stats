from pt_stats.db.database import DatabaseModel
import peewee
from playhouse.hybrid import hybrid_property
from datetime import datetime, timezone
import humanize as H
from typing import TYPE_CHECKING


class Sites(DatabaseModel):
    id = peewee.AutoField(primary_key=True)
    name = peewee.CharField(unique=True)
    url = peewee.CharField()

    # type hints for backrefs
    if TYPE_CHECKING:
        torrents: peewee.ModelSelect


class Torrents(DatabaseModel):
    id = peewee.AutoField(primary_key=True)
    torrent_hash = peewee.CharField(unique=True)
    name = peewee.CharField()
    site = peewee.ForeignKeyField(Sites, backref="torrents")
    sitewise_id = peewee.CharField()  # The torrent ID as per the site
    url = peewee.CharField()  # URL to the torrent page

    size_bytes = peewee.BigIntegerField()
    added_time = peewee.TimestampField(
        resolution=1, utc=True, default=lambda: datetime.now(timezone.utc)
    )
    delete_time = peewee.TimestampField(
        resolution=1, null=True, utc=True, default=None
    )  # resolution=1 means seconds

    # Type hint for backref
    if TYPE_CHECKING:
        stats: peewee.ModelSelect
        select_computed: peewee.ModelSelect

    class Meta:
        indexes = (
            (("site_id", "sitewise_id"), True),  # (site_id, sitewise_id), unique
            (
                ("delete_time",),
                False,
            ),  # (delete_time,), not unique, make queries for non-deleted torrents faster
        )


class TorrentStats(DatabaseModel):
    id = peewee.AutoField(primary_key=True)
    torrent = peewee.ForeignKeyField(Torrents, backref="stats")

    recorded_time = peewee.TimestampField(resolution=1, utc=True)
    connected_seeders = peewee.IntegerField()
    swarm_seeders = peewee.IntegerField()
    connected_leechers = peewee.IntegerField()
    swarm_leechers = peewee.IntegerField()

    uploaded_bytes = peewee.BigIntegerField()
    downloaded_bytes = peewee.BigIntegerField()

    class Meta:
        indexes = (
            (("torrent", "recorded_time"), True),  # (torrent, recorded_time), unique
        )


class StatsComputed(DatabaseModel):
    """
    Note: Deleted torrents are excluded from this view.
    """

    stat_id = peewee.IntegerField()
    torrent_id = peewee.IntegerField()

    ratio = peewee.FloatField()
    popularity = peewee.FloatField()
    active_months = peewee.FloatField()
    recorded_time = peewee.TimestampField(resolution=1, utc=True)

    class Meta:
        primary_key = False
        table_name = "view_stats_computed"

    @staticmethod
    def create_view():
        conn = StatsComputed._meta.database  # type: ignore
        conn.execute_sql(CREATE_VIEW_STATS_COMPUTED)

    def __str__(self):
        return (
            f"StatsComputed(stat_id={self.stat_id}, torrent_id={self.torrent_id}, "
            f"recorded_time={H.naturaltime(self.recorded_time)}, "  # type: ignore
            f"ratio={self.ratio:.1f}, "
            f"active_months={self.active_months:.1f}, popularity={self.popularity:.1f})"
        )


CREATE_VIEW_STATS_COMPUTED = r"""
CREATE VIEW IF NOT EXISTS view_stats_computed AS
SELECT
    ts.id as stat_id,
    ts.torrent_id,
    ts.recorded_time,
    
    -- Ratio Calculation (return 0 if downloaded_bytes is 0)
    CASE
        WHEN ts.downloaded_bytes > 0 THEN CAST(ts.uploaded_bytes AS REAL) / ts.downloaded_bytes
        ELSE 0
    END AS ratio,
    
    -- Active Time (Months), 2592000 ~ 30 days in seconds
    (ts.recorded_time - t.added_time) / 2592000.0 AS active_months,
    
    -- Popularity Calculation
    CASE
        WHEN (ts.recorded_time - t.added_time) > 0
        THEN
            (
                -- the ratio part
                CASE
                    WHEN ts.downloaded_bytes > 0 
                    THEN CAST(ts.uploaded_bytes AS REAL) / ts.downloaded_bytes 
                    ELSE 0 
                END
            ) / ((ts.recorded_time - t.added_time) / 2592000.0)
        ELSE 0
    END AS popularity
FROM torrentstats ts
JOIN torrents t ON ts.torrent_id = t.id
WHERE t.delete_time IS NULL
"""


class TorrentsComputed(DatabaseModel):
    """
    Note: Deleted torrents are excluded from this view.
    """

    torrent = peewee.ForeignKeyField(  # column_name = 'torrent_id'
        Torrents,
        backref="select_computed",
        on_delete="NO ACTION",  # views don't support cascading deletes, this is just for python side
        constraints=[
            peewee.SQL("PRIMARY KEY")
        ],  # Virtual PK for Peewee's internal logic
    )
    torrent_id = peewee.IntegerField()
    latest_stat_id = peewee.IntegerField()
    recorded_time = peewee.TimestampField(resolution=1, utc=True)

    # Handy fields
    name = peewee.CharField()
    ratio = peewee.FloatField()
    popularity = peewee.FloatField()
    active_months = peewee.FloatField()

    class Meta:
        primary_key = False
        table_name = "view_torrents_computed"

    @staticmethod
    def create_view():
        conn = TorrentsComputed._meta.database  # type: ignore
        conn.execute_sql(CREATE_VIEW_TORRENTS_COMPUTED)

    def __str__(self):
        return (
            f"TorrentsComputed(torrent_id={self.torrent_id}, latest_stat_id={self.latest_stat_id}, "
            f"recorded_time={H.naturaltime(self.recorded_time)}, "  # type: ignore
            f"ratio={self.ratio:.1f}, "
            f"active_months={self.active_months:.1f}, "
            f"popularity={self.popularity:.1f})"
        )


CREATE_VIEW_TORRENTS_COMPUTED = r"""
CREATE VIEW IF NOT EXISTS view_torrents_computed AS
WITH latest_stats AS (
    SELECT 
        ts.*,
        ROW_NUMBER() 
        OVER (
            PARTITION BY ts.torrent_id 
            ORDER BY ts.recorded_time DESC
        ) AS rn
    FROM torrentstats ts
)
SELECT
    t.id AS torrent_id,
    ls.id AS latest_stat_id,
    ls.recorded_time,
    
    t.name as name,
    
    -- Math Logic (Duplicated here for performance, to avoid calculating on discarded rows)
    -- ratio
    CASE 
        WHEN ls.downloaded_bytes > 0 
        THEN CAST(ls.uploaded_bytes AS REAL) / ls.downloaded_bytes 
        ELSE 0 
    END AS ratio,
    
    -- active_months
    (ls.recorded_time - t.added_time) / 2592000.0 AS active_months,
    
    -- popularity
    CASE 
        WHEN (ls.recorded_time - t.added_time) > 0 
        THEN (
            -- the ratio part
            CASE 
                WHEN ls.downloaded_bytes > 0 
                THEN CAST(ls.uploaded_bytes AS REAL) / ls.downloaded_bytes 
                ELSE 0 
            END
        ) / ((ls.recorded_time - t.added_time) / 2592000.0)
        ELSE 0 
    END AS popularity
FROM torrents t
JOIN latest_stats ls ON t.id = ls.torrent_id
WHERE t.delete_time IS NULL
  AND ls.rn = 1
"""
