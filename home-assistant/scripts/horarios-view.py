#!/usr/bin/env python3
"""Daily From/Until controls. Preserve all other dashboard views."""
import argparse
import copy
import json

NODES = (1, 2, 3, 4)

def view():
    header = {'type':'vertical-stack', 'grid_options':{'columns':'full'}, 'cards':[
        {'type':'entities','title':'Temporada de riego','show_header_toggle':False,
         'entities':[{'entity':'input_boolean.chacaico_temporada','name':'Habilitar los horarios'}]},
        {'type':'markdown','content':'El rango se repite **todos los días**. Desde y Hasta iguales = sin riego programado.'}]}
    sections = [{'type':'grid', 'column_span':2, 'cards':[header]}]
    for n in NODES:
        sections.append({'type':'grid', 'cards':[{'type':'entities','title':f'Válvula {n}',
          'show_header_toggle':False, 'entities':[
            {'entity':f'input_boolean.chacaico_horario_{n}','name':'Usar este horario'},
            {'entity':f'input_datetime.chacaico_horario_desde_{n}','name':'Desde'},
            {'entity':f'input_datetime.chacaico_horario_hasta_{n}','name':'Hasta'},
            {'entity':f'sensor.chacaico_horario_estado_{n}','name':'Estado'}]}]})
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
