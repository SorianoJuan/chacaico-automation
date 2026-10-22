#!/usr/bin/env python3
"""Generate the configuration view; merge only its reserved path into a UI dashboard."""
import argparse
import copy
import json
from pathlib import Path

VIEW_PATH = "configuracion-lora"
ADVANCED_PATH = "configuracion-lora-avanzada"
DASHBOARD_PATH = "/dashboard-chacaico/"


def entities(title, rows):
    return {"type": "entities", "title": title, "show_header_toggle": False,
            "entities": [{"entity": entity, "name": label} for entity, label in rows]}


def reported(node, fields):
    values = ["{{ states('sensor.chacaico_node_%s_%s_confirmed') }} %s" % (node, key, unit)
              for key, unit in fields]
    return {"type": "markdown", "content": "En uso: " + " · ".join(values)}


def validation(node):
    entity = f"sensor.chacaico_node_{node}_config_input_error"
    return {"type": "conditional", "conditions": [
        {"condition": "state", "entity": entity, "state_not": state}
        for state in ("Sin errores", "unknown", "unavailable")],
        "card": entities("Revisá los valores", [(entity, "Aviso")])}


def view(nodes=(1, 2)):
    sections = []
    for node in nodes:
        prefix = f"chacaico_node_{node}"
        sections.append({"type": "grid", "cards": [
            entities(f"Nodo {node}", [
                (f"number.{prefix}_sleep_s_requested", "Reposo (0 = continuo)"),
                (f"number.{prefix}_pulse_ms_requested", "Pulso"),
                (f"number.{prefix}_tx_power_dbm_requested", "Potencia"),
                (f"button.{prefix}_config_apply", "Aplicar"),
                (f"sensor.{prefix}_config_status", "Última aplicación")]),
            reported(node, [("sleep_s", "s"), ("pulse_ms", "ms"), ("tx_power_dbm", "dBm")]),
            validation(node)]})
    sections.append({"type": "grid", "cards": [
        entities("Raspberry · HAT", [
            ("number.chacaico_bridge_tx_power_requested", "Potencia"),
            ("button.chacaico_bridge_power_apply", "Aplicar"),
            ("sensor.chacaico_bridge_tx_power_applied", "En uso")]),
        {"type": "conditional", "conditions": [{"condition": "state",
            "entity": "sensor.chacaico_bridge_power_status", "state_not": "Aplicada en el HAT"}],
         "card": entities("Potencia del HAT", [("sensor.chacaico_bridge_power_status", "Estado")])},
        {"type": "button", "name": "Más opciones", "icon": "mdi:tune", "show_icon": False,
         "tap_action": {"action": "navigate", "navigation_path": DASHBOARD_PATH + ADVANCED_PATH}}]})
    return {"title": "Configuración LoRa", "path": VIEW_PATH, "icon": "mdi:tune",
            "type": "sections", "max_columns": 2, "show_icon_and_title": True, "sections": sections}


def advanced_view(nodes=(1, 2)):
    sections = []
    for node in nodes:
        prefix = f"chacaico_node_{node}"
        sections.append({"type": "grid", "cards": [
            entities(f"Nodo {node} · Escucha", [
                (f"number.{prefix}_listen_ms_requested", "Ventana de escucha"),
                (f"number.{prefix}_max_awake_ms_requested", "Máximo despierto"),
                (f"button.{prefix}_config_apply", "Aplicar al nodo"),
                (f"sensor.{prefix}_config_status", "Última aplicación")]),
            reported(node, [("listen_ms", "ms de escucha"), ("max_awake_ms", "ms despierto")]),
            validation(node),
            entities("Entrega de órdenes", [
                (f"number.{prefix}_command_ttl_s_requested", "Vigencia (0 = automática)"),
                (f"number.{prefix}_missed_contacts_requested", "Contactos perdidos tolerados"),
                (f"button.{prefix}_policy_apply", "Aplicar política"),
                (f"sensor.{prefix}_policy_status", "Estado")]),
            reported(node, [("command_ttl_s", "s de vigencia"), ("missed_contacts", "contactos")]),
            entities("Diagnóstico", [
                (f"sensor.{prefix}_link", "Comunicación"),
                (f"sensor.{prefix}_metric_uplink_rssi", "Señal recibida por HAT"),
                (f"sensor.{prefix}_metric_downlink_rssi", "Señal recibida por nodo"),
                (f"sensor.{prefix}_metric_last_total_s", "Demora de última orden"),
                (f"button.{prefix}_config_query", "Consultar al nodo")])
        ]})
    return {"title": "Más opciones LoRa", "path": ADVANCED_PATH, "subview": True,
            "back_path": DASHBOARD_PATH + VIEW_PATH, "type": "sections", "max_columns": 2,
            "sections": sections}


def merge(document, nodes=(1, 2)):
    result = copy.deepcopy(document)
    if result.get("key") != "lovelace.dashboard_chacaico":
        raise ValueError("Unexpected dashboard storage key")
    views = result["data"]["config"].setdefault("views", [])
    for replacement in (view(nodes), advanced_view(nodes)):
        matches = [i for i, existing in enumerate(views) if existing.get("path") == replacement["path"]]
        if len(matches) > 1:
            raise ValueError("Duplicate reserved view path")
        if matches:
            index = matches[0]
            if views[index].get("title") != replacement["title"]:
                raise ValueError("Reserved view path is already used by another view")
            views[index] = replacement
        else:
            views.append(replacement)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", type=Path)
    parser.add_argument("--advanced", action="store_true", help="Export the hidden advanced subview")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nodes", type=int, nargs="+", default=[1, 2])
    args = parser.parse_args()
    if len(args.nodes) != len(set(args.nodes)) or any(not 1 <= n <= 65534 for n in args.nodes):
        parser.error("Node IDs must be unique and between 1 and 65534")
    result = merge(json.loads(args.storage.read_text()), args.nodes) if args.storage else (advanced_view(args.nodes) if args.advanced else view(args.nodes))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
