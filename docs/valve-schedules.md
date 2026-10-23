# Horarios de las válvulas

Implementado el23/10/2026 en Core2026.9.4 y bridge0.5.1. Nodos0.5.0 sin cambios.
La temporada se habilita y deshabilita **manualmente**, sin fechas de noviembre
ni marzo. Se usan controles nativos de hora; no hay HACS ni otra app de scheduling.

## Uso: Desde / Hasta

Abrir **Chacaico → Horarios**. Cada tarjeta contiene:

- **Usar este horario**: incluye/excluye esa válvula del programa.
- **Desde**: hora diaria de apertura, editable directamente.
- **Hasta**: hora diaria de cierre, editable directamente.
- **Estado**: apertura/cierre pendiente, sin contacto o confirmación reciente.

Las horas se guardan automáticamente. Encender **Habilitar los horarios** en
Temporada de riego para aplicar los cuatro rangos habilitados. Al terminar la
temporada, apagarlo: solicita cerrar las válvulas que administraba y conserva
los horarios. Los cierres sin confirmar siguen pendientes y se reintentan.

Ejemplos: Desde08:00 / Hasta09:00 abre todos los días de08:00 a09:00;
Desde22:00 / Hasta01:00 cruza medianoche. **Desde igual a Hasta no programa riego**,
no significa24 horas de apertura. El inicio está incluido y el final excluido.
La cuenta admin usa formato24h para mostrar las horas. Zona horaria verificada: `America/Argentina/Buenos_Aires`.

La simplificación del23/10 deja temporada OFF, los cuatro selectores ON y los
rangos00:00–00:00 (sin riego). Los Schedule semanales estaban vacíos y se
conservaron en HA, pero ya no intervienen. Se preservaron los cierres que ya
estaban pendientes antes de la actualización; no se borró su responsabilidad.
No se eligieron horas de operación por el usuario.

Mientras temporada y selector estén ON, manda el horario. Para cambiar ambas
horas sin aplicar valores intermedios, apagar ese selector y esperar su cierre
antes de editar. Para control manual, deshabilitar ese horario y esperar a
confirmar el cierre. Las válvulas que nunca administró el programa se dejan en
control manual cuando temporada está OFF. La vista principal se conserva.

## Confirmaciones y reinicios

- Un controlador común revisa cambios de horarios/controles/estado, arranque de
  HA, reconexión del puente, las ocho horas exactas Desde/Hasta y cada30s como recuperación.
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
  solicitud ya confirmada, tampoco al editar el final de una apertura confirmada.
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

Los campos Desde/Hasta son helpers de hora de HA; se editan desde la tarjeta.
Conservar sus IDs técnicos para que el controlador pueda encontrarlos.

## Archivos, actualización y reversión

- `home-assistant/config/chacaico-horarios.yaml`: paquete nativo, incluido desde
  `homeassistant.packages` en configuration.yaml.
- `home-assistant/config/custom_templates/chacaico_horarios.jinja`: cálculo común
  de rango diario y próximo cambio. Usa días locales, no saltos fijos de86400s.
- Los valores vigentes de los input_datetime residen en HA y se respaldan con su
  configuración. No agregar `initial`: sobrescribiría valores al reiniciar.
- `home-assistant/scripts/horarios-view.py`: vista reproducible y combinación que
  preserva las otras pestañas. Para editar el dashboard activo, usar UI; nunca
  escribir `.storage` mientras Core está ejecutándose.
- `home-assistant/scripts/install-horarios.sh`: primera instalación con backup
  y controles de identidad/concurrencia; no reutilizar para resetear horarios.

Respaldo de despliegue privado en la Pi:
`/config/chacaico-backups/horarios-20261023T193459Z`, parcial Supervisor `ec419329`.
La migración a Desde/Hasta tiene además respaldo privado en
`/config/chacaico-backups/horarios-diario-20261023T201521Z`.
El respaldo inicial contiene configuración y bridge previos; no copiarlo a Git. Para retirar esta
función, primero apagar Temporada y confirmar todos los cierres; después retirar
la inclusión del paquete y la vista, validar Core y reiniciar. Para restaurar
archivos de `.storage`, detener Core antes; no sobrescribir otros cambios hechos
después del backup. Se puede conservar bridge0.5.1: mantiene comandos manuales.

Referencia: [Input Datetime nativo](https://www.home-assistant.io/integrations/input_datetime/).
La validación registrada separa simulación y funcionamiento real de UI/Core;
no prueba posición física ni funcionamiento hidráulico.
