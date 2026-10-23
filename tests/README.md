# Pruebas de configuración y comunicación 0.4.x

```sh
python3 -m unittest discover -s tests -v
python3 tests/simulate-startup.py
python3 tests/run-firmware-startup-test.py
```

No usan Pi, MQTT real, USB, radio ni GPIO físicos. Unittest verifica el scheduler
real, autenticación, persistencia, colas, errores, identidad de builds y el driver
TX→RX. La simulación usa el Engine real con ocho nodos modelados y cinco semillas:
pérdida de peticiones, ACK y READY, colisiones, reinicio de nodo y puente. Fuerza
la pérdida del primer ACK de configuración de cada nodo; exige una sola escritura
por cambio y confirmación posterior. Las órdenes pueden vencer bajo pérdida;
una nueva orden tras recuperar el enlace debe funcionar. No prueba entrega infalible.

La prueba nativa compila el firmware real para IDs 1 y 2, con AES/CMAC real del
core CubeCell 1.6.0 y claves públicas de prueba. Simula radio asíncrona (83 ms),
RTC, flash y GPIO: arranque sin pulso, sesiones, todos los bits autenticados,
reintentos, pulsos de50/200 ms y3000 ms en ambos nodos, restauración persistente a50 ms, destellos, 33 cortes de escritura, error silencioso
de flash, sueño/despertar, límite de ventana, timeout de TX y desborde de reloj.
Requiere g++/cc, cryptography y el core instalado por firmware/setup-toolchain.sh.

Los ejecutables históricos de 0.3.0 con radio/CMAC simplificados fueron sustituidos
por esta prueba. La caracterización original del 6/10/2026 se conserva en
`docs/evidence/2026-10-06/` y en el commit `9ddcd459`.
Los dos scripts aceptan `--output RUTA` para guardar evidencia pública JSON.

## Configuración 0.5.0

`test_stage1_configuration.py`: compatibilidad v2, límites, potencia en dos fases,
ACK final perdido, vigencia, contactos perdidos, métricas, migración del runtime y
fallos al aplicar potencia del HAT. `test_configuration_ui.py`: discovery, rangos,
todas las entidades referenciadas y preservación de las otras vistas. La prueba
C++ del firmware incluye migración de flash,41 cortes de escritura por nodo,
rollback/commit de potencia, persistencia, ventanas y deduplicación.
Las pruebas de campo y el benchmark MQTT/LED se documentan separadamente de estas
simulaciones; un mock no prueba corriente, RF radiada ni posición física.

## Horarios y puente0.5.1

`test_horarios.py` ejecuta la política del YAML real con un entorno Jinja y bus
HA modelados; prueba aislamiento manual, temporada, franjas, expiración,
confirmación reciente, propiedad persistente, cierre tras reinicio y reintentos
sin inundación. También ejecuta el Engine real para vencimientos de OPEN,
reemplazo por CLOSE, límites exactos y saltos de reloj. No es una instancia real
de Core: la carga del paquete y la edición nativa se verifican por separado en
la Pi. Ninguna prueba automática de instalación acciona válvulas reales.

El controlador diario Desde/Hasta usa el macro Jinja real en las pruebas:
inicio inclusivo, final exclusivo, horas iguales deshabilitadas, medianoche,
próximo día local con cambio horario, inputs no disponibles y persistencia.
Los helpers Schedule antiguos no afectan la política diaria. Se conserva la
suite de confirmaciones/reintentos y las pruebas de plazos del bridge.
