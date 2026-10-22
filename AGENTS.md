# Chacaico

Repositorio y carpeta de trabajo: `/home/torce/work/chacaico/chacaico-automation`.
Guardar aquí desarrollo, configuración reproducible, documentación y evidencia.

## Estructura y versiones

- `firmware/nodes/node_1/`: sketch/perfil públicos del ID1, firmware0.5.0; máximo configurable3000ms, aplicado50ms.
- `firmware/nodes/node_2/`: sketch/perfil públicos del ID2, firmware0.5.0; máximo configurable3000ms, aplicado50ms.
- `firmware/libraries/ChacaicoNode/`: lógica compartida; conservar comportamiento
  consistente entre nodos. Cambiar versión en perfiles/librería/banner cuando proceda.
- `bridge/chacaico_lora_bridge/`: app0.5.0 de HAOS, driver SX1262 y protocolo MQTT/LoRa.
- `home-assistant/config/`, `scripts/`, `apps/`, `evidence/`: HAOS y auxiliares.
- `home-assistant/legacy/`: panel retirado; no ejecutarlo ni reinstalarlo.
- `tests/`: pruebas offline; `docs/`: operación, ideas y diagnósticos.

Original HTCC-AB01/ASR6501, core oficial CubeCell1.6.0. PCB V1.2 confirmada para el
nodo1; verificar por separado la del nodo2. Usar `firmware/build-node.py --id N`
y `firmware/flash-node.sh --id N /dev/serial/by-path/PUERTO-port0`.
Cada ID tiene su propio `node_config.h`, build y clave. El helper verifica identidad,
fuentes y checksum antes de subir. Ambos CP2102 tienen serial0001: nunca usar
ese `by-id` para decidir qué placa programar; identificar físicamente el nodo.

GPIO2 abre, GPIO1 cierra, pulso configurable10–3000ms en nodos1/2 (predeterminado y aplicado50ms) y ambos LOW al terminar. No pulso al arrancar.
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
Preservar los controles y demás contenido de la vista original. El usuario autorizó
la fila Orden de válvula inmediatamente después de cada válvula en esa vista,
con su estado de orden independiente del LED. También autorizó una pestaña aparte
Configuración LoRa (`configuracion-lora`) para parámetros/confirmaciones;
no mezclarla con los controles de válvula ni reemplazar otras vistas.
Mantener Configuración LoRa minimalista: reposo, pulso, potencia, Aplicar y
confirmación resumida. Ventanas, políticas y diagnóstico van detrás de Más opciones
(subvista `configuracion-lora-avanzada`). No volver a mostrar todos los contadores
ni explicaciones extensas en la vista inicial. No sustituir estado desconocido por
cerrado para cambiar la apariencia. Mantener estado pendiente/confirmado separado.

La Pi5 tiene1GB de RAM. Usar `home-assistant/scripts/install-local-app.sh` para
construir apps con Core detenido y reactivarlo. Puente usa libgpiod2 sobre RP1;
NSSBCM21; SPI_NO_CS no está soportado. Las rutas `/local_apps/` en la Pi no cambian
porque el código local esté ahora en `bridge/` y `home-assistant/apps/`.

Puente y nodos0.5.0 usan v3 (47 bytes); el puente conserva v2 para migración
escalonada de nodos0.4.x. Actualizar puente antes que nodos. Flash esquema2 migra
registros antiguos conservando contador/revisión: no volver al firmware0.4.x
tras migrar porque podría recuperar contadores/configuración obsoletos.
GPIO sigue10–3000ms en nodos1/2, predeterminado/aplicado50ms; otros perfiles200ms.
Los pulsos largos son solo para banco separado de PCB/válvula. No accionar válvulas
como validación de actualizaciones.
Reposo0 es RX continuo, positivo usa READY, escucha renovable1000–10000ms y
presupuesto5000–60000ms. Defaults3000/10000ms. Presupuesto≥escucha+1000 y pulso+2000.
SET_CONFIG lleva cinco parámetros: reposo, pulso, potencia0–22dBm, escucha y presupuesto.
Cambio de potencia: TRIAL en RAM8s, COMMIT_CONFIG guarda, timeout revierte; no marcar
TRIAL como Confirmada. HAT tiene ajuste local independiente0–22dBm, persistente.
Políticas por nodo residen en bridge: vigencia0–7200s (0auto) y tolerancia1–20 contactos.
AutoTTL=max(15,reposo+presupuesto/1000+10), usando máximos de configuración pendiente.
Sin contacto tras tolerancia×período+10s: período reposo+presupuesto/1000+0,25, o32s
con RX continuo. Políticas nuevas no alteran plazos de órdenes ya encoladas.
Métricas se reinician con el bridge y distinguen espera en cola, entrega, RX en ambos
sentidos, intentos, confirmaciones y vencimientos. No confundir porcentaje de órdenes
con pérdida de paquetes, ni potencia configurada con RF medida.
Defaults0s/50ms/0dBm; detalles en `docs/node-configuration.md`.
El ACK incluye estado/config completos. Mantener error/pendiente/confirmado visibles;
Reposo esperado no es offline. Las órdenes de válvula vencen y no se persisten para
reproducirse al reiniciar el bridge. No hay cierre autónomo ni OTA de firmware.
No cambiar bootloader ni agregar esas funciones sin autorización.

## Validación y secretos

- `python3 -m unittest discover -s tests -v`.
- `python3 tests/simulate-startup.py`: Engine real y ocho nodos modelados; pérdidas,
  reinicios, ACK perdidos, expiración explícita y recuperación en cinco semillas.
- `python3 tests/run-firmware-startup-test.py`: sketch real, radio/GPIO/reloj simulados,
  AES-CMAC real del core; solo claves públicas de prueba, nunca encabezados privados.
- `home-assistant/scripts/test-radio-configuration.py --bench --output /tmp/resultado.json`:
  prueba real por SSH/MQTT con configuración y LED, restaura estado previo; no ejecutarla
  como diagnóstico pasivo. El transporte rechaza órdenes de válvula.
- Compilar ambos IDs después de cambiar estructura/código compartido; no flashear
  para comprobar una reorganización. Los manifiestos permanecen en builds ignorados.

Nunca publicar `.secrets/`, `.tools/`, encabezados privados, firmware compilado,
credenciales MQTT, `.storage`, claves/estado Tailscale ni URLs temporales de login.
Las imágenes contienen claves. Conservar claves existentes al recompilar y revisar
el índice de Git antes de commitear/pushear. Actualizar docs/evidencia con hechos
verificados y distinguir propuestas, simulaciones y validación física.
