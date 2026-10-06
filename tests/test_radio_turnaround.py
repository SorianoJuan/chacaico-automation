"""Actual Radio.send/receive against fake SPI/GPIO and a virtual scheduler.

This characterizes a possible ACK loss; it does not measure the Raspberry Pi.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO/'bridge/chacaico_lora_bridge/radio.py'
values = types.SimpleNamespace(ACTIVE=1,INACTIVE=0)
fake_modules = {
    'gpiod': types.ModuleType('gpiod'),
    'gpiod.line': types.SimpleNamespace(Direction=object,Value=values),
    'spidev': types.ModuleType('spidev'),
}
spec = importlib.util.spec_from_file_location('chacaico_radio_timing_test',SOURCE)
driver = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,fake_modules):
    spec.loader.exec_module(driver)
AIRTIME=0.056576
RESULTS={}


def scenario(scheduler_pause=0,never_tx_done=False):
    now=[0.0]
    tx_done=[None]
    paused=[False]
    pins={driver.RF_SWITCH:1}
    changes=[]
    commands=[]
    radio=driver.Radio.__new__(driver.Radio)
    radio.pins=types.SimpleNamespace(set_value=lambda pin,value:(pins.__setitem__(pin,value),
                                              changes.append((now[0],pin,value))))

    def command(opcode,data=()):
        commands.append((now[0],opcode))
        if opcode==0x83:
            tx_done[0]=now[0]+AIRTIME
        if opcode==0x12:
            done=not never_tx_done and now[0]>=tx_done[0]
            if done and not paused[0]:
                # Inject one scheduler stall after TX ended, before receive().
                paused[0]=True
                now[0]+=scheduler_pause
            return [opcode,0,0,int(done)]
        return [opcode,*data]

    radio.command=command
    clock=types.SimpleNamespace(monotonic=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
    failed=False
    with patch.object(driver,'time',clock):
        try:
            radio.send(bytes(20))
        except TimeoutError:
            failed=True
    rx_at=[at for at,pin,value in changes if pin==driver.RF_SWITCH and value==1][-1]
    ack_starts=tx_done[0]+0.025
    ack_ends=ack_starts+AIRTIME
    return {'simulated_scheduler_pause_seconds':scheduler_pause,'tx_done_at':tx_done[0],
            'rx_switch_at':round(rx_at,6),'tx_to_rx_seconds':round(rx_at-tx_done[0],6),
            'led_ack_start':ack_starts,'led_ack_end':ack_ends,
            'entire_led_ack_precedes_rx':rx_at>ack_ends,'tx_timed_out':failed,
            'finally_returned_to_rx':pins[driver.RF_SWITCH]==1 and commands[-1][1]==0x82}


class RadioTurnaroundTest(unittest.TestCase):
    def test_healthy_turnaround_is_before_ack(self):
        data=scenario()
        self.assertLess(data['rx_switch_at'],data['led_ack_start'])
        self.assertTrue(data['finally_returned_to_rx'])
        RESULTS['healthy']=data

    def test_scheduler_stall_can_miss_entire_ack(self):
        data=scenario(scheduler_pause=0.2)
        self.assertTrue(data['entire_led_ack_precedes_rx'])
        self.assertTrue(data['finally_returned_to_rx'])
        RESULTS['injected_200ms_stall']=data

    def test_tx_timeout_still_restores_rx(self):
        data=scenario(never_tx_done=True)
        self.assertTrue(data['tx_timed_out'])
        self.assertTrue(data['finally_returned_to_rx'])
        RESULTS['tx_timeout']=data


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RadioTurnaroundTest))
    if args.output:
        args.output.write_text(json.dumps({'passed':result.wasSuccessful(),'test_count':result.testsRun,
              'real_driver_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'spi_gpio_scheduler_simulated':True,'raspberry_latency_measured':False,
              'hardware_used':False,'cases':RESULTS},indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
