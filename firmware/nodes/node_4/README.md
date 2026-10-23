# Nodo 4

Firmware **0.5.0**, ID LoRa **4**, perfil **HTCC-AB01 / ASR6501**.
La revisión impresa de la PCB no está verificada.

- `node_4.ino`: entrada Arduino con comprobación del ID y máximo de pulso200ms.
- `profile.json`: identidad pública y versión del core1.6.0.
- `node_config.h` y `build/`: privados, ignorados; incorporan la clave exclusiva de este nodo.
- `.secrets/node-4.json` en la raíz conserva esa clave al recompilar.

GPIO2 abre, GPIO1 cierra; pulso predeterminado50ms y ambos LOW al terminar.
Arranca sin accionar la válvula y con posición desconocida. Reposo0s (RX continuo),
potencia0dBm, escucha3000ms y presupuesto10000ms son los valores iniciales.
Configuración y LED independiente disponibles por Home Assistant. El ACK confirma
la ejecución GPIO, no la posición física. Sin OTA de firmware.

```sh
python3 firmware/build-node.py --id 4
sh firmware/flash-node.sh --id 4 /dev/serial/by-path/PUERTO_FISICO-port0
```

Identificar la placa y conectar su antena antes de cargar. CP2102 serial0001 no
identifica un nodo; usar el puerto físico. Ver [configuración](../../../docs/node-configuration.md).
