#!/usr/bin/env python3
"""Generate the configuration view; merge only its reserved path into a UI dashboard."""
import argparse
import copy
import json
from pathlib import Path

VIEW_PATH = "configuracion-lora"


def view(nodes=(1, 2)):
    sections = []
    for node in nodes:
        prefix = f"chacaico_node_{node}"
        sections.append({"type": "grid", "cards": [
            {"type": "heading", "heading": f"CubeCell {node}", "heading_style": "title", "icon": "mdi:radio-tower"},
            {"type": "markdown", "content": "**0 s = escucha continua.** Editá ambos valores y pulsá **Aplicar**. "
             "Si está dormido, el cambio espera su próximo contacto. El pulso es el impulso eléctrico, "
             "no la duración del riego."},
            {"type": "entities", "title": "Parámetros solicitados", "show_header_toggle": False, "entities": [
                {"entity": f"number.{prefix}_sleep_s_requested", "name": "Reposo (segundos)"},
                {"entity": f"number.{prefix}_pulse_ms_requested", "name": "Pulso GPIO (milisegundos)"},
                {"entity": f"button.{prefix}_config_apply", "name": "Aplicar ambos parámetros"},
                {"entity": f"button.{prefix}_config_query", "name": "Consultar al nodo"},
            ]},
            {"type": "entities", "title": "Última configuración confirmada", "show_header_toggle": False, "entities": [
                {"entity": f"sensor.{prefix}_config_status", "name": "Actualización"},
                {"entity": f"sensor.{prefix}_sleep_s_confirmed", "name": "Reposo"},
                {"entity": f"sensor.{prefix}_pulse_ms_confirmed", "name": "Pulso GPIO"},
                {"entity": f"sensor.{prefix}_config_revision", "name": "Revisión"},
                {"entity": f"sensor.{prefix}_config_confirmed_at", "name": "Confirmada"},
                {"entity": f"sensor.{prefix}_link", "name": "Comunicación"},
                {"entity": f"sensor.{prefix}_command_status", "name": "Última orden"},
            ]},
        ]})
    return {"title": "Configuración LoRa", "path": VIEW_PATH, "icon": "mdi:tune",
            "type": "sections", "max_columns": 2, "show_icon_and_title": True, "sections": sections}


def merge(document, nodes=(1, 2)):
    result = copy.deepcopy(document)
    if result.get("key") != "lovelace.dashboard_chacaico":
        raise ValueError("Unexpected dashboard storage key")
    views = result["data"]["config"].setdefault("views", [])
    for index, existing in enumerate(views):
        if existing.get("path") == VIEW_PATH:
            if existing.get("title") != "Configuración LoRa":
                raise ValueError("Reserved view path is already used by another view")
            views[index] = view(nodes)
            break
    else:
        views.append(view(nodes))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nodes", type=int, nargs="+", default=[1, 2])
    args = parser.parse_args()
    if len(args.nodes) != len(set(args.nodes)) or any(not 1 <= n <= 65534 for n in args.nodes):
        parser.error("Node IDs must be unique and between 1 and 65534")
    result = merge(json.loads(args.storage.read_text()), args.nodes) if args.storage else view(args.nodes)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
