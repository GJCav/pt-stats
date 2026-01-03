# pt-stats

**Note:** This project is currently under development. Features and functionality may change.

## Current features

- Scrape free torrents from M-Team.
- Add the torrents to qBitTorrent automatically via its WebUI API.
- Record the seeding statistics of the torrents in a local SQLite database.
- When downloaded torrents exceed the disk quota, remove "unpopular" torrents based on seeding statistics.
- **Do the above tasks periodically in the background.**

## Usage

**Installation**

```bash
git clone https://github.com/GJCav/pt-stats.git
cd pt-stats
pip install .
```

**Settings**

Generate the settings template:

```bash
cd pt-stats/app
python app.py settings template -o settings.yaml
```

Edit the `settings.yaml` file according to your environment and preferences. The
file is well-documented. Bellow are just a snippet from the file:

```yaml
# Path to the SQLite database file. Set to ':memory:' to use an in-memory database
# for testing purposes.
db_path: qbt_tasks.db

# Disk quota for torrents added by this application in MB. When the total size of
# the torrents added by this application exceeds this limit, old torrents will be
# removed to free up space. Set to 0 for no limit. Default is 204800 (200 GB).
disk_quota_mb: 204800

# Settings related to the daemon mode behavior.
daemon:
  # Interval in hours between attempts to add new free torrents. Default is 6.0
  # hours.
  add_free_torrent_interval_hours: 6.0

  # ... other settings ...
```

To check the current settings, you can run:

```bash
python app.py settings show

# python app.py settings show -c  # show with comments
```

When you forget the meaning of a setting, you can always print the template again:

```bash
python app.py settings template
```

**Run as a daemon**

The application can run as a daemon, performing free torrent addition,
statistics recording, and torrent pruning (on disk quota exceedance)
periodically in the background.

```bash
python app.py daemon
```

Currently, the logging system is very basic. To persist logs, you can redirect
the output to a file:

```bash
python app.py daemon | tee pt-stats.log
```

**Run individual actions**

You can also run individual actions without the daemon mode. This is useful for
checking the functionality or for one-time operations.

```bash
# Add free torrents from M-Team
python app.py add-free
python app.py add-free -d  # dry-run mode, do not actually add torrents

# Sample seeding statistics
python app.py sample-stats

# Prune torrents
python app.py prune
```

**Use `-h` wisely to get help on commands**

The application outputs helpful usage information when you run commands with the `-h`
flag. For example:

```bash
python app.py -h            # which shows all available sub-commands
python app.py add-free -h   # which shows help for the `add-free` sub-command
```


## Related projects

### All-in-one solutions

- [MoviePiloe](https://github.com/jxxghp/MoviePilot): an all-in-one solution for searching, scraping, downloading, and managing movies and TV shows from various torrent sites, including M-Team. It has a user-friendly web interface and supports multiple download clients. However, it lacks open documentation, relies on private QQ/WeChat groups for support, and requires sophisticated authentication to unlock all features. Another reason to refrain from it is that it "embeds" the downloader (like `qBittorrent` or `transmission`) inside the application, which makes it too cumbersome for my use case, where my philosophy is to keep things modular and separate.
- [IYUU](https://iyuu.cn/): another all-in-one solution like *MoviePilot*, sharing the same cons mentioned above. In my trial to add the M-Team into *IYUU*, it failed without useful error messages. So, just give up on it.

### M-Team related

Official documentation:

- [https://wiki.m-team.cc/zh-tw/api](https://wiki.m-team.cc/zh-tw/api): which explicitly states that this [API documentation](https://test2.m-team.cc/api/doc.html) may be inconsistent with the actual API behavior, and recommends users to rely on the devtools of web browsers.
- [API documentation](https://test2.m-team.cc/api/doc.html): the official but may-be-inconsistent API documentation.

Python wrapper around M-Team API:

- [mteamapi](https://github.com/amintong/mteam_python): the most up-to-date Python wrapper around M-Team API, but still lagging behind the actual API behavior. I cannot even run the demo provided in the repository README.
- [mteam-active-top-rss](https://github.com/xiaohaiGreen/mteam-active-top-rss): a project that tracks active torrents on M-Team and generates an RSS feed. However, it seems that the code has bugs and the docker container fails to start.

**Key takeaways**:
- Keeping up with M-Team API changes is unrealistic for third-party developers.
- Just wrap around the APIs that are necessary for your use case, and be prepared to fix things when M-Team updates their API.