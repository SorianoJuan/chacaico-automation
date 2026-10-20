# Configuración remota y ventanas de escucha — nodos0.4.x / bridge0.4.3

## Operación desde Home Assistant

La pestaña **Configuración LoRa** de Chacaico (`dashboard-chacaico/configuracion-lora`)
contiene una sección por nodo. La vista original de válvulas y LED se conserva.

1. Editar reposo en segundos (0–3600) y pulso GPIO en milisegundos (10–3000 en nodos1/2).
2. Pulsar **Aplicar ambos parámetros**. Editar los campos solo modifica el borrador.
3. Esperar **Confirmada** y comprobar los valores, revisión y hora reportados.
4. **Consultar al nodo** pide una lectura nueva; si duerme, espera su anuncio.

La vista principal muestra **Orden de válvula** debajo de cada control: Pendiente,
Confirmada, Sin confirmación; consultando, o Vencida sin confirmar. Es exclusiva
de esa válvula y las órdenes de LED no la sobrescriben. Tras reiniciar el puente
empieza en Sin órdenes pendientes. Los parámetros siguen en Configuración LoRa.

Los valores confirmados son los que devolvió el nodo, no una copia optimista de
lo solicitado. Permanecen visibles durante el reposo. La hora permite distinguir
una lectura reciente de otra anterior. Un error de escritura permanece visible
hasta Aplicar o Consultar; una consulta posterior confirma la configuración que
sigue vigente, no que el intento fallido se haya aplicado.

El reposo predeterminado es **0 s**, escucha continua. El pulso predeterminado es
**50 ms**. El límite configurable es 10–3000 ms en ambos nodos; ambos quedaron aplicados a50 ms.
Son restricciones del software, no una validación
eléctrica de cualquier electroválvula. El pulso no representa duración del riego.
No hay cierre autónomo ni sensor de posición: una confirmación de válvula solo
certifica la ejecución del GPIO. El LED independiente consume energía si se deja
encendido, también durante el reposo.

## Medir los GPIO con un tester

![Puntos de medición en el CubeCell original](hardware/cubecell-gpio-medicion.png)

