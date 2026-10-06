# Demora al conectar y switch que vuelve atrás — 6/10/2026

El usuario desconectó Pi/nodos después de observar demora en HA, un primer LED
que no parecía responder y varios intentos para abrir. Aclaró que «rebote» era
el switch de HA volviendo atrás, no varios accionamientos físicos observados.
Se investigó offline; no se conectó ni modificó ningún equipo durante este trabajo.

## Resultado y límites

Se reprodujeron varios mecanismos compatibles con el síntoma. El sketch acepta
la primera orden en un arranque sano; no apareció un período de calentamiento
necesario ni un sueño activo. No se confirmó cuál mecanismo ocurrió en el episodio
real: falta capturar comando, ejecución y ACK cuando vuelva a conectarse.

| Caso reproducido | Resultado de esta simulación | Evidencia que aporta |
| --- | --- | --- |
| Nodo encendido después del primer barrido fallido | Encendido en t15s, disponible en t60.154488s: demora45.154488s | Consulta fallida se agenda otra vez60s después; el nodo no anuncia arranque |
| Nodo1 responde, nodo2 ausente | Orden LED espera3.17788s | Una consulta ya iniciada al nodo ausente ocupa sus tres intentos antes del siguiente comando |
| Primer SET_LED perdido en sus tres intentos | El primer clic no ejecuta; otro clic posterior funciona | Es posible observar ese patrón sin una condición de calentamiento en el loop |
| Orden LED ejecutada pero sus ACK perdidos | Estado MQTT se actualiza59.352304s después de la ejecución modelada | Fallo de SET_LED no fuerza GET_LED inmediato, a diferencia de SET_VALVE |
| Orden válvula ejecutada pero ACK perdidos | Un pulso; pendiente→sin confirmar→GET_VALVE confirma abierta | El estado puede volver/desconocerse en HA mientras la ejecución ya ocurrió |
| Tres clics de abrir pendientes | Tres secuencias distintas y tres pulsos modelados | Cada clic es una orden nueva; no se agrupan las peticiones iguales |
| Primer LED/abrir con enlace sano | Confirmación rápida y un pulso | No hace falta una orden previa para habilitar la actuación |

Son tiempos deterministas de escenarios artificiales, no mediciones sobre la Pi.
El modelo parte de estado desconocido al arrancar; los casos de abrir después de
una posición cerrada usan una condición inicial explícita de una orden anterior.

## Hallazgos concretos en el código

### Descubrimiento y vecino ausente

`Bridge.start_request()` adelanta el próximo GET60s incluso cuando fallará.
Los nodos solo responden a solicitudes; no hay anuncio de arranque. Si se
conecta una placa justo después del barrido, puede esperar casi un período.
Hay un único `pending`: los comandos no interrumpen una consulta ya enviada.
Tres intentos con espera1s añaden varios segundos cuando el vecino está ausente.

### Confirmación y estado de Home Assistant

El puente publica el estado LED al recibir ACK. Si falla SET_LED, borra `pending`
pero no agenda GET_LED inmediato ni publica una confirmación específica de fallo
para ese LED. Puede quedar el estado anterior hasta la consulta periódica.
SET_VALVE sí publica «unconfirmed»/estado desconocido y fuerza una consulta.

