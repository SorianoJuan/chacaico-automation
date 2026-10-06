#!/usr/bin/env python3
"""Run the unchanged sketch offline with async fake radio and real CubeCell CMAC.

Only public test keys enter compilation. Does not touch private node_config.h,
node build directories, serial ports, the Pi, or USB devices.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve().parent
CORE = REPO / '.tools/arduino/data/packages/CubeCell/hardware/CubeCell/1.6.0'
CRYPTO = CORE / 'cores/asr650x/lora/system/crypto'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    for path in (CRYPTO/'cmac.c', CRYPTO/'aes.c'):
        if not path.is_file():
            raise SystemExit(f'Requires existing official CubeCell1.6.0 core: {path}')
    from cryptography.hazmat.primitives.cmac import CMAC
    from cryptography.hazmat.primitives.ciphers import algorithms
    import struct
    outputs = []
    with tempfile.TemporaryDirectory(prefix='chacaico-firmware-startup-') as folder:
        stage = Path(folder)
        shutil.copyfile(REPO/'firmware/libraries/ChacaicoNode/src/ChacaicoNode.h', stage/'ChacaicoNode.h')
        shutil.copyfile(SOURCE/'firmware_startup_test.cpp', stage/'firmware_startup_test.cpp')
        shutil.copyfile(SOURCE/'firmware-startup-radio.h', stage/'LoRaWan_APP.h')
        arduino = (REPO/'tests/firmware-stubs/Arduino.h').read_text()
        # Match turnOnRGB's 1ms supply delay; not the physical WS2812 waveform.
        arduino = arduino.replace('rgbEdges.push_back({color,clockMs});',
                                  'rgbEdges.push_back({color,clockMs});clockMs+=1;')
        (stage/'Arduino.h').write_text(arduino)
        (stage/'utilities.h').write_text('''#pragma once
#include <stdint.h>
#include <string.h>
#define MIN(a,b) (((a)<(b))?(a):(b))
static inline void memcpy1(uint8_t *d,const uint8_t *s,uint16_t n){memcpy(d,s,n);}
static inline void memset1(uint8_t *d,uint8_t v,uint16_t n){memset(d,v,n);}
''')
        for name in ('aes','cmac'):
            subprocess.run(['cc','-std=c99','-I'+str(stage),'-I'+str(CRYPTO),'-c',
                            str(CRYPTO/f'{name}.c'),'-o',str(stage/f'{name}.o')], check=True)
        for node in (1,2):
            shutil.copyfile(REPO/f'firmware/nodes/node_{node}/node_{node}.ino', stage/'chacaico_node.ino')
            key = bytes(range((node-1)*16,node*16))
            (stage/'node_config.h').write_text(
                f'#define CHACAICO_NODE_ID {node}\n#define CHACAICO_FREQUENCY 916800000\n'
                + '#define CHACAICO_KEY {'+','.join(str(v) for v in key)+'}\n')
            header = struct.pack('<2sBBHIBB',b'CL',1,1,node,1,1,1)
            mac = CMAC(algorithms.AES(key))
            mac.update(header)
            ack = header + mac.finalize()[:8]
            (stage/'test_expected_ack.h').write_text('static const uint8_t EXPECTED_ACK[20] = {'
                                                     + ','.join(str(v) for v in ack) + '};\n')
            executable = stage/f'node-{node}-test'
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-I'+str(stage),'-I'+str(CRYPTO),
                            str(stage/'firmware_startup_test.cpp'),str(stage/'cmac.o'),
                            str(stage/'aes.o'),'-o',str(executable)],check=True)
            outputs.append(subprocess.check_output([str(executable)],text=True).strip())
    for output in outputs:
        print(output)
    if args.output:
        args.output.write_text(json.dumps({'passed':True,'nodes_tested':[1,2],
            'uses_real_sketch':True,'real_cube_cell_cmac_and_aes':True,'async_fake_radio':True,
            'public_test_keys_only':True,'hardware_used':False,'outputs':outputs},indent=2)+'\n')


if __name__ == '__main__':
    main()
