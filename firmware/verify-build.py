#!/usr/bin/env python3
"""Verify a local node image and identity without accessing any hardware."""
import argparse
import hashlib
import json
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(root, node):
    folder = root/'firmware/nodes'/f'node_{node}'
    manifest = json.loads((folder/'build/build-manifest.json').read_text())
    profile = json.loads((folder/'profile.json').read_text())
    require(manifest['node_id'] == profile['node_id'] == node, 'Wrong node identity')
    require(manifest['firmware_version'] == profile['firmware_version'], 'Outdated firmware version')
    require(manifest['core'] == profile['core'] == 'CubeCell:CubeCell@1.6.0', 'Unexpected core')
    expected_fqbn = 'CubeCell:CubeCell:CubeCell-Board:LORAWAN_REGION=2,LORAWAN_AT_SUPPORT=1,LORAWAN_RGB=1'
    require(manifest['fqbn'] == profile['fqbn'] == expected_fqbn, 'Unexpected board profile')
    require(manifest['frequency_hz'] == profile['frequency_hz'], 'Unexpected frequency')
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    require(sha(folder/'node_config.h') == manifest['private_header_sha256'], 'Settings changed: rebuild first')
    expected_sources = {f'firmware/nodes/node_{node}/node_{node}.ino',
                        'firmware/libraries/ChacaicoNode/library.properties',
                        *(str(p.relative_to(root)) for p in (root/'firmware/libraries/ChacaicoNode/src').glob('*.h'))}
    require(set(manifest['source_sha256']) == expected_sources, 'Missing or unexpected source checks')
    require(all(sha(root/path) == digest for path,digest in manifest['source_sha256'].items()),
            'Sources changed: rebuild first')
    require(manifest['image'] == 'CubeCell_Board_REGION_AU915_RGB_1.cyacd', 'Unexpected upload image')
    require(sha(folder/'build'/manifest['image']) == manifest['image_sha256'], 'Upload image changed')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', type=int, required=True)
    args = parser.parse_args()
    if not 1 <= args.id <= 65534:
        parser.error('Node ID must be between 1 and 65534')
    try:
        manifest = verify(Path(__file__).resolve().parent.parent,args.id)
    except (OSError,ValueError,KeyError) as error:
        parser.exit(1, f'Build verification failed: {error}\n')
    print(f"Verified node {args.id}, firmware {manifest['firmware_version']}; select the matching physical board.")


if __name__ == '__main__':
    main()
