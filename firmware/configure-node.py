#!/usr/bin/env python3
"""Prepare local CubeCell settings while preserving existing authentication keys."""
import argparse
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", type=int, default=1)
    parser.add_argument("--frequency", type=int, default=None)
    args = parser.parse_args()
    if not 1 <= args.id <= 65534:
        parser.error("Node ID must be between 1 and 65534")
    root = Path(__file__).resolve().parent.parent
    sketch = root / "firmware" / "nodes" / f"node_{args.id}"
    if not (sketch / f"node_{args.id}.ino").is_file():
        parser.error("Create the public sketch/profile for this node first")
    directory = root / ".secrets"
    path = directory / f"node-{args.id}.json"
    config = json.loads(path.read_text()) if path.exists() else {
        "node_id": args.id, "frequency": 916800000, "key": secrets.token_hex(16)}
    if config["node_id"] != args.id or len(bytes.fromhex(config["key"])) != 16:
        parser.error("Existing node configuration is invalid")
    if args.frequency is not None:
        config["frequency"] = args.frequency
    if not 915000000 <= config["frequency"] <= 928000000:
        parser.error("Frequency is outside the configured 915-928 MHz profile")
    nodes = [json.loads(p.read_text()) for p in directory.glob("node-*.json") if p != path]
    nodes.append(config)
    if len({n['node_id'] for n in nodes}) != len(nodes):
        parser.error("Every node must have a unique ID")
    if len({n['key'].lower() for n in nodes}) != len(nodes):
        parser.error("Every node must have its own authentication key")
    if any(n["frequency"] != config["frequency"] for n in nodes):
        parser.error("All nodes in the bridge must use the same frequency")
    os.umask(0o077)
    directory.mkdir(exist_ok=True, mode=0o700)
    path.write_text(json.dumps(config, indent=2) + "\n")
    path.chmod(0o600)
    key = ", ".join(f"0x{byte:02x}" for byte in bytes.fromhex(config["key"]))
    header = sketch / "node_config.h"
    header.write_text(f"#pragma once\n#define CHACAICO_NODE_ID {args.id}\n"
                      f"#define CHACAICO_FREQUENCY {config['frequency']}UL\n"
                      f"#define CHACAICO_KEY {{{key}}}\n")
    header.chmod(0o600)
    options = {"options": {"frequency": config["frequency"], "self_test": False,
               "nodes": [{"id": n["node_id"], "key": n["key"]} for n in
                         sorted(nodes, key=lambda n: n["node_id"])]}}
    options_path = directory / "bridge-options.json"
    options_path.write_text(json.dumps(options, indent=2) + "\n")
    options_path.chmod(0o600)
    print(f"Node {args.id} configured; keys remain in ignored local files.")


if __name__ == "__main__":
    main()
