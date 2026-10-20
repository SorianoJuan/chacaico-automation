# Validación 0.4.0 — 20/10/2026

- `unit-tests.json`: 40 pruebas del protocolo/scheduler, driver y compilaciones.
- `firmware-fault-tests.json`: firmware real con radio/GPIO/flash simulados y CMAC real.
- `eight-node-simulation.json`: ocho nodos modelados, cinco semillas, pérdidas/reinicios.
- `hardware-result.json`: Raspberry, dos CubeCell y Home Assistant reales.
- `bench-result.txt`: ejecución del script reproducible de configuración y LED.
- Captura final: `../../../home-assistant/evidence/configuration-view.png`.

Se programaron los dos nodos por sus puertos físicos identificados, preservando
las claves. Desde la UI se aplicaron5s/75ms al nodo1 y7s/60ms al nodo2, revisión2.
Reiniciar ambos por USB conservó esos parámetros y avanzó su sesión de arranque.
Una actualización pendiente a6s/80ms del nodo1 sobrevivió a detener el puente
26segundos; se aplicó al recuperar el contacto. Ambos volvieron a responder.

El script de banco volvió a probar borradores sin aplicar, Aplicar/Consultar,
duplicados e independencia de LED con5s/60ms y7s/70ms. Terminó dejando ambos
nodos en0s/50ms y LEDs apagados, revisiones6 y5 respectivamente.

Durante los ensayos no se enviaron órdenes de válvula. Los tiempos de GPIO y
la deduplicación se verificaron en simulación del firmware real. No se midieron
consumo, alcance de campo ni posición física/caudal. La simulación con pérdidas
admite vencimiento explícito de una orden; confirma recuperación al solicitarla
nuevamente después de recuperar la radio, no entrega infalible.

El respaldo de Supervisor y la copia anterior de firmware/bridge se conservan
privados. La nueva vista Configuración LoRa está separada; se comparó la vista
original antes/después y quedó idéntica.
