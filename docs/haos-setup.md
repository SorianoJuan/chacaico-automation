# Configuración aplicada a la Pi

Estado más reciente verificado el 6/10/2026: puente0.3.0, ambos nodos0.3.0,
panel Chacaico administrado desde la UI y Tailscale0.30.1 autorizado. La Pi está
desconectada durante el diagnóstico/reordenamiento posterior de este día.
Los datos de ejecución y credenciales permanecen en la Pi.

## Cronología: instalación inicial del 5/10/2026

- Raspberry Pi5, 1 GB, HAOS18.3, Core2026.9.4, Supervisor2026.09.3.
- Terminal & SSH10.5.0 y Mosquitto7.1.1, con arranque automático y watchdog.
- Perfil `home-assistant/config/configuration-minimal.yaml`: dashboard, automatizaciones,
  MQTT, helpers e historial de 3 días. Se retiró `default_config` y se desactivaron
  entradas de voz/multimedia/descubrimiento que no usa esta Pi.
- SPI del header habilitado mediante `dtparam=spi=on` bajo `[all]` en config.txt.
- Chacaico LoRa bridge0.1.0, protección activa, sin full_access; solo SPI0.0 y GPIO0.
- Prueba de LED y radio verificada; confirmación visual del usuario registrada.
- Puente: aproximadamente 28 MB de RAM; unos 354 MiB disponibles al finalizar.
  No se vieron OOM nuevos en el fragmento de log de host consultado después del
  reinicio; esa observación no sustituye una prueba de estabilidad prolongada.

## Scripts y backups

`apply-minimal.sh` se ejecuta dentro de Terminal & SSH con el nuevo YAML previamente
copiado a `/tmp/chacaico-configuration-minimal.yaml`. Detiene Core, hace backup,
aplica el perfil y desactiva las entradas correspondientes con Core detenido;
valida con el Supervisor y reactiva Core. Incluye recuperación ante errores.

Los backups reales quedan en la Pi:

- `/config/chacaico-backups/minimal-20261005T173728Z-257/`
- `/config/chacaico-backups/boot-spi/`

El primer backup incluye `.storage/core.config_entries`, que contiene secretos:
no copiarlo al repo. `terminal-ssh.example.yaml` muestra la estructura SSH;
`terminal-ssh.yaml` contiene la configuración personal y está ignorado por Git.

## Fuente del configurador temporal

`home-assistant/apps/chacaico_bootstrap` conserva el configurador0.1.4 que se usó una sola
vez para integrar MQTT y habilitar SPI. Se ejecutó con acceso completo al hardware
autorizado para esa operación y después se desinstaló. No está instalado en la Pi.
`spi-setup-proposal.yaml` es una propuesta anterior conservada como referencia.

Para instalar o actualizar el puente, copiar solamente su carpeta:

```sh
scp -F /home/torce/.ssh/config -r bridge/chacaico_lora_bridge pi5.chacaico:/local_apps/
ssh -F /home/torce/.ssh/config pi5.chacaico sh -s -- local_chacaico_lora_bridge < home-assistant/scripts/install-local-app.sh
```

La instalación detiene Home Assistant temporalmente para limitar el pico de RAM.
Las opciones privadas se preparan con `firmware/configure-node.py`; al configurar
el app se transmiten desde `.secrets/bridge-options.json` sin mostrarlas en logs.
No reinstalar el configurador temporal como parte de una actualización del puente.

## Panel y electroválvula (2026-10-06)

- Puente actualizado a0.2.0 conservando claves, frecuencia y permisos de hardware.
- Dashboard YAML en `/config/chacaico-valves.yaml`, URL
  `http://pi5.chacaico/chacaico-valves/valvula-1`, visible como **Chacaico**.
- Entidad MQTT `valve.chacaico_node_1`, registrada y habilitada. Actualiza estado
  solo con respuesta autenticada, sin asumir posición física.
- GPIO2 abre y GPIO1 cierra mediante pulso de 50 ms; ambos quedan LOW.
  LED verde: un destello al abrir, dos al cerrar, luego apagado.
- Consulta de arranque confirmó estado desconocido. Abrir/Cerrar desde el panel
  por el usuario confirmados por radio, con destellos observados por el usuario.
- Memoria del puente observada: 20811776 bytes (aproximadamente 20 MiB).
- Configuración validada con Core detenido y Core reactivado al terminar.
  Se confirmó HTTP200; no fue necesario reiniciar la Pi.
