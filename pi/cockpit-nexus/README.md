# Prototipo opcional de pestaña Cockpit Nexus

> Estado: referencia técnica no aprobada. No instalar ni desplegar sin una decisión
> expresa de Diego.

Prototipo de Nexus como herramienta independiente de Cockpit. Es de
sólo lectura y reutiliza tres fuentes que ya existen en Proyecto Pi:

- `sudo -n /usr/local/bin/bots-info`: perfiles, rutas y consultas de hoy;
- `/opt/nodo/datos/estado.json`: salud de servicios y contenedores;
- `/opt/nodo/datos/uso.json`: consumo local observable de Claude y estado de Codex.

No requiere una base nueva, un servicio nuevo ni una regla sudo adicional. Tampoco
escribe propuestas en esta etapa.

## Revisión local de la lógica

```bash
node test_nexus_logic.cjs
```

## Instalación futura

Sólo después de cerrar las seis puertas de verificación:

```bash
mkdir -p ~/.local/share/cockpit/nexus
cp -a pi/cockpit-nexus/index.html pi/cockpit-nexus/manifest.json \
  pi/cockpit-nexus/nexus.css pi/cockpit-nexus/nexus.js \
  pi/cockpit-nexus/nexus-logic.js ~/.local/share/cockpit/nexus/
```

La prueba debe hacerse con una sesión real de Cockpit y confirmar:

1. que la herramienta aparece como `🧭 Nexus`;
2. que no hay errores CSP en la consola;
3. que una fuente ausente aparece como `sin datos` o `no verificada`;
4. que ningún control ejecuta cambios;
5. que el refresco manual y el de cinco minutos funcionan.

`test_nexus_logic.cjs` es un archivo de desarrollo y no necesita instalarse.
