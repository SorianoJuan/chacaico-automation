# Nodo 1

Firmware **0.4.1**, ID LoRa **1**, placa objetivo **HTCC-AB01 / ASR6501**.
PCB **V1.2** confirmada por el usuario.

- `node_1.ino`: entrada Arduino; rechaza una configuración de otro ID.
- `profile.json`: identidad pública, perfil de compilación y versión.
- `node_config.h`: encabezado **privado e ignorado**, generado desde `.secrets/node-1.json`.
- `build/`: compilación de este nodo, **ignorada** porque el binario incorpora su clave.
- `evidence/`: resultado histórico público de la prueba USB/LoRa.

La lógica está en `../../libraries/ChacaicoNode/src/ChacaicoNode.h` y se comparte
con los otros nodos. Cada nodo mantiene su propia clave y compilación. GPIO2 abre,
GPIO1 cierra, ambos con pulso configurable (50 ms predeterminado); el LED de prueba
conserva su estado tras los destellos. Reposo y pulso se configuran desde la pestaña
Configuración LoRa y se conservan en flash. OTA de firmware no implementado.
El perfil permite hasta **3000 ms** para medir GPIO con el CubeCell separado de
la PCB de potencia y la válvula. Pulso aplicado **50 ms**; bridge instalado0.4.3. Antes de reconectar o volver
a versiones anteriores, aplicar **50 ms** y verificar la confirmación.

Ver [operación y límites](../../../docs/node-configuration.md).

Desde la raíz del repo:

```sh
python3 firmware/build-node.py --id 1
sh firmware/flash-node.sh --id 1 /dev/serial/by-path/PUERTO_FISICO-port0
```

Antes de cargar, identificar físicamente la placa y conectar su antena. Los
CP2102 comparten serial0001: el puerto USB no determina el ID LoRa. La carga USB
reinicia el nodo; no se ejecuta como parte de pruebas offline.