- Backup: `/config/chacaico-backups/valve-panel-20261006T123219Z-221/`.

El panel YAML descrito aquí se retiró posteriormente por pedido del usuario.
Estos pasos quedan como referencia histórica, no como procedimiento actual.
Para reproducir aquel panel, copiar `home-assistant/legacy/chacaico-valves.yaml` a `/tmp/`
y ejecutar `install-valve-panel.sh` antes de `install-local-app.sh`. El primero
deja Core detenido después de validar; el segundo lo reactiva incluso ante error.
Ninguno publica órdenes a la electroválvula. Las pruebas físicas se hacen desde
los botones, con la PCB y su alimentación listas.

## Vista con dos switches (2026-10-06)

El usuario pidió reemplazar los botones Abrir/Cerrar por una fila **Válvula** y
otra fila **LED**. Se conserva la entidad MQTT de válvula y se añade
`switch.chacaico_node_1_valve` con la integración Template; su estado depende
de la confirmación del nodo y conserva estado desconocido/sin disponibilidad.
La fila de LED usa el switch MQTT existente. El panel conserva estado, avisos
de confirmación y enlace RSSI/SNR, y muestra los horarios de comunicación.

La configuración reproducible está en `home-assistant/config/chacaico-controls.yaml`.
En esta etapa, `install-control-switches.sh` instaló ese YAML y el dashboard, con respaldo,
validación y reinicio de Core; no actualiza el puente ni el firmware. El nodo
permanece desconectado. La lógica permanente del LED independiente se prepara
en la siguiente etapa cuando el usuario vuelva a conectar el nodo.

Validación de esta etapa: YAML aceptado por Home Assistant, ambas entidades
registradas y habilitadas, web HTTP200 y hashes de los dos archivos instalados
iguales a los del repo. Backup real en la Pi:
`/config/chacaico-backups/control-switches-20261006T125847Z-349/`.
No se publicaron órdenes ni se modificó/cargó firmware del CubeCell.

## Panel administrado desde la UI (2026-10-06)

Por pedido del usuario se retiró el dashboard YAML `chacaico-valves`. Se conserva
el panel **Chacaico** creado desde la UI, ID `dashboard_chacaico`, URL
`http://pi5.chacaico/dashboard-chacaico/`, y el modo Lovelace `storage`.
La plantilla `chacaico-controls.yaml`, las entidades MQTT y el puente se mantienen.

`remove-yaml-dashboard.sh` comprueba el machine_id y el bloque exacto a retirar,
respalda los archivos, detiene Core, elimina solo ese dashboard, valida y reinicia
Core. Los hashes de todos los archivos `.storage/lovelace*` y del YAML de controles
se verifican antes y después; el script nunca escribe sobre paneles de la UI.
El archivo del panel retirado queda en el respaldo de la Pi y como referencia en
el repo. La configuración mínima ya no lo crea, e `install-control-switches.sh`
actualiza solo las entidades, sin tocar paneles.

Validación: configuración aceptada por HA, Core reactivado y URL del panel de la
UI con HTTP200. Los archivos de paneles de la UI y de controles mantuvieron sus
hashes; los dos switches y la entidad válvula siguen registrados y habilitados.
El puente0.2.0 continúa iniciado. No se enviaron órdenes al nodo ni se modificó
firmware. Respaldo: `/config/chacaico-backups/remove-yaml-dashboard-20261006T130927Z-412/`.
Evidencia: `home-assistant/evidence/ui-dashboard-result.json`.

## Segundo nodo y aislamiento de órdenes (2026-10-06)

El usuario dejó conectado solo el segundo CubeCell, CP2102 `10c4:ea60`, puerto
`/dev/serial/by-path/pci-0000:06:00.1-usb-0:3:1.0-port0` (`/dev/ttyUSB1`). Confirmó
su antena conectada. Ambos adaptadores USB tienen serial0001; se cambió el
script de carga para exigir un puerto físico explícito.

Antes de programarlo, su salida serie informó
`CHACAICO bench node=1 ASR6501 frequency=916800000 LED only` y aceptó una consulta
de LED dirigida al nodo 1. Así se identificó el firmware anterior que explicaba
la reacción de ambos LEDs. No se determinó cómo llegó esa imagen a la placa.

