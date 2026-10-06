#!/usr/bin/env python3
"""Compile an explicit node into its own ignored build directory; never flash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', type=int, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    node_dir = root / 'firmware/nodes' / f'node_{args.id}'
    profile_path = node_dir / 'profile.json'
    if not profile_path.is_file():
        parser.error('Create a public sketch/profile for this node first')
    profile = json.loads(profile_path.read_text())
    if profile['node_id'] != args.id or profile['core'] != 'CubeCell:CubeCell@1.6.0':
        parser.error('Node profile identity/core mismatch')
    libraries = root / 'firmware/libraries'
    version = next(line.split('=', 1)[1] for line in
                   (libraries/'ChacaicoNode/library.properties').read_text().splitlines()
                   if line.startswith('version='))
    if profile['firmware_version'] != version:
        parser.error('Node profile and shared library versions differ')
    config_file = root/'.tools/arduino-cli.yaml'
    cores = json.loads(subprocess.check_output(
        ['arduino-cli','core','list','--config-file',str(config_file),'--format','json'],text=True))
    platforms = cores.get('platforms', [])
    if not any(p.get('id') == 'CubeCell:CubeCell' and p.get('installed_version') == '1.6.0'
               for p in platforms):
        parser.error('Install the pinned core with firmware/setup-toolchain.sh first')
    subprocess.run([sys.executable,str(root/'firmware/configure-node.py'),'--id',str(args.id)],check=True)
    config = json.loads((root/'.secrets'/f'node-{args.id}.json').read_text())
    if config['frequency'] != profile['frequency_hz']:
        parser.error('Public profile and private frequency differ; review both before compiling')
    os.umask(0o077)
    build = node_dir/'build'
    build.mkdir(exist_ok=True,mode=0o700)
    subprocess.run(['arduino-cli','compile','--config-file',str(config_file),
                    '--fqbn',profile['fqbn'],'--libraries',str(libraries),
                    '--build-path',str(build),str(node_dir)],check=True)
    image = build/'CubeCell_Board_REGION_AU915_RGB_1.cyacd'
    if not image.is_file():
        raise SystemExit('Expected CubeCell upload image is missing')
    sources = [node_dir/f'node_{args.id}.ino',libraries/'ChacaicoNode/src/ChacaicoNode.h',
               libraries/'ChacaicoNode/library.properties']
    manifest = {'node_id':args.id,'firmware_version':version,'core':profile['core'],
                'fqbn':profile['fqbn'],'frequency_hz':config['frequency'],
                'image':image.name,'image_sha256':sha256(image),
                'private_header_sha256':sha256(node_dir/'node_config.h'),
                'source_sha256':{str(p.relative_to(root)):sha256(p) for p in sources}}
    (build/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (build/'build-manifest.json').chmod(0o600)
    print(f'Node {args.id} firmware {version} built in {build.relative_to(root)}; no hardware programmed.')


if __name__ == '__main__':
    main()
