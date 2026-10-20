# Puente LoRa ↔ MQTT 0.4.2

- `chacaico_lora_bridge/bridge.py`: MQTT, discovery y transporte.
- `engine.py`: scheduler, ventanas, colas, confirmaciones y persistencia.
- `protocol.py`: tramas v2 de 38 bytes, sesión y AES-CMAC64 individual.
- `radio.py`: SX1262 SPI/libgpiod2, sin cambios en esta actualización.

El protocolo es compatible con firmware0.4.x. El pulso de banco de hasta3000ms
solo se admite para nodo1, con firmware0.4.1; nodo2 conserva su límite200ms. No habilitar automatismos de
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

0.4.2 espera el pulso completo antes de cerrar la ventana/descartar el ACK,
reserva recepción para su respuesta y difiere un pulso si no cabe antes del
límite de vigilia. La metadata de versión de firmware es una etiqueta de despliegue
mantenida en el bridge; la trama v2 no transmite una versión de software.
