#!/usr/bin/env python3
"""Compile actual firmware with real CubeCell AES/CMAC and public hardware mocks."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
CRYPTO = REPO / ".tools/arduino/data/packages/CubeCell/hardware/CubeCell/1.6.0/cores/asr650x/lora/system/crypto"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(REPO/"bridge/chacaico_lora_bridge"))
    from protocol import Frame, RESPONSE, SET_LED, UNKNOWN, encode
    results = []
    with tempfile.TemporaryDirectory(prefix="chacaico-public-firmware-") as directory:
        stage = Path(directory)
        for source in (REPO/"firmware/libraries/ChacaicoNode/src").glob("*.h"):
            shutil.copyfile(source, stage/source.name)
        shutil.copyfile(REPO/"tests/firmware-startup-radio.h", stage/"LoRaWan_APP.h")
        shutil.copyfile(REPO/"tests/firmware_startup_test.cpp", stage/"test.cpp")
        arduino = (REPO/"tests/firmware-stubs/Arduino.h").read_text()
        arduino = arduino.replace("void begin(int){}", "void begin(int){} void flush(){}")
        (stage/"Arduino.h").write_text(arduino)
        (stage/"utilities.h").write_text("""#pragma once
#include <stdint.h>
#include <string.h>
#define MIN(a,b) (((a)<(b))?(a):(b))
static inline void memcpy1(uint8_t*d,const uint8_t*s,uint16_t n){memcpy(d,s,n);}
static inline void memset1(uint8_t*d,uint8_t v,uint16_t n){memset(d,v,n);}
""")
        for name in ("aes", "cmac"):
            subprocess.run(["cc", "-std=c99", "-I"+str(stage), "-I"+str(CRYPTO), "-c",
                            str(CRYPTO/f"{name}.c"), "-o", str(stage/f"{name}.o")], check=True)
        for node in (1, 2):
            shutil.copyfile(REPO/f"firmware/nodes/node_{node}/node_{node}.ino", stage/"node_under_test.ino")
            key = bytes(range((node-1)*16, node*16))
            (stage/"node_config.h").write_text(
                f"#define CHACAICO_NODE_ID {node}\n#define CHACAICO_FREQUENCY 916800000\n"
                + "#define CHACAICO_KEY {"+",".join(str(x) for x in key)+"}\n")
            ack = encode(key, Frame(RESPONSE, node, 1, 1, 1, SET_LED, revision=1, pulse_ms=50, valve=UNKNOWN, led=1))
            (stage/"test_expected_ack.h").write_text(
                "static const uint8_t EXPECTED_ACK[] = {"+",".join(str(v) for v in ack)+"};\n")
            binary = stage/f"node-{node}"
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-I"+str(stage), "-I"+str(CRYPTO),
                            str(stage/"test.cpp"), str(stage/"aes.o"), str(stage/"cmac.o"), "-o", str(binary)], check=True)
            results.append(subprocess.check_output([str(binary)], text=True).strip())
    result = {"passed": True, "nodes": [1, 2], "real_firmware": True, "real_aes_cmac": True,
              "torn_write_cut_points_per_node": 33, "hardware_simulated": True, "results": results}
    print(json.dumps(result, indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    main()
