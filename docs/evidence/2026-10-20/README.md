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


## Prueba posterior con sleep de30s y puente0.4.1

`sleep30-user-valve-test.json` registra una apertura solicitada por el usuario
desde Home Assistant a las14:20:43.152 ART. El nodo1 estaba en Reposo esperado;
la orden pasó a Pendiente y a Confirmada al despertar, a las14:20:52.556:
9.404s desde la solicitud. ACK de SET_VALVE con secuencia949338841, resultado0,
sesión3 y despertar26 (el anterior era25). El estado informado pasó a abierto.
La UI mostró Pendiente junto al switch y después Confirmada con el switch encendido;
la captura `../../../home-assistant/evidence/sleep30-valve-confirmed.png` muestra
el resultado confirmado. No se midió posición mecánica ni caudal.

Quedó configurado el nodo1 en30s/50ms, revisión7; no se modificó el nodo2.
Este ensayo es posterior a los ensayos sin actuación de válvula descritos arriba.


## Pulso de banco de3s, solo nodo1

`pulse3s/` contiene47 pruebas unitarias, pruebas del firmware real simulado para
ambos IDs, simulación de8 nodos y el resultado de configuración real por radio.
Se probó el GPIO en HIGH durante3000ms, regreso a LOW antes del ACK, rechazo de
pulsos largos en nodo2, deduplicación y presupuesto de vigilia/espera del bridge.

Instalados: bridge0.4.2 y firmware0.4.1 solo en nodo1. Nodo2 no se flasheó y sigue
con0.4.0; su perfil0.4.1 se compiló para validar el código compartido. El nodo1
confirmó0s/3000ms, revisión9; nodo2 sigue0s/50ms, revisión5. El reposo de nodo1
ya era0s antes de esta intervención, por cambio posterior del usuario a la prueba
anterior de30s. Las claves y vistas se conservaron; respaldo Supervisor5789b21a.

La captura `../../../home-assistant/evidence/node1-pulse3s-confirmed.png` muestra
el valor confirmado en Home Assistant. No se enviaron órdenes de válvula como
parte de esta actualización. La medición física queda a cargo del usuario con
el CubeCell separado de PCB/válvula. Volver a50ms antes de reconectar la potencia.