Se generó ID 2 con clave propia conservando la del nodo 1. Firmware0.3.0 comprueba
ID y autenticación antes de ejecutar LED/GPIO, mantiene pulsos de 50 ms y ACK
posterior a ambos GPIO bajos, y restaura el estado independiente del LED tras
los destellos de válvula. Compilado: 51672 bytes (39% de flash), checksum USB
correcto y arranque `CHACAICO valve-0.3.0 node=2` observado. El nodo 1 no se cargó
porque está desconectado; su versión anterior sigue siendo0.2.0.

El puente0.2.0 admite ambos IDs sin reconstrucción. `register-node-2.sh` conserva
la clave del nodo 1 y respalda las opciones privadas dentro de la Pi.
`chacaico-controls.yaml` añade el switch de válvula del nodo 2; MQTT discovery
crea su LED, válvula, RSSI y SNR. La vista de la UI se conserva sin cambios.

Pruebas de software: cinco pruebas del puente con claves diferentes; el sketch
se ejecutó simulado como ID 1 y como ID 2, con rechazo de órdenes ajenas/tag
incorrecto, deduplicación, pulsos y estado independiente del LED. La autenticación
del simulador de GPIO es un stub; las pruebas Python usan AES-CMAC real.

La vista del usuario referencia `valve.chacaico_node_1`. Los adaptadores on/off son
`switch.chacaico_node_1_valve` y `switch.chacaico_node_2_valve`. En el frontend de HA,
un estado `unknown` o `assumed_state` presenta dos botones explícitos; no equivale
a una confirmación de válvula abierta/cerrada. El estado confirmado presenta el
toggle. No se cambió la lógica de estado desconocido para ocultar esa diferencia.
Fuente: https://github.com/home-assistant/frontend/blob/dev/src/components/entity/ha-entity-toggle.ts

Verificación real MQTT/LoRa: LED ON confirmado, OFF dirigido al nodo 1 sin ACK,
GET_LED posterior del nodo 2 confirmó que seguía ON; después OFF del nodo 2
confirmado. No se enviaron órdenes de válvula: su estado sigue desconocido.
Se registraron y habilitaron sus cinco entidades; la web responde HTTP200 y los
hashes del panel de la UI y su registro se mantuvieron idénticos.

Respaldos privados dentro de la Pi:
`/config/chacaico-backups/register-node-2-20261006T132044Z-493/` y
`/config/chacaico-backups/control-switches-20261006T132148Z-530/`.
Resultado público: `firmware/nodes/node_2/evidence/node-2-test-result.json`. El resultado MQTT
también queda en `/config/chacaico-node-2-test.json` de la Pi. Estado final LED OFF.

## Actualización del nodo 1 a0.3.0 (2026-10-06)

El usuario desconectó el nodo 2 y conectó solo el nodo 1 con su antena.
Se identificó por puerto físico y arranque `CHACAICO valve-0.2.0 node=1`, antes
de programarlo. `configure-node.py --id 1` conservó las dos configuraciones
privadas sin cambios (comprobadas por hash); solo seleccionó ID 1 para compilar.
Firmware0.3.0 compiló en 51672 bytes (39% de flash), se cargó con checksum USB
correcto y se comprobó el arranque `CHACAICO valve-0.3.0 node=1`.

La lógica es la misma versión ya verificada mediante simulación para los IDs 1
y 2 en la etapa anterior. Ambos nodos quedan con control independiente de LED,
destellos de válvula que restauran su estado y rechazo de órdenes para otros IDs.
El puente y la configuración de Home Assistant no necesitan modificaciones.
En esta etapa la última compilación local correspondía al nodo 1. Después se
separaron las entradas y builds por identidad; ver README para el procedimiento actual.

Verificación real MQTT/LoRa: LED ON del nodo 1 confirmado; un OFF dirigido al
nodo 2 no cambió su estado y GET_LED posterior confirmó que seguía ON. LED OFF
del nodo 1 confirmado al terminar. No se enviaron órdenes de válvula y su estado
tras reiniciar sigue desconocido. Web HTTP200; panel, registro de paneles y YAML
de controles mantuvieron sus hashes. No se reinició Core ni se reconstruyó o
reconfiguró el puente.

Script reproducible: `home-assistant/scripts/test-node-1-led.sh`, con solo nodo 1
alimentado. Evidencia: `firmware/nodes/node_1/evidence/node-1-test-result.json`; la prueba MQTT
queda también en `/config/chacaico-node-1-test.json` de la Pi. Ambos nodos están
actualizados a0.3.0; las evidencias anteriores conservan el estado de cada etapa.

## Disponibilidad y consultas independientes — puente0.3.0 (2026-10-06)

