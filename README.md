# Harvi's Delights

Database-driven storefront for Harvi's Delights. It includes a public product catalogue, persistent browser cart (no checkout/order flow), Django seller administration, product gallery uploads, and a read-only REST API.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Create the database: `python manage.py migrate`
4. Create the seller account: `python manage.py createsuperuser`
5. Start the site: `python manage.py runserver`

Open `/admin/` to add categories, products, primary photos, extra gallery photos, descriptions, prices, weights, Flipkart/Meesho marketplace links, and featured status. The API is available at `/api/products/` and `/api/categories/`.

## Render deployment

The included `render.yaml` creates a Django web service and managed PostgreSQL database. Render wires `DATABASE_URL` privately, runs migrations before each deploy, and stores product uploads on a 1 GB persistent disk mounted at `/var/data`. Production refuses to start without `DATABASE_URL`, ensuring it never falls back to SQLite.

After applying the Blueprint, add your custom domain in the Render Dashboard and update `DJANGO_ALLOWED_HOSTS` plus `DJANGO_CSRF_TRUSTED_ORIGINS` with that domain. The generated `DJANGO_SECRET_KEY` is managed by Render. Keep one web instance while uploads use the local persistent disk; move media to object storage before horizontal scaling.
