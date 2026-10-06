# Pruebas offline

Se ejecutan en esta computadora y no usan la Pi, MQTT real, USB, radio ni GPIO.

```sh
python3 -m unittest discover -s tests -v
python3 tests/simulate-startup.py
python3 tests/run-firmware-startup-test.py
```

La suite unittest contiene20 pruebas:11 del puente,3 de TX→RX y6 de identidad/integridad de builds.
`simulate-startup.py` ejecuta Bridge.run real con reloj virtual y un modelo de
nodo/enlace: siete escenarios de arranque, vecino ausente, pérdida de petición,
pérdida de ACK, clics repetidos y operación sana. Sus aserciones caracterizan
**comportamiento actual, incluyendo defectos**; al corregirlos hay que sustituir
esas expectativas por el comportamiento deseado, conservando las condiciones de fallo.

`run-firmware-startup-test.py` requiere el core oficial CubeCell1.6.0 ya instalado
por `firmware/setup-toolchain.sh`, además de g++/cc y cryptography. Copia las
entradas y librería reales a una carpeta temporal con encabezados/claves públicos,
usa AES/CMAC del core y simula TX_DONE57ms después de Send. Comprueba IDs1/2,
primera orden, pulso50ms, retorno RX, deduplicación y otro clic con nueva secuencia.
No emula el driver Semtech/interrupciones reales ni la placa física.

La prueba anterior más extensa de GPIO/destellos usa CMAC stub y radio sin demora:

```sh
g++ -std=c++17 -Wall -Wextra -Itests/firmware-stubs   tests/firmware_valve_test.cpp -o /tmp/chacaico-valve-test
/tmp/chacaico-valve-test
g++ -std=c++17 -Wall -Wextra -DCHACAICO_NODE_ID=2 -Itests/firmware-stubs   tests/firmware_valve_test.cpp -o /tmp/chacaico-valve-test-2
/tmp/chacaico-valve-test-2
```

También usa solo configuración pública de prueba. Los resultados del6/10/2026
están en `../docs/evidence/2026-10-06/` y se explican en
[el diagnóstico](../docs/startup-diagnosis.md). Los JSON se pueden regenerar con
`--output RUTA` en los tres scripts de caracterización.
