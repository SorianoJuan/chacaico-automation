# Acceso remoto por Tailscale

Configurado y verificado el 2026-10-06. La Pi necesita Internet en el campo;
el enlace LoRa entre Pi y nodos es independiente de ese acceso VPN.

```sh
ssh pi5.chacaico.remoto
```

Desde esta computadora conectada a la misma cuenta Tailscale:
- IP VPN: `100.117.24.7`.
- Web: http://homeassistant.tail3610a7.ts.net/dashboard-chacaico/
- Alternativa: http://100.117.24.7/dashboard-chacaico/
- SSH: `root`, puerto22, clave habitual `~/.ssh/torce_arch`.

El alias está en `/home/torce/.ssh/config`, con `HostKeyAlias pi5.chacaico` para
verificar la misma identidad OpenSSH conocida. Se respaldó ese archivo; el alias
local y las claves privadas no cambiaron. El SSH entra a **Terminal & SSH**, para
administrar configuración y aplicaciones. El SSH de depuración del host HAOS no
fue configurado.

Se instaló `a0d7b954_tailscale`0.30.1, con inicio automático, watchdog, protección
activa y `full_access=false`. El usuario vinculó la Pi con su cuenta. Se mantienen
`accept_dns=false`, `accept_routes=false`, sin rutas anunciadas ni exit node,
sin compartir archivos y `share_homeassistant=disabled`; interfaz VPN de kernel
(`userspace_networking=false`). No se cambió DNS de HA ni se habilitó Funnel.

Instalador reproducible: `home-assistant/scripts/install-tailscale.sh`, solo para primera
instalación. Comprueba machine_id y respalda opciones privadas. Instala imagen
precompilada sin detener Core ni construir código.

Se probaron SSH por IP VPN y alias con la clave existente y machine_id
`2e21da3405714e0cba2d890984d6dfa8`. Web HTTP200 por IP y MagicDNS. Opciones SSH/LoRa
y hashes de paneles/configuración/controles sin cambios. Puente0.3.0 sigue iniciado.
Memoria de Tailscale observada:51822592 bytes (~49.4 MiB).

La prueba fue por Tailscale mientras ambos equipos estaban en la misma LAN.
No se probó aún una red externa/proveedor del campo ni un reinicio de la Pi.

La clave del dispositivo Tailscale vence el **4 de abril de 2027**
(`2027-04-04T13:59:29Z` observado). Antes de dejar la Pi sin atención, decidir entre
desactivar su caducidad o planificar reautenticación; esa política no se cambió.
Es independiente de la clave OpenSSH. Para desactivarla solo en esta Pi: consola
Tailscale → Machines → `homeassistant`, IP100.117.24.7 → menú de tres puntos →
Disable Key Expiry. No hace falta modificar la política global del tailnet.

Respaldos privados: `/config/chacaico-backups/tailscale-20261006T135712Z-1550/`.
No guardar URLs temporales de autorización ni identidad privada de Tailscale en
Git. Evidencia pública: `home-assistant/evidence/tailscale-result.json`.

Fuentes: [aplicación Tailscale](https://github.com/hassio-addons/app-tailscale/blob/main/tailscale/DOCS.md),
[caducidad de claves](https://tailscale.com/docs/features/access-control/key-expiry).
