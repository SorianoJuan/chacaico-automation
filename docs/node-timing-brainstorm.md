# Tiempos, visibilidad y ahorro de energía — ideas, sin implementar

Esta conversación es de diseño. No se modificó el firmware0.3.0 ni se habilitó
sueño, configuración remota de tiempos o nuevas entidades de configuración.
Ambos nodos siguen escuchando LoRa continuamente con `Radio.Rx(0)`.

## Parámetros actuales

| Parámetro | Valor actual | Dónde se controla hoy |
| --- | --- | --- |
| Consulta de válvula | Cada 60 s por nodo; inmediata al recuperar enlace | Puente0.3.0 |
| Consulta de LED | Cada 60 s por nodo, calendario independiente | Puente0.3.0 |
| Sin contacto | 90 s sin ACK del nodo | Puente |
| Estado de válvula sin respuesta | 90 s sin ACK específico de válvula | Puente |
| Espera de ACK | 1 s por intento | Puente, perfil cercano SF7 |
| Intentos por orden | 3, reutilizando secuencia | Puente |
| Vigencia en cola | 15 s desde que llega por MQTT | Puente |
| Pulso de válvula | 50 ms, GPIO2 abrir / GPIO1 cerrar | Firmware |
| Sueño profundo | Deshabilitado | Firmware |
| Ventana de recepción | Continua | Firmware |

Los parámetros del puente están en el código, todavía no en controles de HA.
Las consultas no son una orden de despertar: un nodo con la recepción apagada
no puede recibirlas. Tampoco se usa la consulta para asumir posición física.

## Lo que sería útil mostrar en Home Assistant

- Último contacto del nodo y última confirmación de válvula, por separado.
- Edad del dato: por ejemplo «estado confirmado hace 42 s».
- Última orden, secuencia, intentos y tiempo de respuesta medido.
- Orden pendiente y vencimiento; una orden en espera no significa ejecutada.
- Contadores de comandos enviados, confirmados, agotados y expirados.
- RSSI/SNR; después batería y, si se añade un sensor, posición o caudal.
- Perfil activo y estado de comunicación: escuchando, sueño esperado, sin contacto.
- Próximo despertar previsto, como estimación hasta confirmar un nuevo contacto.

La disponibilidad para comunicarse y el estado confirmado de la válvula son
datos diferentes. Si el nodo reinicia, el estado lógico de la válvula es
desconocido hasta recibir una orden/consulta válida; hoy no hay sensor de posición.

## Controles que podríamos añadir más adelante

Un grupo por dispositivo en HA para perfil, intervalo de despertar, duración de
la ventana de escucha e intervalo de telemetría. El puente tendría controles para
consulta, espera de ACK, reintentos, vigencia de órdenes y tolerancia a contactos
perdidos. Un botón «Aplicar configuración» permitiría distinguir la configuración
deseada de la que el nodo confirmó y evitaría escribir por radio cada movimiento
de un deslizador. El firmware necesitaría recibir, validar y guardar esos ajustes.

Los tiempos de escucha/sueño serían diferentes de los de consulta del puente.
Antes de exponer ajustes hay que validar combinaciones: una orden no debería
vencer siempre antes del próximo despertar, ni el nodo marcarse sin contacto
durante un sueño previsto. La espera de ACK también debe considerar el perfil
LoRa y la duración real de la transmisión; 1 s corresponde a la prueba actual.

## Dos perfiles para pensar

| Perfil propuesto | Comportamiento | Consecuencia |
| --- | --- | --- |
| Pruebas / respuesta inmediata | Escucha continua, como ahora | Mayor consumo; la orden llega sin esperar un despertar |
| Campo / batería y panel | Despierta periódicamente, informa que está listo, escucha y vuelve a dormir | Menor tiempo de radio activa; la orden puede esperar hasta el siguiente despertar |

Como ejemplo conceptual, despertar cada 30 s y escuchar 2 s dejaría unos 28 s
sin escucha por ciclo. Una orden podría esperar cerca de 30 s, más transmisión
y reintentos. Es una ilustración del compromiso, no un valor elegido ni una
estimación de autonomía. Hay que medir la placa completa, la PCB y su conversor.

Para ocho nodos, sus ventanas deberían repartirse con desfases y algo de azar,
para que no todos transmitan a la vez. El nodo iniciaría el contacto al despertar;
la base aprovecharía esa ventana para entregar órdenes pendientes y recibir ACK.
Ese intercambio y la telemetría requieren ampliar el protocolo/firmware actual.

También convendría un mensaje de estado conjunto —LED, última orden de válvula,
batería y perfil— para aprovechar cada despertar con menos intercambios. Hoy LED
y válvula se consultan por separado; esta idea todavía no se implementó.

