#!/usr/bin/env python3
"""Native Schedule editor view and empty first-install seed. No operating hours guessed."""
import argparse
import copy
import json

NODES = (1, 2, 3, 4)

def view():
    header = {'type':'vertical-stack', 'grid_options':{'columns':'full'}, 'cards':[
        {'type':'entities','title':'Temporada de riego','show_header_toggle':False,
         'entities':[{'entity':'input_boolean.chacaico_temporada','name':'Habilitar los horarios'}]},
        {'type':'markdown','content':'Al apagar la temporada se solicita el cierre y se guardan los horarios. Mientras esté activa, manda el horario.\n\nTocá **Editar días y horarios**, marcá las franjas y guardá con **Actualizar / Update**.'}]}
    sections = [{'type':'grid', 'column_span':2, 'cards':[header]}]
    for n in NODES:
        editor = (f'/dashboard-chacaico/horarios?more-info-entity-id=schedule.chacaico_horario_valvula_{n}'
                  '&more-info-view=settings')
        sections.append({'type':'grid', 'cards':[{'type':'entities','title':f'Válvula {n}',
          'show_header_toggle':False, 'entities':[
            {'entity':f'input_boolean.chacaico_horario_{n}','name':'Usar este horario'},
            {'entity':f'schedule.chacaico_horario_valvula_{n}','name':'Editar días y horarios',
             'icon':'mdi:calendar-edit','tap_action':{'action':'navigate','navigation_path':editor}},
            {'entity':f'sensor.chacaico_horario_proximo_{n}','name':'Próximo cambio'},
            {'entity':f'sensor.chacaico_horario_estado_{n}','name':'Estado'}]}]})
    return {'title':'Horarios','path':'horarios','icon':'mdi:calendar-clock', 'type':'sections',
            'max_columns':2, 'show_icon_and_title':True, 'sections':sections}

def seed():
    return {'version':1,'minor_version':1,'key':'schedule','data':{'items':[
        {'id':f'chacaico_horario_valvula_{n}','name':f'Chacaico horario válvula {n}',
         'icon':'mdi:calendar-clock',**{d:[] for d in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')}}
        for n in NODES]}}

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
    parser.add_argument('--seed',action='store_true')
    parser.add_argument('--merge')
    args=parser.parse_args()
    result=merge(json.load(open(args.merge))) if args.merge else seed() if args.seed else view()
    print(json.dumps(result,ensure_ascii=False,indent=2))