Se diagnosticó un período en el que el LED del nodo 2 respondía pero la válvula
seguía no disponible. El puente0.2.0 tenía un calendario compartido: cada ACK de
LED posponía 30 s la consulta siguiente, y la válvula exigía un ACK propio antes
de recuperar disponibilidad. Al volver un nodo, las órdenes al LED retrasaban
esa confirmación; el mismo problema podía hacer caducar un estado de válvula
durante tráfico continuado de LED.

El usuario autorizó corregirlo con ambos nodos conectados. Puente0.3.0 usa un
plazo separado para cada tipo de consulta (60 s), intercala consultas pendientes
y órdenes de usuario, y consulta válvula inmediatamente al recuperar enlace por
un ACK de LED o al reconectar MQTT. Una orden fallida de válvula también provoca
consulta de recuperación, sin repetir pulsos. Se mantiene timeout90 s,
ACK1 s, tres intentos y vigencia en cola15 s; no se añade configuración de tiempos
ni sueño a HA/firmware.

Pasaron once pruebas offline: autenticación y selección de nodo, estado
desconocido, consultas bajo órdenes continuas de LED en ambos nodos, recuperación
de enlace/MQTT, comandos en presencia de consultas y fallos sin inventar posición.
Los GPIO/firmware no cambiaron. Respaldos privados y fuente anterior en
`/config/chacaico-backups/bridge-polling-20261006T134153Z-911/`.
La instalación usó `install-local-app.sh`, construyendo con Core detenido.

Brainstorming, sin cambios de funcionamiento, en `docs/node-timing-brainstorm.md`.

Validación real: 40 comprobaciones de LED durante 226 s con ambos nodos; las
válvulas mantuvieron disponibilidad y su estado no cambió. Se observaron cinco
ACK de válvula por nodo, separados como máximo por aproximadamente60.2 s durante
ese período. No se enviaron órdenes de válvula y se restauraron ambos LEDs a OFF.
El observador de eventos estuvo activo los primeros180 s y se comprobaron
instantáneas de disponibilidad en cada ciclo durante toda la prueba; el script
de futuras pruebas amplía ese límite a360 s para cubrir su duración completa.

Puente0.3.0 iniciado, Core/web HTTP200, opciones privadas conservadas y hashes del
panel UI, registro de paneles y controles sin cambios. La fuente desplegada
coincide con el repo. Memoria observada del puente:20910080 bytes (~20 MiB).
No se modificó firmware ni se activó sueño. Evidencia pública:
`home-assistant/evidence/bridge-polling-result.json`, y resultado MQTT en
`/config/chacaico-bridge-polling-test.json` de la Pi.

## SSH remoto por Tailscale (2026-10-06)

El usuario eligió Tailscale y autorizó la Pi con su cuenta. Se instaló la app
comunitaria0.30.1, auto/watchdog, protección activa, sin modificar DNS/rutas de HA.
El alias `pi5.chacaico.remoto` usa IP100.117.24.7, clave Arch existente y
`HostKeyAlias pi5.chacaico`. Se comprobaron SSH/identidad por VPN, alias y web
HTTP200 por IP y MagicDNS. Opciones de SSH/LoRa y hashes de configuración/UI
sin cambios; puente0.3.0 iniciado. No se cambió firmware ni se implementó OTA.

Detalles/caducidad del dispositivo en `docs/remote-access.md`; exploración de
actualizaciones de nodos en `docs/remote-node-updates.md`. Evidencia pública:
`home-assistant/evidence/tailscale-result.json`. Respaldo privado de la Pi:
`/config/chacaico-backups/tailscale-20261006T135712Z-1550/`.

## Reorganización del repositorio y diagnóstico offline (6/10/2026)

Firmware en `firmware/nodes/node_1/` y `node_2/`, aplicación compartida en
`firmware/libraries/ChacaicoNode/`, puente en `bridge/` y archivos de HAOS en
`home-assistant/`. Scripts de compilación/carga requieren identidad explícita y
mantienen builds separados. Ambas identidades compilan con core1.6.0; la imagen
de carga del nodo1 es byte a byte idéntica a la anterior. Claves/opciones privadas
conservadas y fuera de Git. No se accedió ni desplegó nada en los equipos.

Las simulaciones de reconexión, ACK y cola se explican en
[startup-diagnosis.md](startup-diagnosis.md). No se consideran una corrección
operativa ni evidencia de la causa física del incidente. Las propuestas se
validarán cuando vuelvan a conectarse los equipos.
