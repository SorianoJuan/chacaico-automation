# Pruebas de configuración y comunicación 0.4.0

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
reintentos, pulsos de 50/200 ms, destellos, 33 cortes de escritura, error silencioso
de flash, sueño/despertar, límite de ventana, timeout de TX y desborde de reloj.
Requiere g++/cc, cryptography y el core instalado por firmware/setup-toolchain.sh.

Los ejecutables históricos de 0.3.0 con radio/CMAC simplificados fueron sustituidos
por esta prueba. La caracterización original del 6/10/2026 se conserva en
`docs/evidence/2026-10-06/` y en el commit `9ddcd459`.
Los dos scripts aceptan `--output RUTA` para guardar evidencia pública JSON.
