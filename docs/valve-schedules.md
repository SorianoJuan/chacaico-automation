# Horarios de las válvulas

Implementado el23/10/2026 en Core2026.9.4 y bridge0.5.1. Nodos0.5.0 sin cambios.
La temporada se habilita y deshabilita **manualmente**, sin fechas de noviembre
ni marzo. Se usa Schedule nativo; no hay HACS ni otra app de scheduling.

## Uso

1. Abrir **Chacaico → Horarios**.
2. En cada válvula, tocar **Editar días y horarios**. Se abre directamente el
   editor nativo: arrastrar en la grilla semanal para crear franjas, tocar un
   bloque para ajustar inicio/fin o quitarlo y guardar con **Actualizar / Update**.
   Las fechas de la grilla son ilustrativas: las franjas se repiten semanalmente.
   Para todos los días, definir las franjas en los siete días. No cambiar el ID.
3. Dejar **Usar este horario** activo en las válvulas incluidas. Este selector
   permite excluir una válvula sin borrar sus franjas.
4. Encender **Habilitar los horarios**, dentro de Temporada de riego. Aplica el
   estado que corresponda **ahora**: abre dentro de una franja y cierra fuera.
5. Al finalizar la temporada, apagar ese interruptor. Solicita cerrar las
   válvulas que administraba y conserva los horarios para la próxima temporada.
   Un cierre sin confirmar permanece pendiente y se reintenta.

La entrega inicial deja la temporada **OFF**, los cuatro selectores preparados
**ON** y las franjas **vacías**. No se eligieron horas por el usuario. Una válvula
con horario vacío permanecerá cerrada cuando se habilite su programación.
Zona horaria de la Pi verificada: `America/Argentina/Buenos_Aires`.

El estado de cada tarjeta resume apertura/cierre pendiente, falta de contacto,
reintento o confirmación reciente. **Próximo cambio** muestra inicio o fin de
franja. La vista principal y sus estados de orden se conservan. No se presenta
una confirmación antigua como resultado de una nueva orden.

Mientras temporada y selector estén ON, manda el horario; una acción manual
contraria será reconciliada. Para control manual, deshabilitar ese horario y
esperar a confirmar su cierre. Las válvulas que nunca estuvieron administradas
por el programa se dejan en control manual cuando temporada está OFF.

## Confirmaciones y reinicios

- Un controlador común revisa cambios de horarios/controles/estado, arranque de
  HA, reconexión del puente y cada30s como recuperación.
- Guarda propiedad e intención antes de publicar por MQTT con QoS1 y retain=false.
  El estado pendiente/confirmado continúa siendo responsabilidad del bridge.
- Apertura programada: `{"state":"OPEN","valid_until":<fin Unix de la franja>}`.
  El puente usa el menor plazo entre ese límite y la vigencia configurada. Una
  apertura pendiente deja de transmitirse al terminar su franja; no se conserva
  para reproducirla tras reiniciar el puente. No se inicia una apertura en los
  últimos2s de una franja.
- Cierre: `CLOSE`, reemplaza cualquier apertura pendiente. Si no hay confirmación,
  el controlador vuelve a solicitarlo cada `max(60s, vigencia efectiva + 10s)`,
  sujeto a la revisión de30s. No publica otra orden cada tick ni repite una
  solicitud ya confirmada.
- Solo se considera satisfecho el objetivo si coincide el estado del nodo, la
  confirmación es válida y su timestamp es posterior a la intención. Los ACK
  viejos y estados retained no bastan para liberar un nuevo cierre pendiente.
- Al apagar temporada o un selector, la propiedad se conserva hasta confirmar
  el cierre. Sobrevive reinicios de HA: al volver, se recalcula el objetivo
  vigente y se recupera el cierre. Solo después se devuelve el control manual.
- Un reinicio del nodo deja posición desconocida; una consulta/orden posterior
  restaura observabilidad. Se conservan los mecanismos existentes de sesión,
  autenticación y deduplicación. No hay protocolo de horarios en los nodos.

No borrar los helpers `chacaico_horario_responsable_N` / `chacaico_horario_ultimo_N`
ni desactivar la automatización para suspender el riego. Usar el switch de
Temporada. Si se eliminara el controlador durante un cierre pendiente, no podría
reintentarlo.

## Límites

La ejecución depende de HA, puente, energía y enlace. Una válvula ya abierta
**no se cierra sola** si la Pi se apaga o se pierde la radio: al recuperar el
sistema se solicita el cierre, pero este firmware no tiene tiempo máximo de
apertura autónomo. El ACK confirma el pulso/estado lógico, no posición física ni
caudal. Un paquete que ya salió por radio no se puede retirar retroactivamente.

El horario marca la intención, no un instante garantizado de actuación: sueño,
reintentos y ventanas de radio agregan demora. Si se necesita secuencia sin
solapamiento, dejar separación acorde al reposo y al tiempo de entrega. A pedido
del usuario **no se impone exclusión mutua** entre válvulas; el editor permite
solapamientos. Para una garantía hidráulica harían falta interbloqueo y sensores.

El editor semanal requiere una cuenta de HA con permisos de administración.
Los visitantes sin dichos permisos pueden no tener acceso a editar helpers.
Los nombres e IDs técnicos de los helpers son usados por el controlador y no
deben modificarse desde el editor.

## Archivos, actualización y reversión

- `home-assistant/config/chacaico-horarios.yaml`: paquete nativo, incluido desde
  `homeassistant.packages` en configuration.yaml.
- `home-assistant/config/horarios-seed.json`: helpers vacíos de primera instalación.
  Los horarios vigentes residen en HA y se respaldan con su configuración.
- `home-assistant/scripts/horarios-view.py`: vista reproducible y combinación que
  preserva las otras pestañas. Para editar el dashboard activo, usar UI; nunca
  escribir `.storage` mientras Core está ejecutándose.
- `home-assistant/scripts/install-horarios.sh`: primera instalación con backup
  y controles de identidad/concurrencia; no reutilizar para resetear horarios.

Respaldo de despliegue privado en la Pi:
`/config/chacaico-backups/horarios-20261023T193459Z`, parcial Supervisor `ec419329`.
Contiene configuración y bridge previos; no copiarlo a Git. Para retirar esta
función, primero apagar Temporada y confirmar todos los cierres; después retirar
la inclusión del paquete y la vista, validar Core y reiniciar. Para restaurar
archivos de `.storage`, detener Core antes; no sobrescribir otros cambios hechos
después del backup. Se puede conservar bridge0.5.1: mantiene comandos manuales.

Referencia del componente: [Schedule nativo](https://www.home-assistant.io/integrations/schedule/).
La validación registrada separa simulación y funcionamiento real de UI/Core;
no prueba posición física ni funcionamiento hidráulico.
