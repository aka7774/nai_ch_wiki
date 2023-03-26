cd /d "C:\sd\nai_ch_wiki"
venv\Scripts\python.exe seesawiki_back_up\crawl.py backup
C:\SD\PortableGit\bin\git.exe add .
C:\SD\PortableGit\bin\git.exe commit -m "Backup %date:~0,4%%date:~5,2%%date:~8,2%"
C:\SD\PortableGit\bin\git.exe push
exit
