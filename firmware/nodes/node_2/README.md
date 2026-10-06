# Nodo 2

Firmware **0.3.0**, ID LoRa **2**, placa objetivo **HTCC-AB01 / ASR6501**.
La revisión impresa de esta PCB debe verificarse por separado; no se infiere de la del nodo 1.

- `node_2.ino`: entrada Arduino; rechaza una configuración de otro ID.
- `profile.json`: identidad pública, perfil de compilación y versión.
- `node_config.h`: encabezado **privado e ignorado**, generado desde `.secrets/node-2.json`.
- `build/`: compilación de este nodo, **ignorada** porque el binario incorpora su clave.
- `evidence/`: resultado histórico público de la prueba USB/LoRa.

La lógica está en `../../libraries/ChacaicoNode/src/ChacaicoNode.h` y se comparte
con los otros nodos. Cada nodo mantiene su propia clave y compilación. GPIO2 abre,
GPIO1 cierra, ambos con pulso de 50 ms; el LED de prueba conserva su estado tras
los destellos de válvula. No hay sueño, configuración remota ni OTA implementados.

Desde la raíz del repo:

```sh
python3 firmware/build-node.py --id 2
sh firmware/flash-node.sh --id 2 /dev/serial/by-path/PUERTO_FISICO-port0
```

Antes de cargar, identificar físicamente la placa y conectar su antena. Los
CP2102 comparten serial0001: el puerto USB no determina el ID LoRa. La carga USB
reinicia el nodo; no se ejecuta como parte de pruebas offline.
