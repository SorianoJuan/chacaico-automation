# Máximo de 3000 ms en ambos nodos; pulso aplicado de 50 ms

Cambio solicitado el 20/10/2026: ampliar el máximo configurable en nodos1/2 y
restaurar50 ms en ambos. El reposo se conservó en0 s. No se enviaron órdenes de
apertura ni cierre durante esta actualización.

- Nodo1 conserva firmware0.4.1; nodo2 se identificó por su banner en USB físico
  0:3, se compiló y programó con su propio perfil0.4.1 y se verificó el checksum.
- El banner de nodo2 posterior a la carga y reinicio informa0.4.1, boot6,
  revisión5, reposo0, pulso50 y almacenamiento válido. La configuración persistió.
- Bridge0.4.3 instalado y activo. Home Assistant se detuvo durante la construcción
  para limitar el pico de RAM y se reactivó automáticamente. Respaldo6b7befe0.
- La consulta fresca por LoRa de ambos nodos devolvió50 ms y estado Confirmada;
  borradores50 ms, límites de discovery10–3000 ms. Ver live-confirmation.json.
- Los cuatro campos numéricos de la UI tienen máximos3600/3000/3600/3000 y
  valores0/50/0/50. Screenshot: home-assistant-confirmed.png.
- El SHA256 del dashboard se conservó; no se modificaron sus vistas.

Validación offline: 50 pruebas Python aprobadas. El sketch real con hardware
simulado y AES-CMAC real aprobó para ambos IDs: pulso de3000 ms en GPIO1/2,
retorno a LOW antes del ACK, deduplicación, rechazo de3001 ms, persistencia,
restauración a50 ms y presupuesto de vigilia. No se probaron pulsos físicos
largos en esta actualización. El build del nodo1 existente y el nuevo build de
nodo2 fueron verificados; imágenes y claves permanecen ignoradas.
