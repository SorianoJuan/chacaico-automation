"""Execute the actual HA YAML policy against a fake HA state/service bus.
Radio expiry tests exercise the real bridge, never physical actuators.
"""
import importlib.util
import json
from pathlib import Path
import unittest
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from jinja2 import FileSystemLoader
from jinja2.nativetypes import NativeEnvironment
import yaml
import test_valve_bridge as harness
from protocol import SET_VALVE

ROOT=Path(__file__).resolve().parents[1]
PACKAGE=yaml.safe_load((ROOT/'home-assistant/config/chacaico-horarios.yaml').read_text())
SEQUENCE=PACKAGE['automation'][0]['actions'][-1]['repeat']['sequence']
spec=importlib.util.spec_from_file_location('horarios_view',ROOT/'home-assistant/scripts/horarios-view.py')
VIEW=importlib.util.module_from_spec(spec);spec.loader.exec_module(VIEW)

class HaPolicy:
    def __init__(self):
        self.clock=1800000000.
        self.states={};self.attrs={};self.commands=[];self.persisted=[]
        self.zone=timezone.utc
        self.env=NativeEnvironment(loader=FileSystemLoader(ROOT/"home-assistant/config/custom_templates"))
        def from_json(value, default=None):
            try: return json.loads(value)
            except (ValueError,TypeError): return default
        self.env.filters.update(from_json=from_json,to_json=json.dumps)
        def timestamp(value,default=0):
            if isinstance(value,(int,float)): return value
            if isinstance(value,datetime): return value.timestamp()
            try: return datetime.fromisoformat(value).timestamp()
            except (ValueError,TypeError): return default
        self.env.globals.update(states=lambda e:self.states.get(e,'unknown'),
           is_state=lambda e,v:self.states.get(e,'unknown')==v,
           state_attr=lambda e,a:self.attrs.get(e,{}).get(a),
           as_timestamp=timestamp,now=lambda:datetime.fromtimestamp(self.clock,self.zone),
           today_at=lambda value:datetime.combine(datetime.fromtimestamp(self.clock,self.zone).date(),datetime.strptime(value,'%H:%M:%S').time(),tzinfo=self.zone),
           timedelta=timedelta,as_datetime=lambda value:datetime.fromtimestamp(value,self.zone),as_local=lambda value:value.astimezone(self.zone))
    def render(self,value,variables):
        return self.env.from_string(value).render(**variables) if isinstance(value,str) else value
    def run(self,n=1):
        context={'repeat':{'item':n}}
        def sequence(items):
            for item in items:
                if 'variables' in item:
                    for key,value in item['variables'].items():context[key]=self.render(value,context)
                elif 'if' in item:
                    if all(self.render(c['value_template'],context) for c in item['if']):sequence(item['then'])
                else:
                    action=item['action'];entity=self.render(item.get('target',{}).get('entity_id'),context)
                    data={k:self.render(v,context) for k,v in item.get('data',{}).items()}
                    if action.startswith('input_boolean.'):self.states[entity]='on' if action.endswith('turn_on') else 'off'
                    elif action=='input_text.set_value':self.states[entity]=json.dumps(data['value']) if isinstance(data['value'],dict) else data['value']
                    elif action=='homeassistant.save_persistent_states':self.persisted.append(self.states.copy())
                    elif action=='mqtt.publish':self.commands.append(data)
                    else:raise AssertionError(action)
        sequence(SEQUENCE)
        return context
    def set_time(self,part,stamp,n=1):
        self.states[f'input_datetime.chacaico_horario_{part}_{n}']=datetime.fromtimestamp(stamp,self.zone).strftime('%H:%M:%S')
    def enable(self,n=1,end=None):
        self.states.update({'input_boolean.chacaico_temporada':'on',f'input_boolean.chacaico_horario_{n}':'on'})
        self.set_time('desde',self.clock-60,n)
        self.set_time('hasta',self.clock+1800 if end is None else end,n)
    def report(self,n=1,state='open',status='Confirmada',at=None):
        self.states.update({f'valve.chacaico_node_{n}':state,f'sensor.chacaico_node_{n}_valve_command_status':status})
        self.attrs[f'valve.chacaico_node_{n}']={'confirmation':'confirmed','confirmed_at':at if at is not None else self.clock+1}

