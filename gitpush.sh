cd /root/nai_ch_wiki

if ! venv/bin/python seesawiki_back_up/crawl.py backup; then
    echo "Crawler failed. Aborting." >&2
    exit 1
fi

if ! git status --porcelain | grep -q "."; then
    echo "No changes detected. Skipping commit."
    exit 0
fi

today=$(date "+%Y%m%d")
git add .
git commit -m "Backup ${today}"
git push
