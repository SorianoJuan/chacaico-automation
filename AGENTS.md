# Chacaico

Repositorio y carpeta de trabajo: `/home/torce/work/chacaico/chacaico-automation`.
Guardar aquí desarrollo, configuración reproducible, documentación y evidencia.

## Estructura y versiones

- `firmware/nodes/node_1/`: sketch/perfil públicos del ID1, firmware0.3.0.
- `firmware/nodes/node_2/`: sketch/perfil públicos del ID2, firmware0.3.0.
- `firmware/libraries/ChacaicoNode/`: lógica compartida; conservar comportamiento
  consistente entre nodos. Cambiar versión en perfiles/librería/banner cuando proceda.
- `bridge/chacaico_lora_bridge/`: app0.3.0 de HAOS, driver SX1262 y protocolo MQTT/LoRa.
- `home-assistant/config/`, `scripts/`, `apps/`, `evidence/`: HAOS y auxiliares.
- `home-assistant/legacy/`: panel retirado; no ejecutarlo ni reinstalarlo.
- `tests/`: pruebas offline; `docs/`: operación, ideas y diagnósticos.

Original HTCC-AB01/ASR6501, core oficial CubeCell1.6.0. PCB V1.2 confirmada para el
nodo1; verificar por separado la del nodo2. Usar `firmware/build-node.py --id N`
y `firmware/flash-node.sh --id N /dev/serial/by-path/PUERTO-port0`.
Cada ID tiene su propio `node_config.h`, build y clave. El helper verifica identidad,
fuentes y checksum antes de subir. Ambos CP2102 tienen serial0001: nunca usar
ese `by-id` para decidir qué placa programar; identificar físicamente el nodo.

GPIO2 abre, GPIO1 cierra, pulsos50ms y ambos LOW al terminar. No pulso al arrancar.
LED: un destello abrir/dos cerrar y restaurar estado del LED independiente.
ACK significa ejecución GPIO; no afirmar posición/caudal sin medición física.
No accionar una válvula conectada como parte automática de instalar o validar:
consultas de estado y LED; primera actuación física desde los controles de HA.
Mantener antenas conectadas al transmitir. Abrir el puerto serie puede reiniciar
la placa: no hacerlo durante una operación de válvula como simple diagnóstico.

## Pi operativa y Home Assistant

Destino `pi5.chacaico`, usando `/home/torce/.ssh/config`, HA en
`http://pi5.chacaico/` (puerto80). `/home/torce/ha-config` y
`/home/torce/haconfig-repo` pertenecen a otro sistema.
Alias VPN `pi5.chacaico.remoto` (IP100.117.24.7), misma clave y HostKeyAlias.
Web `http://homeassistant.tail3610a7.ts.net/`; VPN requiere Internet.
Verificar Supervisor machine_id **2e21da3405714e0cba2d890984d6dfa8** antes de cambios.
SSH entra en la app Terminal & SSH, no en el host HAOS.

El panel Chacaico es de almacenamiento y lo administra el usuario desde la UI.
Crear entidades sin modificar el panel. No sustituir estado desconocido por
cerrado para cambiar la apariencia. Mantener estado pendiente/confirmado separado.

La Pi5 tiene1GB de RAM. Usar `home-assistant/scripts/install-local-app.sh` para
construir apps con Core detenido y reactivarlo. Puente usa libgpiod2 sobre RP1;
NSSBCM21; SPI_NO_CS no está soportado. Las rutas `/local_apps/` en la Pi no cambian
porque el código local esté ahora en `bridge/` y `home-assistant/apps/`.

Puente0.3.0: consulta LED/válvula independientes60s, offline90s, ACK1s, tres intentos,
cola15s y turnos entre consultas/comandos. Diagnóstico de arranque en
`docs/startup-diagnosis.md`: demoras/ACK perdidos reproducidos offline, causa
física todavía no capturada. No declarar corregido/desplegado con solo simulación.
Sueño, configuración remota, cierre autónomo y OTA siguen en brainstorming;
no implementarlos ni cambiar bootloader sin nueva autorización.

## Validación y secretos

- `python3 -m unittest discover -s tests -v`.
- `python3 tests/simulate-startup.py`: ejecuta Bridge.run real con radio/nodo modelados;
  caracteriza defectos actuales. Revisar expectativas al corregirlos.
- `python3 tests/run-firmware-startup-test.py`: sketch real, radio/GPIO/reloj simulados,
  AES-CMAC real del core; solo claves públicas de prueba, nunca encabezados privados.
- Compilar ambos IDs después de cambiar estructura/código compartido; no flashear
  para comprobar una reorganización. Los manifiestos permanecen en builds ignorados.

Nunca publicar `.secrets/`, `.tools/`, encabezados privados, firmware compilado,
credenciales MQTT, `.storage`, claves/estado Tailscale ni URLs temporales de login.
Las imágenes contienen claves. Conservar claves existentes al recompilar y revisar
el índice de Git antes de commitear/pushear. Actualizar docs/evidencia con hechos
verificados y distinguir propuestas, simulaciones y validación física.
