# Chacaico automation

Control de electroválvulas CubeCell desde Home Assistant mediante una Raspberry
Pi5 y un HAT Waveshare SX1262 868/915M LoRaWAN/GNSS (SKU24654).
Carpeta de trabajo: `/home/torce/work/chacaico/chacaico-automation`.

## Organización

```text
firmware/
  nodes/node_1/          Firmware Arduino, perfil y evidencia del nodo 1
  nodes/node_2/          Firmware Arduino, perfil y evidencia del nodo 2
  libraries/ChacaicoNode/ Lógica compartida de los nodos
  configure-node.py     Genera encabezados privados conservando las claves
  build-node.py         Compila un ID explícito en su propia carpeta build/
  flash-node.sh         Comprueba ID/imagen y carga por un puerto USB explícito
  setup-toolchain.sh    Instala el core CubeCell1.6.0 en .tools/
bridge/
  chacaico_lora_bridge/  App de HAOS: MQTT, protocolo autenticado y driver SX1262
home-assistant/
  config/               YAML mínimo de HAOS y switches de válvula
  scripts/              Instalación, diagnóstico y pruebas supervisadas
  apps/                 Apps auxiliares de sondeo/configuración inicial
  examples/             Opciones SSH y propuesta histórica de SPI
  evidence/             Resultados públicos de HAOS, MQTT, HAT y VPN
  legacy/               Panel YAML retirado y su instalador histórico
tests/                 Pruebas offline y simulaciones, sin hardware
docs/                  Operación, brainstorming y diagnóstico
```

Cada nodo tiene su entrada Arduino y una comprobación de ID. Comparten el mismo
código de control para que las correcciones sean consistentes. Sus claves,
encabezados privados y compilaciones permanecen separados. Los binarios contienen
claves y **no se publican**.

## Estado operativo conocido

| Componente | Versión / identidad | Código |
| --- | --- | --- |
| Nodo 1 | Firmware0.3.0, ID1, HTCC-AB01/ASR6501, PCB V1.2 confirmada | [firmware/nodes/node_1](firmware/nodes/node_1/README.md) |
| Nodo 2 | Firmware0.3.0, ID2, HTCC-AB01/ASR6501; revisión de PCB por verificar | [firmware/nodes/node_2](firmware/nodes/node_2/README.md) |
| Puente | App0.3.0, Python, MQTT ↔ LoRa | [bridge](bridge/README.md) |
| Home Assistant | HAOS18.3, Core2026.9.4, Supervisor2026.09.3, última verificación6/10/2026 | [home-assistant](home-assistant/README.md) |

La reorganización del 6/10/2026 no desplegó software ni cargó dispositivos.
Las simulaciones identifican mejoras pendientes; los equipos siguen con la
última versión probada cuando se vuelvan a conectar.

El recorrido es Home Assistant → MQTT → puente → HAT SPI → LoRa → CubeCell → ACK.
El HAT contiene una sola radio; esta implementación usa LoRa directo, no un
gateway multicanal LoRaWAN. Perfil de banco: **916.8MHz, SF7, BW125kHz, CR4/5,
preámbulo8, CRC, IQ normal, sync privado0x1424 y TX0dBm**.

- GPIO2 abre y GPIO1 cierra con un pulso de50ms; ambos quedan LOW.
- No hay pulsos al arrancar. El estado de una válvula biestable empieza desconocido.
- Un destello verde al abrir, dos al cerrar; luego se restaura el LED de prueba.
- ID y AES-CMAC se validan antes de actuar. Los reintentos de una misma secuencia
  no repiten el pulso. La protección de secuencia del nodo sigue en RAM.
- El ACK confirma la ejecución lógica/GPIO, no la posición física ni el caudal.
- Escucha continua; sueño, parámetros remotos, cierre autónomo y OTA aún no existen.

## Home Assistant y acceso

Pi operativa: `pi5.chacaico`, Home Assistant en `http://pi5.chacaico/` (puerto80).
El panel **Chacaico** se administra desde la UI del usuario:
`http://pi5.chacaico/dashboard-chacaico/`. No instalar el panel retirado de `legacy/`.

Entidades, con `N` igual a1 o2:

- `switch.chacaico_node_N_valve`: adaptador on/off del estado confirmado.
- `valve.chacaico_node_N`: válvula MQTT nativa y sus atributos de confirmación.
- `switch.cubecell_N_led_de_prueba`: LED independiente.
- `sensor.cubecell_N_rssi`, `sensor.cubecell_N_snr`: señal recibida por el HAT.

