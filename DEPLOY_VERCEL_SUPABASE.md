# Deploy en Vercel + Supabase — Café & Barista

## 1. Supabase: crear proyecto y tablas (5 min)

1. Entra a https://supabase.com > New project. Guarda el **Database Password**.
2. Ve a **SQL Editor > New query**, pega todo el contenido de `supabase/schema.sql` y dale **Run**.
3. Ve a **Project Settings > Database > Connection string > URI** y copia:
   - **Pooler (para Vercel, recomendado)**: cambia el puerto a `6543` y agrega `?pgbouncer=true&sslmode=require`.
     Ejemplo:
     `postgresql://postgres:TU_PASSWORD@aws-0-us-east-1.pooler.supabase.com:6543/postgres?sslmode=require&pgbouncer=true`
   - **Directa (solo para el seed inicial)**: puerto `5432` con `?sslmode=require`.

4. Seed inicial desde tu PC (PowerShell):
   ```powershell
   pip install -r requirements.txt
   $env:DATABASE_URL="postgresql://postgres:TU_PASSWORD@db.TU_REF.supabase.co:5432/postgres?sslmode=require"
   python seed.py
   # Debe imprimir: Se cargaron 16 productos...
   ```

## 2. Vercel: importar y configurar

1. Sube este proyecto a GitHub y en https://vercel.com > **Add New > Project** > Import.
2. **Framework Preset**: Other. **Root Directory**: la raíz del repo.
   Vercel detecta `vercel.json` + `api/index.py` automáticamente (Python serverless).
3. En **Environment Variables** agrega (Production + Preview):
   - `DATABASE_URL` = la URL del **pooler** (puerto 6543)
   - `FLASK_SECRET_KEY` = cadena larga aleatoria (`python -c "import secrets; print(secrets.token_hex(32))"`)
   - `ADMIN_PASSWORD` = tu clave del panel `/admin`
   - `WHATSAPP_NUMBER` = ej. `573173169936`
   - `SHOP_NAME` = `Café & Barista`
   - `SHOP_LOCATION` = `Villavicencio, Colombia`
   - `MP_ACCESS_TOKEN` = (opcional; sin esto el pago es por WhatsApp)
4. **Deploy**. Verifica:
   - `https://tu-app.vercel.app/api/health` → `{"ok":true,"db":"up"}`
   - `https://tu-app.vercel.app/api/productos` → lista JSON
   - `/admin/` entra con tu clave.

## 3. Notas importantes (Vercel serverless)

- No hay SQLite ni archivos persistentes: toda la data vive en Supabase.
- `db.create_all()` **no** corre en Vercel; las tablas se crean con `schema.sql`.
- El plan Hobby de Vercel duerme funciones tras inactividad: el primer request (cold start) tarda unos segundos, es normal.
- MercadoPago `back_urls` usa `request.host_url`, así que en Vercel apuntan solas al dominio correcto.
- Logs: Vercel Dashboard > tu proyecto > Logs / Observability.

## 4. Desarrollo local

```powershell
Copy-Item .env.example .env
# edita .env si quieres Supabase, o deja sin DATABASE_URL para SQLite
pip install -r requirements.txt
python seed.py
python app.py
# abre http://localhost:5000
```
