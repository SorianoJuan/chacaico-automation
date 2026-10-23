# Alta de nodos3 y4 — 23/10/2026

Ambos HTCC-AB01/ASR6501 cargados con firmware0.5.0, core1.6.0 e identidades y
claves independientes. Revisión impresa de PCB no verificada. Cada imagen ocupa
56524bytes (43%). El uploader identificó silicon0x256a11b5 y verificó el checksum.

Asignación física durante esta sesión (no identificación permanente):

| Nodo | Puerto USB físico | Dispositivo Linux |
| --- | --- | --- |
| 3 | `pci-0000:06:00.1-usb-0:3:1.0-port0` | `/dev/ttyUSB0` |
| 4 | `pci-0000:06:00.1-usb-0:4:1.0-port0` | `/dev/ttyUSB1` |

El primer intento del3 falló al sincronizar con el bootloader (firma0x80).
El segundo terminó correctamente; el4 se cargó al primer intento.
El usuario otorgó ACL para los puertos. No confiar en serial0001 para distinguirlos.

Puente0.5.0 registrado con IDs1/2/3/4. Verificado machine_id de la Pi y preservadas
las identidades y opciones anteriores. Respaldo privado de opciones en la Pi.
No se modificó el firmware de1/2 ni se probó su hardware en esta sesión.

Verificación real por MQTT/LoRa, registrada en `radio-result.json`:

- Ambos confirman protocolov3 y configuración0s/50ms/0dBm/3000ms/10000ms.
- Máximo configurable de pulso200ms para3/4;1/2 conservan3000ms.
- LED ON/OFF con ACK en cada nodo; consulta fresca al otro confirma independencia.
- LEDs finales OFF. Cero órdenes de válvula; posición inicial desconocida.
- La prueba es de banco cercano, no acredita alcance de campo ni posición física.

Home Assistant: entidades MQTT de3/4, switches plantilla
`switch.chacaico_node_3_valve` y `switch.chacaico_node_4_valve`, configuración
minimalista y subvista avanzada para cuatro nodos. `ha core check` correcto;
recarga de plantillas desde UI sin reiniciar Core. Vista principal idéntica a la
copia previa; entidades disponibles para agregar manualmente.

Validación offline:68 pruebas unittest correctas. Perfiles y manifiestos de3/4
verificados antes de cargar; se conservan ignorados los builds y secretos.