Con estado desconocido la UI estándar puede mostrar dos acciones on/off; con
estado conocido muestra el toggle. Una orden pendiente no equivale a éxito:
HA espera la publicación del estado confirmado. La disponibilidad de válvula
requiere su propio ACK, aunque el LED responda.

SSH usa la clave ya existente de Arch. En la LAN: `ssh pi5.chacaico`.
Por Tailscale: `ssh pi5.chacaico.remoto`, web
`http://homeassistant.tail3610a7.ts.net/`. La Pi necesita Internet; el acceso VPN
se probó usando la IP100.x estando ambos equipos en la misma LAN. Prueba desde
otra red pendiente. La caducidad de clave y los detalles están en
[docs/remote-access.md](docs/remote-access.md).

## Compilar y programar un nodo

```sh
sh firmware/setup-toolchain.sh
python3 firmware/build-node.py --id 1
python3 firmware/build-node.py --id 2
```

El core está fijado a **CubeCell:CubeCell1.6.0**. Se compila con la librería local
y el FQBN guardado en cada `profile.json`; los resultados quedan en
`firmware/nodes/node_1/build/` y `firmware/nodes/node_2/build/`.

La configuración se toma de `.secrets/node-1.json` y `.secrets/node-2.json`.
Las claves existentes se conservan. En un clon nuevo se generan claves nuevas:
para actualizar placas existentes, recuperar primero su configuración privada
vigente. El puente debe usar las mismas claves que cada nodo.

Con la placa identificada, su antena conectada y el puerto accesible:

```sh
sh firmware/flash-node.sh --id 1 /dev/serial/by-path/PUERTO_FISICO-port0
```

La carga exige un ID y un puerto físico, y comprueba el manifiesto, encabezado,
fuentes y checksum de la imagen. Ambos CP2102 reportan serial0001; no usar `by-id`
para distinguir placas. El puerto no prueba el ID: identificar físicamente el nodo.
Las ACL del puerto USB pueden perderse al desconectarlo.

## Puente y configuración de HAOS

La Pi5 tiene1GB de RAM. Las apps locales se construyen con Core detenido mediante
`home-assistant/scripts/install-local-app.sh`; el script reactiva Core al terminar
y comprueba el machine_id antes de modificar la Pi.

Para una actualización autorizada del puente:

```sh
scp -F /home/torce/.ssh/config -r bridge/chacaico_lora_bridge pi5.chacaico:/local_apps/
ssh -F /home/torce/.ssh/config pi5.chacaico sh -s -- local_chacaico_lora_bridge \
  < home-assistant/scripts/install-local-app.sh
```

Opciones privadas: `.secrets/bridge-options.json`; no imprimir ni commitear.
La Pi conserva credenciales MQTT y backups privados. Scripts/configuración y
límites están en [home-assistant/README.md](home-assistant/README.md) y
[docs/haos-setup.md](docs/haos-setup.md).

## Pruebas offline y diagnóstico de arranque

```sh
python3 -m unittest discover -s tests -v
python3 tests/simulate-startup.py
python3 tests/run-firmware-startup-test.py
```

Las pruebas no se conectan a la Pi, MQTT, USB ni radio. La última ejecuta el
código real del nodo con reloj/GPIO/radio simulados y AES-CMAC del core oficial,
usando únicamente claves públicas de prueba. Detalles en [tests/README.md](tests/README.md).

El 6/10/2026 se reprodujeron demoras de descubrimiento tras conectar el nodo,
espera causada por un vecino ausente y desactualización de estado al perder ACK.
El loop sano acepta la primera orden. La causa física del episodio observado
requiere una captura cuando se reconecte; **las correcciones operativas quedan
pendientes**. Diagnóstico, evidencia y pasos siguientes:
[docs/startup-diagnosis.md](docs/startup-diagnosis.md).

## Diseño pendiente y referencias

- [Tiempos, visibilidad, batería y parámetros remotos](docs/node-timing-brainstorm.md).
- [Opciones de programación remota y OTA](docs/remote-node-updates.md).
- [Core y ejemplos oficiales CubeCell](https://github.com/HelTecAutomation/CubeCell-Arduino).
- [Driver SX126x de Semtech](https://github.com/Lora-net/sx126x_driver).

`.secrets/`, `.tools/`, `node_config.h`, builds y estado privado de VPN están fuera
de Git. El último build anterior a la separación se conserva localmente en
`firmware/build-legacy-node-1/`, también ignorado.