HA MQTT con `state_topic` y sin modo optimista cambia el estado con los mensajes
recibidos, no con el envío de la orden. Eso explica por qué el control puede
volver al último estado conocido al pulsarlo; no demuestra por sí solo que el
GPIO no actuó. La simulación examina publicaciones MQTT, no renderiza el frontend.
Fuente: [MQTT Valve](https://www.home-assistant.io/integrations/valve.mqtt/) y
[MQTT Switch](https://www.home-assistant.io/integrations/switch.mqtt/).

### Cambio TX→RX y ACK temprano

`Radio.send()` espera TX_DONE y después ejecuta `receive()`; la Pi no está
recibiendo mientras su conmutador de RF está en TX. El nodo prepara el ACK25ms
después de procesar el LED; para válvula espera además el pulso50ms y algo de
procesamiento/RGB. Una pausa del proceso en ese cambio puede perder la respuesta.

Se ejecutó el driver Python real con SPI/GPIO/reloj falsos: sin pausa cambió a
RX antes del ACK; con una pausa inyectada de200ms cambió después de terminar
el ACK completo. Esto demuestra la posibilidad temporal en ese camino del código,
no que la Pi haya sufrido esa pausa. La transmisión modelada de20bytes dura
56.576ms en SF7/BW125/CR4/5, header explícito, CRC y preámbulo8.

### Reintento frente a otro clic

El firmware reconoce una secuencia repetida y reenvía ACK sin repetir GPIO.
El puente asigna una secuencia nueva a cada MQTT recibido y usa FIFO: varios
clics iguales pendientes se ejecutan separadamente. El sketch actual vuelve a
pulsar aun cuando la nueva orden pide el mismo estado lógico conocido.
Esto se confirmó también ejecutando el código C++ real con radio asíncrona falsa.

## Cómo se comprobó

- `tests/simulate-startup.py`: Bridge.run real, sus callbacks MQTT y AES-CMAC real;
  reloj virtual, nodo/radio de aplicación modelados, siete escenarios.
- `tests/test_radio_turnaround.py`: métodos reales Radio.send/receive,
  SPI/GPIO/reloj simulados; tres pruebas de cambio RX y timeout.
- `tests/run-firmware-startup-test.py`: copia temporal del sketch/librería reales,
  claves públicas distintas para IDs1/2, AES/CMAC oficial CubeCell1.6.0, GPIO/reloj
  falsos y TX_DONE diferido57ms. Confirma primer comando, pulso50ms, retorno RX,
  deduplicación y repetición por otra secuencia; contrasta un ACK con Python.
- Las once pruebas previas del puente siguen pasando. Se agregaron además6 pruebas de ID/integridad de builds al reorganizar: la suite unittest suma20.

No se emula el driver Semtech del MCU, las interrupciones reales/reentrancia,
USB/bootloader, brownouts, bobina/PCB, interferencia, pérdidas naturales ni frontend.
Las pruebas previas de GPIO usaban TX_DONE inmediato; ahora se añade el caso
asíncrono. Se corrigió su inclusión para que usen la configuración pública de
prueba y no puedan tomar accidentalmente un encabezado privado del proyecto.

Resultados públicos:
- [Simulación del puente](evidence/2026-10-06/startup-simulation-result.json).
- [Sketch real con radio asíncrona](evidence/2026-10-06/firmware-startup-result.json).
- [Cambio TX/RX del driver](evidence/2026-10-06/radio-turnaround-result.json).
- [Compilaciones y reorganización](evidence/2026-10-06/reorganization-result.json).

## Próxima conexión: captura y correcciones propuestas

1. Arrancar Pi/puente, alimentar un solo nodo y registrar instante de encendido,
   primer GET/ACK, disponibilidades y estado LED/válvula. Repetir con ambos para
   separar la espera causada por un vecino ausente.
2. Registrar tiempos reales de fin TX/inicio RX en la Pi, secuencia/op/intentos,
   y comando/pulso/ACK en el nodo. Abrir serie puede reiniciarlo; planificar la
   captura y no hacerlo durante un riego. Empezar con consultas/LED.
3. Corregir la reconfirmación inmediata de LED tras timeout; separar búsqueda
   de nodos ausentes del período normal de telemetría y acotar sus intentos para
   que no retrasen tanto órdenes a nodos presentes. Medir impacto con ocho nodos.
4. Agrupar clics idénticos todavía pendientes y distinguirlos de reintentos;
   definir prioridad/cancelación de aperturas pendientes ante una orden de cerrar.
   Considerar actuación idempotente del mismo estado lógico en el receptor,
   preservando primer pulso tras arranque desconocido y el límite de confirmación GPIO.
5. Mostrar orden pendiente/confirmación fallida/antigüedad por separado. El panel
   permanece bajo control del usuario; nuevas entidades se agregarían manualmente.
6. Si la captura confirma que la respuesta llega antes de RX, ajustar coordinadamente
   el margen de respuesta y timeout; verificar bajo carga de HA. Para descubrir
   reinicios rápidamente, evaluar anuncio autenticado de arranque con sesión/uptime,
   que requiere ampliar protocolo y actualizar puente/nodo.

No se aplicaron estas correcciones al puente/nodos. Reorganizar fuentes y compilar
las dos identidades no constituye despliegue ni prueba física. Sueño y parámetros
remotos continúan fuera de esta corrección.
