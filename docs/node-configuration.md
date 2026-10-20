# Configuración remota y ventanas de escucha — 0.4.0

## Operación desde Home Assistant

La pestaña **Configuración LoRa** de Chacaico (`dashboard-chacaico/configuracion-lora`)
contiene una sección por nodo. La vista original de válvulas y LED se conserva.

1. Editar reposo en segundos (0–3600) y pulso GPIO en milisegundos (10–200).
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
**50 ms**. El límite 10–200 ms es una restricción del software, no una validación
eléctrica de cualquier electroválvula. El pulso no representa duración del riego.
No hay cierre autónomo ni sensor de posición: una confirmación de válvula solo
certifica la ejecución del GPIO. El LED independiente consume energía si se deja
encendido, también durante el reposo.

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
0.4.0 deben actualizarse juntos; no hay compatibilidad de radio con 0.3.0.
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
