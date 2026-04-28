# Despliegue en Railway

Esta guía deja el catálogo Colsein corriendo en una URL pública de Railway,
con los cambios del modo admin persistiendo entre redeploys (volumen SQLite).

## Lo que cambió respecto al setup local

- `colsein_agent_v3.py`: la BD, taxonomía y HTML generado se leen/escriben en
  `$DATA_DIR` (default `HERE` en local, `/data` en Railway via volumen).
- `cmd_serve` se partió en `build_app()` (la usa gunicorn) + wrapper `serve`
  (Flask dev local).
- Login admin lee `ADMIN_USER` / `ADMIN_PASS` de variables de entorno (con
  fallback `Felipe/Felipe` y aviso ruidoso si no configuras).
- `wsgi.py`, `Procfile`, `railway.json`, `requirements.txt`, `start.sh`.

## Paso a paso

### 1. Subir el código a un repo Git

Railway despliega desde GitHub. Crea un repo nuevo (público o privado) y sube
todo este directorio:

```bash
git init
git add .
git commit -m "Catálogo Colsein listo para Railway"
git branch -M main
git remote add origin git@github.com:<tu-usuario>/<tu-repo>.git
git push -u origin main
```

> El `.gitignore` ya excluye `colsein.db` y los HTML generados — ésos viven
> solo en el volumen de Railway, no en el repo.

### 2. Crear el proyecto en Railway

1. Entra a https://railway.com → **New Project** → **Deploy from GitHub repo**.
2. Selecciona el repo recién creado. Railway detecta Python automáticamente
   por `requirements.txt` y usa Nixpacks como builder.
3. El primer deploy va a fallar porque aún no hay volumen ni variables; eso
   es normal, se arregla en los siguientes pasos.

### 3. Crear el volumen persistente

Esto es lo que evita que se pierdan los productos/filtros del modo admin.

1. Dentro del proyecto → tu servicio → pestaña **Settings** → **Volumes**.
2. **Add Volume**:
   - **Mount path**: `/data`
   - **Size**: 1 GB (de sobra para SQLite + imágenes blob; puedes subirlo
     después).
3. Guarda. Railway reinicia el servicio.

### 4. Configurar variables de entorno

Settings → **Variables** → agrega estas tres:

| Variable     | Valor sugerido                       | Para qué sirve                                                                |
| ------------ | ------------------------------------ | ----------------------------------------------------------------------------- |
| `DATA_DIR`   | `/data`                              | Apunta al volumen montado. **Obligatoria**.                                   |
| `ADMIN_USER` | el usuario admin que tú elijas       | Cambia el `Felipe` por defecto. **Obligatoria si es público**.                |
| `ADMIN_PASS` | una contraseña fuerte (32+ chars)    | Cambia el `Felipe` por defecto. **Obligatoria si es público**.                |
| `FLASK_SECRET_KEY` *(opcional)* | hex de 64 chars (`openssl rand -hex 32`) | Mantiene firmadas las sesiones entre reinicios (no obligatorio). |
| `WEB_CONCURRENCY` *(opcional)* | `2`                              | Workers de gunicorn. Sube a `4` si tienes tráfico.                            |

Nota: `PORT` lo inyecta Railway solo, no lo agregues tú.

### 5. Generar dominio público

Settings → **Networking** → **Generate Domain**. Te da una URL tipo
`https://<algo>.up.railway.app`. También puedes conectar un dominio propio
desde la misma pestaña.

### 6. Redeploy

Tras los pasos 3-5, dispara un redeploy (botón **Deploy** o pusheando un
commit). Cuando arranque verás logs así:

```
[start] DATA_DIR=/data
[start] sembrando taxonomy_editable.json en el volumen
✓ Base de datos creada: /data/colsein.db
[start] productos en BD: 0
[start] BD vacía, importando seed 06_products_classified_v2.json
✓ Importados: 443 nuevos, 0 actualizados, 0 omitidos
✓ HTML generado: /data/colsein_app_v3.html (XX KB)
[start] gunicorn en 0.0.0.0:8080 con 2 workers
```

