# Home Assistant / HAOS

La Pi `pi5.chacaico` usa HAOS, Core mínimo, Mosquitto, Terminal & SSH, el puente
LoRa y Tailscale. Este directorio conserva configuración reproducible, scripts,
apps auxiliares y evidencia; no contiene credenciales ni `.storage` de la Pi.

| Carpeta | Contenido |
| --- | --- |
| `config/` | Perfil mínimo, recorder3d/commit30, plantillas de switches de válvula |
| `scripts/` | Instalación guardada por machine_id, sondeo, VPN, retiro del panel y pruebas LED |
| `apps/` | Probe SX1262 y configurador histórico de SPI/host |
| `examples/` | Opciones SSH sin clave y propuesta de configuración SPI |
| `evidence/` | Resultados públicos; los backups privados siguen en la Pi |
| `legacy/` | Panel YAML retirado y su instalador; no ejecutar en el sistema actual |

El código de la app permanente del puente está en `../bridge/chacaico_lora_bridge/`.
Copiar cada app a `/local_apps/` en la Pi antes del instalador, conservando su
nombre de carpeta/slug. Para Pi1GB, `scripts/install-local-app.sh` detiene Core
durante la construcción y lo reactiva al terminar.

El panel Chacaico se edita desde la UI del usuario. La pestaña nueva
**Configuración LoRa** muestra solo reposo, pulso, potencia, Aplicar y una
confirmación breve por nodo, más potencia del HAT. **Más opciones** abre una
subvista oculta con escucha, política de entrega y diagnóstico resumido. Los
errores de validación aparecen solo cuando existen. Las demás métricas siguen
disponibles como entidades, sin llenar la pantalla de contadores.
La vista original se preserva. El generador reproducible es
`scripts/node-config-view.py`; los JSON públicos están en `config/node-config-view.json` y
`config/node-config-advanced-view.json` (exportar con `--advanced`).
`deploy-config-view.sh` instala con respaldo privado y control SHA256 de edición
concurrente. Ver [operación de configuración](../docs/node-configuration.md). Las plantillas de
`config/chacaico-controls.yaml` agregan switches para los IDs1/2/3/4, sin editarlo.
El instalador de plantillas es
`scripts/install-control-switches.sh`. No ejecutar `legacy/install-valve-panel.sh`.

Los scripts `test-node-1-led.sh`, `test-node-2-led.sh` y `test-bridge-polling.sh`
son históricos de0.3.0; no constituyen la suite de configuración0.4.0.
Los dos primeros requieren **solo** el nodo indicado
alimentado para su prueba de destino ajeno; si ambos están conectados no usar
esa expectativa. `test-bridge-polling.sh` prueba ambos con LED/consultas y restaura
sus LEDs. Ninguno publica órdenes de válvula.

SPI ya fue habilitado; el configurador temporal fue retirado. No reinstalarlo
como operación rutinaria. Tailscale ya está instalado; su instalador es solo
para la primera instalación. Las modificaciones remotas comprueban el Supervisor
machine_id **2e21da3405714e0cba2d890984d6dfa8**.

[Operación y evidencia histórica](../docs/haos-setup.md),
[acceso remoto](../docs/remote-access.md),
[diagnóstico de arranque](../docs/startup-diagnosis.md).

## Prueba de banco histórica 0.4.x

`scripts/test-node-configuration.sh --bench` se ejecuta dentro de Terminal & SSH,
con ambos nodos/antenas conectados. Exige empezar en0s/50ms y LEDs apagados;
verifica borradores, Aplicar, Consultar, deduplicación e independencia durante sueño.
Restaura0s/50ms y LEDs apagados. No envía órdenes de válvula. Modifica configuración:
no ejecutarla como simple diagnóstico en una instalación de campo.

La prueba adicional del20/10 reinició ambos nodos por USB y detuvo el bridge25s
con una configuración pendiente; la evidencia está en `../docs/evidence/2026-10-20/`.

## Orden de válvula en la vista principal

