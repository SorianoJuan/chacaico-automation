# Puente LoRa ↔ MQTT 0.4.1

- `chacaico_lora_bridge/bridge.py`: MQTT, discovery y transporte.
- `engine.py`: scheduler, ventanas, colas, confirmaciones y persistencia.
- `protocol.py`: tramas v2 de 38 bytes, sesión y AES-CMAC64 individual.
- `radio.py`: SX1262 SPI/libgpiod2, sin cambios en esta actualización.

El protocolo requiere firmware 0.4.0 en los nodos. No habilitar automatismos de
prueba: la opción heredada self_test se ignora. Los comandos de configuración son
independientes de las válvulas; no hay actuación de válvula al instalar/arrancar.
Las credenciales MQTT se obtienen de Supervisor y las claves de opciones privadas.
Preservar los datos del add-on: sequence.json y runtime-v2.json.

La app sigue en `/local_apps/chacaico_lora_bridge` en la Pi. Construir con Core
detenido mediante el instalador de `../home-assistant/scripts/`. La copia de
seguridad de Home Assistant debe hacerse antes de detener Core.

Operación, tiempos, límites y recuperación: [configuración de nodos](../docs/node-configuration.md).

0.4.1 agrega un estado exclusivo de la última orden de válvula por nodo.
Las confirmaciones de LED y consultas de fondo no lo sobrescriben.
