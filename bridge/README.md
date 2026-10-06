# Puente LoRa ↔ MQTT

Código de la app HAOS **Chacaico LoRa bridge0.3.0** en `chacaico_lora_bridge/`:

- `bridge.py`: descubrimiento MQTT, colas, confirmaciones y disponibilidad.
- `radio.py`: SX1262 por SPI/libgpiod2, cableado Waveshare/Pi5.
- `protocol.py`: destino/secuencia/operación y AES-CMAC truncado64bits.
- `config.yaml`, `Dockerfile`: manifiesto y empaquetado de la app.

Es software de la Raspberry; los firmwares MCU están en `../firmware/nodes/`.
Consultas LED/válvula independientes60s, offline90s, ACK1s, tres intentos,
cola15s. Alterna consultas y comandos, con una transacción de radio pendiente.
Las opciones privadas vienen del Supervisor; las credenciales MQTT no se guardan
en el código. Preservar claves por nodo y la secuencia persistente del puente.

La reorganización no cambia contenido de estos tres módulos ni el manifiesto.
La instalación en la Pi sigue en `/local_apps/chacaico_lora_bridge`.
Usar `../home-assistant/scripts/install-local-app.sh` con Core detenido para
construir en la Pi1GB. Instrucciones en el README raíz.

[Diagnóstico de conexión/ACK](../docs/startup-diagnosis.md): mejoras pendientes,
no desplegadas. No habilitar self_test como parte de instalar si se pretende
solo consultar; esa opción envía ON/OFF al LED del primer nodo.