class SchedulePolicyTest(unittest.TestCase):
    def setUp(self): self.ha=HaPolicy()
    def test_fresh_install_never_actuates_even_if_manual_valve_is_open(self):
        for n in VIEW.NODES:self.ha.report(n)
        for n in VIEW.NODES:self.ha.run(n)
        self.assertEqual(self.ha.commands,[])
    def test_empty_schedule_requests_closed_only_when_enabled(self):
        self.ha.enable();self.ha.states['input_datetime.chacaico_horario_hasta_1']=self.ha.states['input_datetime.chacaico_horario_desde_1']
        self.ha.run();self.assertEqual(self.ha.commands[-1]['payload'],'CLOSE')
    def test_open_is_nonretained_and_bound_to_current_slot(self):
        self.ha.enable();self.ha.run()
        msg=self.ha.commands[-1]
        self.assertFalse(msg['retain']);self.assertEqual(msg['qos'],1)
        self.assertEqual(msg['payload'],{'state':'OPEN','valid_until':self.ha.clock+1800})
    def test_pending_is_not_republished_each_tick(self):
        self.ha.enable();self.ha.run();self.ha.clock+=30;self.ha.run()
        self.assertEqual(len(self.ha.commands),1)
    def test_retry_after_ttl_but_no_flood(self):
        self.ha.enable();self.ha.run()
        self.ha.states['sensor.chacaico_node_1_metric_command_ttl_s']='300'
        self.ha.clock+=90;self.ha.run();self.assertEqual(len(self.ha.commands),1)
        self.ha.clock+=221;self.ha.run();self.assertEqual(len(self.ha.commands),2)
    def test_confirmed_does_not_repeat_pulses(self):
        self.ha.enable();self.ha.run();self.ha.report()
        for _ in range(10):self.ha.clock+=60;self.ha.run()
        self.assertEqual(len(self.ha.commands),1)
    def test_shutdown_cancels_queued_open_even_if_last_report_says_closed(self):
        self.ha.enable();self.ha.run();self.ha.report(state='closed',status='Pendiente')
        self.ha.states['input_boolean.chacaico_temporada']='off';self.ha.run()
        self.assertEqual(self.ha.commands[-1]['payload'],'CLOSE')
        self.assertEqual(self.ha.states['input_boolean.chacaico_horario_responsable_1'],'on')
    def test_close_remains_owned_across_restart_and_recovers(self):
        self.ha.enable();self.ha.run();self.ha.states['input_boolean.chacaico_temporada']='off';self.ha.run()
        restarted=HaPolicy();restarted.states=self.ha.states.copy();restarted.attrs=self.ha.attrs.copy()
        restarted.clock=self.ha.clock+90;restarted.run()
        self.assertEqual(restarted.commands[-1]['payload'],'CLOSE')
        restarted.report(state='closed');restarted.run()
        self.assertEqual(restarted.states['input_boolean.chacaico_horario_responsable_1'],'off')
        restarted.report(state='open');restarted.clock+=90;restarted.run()
        self.assertEqual(len(restarted.commands),1)  # manual after completed shutdown
    def test_old_close_confirmation_cannot_clear_pending_shutdown(self):
        self.ha.enable();self.ha.run();self.ha.report(state='closed',at=self.ha.clock-10)
        self.ha.states['input_boolean.chacaico_temporada']='off';self.ha.run();self.ha.run()
        self.assertEqual(self.ha.states['input_boolean.chacaico_horario_responsable_1'],'on')
    def test_restart_after_end_never_replays_open(self):
        self.ha.enable();self.ha.run();self.ha.clock+=1900
        self.ha.run()
        self.assertEqual(self.ha.commands[-1]['payload'],'CLOSE')
    def test_edit_shortens_pending_open_boundary(self):
        self.ha.enable();self.ha.run();self.ha.set_time('hasta',self.ha.clock+20)
        self.ha.run();self.assertEqual(self.ha.commands[-1]['payload']['valid_until'],self.ha.clock+20)
    def test_edit_does_not_repeat_a_confirmed_open_pulse(self):
        self.ha.enable();self.ha.run();self.ha.report()
        self.ha.set_time('hasta',self.ha.clock+60)
        self.ha.run();self.assertEqual(len(self.ha.commands),1)
        self.ha.set_time('hasta',self.ha.clock+3600)
        self.ha.run();self.assertEqual(len(self.ha.commands),1)
    def test_expired_or_missing_boundary_never_opens(self):
        self.ha.enable(end=self.ha.clock-1);self.ha.run()
        self.assertEqual(self.ha.commands[-1]['payload'],'CLOSE')
    def test_nodes_have_distinct_topics_and_ownership(self):
        for n in VIEW.NODES:self.ha.enable(n);self.ha.run(n)
        self.assertEqual(len({m['topic'] for m in self.ha.commands}),4)
        self.ha.states['input_boolean.chacaico_horario_2']='off';self.ha.run(2)
        self.assertEqual(self.ha.commands[-1]['topic'],'chacaico/lora/node/2/valve/set')
    def test_helper_values_restore_not_reset_on_boot(self):
        for domain in ('input_boolean','input_text','input_datetime'):
            self.assertTrue(all('initial' not in spec for spec in PACKAGE[domain].values()))
    def test_view_merge_preserves_other_views_and_has_two_time_inputs(self):
        original={'data':{'config':{'views':[{'title':'Mi vista','cards':[{'type':'entities'}]}]}}}
        merged=VIEW.merge(original)
        self.assertEqual(merged['data']['config']['views'][0],original['data']['config']['views'][0])
        self.assertEqual(VIEW.merge(merged),merged)
        for n,section in enumerate(VIEW.view()['sections'][1:],1):
            entities=section['cards'][0]['entities']
            self.assertEqual([row['name'] for row in entities],['Usar este horario','Horario de inicio','Horario de corte','Estado'])
            self.assertEqual(entities[1]['entity'],f'input_datetime.chacaico_horario_desde_{n}')
            self.assertEqual(entities[2]['entity'],f'input_datetime.chacaico_horario_hasta_{n}')

    def test_responsibility_and_intent_are_persisted_before_dispatch(self):
        self.ha.enable();self.ha.run()
        self.assertEqual(self.ha.persisted[0]['input_boolean.chacaico_horario_responsable_1'],'on')
        saved=json.loads(self.ha.persisted[0]['input_text.chacaico_horario_ultimo_1'])
        self.assertEqual(saved['desired'],'OPEN')
        self.assertEqual(saved['at'],self.ha.clock)
    def test_stale_ack_is_never_displayed_as_confirmed(self):
        self.ha.enable();self.ha.run();self.ha.report(at=self.ha.clock-20)
        state=self.ha.render(PACKAGE['template'][0]['sensor'][0]['state'],{}).strip()
        self.assertEqual(state,'Apertura pendiente')
    def test_fresh_report_after_expired_order_is_displayed_as_confirmed(self):
        self.ha.enable();self.ha.run()
        self.ha.report(status='Vencida sin confirmar')
        state=self.ha.render(PACKAGE['template'][0]['sensor'][0]['state'],{}).strip()
        self.assertEqual(state,'Apertura confirmada')
    def test_pending_close_cannot_be_displayed_as_closed_from_an_old_report(self):
        self.ha.enable();self.ha.run();self.ha.report(state='closed',at=self.ha.clock-20)
        self.ha.states['input_boolean.chacaico_temporada']='off';self.ha.run()
        state=self.ha.render(PACKAGE['template'][0]['sensor'][0]['state'],{}).strip()
        self.assertEqual(state,'Cierre pendiente')
    def test_master_off_per_valve_enable_does_not_take_ownership_or_send(self):
        self.ha.enable();self.ha.states['input_boolean.chacaico_temporada']='off';self.ha.run()
        self.assertEqual(self.ha.commands,[])
        self.assertNotEqual(self.ha.states.get('input_boolean.chacaico_horario_responsable_1'),'on')

    def range_at(self,when,start,stop,zone='America/Argentina/Buenos_Aires'):
        self.ha.zone=ZoneInfo(zone)
        self.ha.clock=datetime.fromisoformat(when).replace(tzinfo=self.ha.zone).timestamp()
        self.ha.enable()
        self.ha.states['input_datetime.chacaico_horario_desde_1']=start
        self.ha.states['input_datetime.chacaico_horario_hasta_1']=stop
        return self.ha.run()
    def test_daytime_start_inclusive_end_exclusive(self):
        v=self.range_at('2026-10-24T08:00:00','08:00:00','09:00:00')
        self.assertEqual(v['desired'],'OPEN')
        self.ha.clock+=3600
        v=self.ha.run();self.assertEqual(v['desired'],'CLOSE')
    def test_window_before_start_does_not_open(self):
        v=self.range_at('2026-10-24T07:59:59','08:00:00','09:00:00')
        self.assertEqual(v['desired'],'CLOSE')
    def test_overnight_bound_stays_same_across_midnight(self):
        v=self.range_at('2026-10-24T23:00:00','22:00:00','01:00:00')
        end=v['end'];self.assertEqual(v['desired'],'OPEN')
        self.ha.report();self.ha.clock+=5400
        v=self.ha.run();self.assertEqual(v['desired'],'OPEN');self.assertEqual(v['end'],end)
        self.assertEqual(len(self.ha.commands),1)
        self.ha.clock=end;self.assertEqual(self.ha.run()['desired'],'CLOSE')
    def test_same_times_are_off_not_a_24_hour_open(self):
        v=self.range_at('2026-10-24T08:00:00','08:00:00','08:00:00')
        self.assertEqual(v['desired'],'CLOSE');self.assertFalse(v['window']['valid'])
    def test_unavailable_time_fails_closed(self):
        self.ha.enable();self.ha.states['input_datetime.chacaico_horario_hasta_1']='unavailable'
        self.assertEqual(self.ha.run()['desired'],'CLOSE')
    def test_next_day_uses_local_calendar_across_dst(self):
        v=self.range_at('2026-03-07T23:00:00','22:00:00','04:00:00','America/New_York')
        close=datetime.fromtimestamp(v['end'],self.ha.zone)
        self.assertEqual(close.isoformat(),'2026-03-08T04:00:00-04:00')
        self.assertEqual(v['end']-self.ha.clock,4*3600)
    def test_old_weekly_helper_cannot_control_the_new_range(self):
        self.range_at('2026-10-24T08:00:00','00:00:00','00:00:00')
        self.ha.states['schedule.chacaico_horario_valvula_1']='on'
        self.assertEqual(self.ha.run()['desired'],'CLOSE')
    def test_exact_time_triggers_include_every_from_and_until(self):
        triggers=PACKAGE['automation'][0]['triggers']
        times=next(t['at'] for t in triggers if t['trigger']=='time')
        self.assertEqual(set(times),{'input_datetime.'+x for x in PACKAGE['input_datetime']})

