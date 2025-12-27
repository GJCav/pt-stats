# pt-stats

**Note:** This project is currently under development. Features and functionality may change.

## Current features

**Automatically adding free torrents from M-Team to qBittorrent**

Script: [`app/add_free_torrents_to_qbit.py`](app/add_free_torrents_to_qbit.py)

Minimal configuration:

``` env
# Create a .env file with the following content:

## QBittorrent settings
# URL for QBittorrent Web UI API
QBIT_API_URL=<your_url>

# If you have configured the "Bypass authentication for clients in whitelisted IP subnets" option in qBittorrent Web UI settings, you may leave the username and password empty.
QBIT_API_USERNAME=<your_username>
QBIT_API_PASS=<your_password>


## M-Team settings
MTEAM_API_KEY=<your_mteam_api_key>

# (Optional) If your ISP bans access to M-Team, you may need to set up a proxy.
# MTEAM_PROXY=http://xxx/
```

For more configuration options, please refer to the [script source code](app/add_free_torrents_to_qbit.py).


Run the script:

``` bash
cd path/to/pt-stats

# Dry run (without adding torrents to qBittorrent)
python app/add_free_torrents_to_qbit.py --dry-run

# Actual run (adding torrents to qBittorrent)
python app/add_free_torrents_to_qbit.py
```

Then, configure a cron job to run the script periodically.

Note: 
- The script saves its data in the `qbt_tasks.db`, whose location can be configured via the `DB_PATH` environment variable. By default, it is created in the current working directory.

## Related projects

## All-in-one solutions

- [MoviePiloe](https://github.com/jxxghp/MoviePilot): an all-in-one solution for searching, scraping, downloading, and managing movies and TV shows from various torrent sites, including M-Team. It has a user-friendly web interface and supports multiple download clients. However, it lacks open documentation, relies on private QQ/WeChat groups for support, and requires sophisticated authentication to unlock all features. Another reason to refrain from it is that it "embeds" the downloader (like `qBittorrent` or `transmission`) inside the application, which makes it too cumbersome for my use case, where my philosophy is to keep things modular and separate.
- [IYUU](https://iyuu.cn/): another all-in-one solution like *MoviePilot*, sharing the same cons mentioned above. In my trial to add the M-Team into *IYUU*, it failed without useful error messages. So, just give up on it.

## M-Team related

Official documentation:

- [https://wiki.m-team.cc/zh-tw/api](https://wiki.m-team.cc/zh-tw/api): which explicitly states that this [API documentation](https://test2.m-team.cc/api/doc.html) may be inconsistent with the actual API behavior, and recommends users to rely on the devtools of web browsers.
- [API documentation](https://test2.m-team.cc/api/doc.html): the official but may-be-inconsistent API documentation.

Python wrapper around M-Team API:

- [mteamapi](https://github.com/amintong/mteam_python): the most up-to-date Python wrapper around M-Team API, but still lagging behind the actual API behavior. I cannot even run the demo provided in the repository README.
- [mteam-active-top-rss](https://github.com/xiaohaiGreen/mteam-active-top-rss): a project that tracks active torrents on M-Team and generates an RSS feed. However, it seems that the code has bugs and the docker container fails to start.

**Key takeaways**:
- Keeping up with M-Team API changes is unrealistic for third-party developers.
- Just wrap around the APIs that are necessary for your use case, and be prepared to fix things when M-Team updates their API.