## Condiciones necesarias antes de llevarlo al campo

- Distinguir sueño esperado de falta de contacto; tolerar varios despertares
  perdidos, en vez de usar siempre un plazo fijo ajeno al perfil del nodo.
- Cada orden con vencimiento y confirmación explícita; no ejecutar mucho después
  una orden de abrir que ya perdió sentido para la automatización.
- Considerar que el nodo controle localmente la duración del riego y el cierre,
  aunque durante el riego pierda contacto con la base. Esto todavía no existe.
- Definir reinicio, batería baja y pérdida de enlace junto con el circuito real
  de la válvula; la posición de una válvula biestable no se deduce del arranque.
- Completar protección persistente contra repetición; hoy la secuencia del nodo
  solo se conserva en RAM.
- Evaluar un LED de diagnóstico temporal en perfil de batería, porque dejarlo
  encendido consume energía aunque el resto del nodo pueda dormir.

Primero conviene medir consumo y demora real de los ocho nodos con sus antenas,
altura, batería, panel y PCB. Esos datos permitirán elegir el intervalo de sueño
y la tolerancia a pérdidas sin prometer tiempos de respuesta que no se cumplen.

## Investigación de parámetros remotos — 6 de octubre de 2026

Se revisaron fuentes primarias de MySensors, The Things Network, Milesight y
Dragino. No se cambió software operativo ni se eligieron tiempos de campo.
La configuración remota necesita primero una carga de firmware que la soporte;
el firmware0.3.0 todavía no interpreta mensajes de configuración.

### Patrones publicados y cómo aprovecharlos

- MySensors documenta `sleep(ms, true)`: envía un heartbeat y procesa mensajes
  entrantes antes de dormir, con una espera configurable. Es una referencia de
  diseño, no una validación de este framework en nuestros CubeCell.
- LoRaWAN clase A abre ventanas de recepción después de transmitir; una orden
  que pierde esa oportunidad espera otro uplink. Podemos tomar la idea de que
  el nodo inicie el contacto, manteniendo nuestro protocolo LoRa directo.
- Milesight UC51x separa recolección, reporte y oportunidad de recibir comandos;
  publica confirmación de comandos, pulso de válvula y reglas por tiempo/volumen.
- Dragino SVC01-LS2 permite configurar por downlink intervalo de transmisión,
  tiempos de receptor activo/inactivo y pulso. También ofrece abrir con temporizador
  y planes locales. Sus valores, alimentación y modos son de ese equipo; no son
  configuraciones validadas para HTCC-AB01 ni para nuestra PCB.

### Parámetros por nodo propuestos

| Parámetro | Para qué serviría | Criterio inicial |
| --- | --- | --- |
| Perfil | Banco, campo o mantenimiento temporal | Perfil simple en HA; mantenimiento vence automáticamente |
| Intervalo de contacto con válvula cerrada | Ahorro frente a demora de una nueva orden | Definir demora tolerable y medir consumo |
| Intervalo de contacto durante riego | Facilitar un cierre anticipado y supervisión | Más frecuente que en reposo si la energía lo permite |
| Ventana de recepción | Esperar orden/configuración tras anunciarse | Dimensionar por airtime, procesamiento y reintentos |
| Extensión máxima de ventana | Terminar un intercambio ya iniciado | Límite para no quedar despierto indefinidamente |
| Intervalo de reporte de mediciones | Enviar batería/sensores sin repetir todo en cada contacto | Separar de la oportunidad de recibir órdenes |
| Duración máxima de apertura | Programar cierre autónomo en el nodo | Temporizador local que funcione también durante sueño |
| Regla por pérdida de enlace | Continuar el tiempo aprobado o cerrar tras cierto plazo | Definir explícitamente; no confundir con sueño previsto |
| Umbral de batería baja y recuperación | Avisar, ahorrar y evitar aperturas sin energía para cerrar | Medir batería real y reserva necesaria; histéresis |
| Tiempo de LED de diagnóstico | Identificación/prueba con apagado automático | Evitar LED permanente en campo |
| Pulso de apertura/cierre | Adaptar a PCB y electroválvula | Avanzado, con límites validados; hoy ambos 50 ms |
| Caudal/volumen y calibración | Alarmas por falta de agua/fuga y cierre por volumen | Futuro, necesita sensor y circuito adecuados |
| Plan horario local | Ejecutar programas aunque HA no esté accesible | Futuro: reloj, sincronización y recuperación tras reinicio |

