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

El panel Chacaico se edita desde la UI del usuario. Las plantillas de
`config/chacaico-controls.yaml` agregan switches para los IDs1/2, sin editarlo.
El instalador de plantillas es
`scripts/install-control-switches.sh`. No ejecutar `legacy/install-valve-panel.sh`.

`test-node-1-led.sh` y `test-node-2-led.sh` requieren **solo** el nodo indicado
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