class ScheduledDeadlineTest(unittest.TestCase):
    # Reuse radio harness helpers, without rerunning all inherited tests.
    setUp = harness.EngineTest.setUp
    create = harness.EngineTest.create
    ready = harness.EngineTest.ready
    request = harness.EngineTest.request
    respond = harness.EngineTest.respond
    connect = harness.EngineTest.connect
    def test_scheduled_open_expires_before_sleeping_node_wakes(self):
        self.connect(sleep=30);self.respond(self.request())
        end=self.engine.wall()+5
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':end}))
        self.clock+=6;self.engine.tick();self.assertNotIn(SET_VALVE,self.engine.nodes[1].actions)
    def test_invalid_and_retained_scheduled_open_is_rejected(self):
        for until in (self.engine.wall()-1,True,float('nan'),'tomorrow'):
            self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':until}))
            self.assertNotIn(SET_VALVE,self.engine.nodes[1].actions)
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+60}),retained=True)
        self.assertNotIn(SET_VALVE,self.engine.nodes[1].actions)
    def test_edit_can_shorten_not_extend_pending_transaction(self):
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+10}))
        deadline=self.engine.nodes[1].actions[SET_VALVE]['deadline']
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+100}))
        self.assertEqual(self.engine.nodes[1].actions[SET_VALVE]['deadline'],deadline)
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+2}))
        self.assertLess(self.engine.nodes[1].actions[SET_VALVE]['deadline'],deadline)
    def test_close_supersedes_scheduled_open(self):
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+10}))
        self.engine.message(1,'valve/set','CLOSE')
        self.assertEqual(self.engine.nodes[1].actions[SET_VALVE]['value'],0)
        self.assertNotIn('valid_until',self.engine.nodes[1].actions[SET_VALVE])

    def test_forward_wall_clock_jump_expires_open_before_dispatch(self):
        self.connect()
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+60}))
        old_wall=self.engine.wall()
        self.engine.wall=lambda:old_wall+90
        self.engine.next_frame()
        self.assertNotIn(SET_VALVE,self.engine.nodes[1].actions)
        self.assertTrue(self.engine.nodes[1].pending is None or self.engine.nodes[1].pending['frame'].op!=SET_VALVE)
    def test_ack_at_exact_deadline_is_not_confirmation(self):
        self.connect()
        self.engine.message(1,'valve/set',json.dumps({'state':'OPEN','valid_until':self.engine.wall()+5}))
        self.clock+=1
        request=self.request();self.assertEqual(request.op,SET_VALVE)
        self.clock=self.engine.nodes[1].actions[SET_VALVE]['deadline']-.3
        self.respond(request)
        self.assertIn(('chacaico/lora/node/1/valve/command/status','Vencida sin confirmar'),self.output)
