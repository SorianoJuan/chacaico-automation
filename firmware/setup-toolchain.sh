#!/bin/sh
set -eu
chacaico_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$chacaico_script_dir/.."
command -v arduino-cli >/dev/null
command -v python3 >/dev/null
python3 - <<'CONFIG'
import json
from pathlib import Path
root = Path.cwd().resolve()
dirs = {name: str(root / ".tools" / "arduino" / subdir) for name, subdir in
        (("data", "data"), ("downloads", "downloads"), ("user", "user"))}
for directory in dirs.values():
    Path(directory).mkdir(parents=True, exist_ok=True)
config = {"board_manager": {"additional_urls": [
    "https://raw.githubusercontent.com/HelTecAutomation/CubeCell-Arduino/master/package/package_CubeCell_index.json"]},
    "directories": dirs}
# JSON is accepted by the Arduino CLI YAML configuration parser.
(root / ".tools" / "arduino-cli.yaml").write_text(json.dumps(config, indent=2) + "\n")
CONFIG
arduino-cli core update-index --config-file .tools/arduino-cli.yaml
arduino-cli core install CubeCell:CubeCell@1.6.0 --config-file .tools/arduino-cli.yaml
