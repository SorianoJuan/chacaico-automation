#!/usr/bin/env python3
"""Bounded node-1 bench cycles. Requires an isolated CubeCell, sleep=0, pulse=3000.

Uses the existing SSH alias and the private /tmp/mqtt-env.sh helper on the Pi.
No firmware/configuration edits. SIGINT/SIGTERM stops issuing further commands;
an already-started pulse completes locally on the node. Logs contain telemetry,
never credentials. Only one copy of this controller can run at a time.
"""
import argparse,datetime,fcntl,json,os,queue,signal,subprocess,threading,time
from pathlib import Path
from zoneinfo import ZoneInfo

SSH=['ssh','-T','-F','/home/torce/.ssh/config','-o','BatchMode=yes','-o','ConnectTimeout=5','pi5.chacaico']
ROOT='chacaico/lora/node/1/'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--cycles',type=int,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
if not 1<=args.cycles<=100:parser.error('Cycles must be between 1 and 100')
lock=Path('/tmp/chacaico-cycle-node1.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('A node-1 bench controller is already running')
path=args.output
pid_path=path.with_suffix('.pid')
pid_path.write_text(str(os.getpid()))
def interrupt(signum,frame):raise KeyboardInterrupt(f'Stopped by signal {signum}')
signal.signal(signal.SIGTERM,interrupt)
signal.signal(signal.SIGINT,interrupt)
q=queue.Queue(); current={}; command=None; proc=None
log=path.open('w')
def record(kind,**fields):
 entry={'time':datetime.datetime.now(ZoneInfo('America/Argentina/Buenos_Aires')).isoformat(timespec='milliseconds'),'event':kind,**fields}
 log.write(json.dumps(entry,ensure_ascii=False)+'\n');log.flush()
 if kind!='mqtt':print(json.dumps(entry,ensure_ascii=False),flush=True)
def consume(timeout):
 global command
 try: stamp,line=q.get(timeout=max(0,timeout))
 except queue.Empty:return
 if line is None:raise RuntimeError('MQTT observer disconnected')
 topic,sep,raw=line.partition(' ')
 if not sep:return
 try: value=json.loads(raw)
 except ValueError:value=raw
 record('mqtt',topic=topic,payload=value)
 suffix=topic[len(ROOT):] if topic.startswith(ROOT) else topic
 current[suffix]=value
 if suffix=='config/reported' and (value.get('sleep_s')!=0 or value.get('pulse_ms')!=3000):
  raise RuntimeError('Node configuration changed; stopping cycle')
 if command and stamp>=command['start']:
  if suffix=='valve/set':
   if value!=command['target']:raise RuntimeError('Another valve command was received; stopping cycle')
   command['received']=True;command['mqtt_at']=stamp
  elif suffix=='valve/command/status':
   if value=='Pendiente':command['pending']=True
   elif value=='Confirmada' and command.get('pending'):command['confirmed']=True
   elif 'Vencida' in str(value) or 'Sin confirmación' in str(value):
    raise RuntimeError('Valve command was not confirmed normally; stopping cycle')
  elif suffix=='valve/status' and isinstance(value,dict) and value.get('confirmation')=='confirmed' and command.get('pending'):
   command['ack']=value

def pump_until(deadline):
 while time.monotonic()<deadline:consume(min(.1,deadline-time.monotonic()))

def act(target,index):
 global command
 if current.get('config/reported',{}).get('pulse_ms')!=3000:raise RuntimeError('Unexpected pulse configuration')
 command={'target':target,'start':time.monotonic()}
 record('command',index=index,command=target,node=1)
 script=f'set -eu\n. /tmp/mqtt-env.sh\npub 1 valve/set {target}\n'
 subprocess.run(SSH+['sh','-s'],input=script,text=True,check=True,timeout=4,stdout=subprocess.DEVNULL)
 deadline=command['start']+4.8
 expected='open' if target=='OPEN' else 'closed'
 while time.monotonic()<deadline:
  consume(.05)
  if (command.get('received') and command.get('confirmed') and command.get('ack')
      and current.get('valve/state')==expected):
   record('confirmed',index=index,command=target,node=1,
          latency_s=round(time.monotonic()-command['start'],3),
          sequence=command['ack'].get('sequence'),state=expected)
   return
 raise RuntimeError(f'No matching fresh ACK within 4.8 seconds for {target}')

try:
 script=f"set -eu\n. /tmp/mqtt-env.sh\nsub -W {args.cycles*10+30} -v -t 'chacaico/lora/node/1/valve/#' -t chacaico/lora/node/1/config/reported -t chacaico/lora/node/1/link/state\n"
 proc=subprocess.Popen(SSH+['sh','-s'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
 proc.stdin.write(script);proc.stdin.close()
 def reader():
  for line in proc.stdout:q.put((time.monotonic(),line.rstrip('\n')))
  q.put((time.monotonic(),None))
 threading.Thread(target=reader,daemon=True).start()
 stop=time.monotonic()+8
 while time.monotonic()<stop and not all(k in current for k in ('config/reported','link/state','valve/state','valve/command/status')):
  consume(.1)
 assert current.get('config/reported',{}).get('sleep_s')==0
 assert current.get('config/reported',{}).get('pulse_ms')==3000
 assert current.get('link/state')=='Escuchando'
 assert current.get('valve/command/status') in ('Confirmada','Sin órdenes pendientes')
 record('started',node=1,cycles=args.cycles,interval_s=5,pulse_ms=3000,initial_state=current.get('valve/state'))
 if current.get('valve/state')=='open':
  baseline=time.monotonic();act('CLOSE','baseline');pump_until(baseline+5)
 schedule=time.monotonic()
 for i in range(args.cycles*2):
  pump_until(schedule+i*5)
  act('OPEN' if i%2==0 else 'CLOSE',i+1)
 record('completed',cycles=args.cycles,commands=args.cycles*2,final_state=current.get('valve/state'))
except (Exception,KeyboardInterrupt) as exc:
 record('stopped',reason=str(exc) or 'Interrupted',last_state=current.get('valve/state'))
 raise
finally:
 if proc:
  proc.terminate()
  try:proc.wait(timeout=3)
  except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
 pid_path.unlink(missing_ok=True)
