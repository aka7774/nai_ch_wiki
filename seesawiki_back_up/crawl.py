from scrapy.cmdline import execute
import sys
import pathlib

args = sys.argv

root_dir = pathlib.Path(__file__).parents[1].resolve()
save_file_dir = "back_up"
full_save_file_dir = pathlib.Path(root_dir, save_file_dir)
# 保存先のディレクトリが存在しない場合は、ディレクトリを作成する
if not full_save_file_dir.exists():
    full_save_file_dir.mkdir()
execute(["scrapy", "crawl", args[1], "-a", f"save_dir={full_save_file_dir}"])