En el HTCC-AB01 original, mirando los componentes con el micro USB hacia arriba,
GPIO2 es el tercer contacto desde abajo de la hilera derecha y GPIO1 el segundo.
El contacto superior de esa hilera es GND. Son nombres de GPIO, no números de
patillas del chip. Posiciones verificadas en el
[pinout oficial de Heltec](https://resource.heltec.cn/download/CubeCell/HTCC-AB01/HTCC-AB01_PinoutDiagram.pdf);
el [esquemático oficial](https://resource.heltec.cn/download/CubeCell/HTCC-AB01/HTCC-AB01_SchematicDiagram.pdf)
identifica las mismas señales. No confundir la placa original con la V2 de USB-C.

Usar tensión continua, escala 20 V o automática: punta negra en COM/GND y roja en
el borne V/Ω y el GPIO que se prueba. GPIO2 sube a aproximadamente 3,3 V al abrir;
GPIO1 al cerrar. El otro GPIO queda en 0 V y ambos vuelven a0V al terminar el pulso.
No medir en modo corriente ni continuidad. Esto comprueba la señal lógica del
CubeCell; la tensión en la salida de potencia depende de la PCB externa.

El pulso predeterminado de 50 ms y aun 200 ms pueden ser muy breves para un tester
común. El20/10/2026 se habilitó y aplicó **3000 ms al nodo1**, con autorización del
usuario para probarlo separado de PCB/válvula. Firmware0.4.1 y bridge0.4.2 conservan
la confirmación después de completar el pulso, deduplicación y retorno a LOW.
Posteriormente, el usuario pidió ampliar también el máximo del nodo2 a3000 ms
y restaurar50 ms en ambos. Se programó nodo2 con firmware0.4.1 y se desplegó
bridge0.4.3. Ambos confirmaron50 ms; el reposo se conservó en0 s.
La ampliación del límite no cambia por sí sola el pulso aplicado.
Evidencia: [ampliación y restauración](evidence/2026-10-20/both-pulse-limit/README.md).

**Antes de reconectar la potencia, aplicar50 ms y comprobar el valor confirmado.**
El parámetro se conserva al reiniciar; no vuelve automáticamente a50 ms. Restaurar
el pulso también antes de bajar a versiones que rechazan valores superiores a200 ms.
Para esa prueba, aislar el CubeCell de la PCB de potencia y de la válvula: no se
ha comprobado que admitan excitación prolongada. Si se mide con la electrónica
conectada, conservar sus tiempos admitidos y usar osciloscopio o analizador lógico
compatible con 3,3 V. Alternar abrir/cerrar para repetir la medición: pedir el estado
ya confirmado no vuelve a generar un pulso.

## Ventana de comunicación

Con reposo positivo el nodo despierta, anuncia READY y escucha inicialmente
**3 segundos**. Cada intercambio válido renueva la espera, con un presupuesto
máximo de **10 segundos** desde el anuncio. El puente responde cuando recibe el
anuncio, entrega órdenes pendientes y cierra con END. Si no hay respuesta, el
nodo vuelve a dormir solo. Pulso, ACK y destellos ya iniciados terminan antes de
dormir; por eso el límite es un presupuesto y no un corte eléctrico abrupto.
Hay un pequeño jitter de anuncio/reposo para reducir colisiones entre nodos.

La radio usa 150 ms de margen antes de responder; el puente reserva tiempo de RX
para no tapar ese ACK. El scheduler puede atender otro nodo mientras espera un
reintento. Prioriza cierre solicitado y órdenes del usuario sobre consultas de
fondo. No garantiza entrega si no hay enlace.

El estado **Reposo esperado** no equivale a desconexión. Se marca Sin contacto
tras `max(90, 3*(reposo+10)+10)` segundos sin ACK válido. Las órdenes de LED/válvula
vencen tras `max(15, reposo+20)` segundos; se muestra el vencimiento y no se
mantiene una apertura indefinidamente en cola. La configuración espera hasta
24 horas y sobrevive a reiniciar el puente. Las órdenes de válvula no se guardan
para ejecutarlas después de reiniciar el puente.

## Protocolo, persistencia y recuperación

Protocolo v2: 38 bytes, AES-CMAC truncado a 64 bits con clave individual. Incluye
ID, sesión de arranque persistente, ventana de despertar, secuencia, operación,
resultado, revisión, reposo, pulso y estados de LED/válvula. Firmware y puente
0.4.x son compatibles en protocolo; pulsos largos en ambos nodos requieren sus
perfiles0.4.1 y puente0.4.3 (0.4.2 solo los admitía en nodo1). No hay compatibilidad de radio con0.3.0.
No se modificó el bootloader y esto no implementa actualización OTA de firmware.

SET_CONFIG es independiente de SET_VALVE y SET_LED. Se aplican ambos parámetros
juntos, con revisión y lectura de verificación. Todos los ACK devuelven la
configuración completa. Si se pierde un ACK, una consulta permite reconciliar lo
que realmente quedó aplicado. Reintentos de una misma transacción no repiten
pulsos ni escrituras. Una nueva orden de válvula al mismo estado conocido tampoco
repite el pulso. Tras reiniciar el nodo la posición vuelve a desconocida.

Tres filas separadas de user flash del ASR6501 contienen registros con CRC y
contador de generación; se escribe una fila inactiva y se verifica leyéndola.
La fila 3 del fabricante no se toca. Un fallo de persistencia del contador de
arranque impide aceptar órdenes. Hay una escritura por arranque y por cambio de
configuración, no por despertar. Es flash con desgaste finito; no usar Aplicar
como temporizador ni reiniciar continuamente para controlar un nodo.

El puente guarda borradores, confirmaciones y configuración pendiente con rename
atómico y fsync. Reserva secuencias en bloques para reducir escrituras en la SD.
Preservar su directorio de datos y las claves en actualizaciones/restauraciones.
Un archivo persistente inválido detiene el puente antes de reutilizar secuencias.

## Instalación y validación

Compilar cada ID y verificar su manifiesto antes de cargar por su puerto físico.
No intercambiar las dos placas ni usar el serial CP2102 común para identificarlas.
Respaldar el add-on y Home Assistant antes de actualizar; la copia de HA necesita
Core disponible. Para construir el add-on en la Pi de 1 GB, detener Core después
del respaldo y reactivarlo al terminar.

`home-assistant/scripts/node-config-view.py` genera la vista y puede combinarla
con una copia privada del dashboard de almacenamiento. Conserva las otras vistas.
`deploy-config-view.sh` recibe directorio remoto de app, JSON combinado y SHA256
del dashboard original; comprueba identidad de Pi, respaldo y ausencia de edición
concurrente antes de sustituir el archivo con Core detenido. No publicar `.storage`.

Las pruebas offline incluyen pérdidas, reinicios, ocho nodos, cortes de escritura,
autenticación, tiempo GPIO y retorno a recepción. No prueban consumo eléctrico,
alcance en el campo, desgaste a largo plazo ni posición física de la válvula.
Las pruebas de banco deben usar consultas/configuración/LED. La primera actuación
física de válvula corresponde al usuario desde Home Assistant.
