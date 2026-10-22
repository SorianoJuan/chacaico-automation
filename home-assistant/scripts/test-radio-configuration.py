#!/usr/bin/env python3
"""Explicit live bench test through SSH/MQTT; only configuration and LED commands.
Stages mqtt-bench-transport.sh on the verified Pi. Restores settings and LED state.
Requires both v3 nodes online and at most 30 seconds of sleep. No valve commands.
"""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import threading
import time

ROOT='chacaico/lora'
KEYS=('sleep_s','pulse_ms','tx_power_dbm','listen_ms','max_awake_ms')

class Bench:
    def __init__(self, host):
        self.ssh=['ssh','-F','/home/torce/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=10',host]
        self.remote='/tmp/chacaico-stage1/mqtt-bench-transport.sh'
        self.values={};self.times={};self.events=[];self.cv=threading.Condition()
        script=Path(__file__).with_name('mqtt-bench-transport.sh').read_bytes()
        subprocess.run(self.ssh+['umask 077; mkdir -p /tmp/chacaico-stage1; cat > '+self.remote],input=script,check=True)
        self.proc=subprocess.Popen(self.ssh+['sh '+self.remote+' sub'],stdout=subprocess.PIPE,text=True)
        self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()
    def read(self):
        for line in self.proc.stdout:
            topic,sep,payload=line.rstrip('\n').partition('\t')
            if not sep: continue
            try: value=json.loads(payload)
            except (ValueError,TypeError): value=payload
            with self.cv:
                self.values[topic]=value;self.times[topic]=time.monotonic()
                if topic.endswith(('/config/status','/config/reported','/led/command/status','/bridge/power','/policy/reported')):
                    self.events.append({'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'topic':topic,'value':value})
                self.cv.notify_all()
    def wait(self, topic, predicate=lambda v:True, timeout=65, after=0):
        deadline=time.monotonic()+timeout
        with self.cv:
            while time.monotonic()<deadline:
                value=self.values.get(topic)
                if value is not None and self.times.get(topic,0)>=after and predicate(value): return value
                if self.proc.poll() is not None: raise RuntimeError('MQTT subscriber stopped')
                self.cv.wait(min(1,deadline-time.monotonic()))
            raise TimeoutError(f'{topic}: last value {self.values.get(topic)!r}')
    def pub(self, topic, value):
        started=time.monotonic()
        subprocess.run(self.ssh+['sh '+self.remote+' pub '+shlex.quote(topic)+' '+shlex.quote(str(value))],check=True,timeout=20)
        return started
    def cfg(self,n,cfg):
        base=f'{ROOT}/node/{n}'
        # Stage a permissive budget before reducing or increasing dependent fields.
        for key,value in [('max_awake_ms',60000)]+[(k,cfg[k]) for k in KEYS if k!='max_awake_ms']+[('max_awake_ms',cfg['max_awake_ms'])]:
            self.pub(base+f'/config/{key}/set',value)
            self.wait(base+'/config/draft',lambda v,k=key,x=value:v[k]==x,timeout=10)
        unchanged=all(self.values[base+'/config/reported'][k]==cfg[k] for k in KEYS)
        sent=self.pub(base+'/config/apply','APPLY')
        if unchanged:self.pub(base+'/config/query','QUERY')
        reported=self.wait(base+'/config/reported',lambda v:all(v[k]==cfg[k] for k in KEYS),after=sent)
        self.wait(base+'/config/status',lambda v:v=='Confirmada')
        return reported
    def policy(self,n,policy):
        base=f'{ROOT}/node/{n}'
        for key,value in policy.items():
            self.pub(base+f'/policy/{key}/set',value)
            self.wait(base+'/policy/draft',lambda v,k=key,x=value:v[k]==x,timeout=10)
        self.pub(base+'/policy/apply','APPLY')
        return self.wait(base+'/policy/reported',lambda v:v==policy,timeout=10)
    def hat(self,power):
        self.pub(ROOT+'/bridge/power/set',power)
        self.wait(ROOT+'/bridge/power',lambda v:v['requested']==power,timeout=10)
        self.pub(ROOT+'/bridge/power/apply','APPLY')
        return self.wait(ROOT+'/bridge/power',lambda v:v['applied']==power and v['status']=='Aplicada en el HAT',timeout=10)
    def led(self,n,value):
        base=f'{ROOT}/node/{n}';sent=self.pub(base+'/led/set',value)
        self.wait(base+'/led/command/status',lambda v:v=='Confirmada',after=sent)
        self.wait(base+'/led/state',lambda v:v==value)
    def close(self):
        self.proc.terminate()
        try:self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.wait()


def run(b, result):
    originals={}
    for n in (1,2):
        base=f'{ROOT}/node/{n}'
        b.wait(base+'/config/protocol',lambda v:v=='v3')
        sent=b.pub(base+'/config/query','QUERY')
        cfg=b.wait(base+'/config/reported',after=sent)
        if cfg['sleep_s']>30: raise RuntimeError('Bench requires sleep <=30s; no settings changed')
        originals[n]={'config':{k:cfg[k] for k in KEYS},'policy':b.wait(base+'/policy/reported'),'led':b.wait(base+'/led/state')}
    oldhat=b.wait(ROOT+'/bridge/power')['applied']
    result['before']={'nodes':originals,'hat_power_dbm':oldhat}
    restore_errors=[]
    try:
        b.hat(14)
        for n in (1,2):
            base=f'{ROOT}/node/{n}';other=f'{ROOT}/node/{3-n}'
            cfg={**originals[n]['config'],'sleep_s':8,'tx_power_dbm':14,'listen_ms':2000,'max_awake_ms':12000}
            before=b.wait(base+'/config/reported')
            b.pub(base+'/config/tx_power_dbm/set',14)
            b.wait(base+'/config/draft',lambda v:v['tx_power_dbm']==14)
            assert all(b.values[base+'/config/reported'][k]==before[k] for k in ('revision',)+KEYS),'Draft applied without Apply'
            configured=b.cfg(n,cfg)
            b.policy(n,{'command_ttl_s':0,'missed_contacts':4})
            b.wait(base+'/link/state',lambda v:v=='Reposo esperado',after=time.monotonic())
            target='ON' if originals[n]['led']=='OFF' else 'OFF'
            sent=b.pub(base+'/led/set',target)
            b.wait(base+'/led/command/status',lambda v:v=='Pendiente',after=sent,timeout=3)
            b.wait(base+'/led/command/status',lambda v:v=='Confirmada',after=sent)
            b.wait(base+'/led/state',lambda v:v==target)
            assert b.values[other+'/led/state']==originals[3-n]['led'],'LED isolation failed'
            metrics=b.wait(base+'/metrics',lambda v:v['confirmed']>=1 and v['last_queue_s'] is not None and v['last_queue_s']>1)
            assert metrics['downlink_rssi'] is not None and metrics['uplink_rssi'] is not None
            b.policy(n,{'command_ttl_s':1,'missed_contacts':4})
            b.wait(base+'/link/state',lambda v:v=='Reposo esperado',after=time.monotonic())
            expired_before=b.values[base+'/metrics']['expired']
            sent=b.pub(base+'/led/set',originals[n]['led'])
            b.wait(base+'/led/command/status',lambda v:v=='Vencida sin confirmar',after=sent,timeout=5)
            expired=b.wait(base+'/metrics',lambda v:v['expired']==expired_before+1,timeout=5)
            # Require a fresh round-trip after a subsequent wake, then verify no late actuation.
            b.pub(base+'/config/query','QUERY')
            b.wait(base+'/config/reported',after=sent+2)
            assert b.values[base+'/led/state']==target,'Expired LED command executed later'
            b.policy(n,originals[n]['policy'])
            b.led(n,originals[n]['led'])
            b.cfg(n,originals[n]['config'])
            result.setdefault('nodes',{})[n]={'applied':configured,'sleeping_order_metrics':metrics,'expired_order_metrics':expired,'isolation':True,'expired_not_replayed':True,'restored':True}
            print(f'PASS node {n}: draft, power trial+commit, windows, queued LED, expiry, isolation, restoration',flush=True)
    finally:
        for n in (1,2):
            try:
                b.policy(n,originals[n]['policy'])
                b.cfg(n,originals[n]['config'])
                b.led(n,originals[n]['led'])
            except Exception as exc:restore_errors.append(f'node {n}: {exc}')
        try:b.hat(oldhat)
        except Exception as exc:restore_errors.append(f'HAT: {exc}')
        result['restore_errors']=restore_errors
        if restore_errors:raise RuntimeError('; '.join(restore_errors))
    result['after']={n:{'config':b.values[f'{ROOT}/node/{n}/config/reported'],'policy':b.values[f'{ROOT}/node/{n}/policy/reported'],'led':b.values[f'{ROOT}/node/{n}/led/state']} for n in (1,2)}
    result['hat_after']=b.values[ROOT+'/bridge/power']
    result['valve_commands_sent']=0
    result['result']='PASS'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bench',action='store_true',required=True)
    parser.add_argument('--host',default='pi5.chacaico')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'result':'INCOMPLETE'}
    b=Bench(args.host)
    try:run(b,result)
    finally:
        result['events']=b.events;b.close()
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS all settings restored; no valve commands sent',flush=True)

if __name__=='__main__':main()