Abre la URL pública: el catálogo debe cargarse igual que en local. Healthcheck
en `/api/health` debe responder `{"ok": true, "version": 4}`.

## Operación

### Login admin

Usa las credenciales de `ADMIN_USER` / `ADMIN_PASS`. Click en el badge
"Invitado" arriba a la derecha.

### Persistencia

Todo lo que el admin haga (scraping de nuevos productos, refresh-filters,
edición de taxonomía, regeneración de HTML) escribe a archivos en `/data`,
que sobreviven a redeploys. **Lo que se pierde** entre redeploys: los tokens
de sesión admin (viven en memoria del proceso) — el admin tiene que volver a
loguearse.

### Re-seed manual

Si alguna vez quieres volver a empezar:

```bash
# Desde Railway CLI, conectado al servicio:
railway run python colsein_agent_v3.py init
railway run python colsein_agent_v3.py import-json 06_products_classified_v2.json --replace
railway run python colsein_agent_v3.py export-html "$DATA_DIR/colsein_app_v3.html"
```

O más simple: borra y recrea el volumen desde la UI; en el próximo arranque
`start.sh` rehace todo desde el seed.

### Logs

Pestaña **Deployments** → click en el deploy activo → **View Logs**. Los logs
de gunicorn (access + error) salen ahí.

## Seguridad — qué falta para "público de verdad"

El login Felipe-style **no es seguridad real**, incluso con env vars. Lo que
sí ganas en este setup:

- HTTPS automático (Railway lo da con dominio propio o `.up.railway.app`).
- Credenciales admin fuera del código.
- Filesystem aislado por contenedor.

Lo que **no** está cubierto y conviene reforzar antes de exponer ampliamente:

- **Rate-limiting** del endpoint `/api/admin/login` (alguien puede brute-forcear
  la contraseña). Mitigación rápida: usa una contraseña de 32+ chars random.
- **Tokens admin sin expiración**: viven en memoria hasta que reinicies el
  proceso o llames a logout. Considera agregar TTL si vas a tener varios admins.
- **CSRF**: los endpoints admin solo validan `X-Admin-Token`, lo cual es
  suficiente porque no hay cookies same-site, pero asegúrate de que el
  frontend nunca guarde el token donde scripts de terceros puedan leerlo.
- **Endpoint `/api/products` (POST)**: actualmente NO requiere login. Cualquiera
  con la URL pública puede insertar productos. Si esto es indeseable en modo
  público, agrega `if not require_admin(): return 401` al inicio de
  `api_create_product` (línea ~1362).

## Troubleshooting

| Síntoma                                 | Causa probable                                              | Fix                                                                       |
| --------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------- |
| Healthcheck timeout en el deploy        | `start.sh` tardó >100s sembrando datos                       | Sube `healthcheckTimeout` en `railway.json` o pre-genera la BD localmente |
| `Frontend no encontrado`                | El export-html falló o `DATA_DIR` no apunta al volumen      | Revisa logs de start.sh; verifica `DATA_DIR=/data` en variables           |
| Modo admin pierde cambios al redeploy   | Volumen no montado o `DATA_DIR` mal configurado             | Verifica que el volumen esté en `/data` y que `DATA_DIR=/data`            |
| `find-products` retorna 0 candidatos    | Fabricantes industriales bloquean bots con HTTP 403         | Esperado, mismo comportamiento que en local                                |
| Imágenes blob no se ven                 | Las URLs blob requieren el endpoint `/api/products/<id>/image` | Esto sí funciona en Railway; si no se ve, revisa la consola del navegador |

## Costo aproximado

- **Hobby plan** ($5/mes incluye $5 de créditos): un servicio con 0.5 GB RAM
  + 1 GB volumen ≈ $3-5/mes con tráfico bajo. Suficiente para este catálogo.
- **Pro plan** ($20/mes): si esperas tráfico real o necesitas mejor SLA.

Railway factura por uso real (CPU + RAM + egress + storage), no por slots.
