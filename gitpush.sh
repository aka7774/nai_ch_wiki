cd /root/nai_ch_wiki
venv/bin/python seesawiki_back_up/crawl.py backup
git add .
git commit -m "Backup %date:~0,4%%date:~5,2%%date:~8,2%"
git push

