# Acceso remoto: web pública y administración privada

## Estado verificado el 2026-10-23

- Web HTTPS sin VPN: **https://homeassistant.tail3610a7.ts.net/**.
- Panel: https://homeassistant.tail3610a7.ts.net/dashboard-chacaico/.
- Cada visitante debe iniciar sesión con un usuario de Home Assistant. Funnel
  publica la pantalla de acceso; no sustituye la autenticación de HA.
- Administración SSH privada: `ssh pi5.chacaico.remoto`, con Tailscale en el cliente
  y la clave OpenSSH habitual. El Funnel publica solo el servicio web HTTPS.
- LAN: `http://pi5.chacaico/`, puerto80. Internet es necesario para Funnel/VPN;
  las comunicaciones LoRa y el acceso LAN no dependen del túnel.

Se autorizó expresamente la publicación permanente de
`homeassistant.tail3610a7.ts.net` en Certificate Transparency. Se habilitó HTTPS
para el tailnet y se agregó únicamente este permiso a la política existente:

```json
"nodeAttrs": [
  {"target": ["100.117.24.7"], "attr": ["funnel"]}
]
```

El editor de Tailscale aceptó y guardó el destino por IP. No se alteraron los
`grants` ni las reglas SSH existentes. No usar el botón de habilitación global
si se desea conservar esta restricción a la Pi.

La aplicación `a0d7b954_tailscale`0.30.1 quedó con
`share_homeassistant: funnel` y `share_on_port: "443"`, conservando sus demás
opciones, inicio automático, watchdog y protección. El proceso de la app mantiene
el Funnel y gestiona el certificado; no hay un comando manual en segundo plano.
El proxy termina TLS y conecta con HA en `http://127.0.0.1:80`.

En **Configuración → Sistema → Red**, Core2026.9.4 administra HTTP desde la UI:
**Trust X-Forwarded-For** activado y **Trusted proxies** exclusivamente
`127.0.0.1/32`. Se reinició Core y confirmó la nueva configuración HTTP.
No agregar estas opciones a YAML ni editar `.storage` en caliente.
La URL de Internet quedó `https://homeassistant.tail3610a7.ts.net`; la URL local
sigue automática. Estos cambios no modificaron controles ni parámetros LoRa.

### Comprobaciones

Se resolvió el nombre mediante DNS público y se forzó la conexión a cada uno de
los dos relays públicos anunciados, manteniendo Host/SNI y la validación TLS.
Así la prueba no dependió de MagicDNS ni de una conexión al IP privado de la VPN.
En ambos: portadaHTTP200, API sin credencialesHTTP401, WebSocketHTTP101 seguido
de `auth_required`. TLS1.3 y certificado válido hasta el21/01/2027; la aplicación
se encarga de renovarlo. Se comprobó además la pantalla de login en el navegador.
No se enviaron órdenes a válvulas ni se probaron credenciales desde la web pública.

SSH por VPN con autenticación de clave pública siguió funcionando; identidad de
máquina comprobada. El puente0.5.0 y Tailscale quedaron iniciados. Hashes de
`configuration.yaml`, `chacaico-controls.yaml` y dashboard conservados tras la
activación. No se probó un arranque en frío ni el router definitivo del campo.
El acceso desde un teléfono con Wi-Fi y VPN desactivados sirve como prueba adicional.

Evidencia: `home-assistant/evidence/funnel-result.json` y captura de login
`home-assistant/evidence/funnel-login.png`. El aviso inicial de DNS al solicitar
el certificado se resolvió durante el arranque; luego se emitió y validó el
certificado en ambos relays públicos.

### Reproducción y reversión

`home-assistant/scripts/enable-funnel.sh` es solo para la primera activación,
después de autorizar HTTPS/Funnel y configurar el proxy por UI. Comprueba la
identidad, respalda las opciones privadas, modifica solo las dos opciones de
publicación, reinicia Tailscale y verifica el arranque. Debe ejecutarse por LAN:

```sh
ssh -F /home/torce/.ssh/config -o BatchMode=yes pi5.chacaico sh -s \
  < home-assistant/scripts/enable-funnel.sh
```

Después hay que verificar el dominio mediante una ruta pública, autenticación y
WebSocket. El script comprueba activación, no certifica conectividad externa.
Si falla al aplicar o arrancar, intenta restaurar las opciones anteriores.
Respaldos privados de esta operación:
`/config/chacaico-backups/funnel-20261023T140917Z-614/`.
Incluyen opciones originales, comprobantes de hashes y HTTP antes/después.
No versionar su contenido ni la política completa de la cuenta.

Para retirar el acceso público conservando VPN/SSH: en la configuración de la
app Tailscale poner `share_homeassistant: disabled`, guardar y reiniciarla.
Comprobar después que HTTPS público dejó de servir HA y SSH VPN sigue disponible.
Retirar también el atributo `funnel` de esta Pi si se quiere revocar el permiso
para futuras publicaciones. La configuración de proxy localhost puede permanecer;
no restaurar `.storage` con Core en ejecución.

La URL es pública y exige cuenta de HA; para terceros crear usuarios propios.
Funnel requiere Internet, usa relays de Tailscale y tiene límites de ancho de
banda no configurables. No se abrieron puertos del router. La clave del dispositivo
Tailscale aún vence el **4/04/2027**; su política de caducidad sigue sin modificar.
Ese vencimiento es distinto del certificado HTTPS y requiere planificación para
una instalación remota sin atención.

Fuentes: [app Tailscale0.30.1](https://github.com/hassio-addons/app-tailscale/blob/v0.30.1/tailscale/DOCS.md),
[Funnel y sus límites](https://tailscale.com/docs/features/tailscale-funnel),
[certificados HTTPS](https://tailscale.com/docs/how-to/set-up-https-certificates).

## Instalación inicial de VPN (histórico, 2026-10-06)

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