Conviene expresar el intervalo entre contactos, en vez de ajustar por separado
un sueño y un período total que puedan contradecirse. La escucha se mide desde
un evento definido, por ejemplo el final del anuncio. Para los ocho nodos,
asignar desfases y agregar pequeñas variaciones aleatorias evita que todos se
anuncien juntos. El HAT tiene una sola radio: no recibe mientras transmite.

Un contacto puede llevar ID, configuración vigente y última orden confirmada,
con un estado compacto. Las mediciones más extensas pueden enviarse menos
frecuentemente, y los cambios de válvula/fallos importantes reportarse de inmediato.
Un anuncio emitido tampoco garantiza que la Pi lo recibió: hace falta respuesta.
Si no la recibe, el nodo debe volver a dormir/reintentar según una regla acotada.

### Decisiones en el puente y Home Assistant

- Vigencia de las órdenes de abrir, cola por nodo y prioridad de cierre. Una
  apertura pendiente cancelada debe eliminarse al llegar una orden posterior
  de cierre, no ejecutarse en el siguiente despertar. Lo que ya se transmitió
  puede haberse ejecutado: conservar esa incertidumbre hasta una confirmación.
- Tiempo de ACK acorde al perfil de radio, intentos y espera aleatoria entre
  contactos fallidos, evitando ocupar todo el canal por un nodo ausente.
- Tolerancia expresada en contactos esperados perdidos, con margen de tiempos.
  Un nodo dormido puede conservar su último estado confirmado con su antigüedad;
  no debe presentarse como si estuviera escuchando o como físicamente verificado.
- Configuración deseada, pendiente y vigente confirmada por separado, más revisión,
  rechazo con motivo y fecha de aplicación. Nunca actualizar solo el valor en HA
  y presentarlo como aplicado en el dispositivo.

Hoy la cola vence a los 15 s y el plazo sin respuesta es 90 s. No se pueden
habilitar contactos de varios minutos sin adaptar ambos criterios y el protocolo.
Una ventana de 2 s tampoco se debe tomar como suficiente por defecto: depende
del SF, tamaño de paquetes, transacciones y reintentos del perfil de campo.

### Aplicación y recuperación de configuración

1. HA prepara un conjunto de ajustes y muestra «pendiente» al pulsar Aplicar.
2. La Pi lo entrega cuando el nodo anuncia que está escuchando.
3. El nodo verifica autenticidad/destino, revisión, tipos, límites y compatibilidad
   entre parámetros, y devuelve aceptación o rechazo con valores efectivos.
4. Se prueba la nueva configuración y se confirma desde un contacto posterior.
   Si impide reestablecer el enlace, una configuración candidata debería volver
   a la última configuración de comunicación válida tras un plazo acotado.
5. Guardar solo cambios reales, con registros recuperables ante corte de energía;
   no escribir flash en cada contacto. El arranque debe validar lo guardado y
   tener un perfil de recuperación definido.

También habrá que conservar la protección contra órdenes repetidas tras un
reinicio. Recuperar la configuración de comunicación no es una orden de válvula:
la actuación al reiniciar y el vencimiento de un riego deben diseñarse aparte.
Con válvula biestable, un pulso confirmado sigue sin demostrar posición o caudal.

En HA serían controles numéricos/selección y un botón Aplicar, junto con último
contacto, próximo contacto estimado, sueño previsto/sin contacto, orden pendiente,
último ACK, intentos y proporción de confirmaciones. RSSI/SNR son diagnósticos de
radio; la confirmación de ejecución y eventual medición física aportan evidencia
adicional. Mostrar batería/energía solo cuando haya medición implementada.

Mantendría frecuencia, SF/BW, syncword, ID y claves fuera de los controles simples.
Cambiar un perfil de radio requiere coordinación con la única radio del HAT y
recuperación, para no perder nodos. Los primeros ajustes serían los dos intervalos
de contacto, ventana, reporte, duración máxima de apertura y LED temporal; en
el puente, vigencia de apertura y contactos perdidos tolerados. El pulso de 50 ms
seguiría fijo hasta validar la electroválvula/PCB.

Fuentes consultadas:
- [MySensors: sueño y heartbeat](https://www.mysensors.org/apidocs/group__MySensorsCoregrp.html) y [espera de mensajes](https://www.mysensors.org/apidocs/group__SleepSettingGrpPub.html).
- [The Things Network: clases y ventanas de recepción](https://www.thethingsnetwork.org/docs/lorawan/classes/).
- [Milesight UC51x: parámetros configurables](https://www.milesight.com/development-platform/docs/en/device-reference/uc51x-properties.html).
- [Dragino SVC01-LS2: configuración y órdenes de válvula](https://wiki.dragino.com/docs/LoRaWAN-End-Node/soil-agriculture-sensors/svc01-ls2/).
