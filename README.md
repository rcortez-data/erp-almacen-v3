# Web Price Shoes

MVP de catálogo y pedidos para un distribuidor independiente, construido con Django, Bootstrap y JavaScript vanilla. No incluye scraping ni contenido de terceros.

## Instalación en Windows

Requiere Python 3.12 y Git. En PowerShell:

```powershell
cd "C:\Users\RTX 3070\Desktop\web price shoes"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```

Visita `http://127.0.0.1:8000/` y el panel en `/admin/`. En este equipo se validó además con Python 3.13 por ser el intérprete disponible.

## Comandos útiles

```powershell
python manage.py check
python manage.py test
python manage.py import_catalog sample_catalog.csv
python manage.py collectstatic --noinput
```

El CSV requiere: `product_sku,name,category,price,variant_sku,size,color,stock`. Las columnas adicionales son opcionales.

## Variables y bases de datos

Copia `.env.example` como `.env`. SQLite se usa cuando `DATABASE_URL` está vacío. La configuración también acepta URLs `mysql://` y `postgresql://`; instala `mysqlclient` o `psycopg` al migrar. Nunca publiques `.env`, la base local ni credenciales.

## Despliegue en PythonAnywhere

1. Crea una web app manual con Python compatible y clona el repositorio.
2. Crea un virtualenv e instala `requirements.txt`.
3. Crea `.env` con `DEBUG=False`, una `SECRET_KEY` aleatoria de al menos 50 caracteres, `ALLOWED_HOSTS=tuusuario.pythonanywhere.com`, `CSRF_TRUSTED_ORIGINS=https://tuusuario.pythonanywhere.com`, `SECURE_SSL_REDIRECT=True` y el WhatsApp real. Activa HSTS solo después de confirmar que HTTPS funciona en todo el dominio.
4. Configura el archivo WSGI para añadir la carpeta del proyecto al `sys.path` e importar `config.wsgi.application`.
5. Ejecuta `python manage.py migrate`, `python manage.py collectstatic --noinput` y `python manage.py createsuperuser`.
6. En Web > Static Files, mapea `/static/` a la ruta absoluta `staticfiles` y `/media/` a `media`.
7. Recarga la web app y revisa los logs. SQLite sirve para demo; usa MySQL/PostgreSQL y copias de seguridad antes de procesar pedidos reales.

## Antes de producción

- Sustituir nombre, teléfono, costo de envío y textos legales.
- Confirmar autorización para marcas, fotografías y datos del catálogo.
- Configurar correo transaccional real y probar recuperación de contraseña.
- Usar base de datos de producción, HTTPS, copias de seguridad y monitoreo.
- Revisar permisos del admin y crear cuentas individuales para operadores.
- Probar compra móvil, existencias concurrentes, envío y atención por WhatsApp.
- Preparar Cloudinary/S3 si se desplegarán muchas imágenes.
- Integrar Mercado Pago con webhooks verificados; nunca guardar tarjetas.
