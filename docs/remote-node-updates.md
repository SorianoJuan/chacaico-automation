# Actualización remota de CubeCell — exploración, sin implementar

HTCC-AB01/ASR6501 mantienen firmware0.3.0 con GET/SET LED y válvula. Tailscale
administra la Raspberry, pero no agrega un cargador de firmware al nodo.

| Opción | Qué permite | Pendiente |
| --- | --- | --- |
| Parámetros por LoRa | Sueño, escucha, telemetría o reglas sin reemplazar código | Mensajes autenticados nuevos, validación y guardado persistente |
| USB remoto | Compilar aquí y cargar desde una Pi/computadora junto a una placa conectada por USB | Preparar programador y puerto allí; no alcanza a nodos conectados solo por radio |
| Firmware por LoRa | Reprogramar nodos del campo sin USB | Fragmentación, progreso persistente, flash, autenticación y recuperación de arranque |

ESPHome tiene radio SX126x, pero ASR6501/CubeCell no aparece en su lista actual
de microcontroladores. Transporte de paquetes y OTA de firmware son capacidades
diferentes. El toolchain que usamos es Arduino/C++ CubeCell1.6.0.

Evidencia revisada en nuestro core/artefacto antes de separar las carpetas por nodo (6/10/2026):
- La compilación informa51672 bytes; el `.cyacd` del nodo 1 tiene171 filas,
  43776 bytes de datos y89959 bytes como texto. Definir una imagen OTA compacta
  compatible con el cargador, sin asumir que se transmite el texto hexadecimal.
- `platform.txt` invoca `CubeCellflash -serial ... imagen.cyacd`.
- `Bootloadable_1_Load()` selecciona bootloader y reinicia; no instala una imagen
  recibida por radio.
- `FLASH_update()` escribe flash y protege el área anterior a34 filas de256 bytes;
  no constituye por sí sola un mecanismo de actualización recuperable.
- `board.c` define aplicación112 KiB y cuatro particiones de parámetros4 KiB, sin
  inicializar `HAL_PARTITION_OTA_TEMP`. Revisar linker, metadatos y espacio antes
  de afirmar que caben dos imágenes o un área para recibir la nueva.

Un diseño posible necesitaría una carga USB inicial del gestor OTA. La Pi
anunciaría placa, versión, tamaño y autenticación, enviaría fragmentos numerados,
y el nodo confirmaría progreso/pediría faltantes. Debe poder reanudar tras cortes,
guardar la imagen sin destruir la aplicación activa, validarla e instalarla con
recuperación. Después se confirma la nueva versión e identidad del nodo.

La demora depende de SF/BW, pérdidas, reintentos, escucha y formato. No se midió
OTA ni se promete duración. Imagen alternativa o instalación transaccional son
posibilidades todavía no validadas aquí. Un checksum sin autenticación no basta.

Hoy la clave CMAC está compilada dentro de la imagen. Transmitir esa imagen en
claro expondría la clave: CMAC autentica pero no cifra. Para OTA conviene separar
identidad/configuración de la imagen y diseñar una transferencia protegida.
No se cambiaron claves, flash ni firmware durante esta exploración.

LoRaWAN dispone de protocolos FUOTA para fragmentación y gestión; también requiere
capacidad de actualización en cada nodo. Un gateway no crea ese bootloader.
Nuestro enlace es LoRa directo con protocolo propio. MySensors publica OTA
genérico, pero no se validó aquí una actualización completa/recuperable en
HTCC-AB01/V1.2; no se propone cambiar framework sin una prueba de banco.

Orden sugerido: acceso fiable a la base, configuración persistente por radio,
transferencia de datos grandes sin instalar código, y después cargador validado
con cortes de energía/paquetes perdidos. Definir también mantenimiento y estado
seguro de válvulas para aplicar firmware en el campo.

Fuentes:
- [Plataformas ESPHome](https://esphome.io/components/) y [SX126x](https://esphome.io/components/sx126x/).
- [Programación CubeCell](https://docs.heltec.org/en/node/asr650x/asr650x_general_docs/quick_start/index.html).
- [Proceso FUOTA](https://lora-alliance.org/resource_hub/fuota-process-summary-technical-recommendation-tr002-v1-0-0/).
- [OTA MySensors](https://www.mysensors.org/apidocs/group__MyOTAFirmwaregrp.html).
