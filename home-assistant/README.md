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
**Configuración LoRa** contiene todos los parámetros y sus confirmaciones.
La vista original se preserva. El generador reproducible es
`scripts/node-config-view.py`; el JSON público está en `config/node-config-view.json`.
`deploy-config-view.sh` instala con respaldo privado y control SHA256 de edición
concurrente. Ver [operación de configuración](../docs/node-configuration.md). Las plantillas de
`config/chacaico-controls.yaml` agregan switches para los IDs1/2, sin editarlo.
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

## Prueba de banco actual

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
