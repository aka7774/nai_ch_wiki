cd /root/nai_ch_wiki
venv/bin/python seesawiki_back_up/crawl.py backup
today=$(date "+%Y%m%d")
git add .
git commit -m "Backup ${today}"
git push

