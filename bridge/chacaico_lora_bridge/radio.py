"""SX1262 driver for Waveshare SKU 24654 on Pi 5 / libgpiod 2.

Commands follow Semtech DS_SX1261-2 V1.2; board wiring follows Waveshare
SX1262_XXXM_LoRaWAN_HAT_sch.pdf. CE0 is unused, NSS is BCM21.
"""
import time

import gpiod
import spidev
from gpiod.line import Direction, Value

RESET, BUSY, NSS, RF_SWITCH, DIO1 = 18, 20, 21, 6, 16


class Radio:
    def __init__(self, frequency):
        self.spi = None
        self.pins = gpiod.request_lines("/dev/gpiochip0", consumer="chacaico-lora", config={
            RESET: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
            NSS: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
            RF_SWITCH: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
            BUSY: gpiod.LineSettings(direction=Direction.INPUT),
            DIO1: gpiod.LineSettings(direction=Direction.INPUT),
        })
        try:
            self.spi = spidev.SpiDev()
            self.spi.open(0, 0)
            self.spi.max_speed_hz = 500_000
            self.spi.mode = 0  # RP1 does not support SPI_NO_CS.
            self.pins.set_value(RESET, Value.INACTIVE)
            time.sleep(0.002)
            self.pins.set_value(RESET, Value.ACTIVE)
            time.sleep(0.020)
            self.command(0x80, [0])
            status = self.command(0xC0, [0])[1]
            if (status >> 4) & 7 != 2:
                raise RuntimeError(f"Invalid SX1262 standby status: {status:02x}")
            self.command(0x8A, [1])  # LoRa
            self.command(0x96, [0])  # LDO
            self.command(0x9D, [1])  # DIO2 RF switch as in Waveshare demo
            self.command(0x89, [0x7F])  # calibrate using the onboard crystal
            self.command(0x98, [0xE1, 0xE9])  # image calibration 902-928 MHz
            self.command(0x86, list(int(frequency * (1 << 25) / 32_000_000).to_bytes(4, "big")))
            self.command(0x95, [4, 7, 0, 1])  # SX1262 PA
            self.command(0x8E, [0, 2])  # 0 dBm, 40 us ramp (bench test)
            self.write_reg(0x08D8, [self.read_reg(0x08D8) | 0x1E])  # TX clamp workaround
            self.write_reg(0x0889, [self.read_reg(0x0889) | 0x04])  # BW125 workaround
            self.command(0x8B, [7, 4, 1, 0])  # SF7, BW125, CR4/5, LDRO off
            self.write_reg(0x0740, [0x14, 0x24])  # private sync word
            self.write_reg(0x0736, [self.read_reg(0x0736) | 0x04])  # standard IQ
            self.command(0x8F, [0, 0])  # TX and RX buffer base
            self.command(0x08, [0x03, 0x43, 0x03, 0x43, 0, 0, 0, 0])
            self.command(0x07, [0, 0])  # clear device errors
            self.receive()
        except BaseException:
            self.close()
            raise

    def command(self, opcode, data=()):
        deadline = time.monotonic() + 1
        while self.pins.get_value(BUSY) == Value.ACTIVE:
            if time.monotonic() > deadline:
                raise TimeoutError("SX1262 BUSY remained high")
            time.sleep(0.001)
        self.pins.set_value(NSS, Value.INACTIVE)
        try:
            return self.spi.xfer2([opcode, *data])
        finally:
            self.pins.set_value(NSS, Value.ACTIVE)

    def read_reg(self, address):
        return self.command(0x1D, [address >> 8, address & 255, 0, 0])[-1]

    def write_reg(self, address, data):
        self.command(0x0D, [address >> 8, address & 255, *data])

    def packet_params(self, length):
        self.command(0x8C, [0, 8, 0, length, 1, 0])  # preamble8, explicit, CRC on

    def receive(self):
        self.command(0x80, [0])
        self.pins.set_value(RF_SWITCH, Value.ACTIVE)  # Waveshare HIGH = RX
        self.packet_params(255)
        self.command(0x02, [0xFF, 0xFF])
        self.command(0x82, [0xFF, 0xFF, 0xFF])  # continuous RX

    def send(self, payload):
        self.command(0x80, [0])
        self.pins.set_value(RF_SWITCH, Value.INACTIVE)  # LOW = TX
        self.packet_params(len(payload))
        self.command(0x0E, [0, *payload])
        self.command(0x02, [0xFF, 0xFF])
        self.command(0x83, [0x01, 0xF4, 0])  # 2 seconds
        deadline = time.monotonic() + 2.2
        try:
            while time.monotonic() < deadline:
                response = self.command(0x12, [0, 0, 0])
                irq = int.from_bytes(bytes(response[-2:]), "big")
                if irq & 1:
                    return
                if irq & 0x200:
                    break
                time.sleep(0.002)
            raise TimeoutError("SX1262 TX timed out")
        finally:
            self.receive()

    def poll(self):
        if self.pins.get_value(DIO1) != Value.ACTIVE:
            return None
        response = self.command(0x12, [0, 0, 0])
        irq = int.from_bytes(bytes(response[-2:]), "big")
        result = None
        if irq & 2 and not irq & 0x60:
            length, offset = self.command(0x13, [0, 0, 0])[-2:]
            payload = bytes(self.command(0x1E, [offset, 0, *([0] * length)])[3:])
            rssi, snr, _ = self.command(0x14, [0, 0, 0, 0])[-3:]
            result = payload, -rssi / 2, (snr if snr < 128 else snr - 256) / 4
        self.command(0x02, [0xFF, 0xFF])
        return result

    def close(self):
        if self.spi is not None:
            try:
                self.command(0x80, [0])
            except Exception:
                pass
            self.spi.close()
        self.pins.release()