`Orden de válvula` aparece inmediatamente debajo del control de cada válvula.
Usa `sensor.chacaico_node_N_valve_command_status`, publicado por el bridge0.4.1
sobre `chacaico/lora/node/N/valve/command/status`: Pendiente, Confirmada,
Sin confirmación; consultando, o Vencida sin confirmar. El LED no cambia este
estado. Tras reiniciar el puente empieza en Sin órdenes pendientes: no se presume
éxito ni se reproducen órdenes previas. La pestaña Configuración LoRa se conserva.
`scripts/main-view-order-status.py` combina únicamente esas dos filas con una
copia privada del dashboard, preservando el resto y verificando que cada control
aparece una sola vez. No publicar el JSON privado resultante.


## Ciclos de banco solicitados por el usuario

`python3 home-assistant/scripts/cycle-node1-bench.py --cycles 100 --output /tmp/prueba-nodo1.jsonl`
alterna OPEN/CLOSE del nodo1 con cinco segundos entre el inicio de las órdenes.
Solo usar con el CubeCell separado de PCB/válvula y autorización explícita para
accionar. Exige sleep0, pulso3000ms y una confirmación nueva antes de continuar;
termina después del cierre del último ciclo. Un fallo/intervención de otro control
interrumpe la tanda. SIGINT/SIGTERM deja de enviar órdenes; un pulso ya iniciado
termina en el nodo. No instala una automatización permanente ni modifica parámetros.

Usa el alias SSH `pi5.chacaico` y el helper privado `/tmp/mqtt-env.sh` de esa Pi;
el helper y sus credenciales no están versionados. El `.pid` junto al log permite
identificar la ejecución; verificar el proceso antes de enviarle una señal.
Los100 ciclos del20/10/2026 quedaron en ejecución en segundo plano; consultar
`docs/evidence/2026-10-20/pulse3s/hundred-cycle-start.json` para el registro vivo.
Ese archivo acredita el inicio y las confirmaciones observadas, no la finalización.

## Prueba de banco 0.5.0

`python3 home-assistant/scripts/test-radio-configuration.py --bench --output /tmp/result.json`
se ejecuta desde esta computadora por SSH. Verifica máquina, exige ambos nodosv3
con reposo≤30s, guarda los ajustes iniciales y prueba14dBm, escucha2s, presupuesto12s,
reposo8s, LED en cola y vencimiento de una orden con plazo1s. Comprueba aislamiento,
métricas de ambas direcciones y que la orden vencida no se ejecute al despertar.
Restaura y confirma ajustes, políticas, potencia del HAT y LED originales, incluso
si falla una prueba; informa errores de restauración si el enlace se pierde.
El transporte `mqtt-bench-transport.sh` rechaza temas de válvula y mantiene las
credenciales MQTT en la Pi. Es una prueba que modifica el banco, no un diagnóstico
pasivo. No lanzarla durante el uso de las válvulas.

## Agregar nodos conservando los existentes

Crear el sketch y perfil público, compilar con `firmware/build-node.py --id N` y
cargar únicamente la placa identificada. `configure-node.py` conserva claves
existentes y genera `.secrets/bridge-options.json`. Copiar este archivo privado a
`/tmp/chacaico-bridge-options.json` de la Pi y ejecutar allí `register-nodes.sh 3 4`
para esta ampliación. El script compara todas las identidades existentes, solo
admite los IDs explícitos, conserva otras opciones y respalda/restaura ante fallo.
Reinicia solo el puente; no recompila la app ni reinicia Core.

Agregar las plantillas de válvula y recargar **Template entities** desde las
herramientas YAML después de `ha core check`. El generador de vistas incluye1–4
por defecto; verificar que preserve la vista principal antes de guardar desde UI.
[Alta verificada del23/10/2026](../docs/evidence/2026-10-23/nodes-3-4/README.md).

## Tarjetas de los nodos3 y4 en la vista principal

Agregadas el23/10/2026 a pedido del usuario, copiando el formato de1/2:
válvula MQTT nativa, Orden de válvula, LED independiente, SNR y RSSI.
`config/main-view-node-3-4-cards.json` conserva únicamente las dos tarjetas públicas;
no contiene el dashboard privado. Se agregaron después de Nodo2, preservando las
otras tarjetas y ambas vistas de configuración. Verificadas en UI con señal real
para3/4; sin accionar válvulas ni LED como parte de esta edición.
