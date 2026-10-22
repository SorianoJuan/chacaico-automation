# Configuración LoRa 0.5.0 — 22/10/2026

Se desplegó bridge0.5.0 y la pestaña Configuración LoRa en la Pi verificada,
y se programaron ambos HTCC-AB01 con firmware0.5.0. Puerto3 identificado por
`CMD node=1` y puerto4 por `CMD node=2` antes de cargar. El loader verificó checksum
al terminar ambas cargas. Las claves privadas existentes se conservaron.

## Resultados

- 68 pruebas Python pasaron; scheduler, protocolo, discovery, UI y manifiestos.
- Firmware C++ real con AES-CMAC del core1.6.0: ambos IDs y41 puntos de corte
 de escritura por nodo. Incluye migración, persistencia, prueba/rollback/commit
 de potencia, deduplicación, pulso GPIO simulado y retorno a recepción.
- Scheduler real con8 nodos modelados, pérdidas/reinicios y5 semillas: PASS.
- Prueba física MQTT/LoRa en ambos nodos: PASS. HAT14dBm, nodos14dBm, reposo8s,
 escucha2000ms y presupuesto12000ms. El borrador no cambia el nodo sin Aplicar.
- Las órdenes de LED durante reposo mostraron Pendiente y luego Confirmada:
 nodo1 esperó8,923s antes del primer envío y confirmó0,357s después; nodo2
 esperó8,554s y confirmó0,358s después. Son mediciones de banco de esa ejecución.
- Con vigencia1s, la orden opuesta venció. Una consulta posterior al siguiente
 despertar comprobó que no se había ejecutado. Una orden nueva volvió a funcionar.
- Independencia entre nodos y RSSI/SNR en ambas direcciones verificados.
- Parámetros no predeterminados (10dBm, reposo3s, escucha1500ms, presupuesto8000ms)
 conservaron revisión/valores al reiniciar ambos nodos por USB.
- Reiniciar la app conservó HAT14dBm y políticas45s/4 contactos; recuperó los nodos.
- Los botones Consultar al nodo se probaron también desde la interfaz: ambos
 volvieron de Consultando a Confirmada con protocolo v3.
- Comparación del almacenamiento: una sola vista Configuración LoRa y la otra
 vista del usuario exactamente igual antes/después.68 pruebas offline no sustituyen
 esta comparación con la configuración real.
- No se enviaron órdenes de válvula. LED y configuración se restauraron.

Estado final confirmado para ambos: reposo0s, pulso50ms, TX0dBm, escucha3000ms,
presupuesto10000ms. HAT0dBm. Vigencia0(auto), tolerancia3 contactos, LEDs OFF.
Métricas reiniciadas al reiniciar la app, según el comportamiento documentado.

## Incidencias y límites

La Pi tenía el puente0.4.3 en error: Supervisor registró OOM al iniciar el contenedor
durante el arranque. Se inició correctamente antes de la actualización. Se hizo
backup9f01c042 con Core funcionando y se detuvo Core durante la construcción0.5.0.
El puente actualizado usaba17.420.288 bytes en la muestra de memoria observada.
Esto no elimina la limitación de1GB ni prueba futuros arranques completos de HAOS.

La primera prueba de persistencia tenía un límite de15s después del reset.
El nodo2 no recuperó contacto dentro de ese límite, aunque luego apareció con
boot18 y los valores guardados. La restauración se completó. Se repitió la prueba
con captura del banner y un plazo de65s para varios despertares: PASS en ambos.
No se ha demostrado una causa física de esa demora; no se presenta como entrega
inmediata garantizada. No hubo que volver a programar el nodo para recuperarlo.

Son pruebas de banco y simulaciones, no mediciones de RF radiada, corriente,
alcance5km, seguridad de la PCB de potencia ni posición real de la válvula.

## Archivos

-  `deployment.json`: versiones, tamaños, puertos identificados y preservación UI.
-  `hardware-bench.json`: acciones/estados y métricas de la prueba MQTT/LED.
-  `hardware-persistence.json`: banners, revisiones, reinicios y restauración.
-  `firmware-mocks.json`: firmware real con GPIO/radio/flash simulados.
-  `eight-node-simulation.json`: scheduler real con nodos modelados.
-  `configuracion-lora.png`: captura de los controles instalados.

Reproducción offline: comandos de `tests/README.md`. Prueba real explícita:
`python3 home-assistant/scripts/test-radio-configuration.py --bench --output /tmp/prueba.json`.
Los backups de HA, archivos .storage, claves y binarios no se incluyen.
