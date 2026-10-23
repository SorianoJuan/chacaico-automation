#!/usr/bin/env python3
"""Daily schedule controls, visible in season. Preserve other dashboard views."""
import argparse
import copy
import json

NODES = (1, 2, 3, 4)
DAYS = (('lunes', 'Lun'), ('martes', 'Mar'), ('miercoles', 'Mié'), ('jueves', 'Jue'), ('viernes', 'Vie'), ('sabado', 'Sáb'), ('domingo', 'Dom'))

def view():
    header = {'type':'entities', 'grid_options':{'columns':'full'},
              'title':'Temporada de riego', 'show_header_toggle':False,
              'entities':[{'entity':'input_boolean.chacaico_temporada','name':'Habilitar los horarios'}]}
    days = {'type':'glance', 'title':'Días de riego', 'columns':7,
            'grid_options':{'columns':'full'}, 'show_state':False, 'state_color':True,
            'entities':[{'entity':f'input_boolean.chacaico_dia_{day}', 'name':label,
                         'tap_action':{'action':'toggle'}} for day,label in DAYS]}
    sections = [{'type':'grid', 'column_span':2, 'cards':[header, days]}]
    for n in NODES:
        sections.append({'type':'grid', 'visibility':[
          {'condition':'state','entity':'input_boolean.chacaico_temporada','state':'on'}], 'cards':[{'type':'entities','title':f'Válvula {n}',
          'show_header_toggle':False, 'entities':[
            {'entity':f'input_boolean.chacaico_horario_{n}','name':'Habilitar riego por horarios'},
            {'entity':f'input_datetime.chacaico_horario_desde_{n}','name':'Horario de inicio'},
            {'entity':f'input_datetime.chacaico_horario_hasta_{n}','name':'Horario de corte'}]}]})
    return {'title':'Horarios','path':'horarios','icon':'mdi:calendar-clock', 'type':'sections',
            'max_columns':2, 'show_icon_and_title':True, 'sections':sections}

def merge(original):
    updated=copy.deepcopy(original)
    views=updated['data']['config']['views']
    matches=[i for i,v in enumerate(views) if v.get('path')=='horarios']
    if len(matches)>1: raise ValueError('Duplicate horarios view')
    if matches: views[matches[0]]=view()
    else: views.append(view())
    return updated

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--merge')
    args=parser.parse_args()
    result=merge(json.load(open(args.merge))) if args.merge else view()
    print(json.dumps(result,ensure_ascii=False,indent=2))
