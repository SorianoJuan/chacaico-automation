# Puente LoRa ↔ MQTT 0.5.1

- `chacaico_lora_bridge/bridge.py`: MQTT, discovery y transporte.
- `engine.py`: scheduler, ventanas, colas, confirmaciones y persistencia.
- `protocol.py`: tramas v3 de47 bytes y compatibilidad v2 de38 bytes, sesión y AES-CMAC64 individual.
- `radio.py`: SX1262 SPI/libgpiod2 y potencia TX configurable.

El puente admite firmware0.5.0 y nodos0.4.x durante la migración. Los nuevos
parámetros de radio requieren firmware0.5.0. El pulso de banco de hasta3000ms
se admite en nodos1/2 con firmware0.4.1; ambos quedaron configurados a50ms. No habilitar automatismos de
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

0.4.3 amplía el máximo configurable a3000ms también para nodo2 y publica el
mismo límite en Home Assistant. Se conserva50ms como valor predeterminado.

0.5.0 permite potencia HAT/nodos, escucha/presupuesto, vigencia/tolerancia y
métricas. Los cambios de potencia del nodo usan TRIAL/COMMIT_CONFIG con reversión
si no se confirma en8s. La política de entrega reside en el puente. Los contadores
son de sesión; no reproducir órdenes de válvula/LED tras reiniciar. El archivo
runtime-v2.json conserva el nombre, pero migra su esquema interno de1 a2.
La frecuencia y el perfil de modulación no cambian.

0.5.1 agrega apertura programada en el tema habitual `node/N/valve/set`:
`{"state":"OPEN","valid_until":1800000000}` (ejemplo de timestamp Unix en segundos).
El plazo efectivo es el menor entre la vigencia normal y ese fin de franja.
Un mismo OPEN pendiente solo puede acortarse, nunca extenderse por repetición.
Un CLOSE cancela/reemplaza el OPEN pendiente. Se rechazan fechas vencidas,
valores no numéricos/no finitos y mensajes retained. Se comprueba el límite
antes de transmitir y al recibir ACK; saltos hacia adelante del reloj también
vencen la orden. Los strings manuales OPEN/CLOSE no cambian. No requiere
reprogramar nodos ni cambia la trama de radio. [Control de horarios](../docs/valve-schedules.md).
