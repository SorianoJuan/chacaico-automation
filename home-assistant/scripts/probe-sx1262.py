#!/usr/bin/env python3
"""Check the Waveshare SKU 24654 over SPI without transmitting RF.

Requires the libgpiod 2.x Python bindings and spidev.
Pinout: Waveshare SX1262_XXXM_LoRaWAN_HAT_sch.pdf and official demo.
Unlike native SPI CE0, this HAT's NSS is on BCM GPIO21.
"""

import json
import time
from pathlib import Path

import gpiod
import spidev
from gpiod.line import Direction, Value

RESET, BUSY, NSS, RF_SWITCH = 18, 20, 21, 6


def find_rp1_chip():
    for path in sorted(Path("/dev").glob("gpiochip*")):
        with gpiod.Chip(str(path)) as chip:
            info = chip.get_info()
            if "rp1" in info.label.lower() and info.num_lines > NSS:
                return str(path), info.label
    raise RuntimeError("RP1 GPIO chip not available in this container")


def probe():
    if not Path("/dev/spidev0.0").exists():
        raise RuntimeError("Header SPI0 is unavailable: enable dtparam=spi=on in HAOS")
    chip_path, chip_label = find_rp1_chip()
    config = {
        RESET: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
        NSS: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
        RF_SWITCH: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
        BUSY: gpiod.LineSettings(direction=Direction.INPUT),
    }
    with gpiod.request_lines(chip_path, consumer="chacaico-lora-probe", config=config) as pins:
        def wait_ready():
            deadline = time.monotonic() + 1.0
            while pins.get_value(BUSY) == Value.ACTIVE:
                if time.monotonic() >= deadline:
                    raise TimeoutError("SX1262 BUSY stayed high")
                time.sleep(0.001)

        pins.set_value(RESET, Value.INACTIVE)
        time.sleep(0.002)
        pins.set_value(RESET, Value.ACTIVE)
        time.sleep(0.020)
        wait_ready()

        spi = spidev.SpiDev()
        try:
            spi.open(0, 0)
            spi.max_speed_hz = 500_000
            spi.mode = 0
            # RP1 rejects SPI_NO_CS. Its native CE0 is unused by this HAT;
            # GPIO21 selects the SX1262, as in Waveshare's official example.

            def command(data):
                wait_ready()
                pins.set_value(NSS, Value.INACTIVE)
                try:
                    return spi.xfer2(data)
                finally:
                    pins.set_value(NSS, Value.ACTIVE)

            command([0x80, 0x00])  # SetStandby(STBY_RC)
            status = command([0xC0, 0x00])[1]
            if (status >> 4) & 0x07 != 2:
                raise RuntimeError(f"Invalid standby status: 0x{status:02x}")

            # Set/read both modem types to reject stuck or floating MISO.
            for modem in (0, 1):
                command([0x8A, modem])
                response = command([0x11, 0x00, 0x00])[2]
                if response != modem:
                    raise RuntimeError(f"Packet type readback failed: {response} != {modem}")

            sync_word = command([0x1D, 0x07, 0x40, 0x00, 0x00, 0x00])[-2:]
            errors = command([0x17, 0x00, 0x00, 0x00])[-2:]
            return {
                "spi_verified": True,
                "spi_device": "/dev/spidev0.0",
                "gpio_chip": chip_path,
                "gpio_label": chip_label,
                "nss_bcm": NSS,
                "standby_status": f"0x{status:02x}",
                "sync_word": bytes(sync_word).hex(),
                "device_errors": bytes(errors).hex(),
                "rf_transmitted": False,
            }
        finally:
            spi.close()


if __name__ == "__main__":
    print(json.dumps(probe(), indent=2))
