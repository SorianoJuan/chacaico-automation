# Firmware CubeCell

Entradas separadas en `nodes/node_1/` y `nodes/node_2/`, cada una con su ID,
perfil público y build privado. Firmware0.5.0 para ambas; máximo configurable3000ms, pulso aplicado50ms. La aplicación compartida
está en `libraries/ChacaicoNode/src/ChacaicoNode.h`; los encabezados ChacaicoProtocol.h y ChacaicoStorage.h contienen protocolo y persistencia.

`configure-node.py --id N` conserva `.secrets/node-N.json`, verifica ID/clave
únicos y frecuencia común, y genera solo el encabezado privado del nodo elegido.
Para agregar un ID futuro, crear primero su entrada Arduino/perfil público.
`build-node.py --id N` usa core1.6.0 y librería local, y guarda imagen/manifiesto en
`nodes/node_N/build/`. `flash-node.sh --id N PUERTO` verifica ID, fuentes,
configuración e imagen con `verify-build.py` antes de acceder al USB. Ese verificador
se puede ejecutar solo con `python3 firmware/verify-build.py --id N`.

Los binarios incluyen claves, por lo que se ignoran junto con `node_config.h`.
La copia previa de build del nodo1 se conserva en `build-legacy-node-1/`, ignorada.
Compilar no programa nodos; la carga se hace solo cuando se autoriza y la placa
está identificada con su antena conectada. En la raíz están los comandos exactos.

Configuración remota y sueño implementados en 0.4.0; OTA de firmware no implementado.
[Operación y límites](../docs/node-configuration.md).

0.5.0 agrega potencia TX, ventanas configurables, señal de bajada y prueba/commit
de potencia. Migra flash anterior; no volver a firmware0.4.x después de migrar.
