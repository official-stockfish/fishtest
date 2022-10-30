import hashlib
import json
from pathlib import Path

worker_dir = Path(__file__).parent.parent.parent / "worker"

FILE_LIST = ["updater.py", "worker.py", "games.py"]
md5dict = {}
for file in FILE_LIST:
    item = worker_dir / file
    bytes = item.read_bytes()
    md5 = hashlib.md5(bytes).hexdigest()
    md5dict[file] = md5

(worker_dir / "md5sums").write_text(json.dumps(md5dict) + "\n")
