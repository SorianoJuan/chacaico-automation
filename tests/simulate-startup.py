#!/usr/bin/env python3
"""Exercise the real scheduler with eight modeled nodes and deterministic RF loss."""
import argparse
import dataclasses
import heapq
import json
from pathlib import Path
import random
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"bridge/chacaico_lora_bridge"))
from engine import Engine
from protocol import *


class ModelNode:
    def __init__(self, ident, rng):
        self.ident, self.rng = ident, rng
        self.boot, self.wake, self.seq = 1, 0, 0
        self.revision, self.sleep, self.pulse = 1, 5, 50
        self.led, self.valve = 0, UNKNOWN
        self.next_wake = ident*.27
        self.active = False
        self.until = self.hard = 0
        self.cached = None
        self.writes = self.pulses = 0
        self.opened_at = None
        self.longest_awake = 0

    def frame(self, kind, seq=0, op=GET_STATE, status=OK):
        return Frame(kind,self.ident,self.boot,self.wake,seq,op,status,self.revision,
                     self.sleep,self.pulse,self.valve,self.led)

    def end(self, now):
        self.longest_awake = max(self.longest_awake, now-self.opened_at)
        self.active = False
        self.next_wake = now+self.sleep+self.rng.random()*.25

    def tick(self, now):
        if self.active and now >= min(self.until,self.hard):
            self.end(now)
        if not self.active and now >= self.next_wake:
            self.active = True;self.wake += 1
            self.until = now+3;self.hard = now+10;self.opened_at = now
            return self.frame(READY)

    def receive(self, f, now):
        if not self.active or (f.boot,f.wake)!=(self.boot,self.wake) or f.sequence<self.seq:
            return None
        if f.sequence==self.seq:
            self.until=min(now+3,self.hard)
            return self.cached
        self.seq=f.sequence
        status=OK
        if f.op==SET_CONFIG:
            if not valid_config(f.sleep_s,f.pulse_ms):status=INVALID
            elif f.revision==self.revision and (f.sleep_s,f.pulse_ms)==(self.sleep,self.pulse):pass
            elif f.revision!=self.revision+1:status=CONFLICT
            else:
                self.revision=f.revision;self.sleep=f.sleep_s;self.pulse=f.pulse_ms;self.writes+=1
        elif f.op==SET_LED:self.led=f.led
        elif f.op==SET_VALVE:
            if self.valve!=f.valve:self.pulses+=1;self.valve=f.valve
        self.until=min(now+3,self.hard)
        self.cached=self.frame(RESPONSE,f.sequence,f.op,status)
        if f.op==END:self.end(now+.24)
        return self.cached


def scenario(seed):
    rng=random.Random(seed)
    keys={i:bytes([i])*16 for i in range(1,9)}
    nodes={i:ModelNode(i,rng) for i in keys}
    now=[0.]
    dropped_config=set();published={}
    events=[];serial=0;requests=responses=losses=0
    ready_on=0.
    with tempfile.TemporaryDirectory(prefix="chacaico-model-") as folder:
        def create():
            return Engine(keys,folder,lambda topic,value:published.update({topic:value}),
                          lambda:now[0],lambda:1800000000+now[0])
        engine=create()
        for n in nodes:
            engine.message(n,"config/sleep_s/set","5")
            engine.message(n,"config/pulse_ms/set","75")
            engine.message(n,"config/apply","APPLY")
        rebooted=bridge_restarted=led_ordered=recovery_ordered=False
        expirations=0
        for step in range(9000):
            now[0]=step*.02;t=now[0]
            if t>=25 and not rebooted:
                nodes[3].boot+=1;nodes[3].wake=nodes[3].seq=0
                nodes[3].active=False;nodes[3].next_wake=t;nodes[3].valve=UNKNOWN
                rebooted=True
            if t>=35 and not bridge_restarted:
                engine=create();bridge_restarted=True
            if t>=80 and not led_ordered:
                for ident in nodes:engine.message(ident,"led/set","ON")
                led_ordered=True
            if t>=120 and not recovery_ordered:
                # RF delivery cannot be guaranteed. A missed deadline must be
                # explicit; a later, new user request must recover when loss ends.
                for ident,n in nodes.items():
                    if not n.led:
                        assert published.get(f"chacaico/lora/node/{ident}/command/status")=="Vencida sin confirmar"
                        expirations+=1
                    engine.message(ident,"led/set","ON")
                recovery_ordered=True
            announcements=[]
            for n in nodes.values():
                announcement=n.tick(t)
                if announcement:announcements.append(announcement)
            for announcement in announcements:
                if t<ready_on or len(announcements)>1 or (t<110 and rng.random()<.1):
                    losses+=1;continue
                engine.receive(encode(keys[announcement.node],announcement),-80,5)
            while events and events[0][0]<=t:
                _,_,response=heapq.heappop(events)
                if t<110 and rng.random()<.15:
                    losses+=1;continue
                engine.receive(encode(keys[response.node],response),-80,5);responses+=1
            outgoing=engine.next_frame()
            if outgoing:
                ident,payload=outgoing
                request=decode(keys[ident],payload);requests+=1
                ready_on=t+.083
                engine.sent(ident)
                if t<110 and rng.random()<.15:
                    losses+=1;continue
                response=nodes[ident].receive(request,t)
                if response:
                    if request.op==SET_CONFIG and ident not in dropped_config:
                        dropped_config.add(ident);losses+=1;continue
                    serial+=1;heapq.heappush(events,(t+.30,serial,response))
        assert all(n.pulse==75 and n.sleep==5 and n.writes==1 for n in nodes.values())
        assert all(n.led==1 for n in nodes.values()), {i:n.led for i,n in nodes.items()}
        assert all(n.pulses==0 for n in nodes.values())
        assert all(n.config_job is None and n.confirmed and n.confirmed["pulse_ms"]==75 for n in engine.nodes.values())
        assert all(n.longest_awake<=10.3 for n in nodes.values())
        return {"seed":seed,"nodes":8,"seconds":180,"requests":requests,"responses":responses,
                "injected_losses":losses,"config_writes_per_node":[n.writes for n in nodes.values()],
                "all_configurations_confirmed":True,"all_leds_confirmed":all(n.led for n in nodes.values()),
                "explicit_expirations_during_loss":expirations,"new_user_request_after_rf_recovery":True,
                "valve_pulses":0,"node_reboot":True,"bridge_restart":True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path);args=parser.parse_args()
    result={"passed":True,"real_scheduler":True,"modeled_nodes_and_radio":True,
            "scenarios":[scenario(seed) for seed in (1,7,42,91,137)]}
    print(json.dumps(result,indent=2))
    if args.output:args.output.write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":main()
