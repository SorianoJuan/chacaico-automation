#!/usr/bin/env python3
"""Generate the configuration view; merge only its reserved path into a UI dashboard."""
import argparse
import copy
import json
from pathlib import Path

VIEW_PATH = "configuracion-lora"


def view(nodes=(1, 2)):
    def entities(title, rows):
        return {"type": "entities", "title": title, "show_header_toggle": False,
                "entities": [{"entity": entity, "name": label} for entity, label in rows]}
    sections = [{"type": "grid", "cards": [
        {"type": "heading", "heading": "Radio de la Raspberry", "heading_style": "title"},
        entities("Potencia del HAT", [
            ("number.chacaico_bridge_tx_power_requested", "Potencia solicitada (dBm)"),
            ("button.chacaico_bridge_power_apply", "Aplicar potencia"),
            ("sensor.chacaico_bridge_tx_power_applied", "Potencia aplicada"),
            ("sensor.chacaico_bridge_power_status", "Estado")]),
        {"type": "markdown", "content": "14 dBm ≈ 25 mW · 20 dBm = 100 mW · 22 dBm ≈ 158 mW. "
         "La potencia aplicada es el ajuste del transmisor; no es una medición de RF ni confirma el enlace."}]}]
    for node in nodes:
        prefix = f"chacaico_node_{node}"
        parameters = [("sleep_s", "Reposo (s)"), ("pulse_ms", "Pulso GPIO (ms)"),
                      ("tx_power_dbm", "Potencia TX (dBm)"), ("listen_ms", "Escucha renovable (ms)"),
                      ("max_awake_ms", "Presupuesto despierto (ms)")]
        cards = [
            {"type": "heading", "heading": f"CubeCell {node}", "heading_style": "title", "icon": "mdi:radio-tower"},
            {"type": "markdown", "content": "**0 s = escucha continua.** Editá los valores y pulsá **Aplicar al nodo**. "
             "Si duerme, espera al próximo contacto. La escucha se renueva con intercambios válidos y puede terminar antes "
             "si no hay trabajo. El pulso GPIO no es la duración del riego. Cambiar potencia incluye una prueba de ida y vuelta; "
             "si falla, el nodo recupera el valor anterior."},
            entities("Parámetros solicitados", [(f"number.{prefix}_{key}_requested", label) for key, label in parameters] + [
                (f"sensor.{prefix}_config_input_error", "Validación"),
                (f"button.{prefix}_config_apply", "Aplicar al nodo"),
                (f"button.{prefix}_config_query", "Consultar al nodo")]),
            entities("Configuración confirmada por el nodo", [
                (f"sensor.{prefix}_config_status", "Actualización"),
                (f"sensor.{prefix}_protocol", "Compatibilidad")]
                + [(f"sensor.{prefix}_{key}_confirmed", label) for key, label in parameters] + [
                (f"sensor.{prefix}_config_revision", "Revisión"),
                (f"sensor.{prefix}_config_confirmed_at", "Confirmada"),
                (f"sensor.{prefix}_link", "Comunicación")]),
            {"type": "markdown", "content": "**Política del puente:** se aplica sin despertar al nodo. Vigencia **0 = automática** "
             "según reposo y ventana. El plazo elegido solo afecta órdenes nuevas; una orden vencida no se vuelve a enviar. "
             "Si el plazo es menor que el reposo, puede vencer antes de que despierte."},
            entities("Entrega y alerta de contacto", [
                (f"number.{prefix}_command_ttl_s_requested", "Vigencia solicitada (s)"),
                (f"number.{prefix}_missed_contacts_requested", "Contactos perdidos tolerados"),
                (f"button.{prefix}_policy_apply", "Aplicar política"),
                (f"sensor.{prefix}_policy_status", "Estado"),
                (f"sensor.{prefix}_command_ttl_s_confirmed", "Vigencia configurada"),
                (f"sensor.{prefix}_missed_contacts_confirmed", "Tolerancia aplicada"),
                (f"sensor.{prefix}_metric_command_ttl_s", "Vigencia efectiva (órdenes nuevas)"),
                (f"sensor.{prefix}_metric_contact_timeout_s", "Plazo sin contacto")]),
            entities("Calidad del enlace", [(f"sensor.{prefix}_metric_{key}", label) for key, label in (
                ("uplink_rssi", "RSSI nodo → HAT"), ("uplink_snr", "SNR nodo → HAT"),
                ("downlink_rssi", "RSSI HAT → nodo"), ("downlink_snr", "SNR HAT → nodo"),
                ("last_ack_ms", "Tiempo de última respuesta"), ("tx_attempts", "Intentos TX"),
                ("tx_errors", "Errores TX"), ("retries", "Reenvíos"), ("acks", "Respuestas válidas"))]),
            entities("Órdenes de válvula y LED", [(f"sensor.{prefix}_command_status", "Última orden")]
                + [(f"sensor.{prefix}_metric_{key}", label) for key, label in (
                ("orders", "Aceptadas"), ("confirmed", "Confirmadas"), ("expired", "Vencidas sin confirmar"),
                ("superseded", "Sustituidas por otra orden"), ("pending", "Pendientes"),
                ("success_percent", "Éxito entre confirmadas y vencidas"),
                ("last_attempts", "Envíos de última orden finalizada"),
                ("last_queue_s", "Espera antes del primer envío"),
                ("last_delivery_s", "Demora desde primer envío"), ("last_total_s", "Demora total"))]
                + [(f"sensor.{prefix}_metrics_started_at", "Contadores desde")]),
            {"type": "markdown", "content": "Las métricas se reinician al arrancar el puente. El porcentaje cuenta órdenes "
             "confirmadas y vencidas; excluye pendientes y sustituidas. No mide pérdida de paquetes. Una confirmación de válvula "
             "confirma ejecución GPIO, no posición física. El tiempo de respuesta incluye el pulso cuando corresponde."},
        ]
        sections.append({"type": "grid", "cards": cards})
    return {"title": "Configuración LoRa", "path": VIEW_PATH, "icon": "mdi:tune",
            "type": "sections", "max_columns": 3, "show_icon_and_title": True, "sections": sections}


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
