# Harvi's Delights

Database-driven storefront for Harvi's Delights. It includes a public product catalogue, persistent browser cart (no checkout/order flow), Django seller administration, product gallery uploads, and a read-only REST API.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Create the database: `python manage.py migrate`
4. Create the seller account: `python manage.py createsuperuser`
5. Start the site: `python manage.py runserver`

Open `/admin/` to add categories, products, primary photos, extra gallery photos, descriptions, prices, weights, Flipkart/Meesho marketplace links, and featured status. The API is available at `/api/products/` and `/api/categories/`.

## Customer accounts

Customers can register and sign in with their email address at `/signup/` and `/login/`. Accounts use Django's built-in authentication tables in the configured database (Render PostgreSQL in production). Customers can view their account and change their password; email-based password recovery is intentionally deferred until email delivery is configured.

## Render deployment

The included `render.yaml` creates a Django web service and managed PostgreSQL database. Render wires `DATABASE_URL` privately, runs migrations before each deploy, and stores product uploads on a 1 GB persistent disk mounted at `/var/data`. Production refuses to start without `DATABASE_URL`, ensuring it never falls back to SQLite.

After applying the Blueprint, add your custom domain in the Render Dashboard and update `DJANGO_ALLOWED_HOSTS` plus `DJANGO_CSRF_TRUSTED_ORIGINS` with that domain. The generated `DJANGO_SECRET_KEY` is managed by Render. Keep one web instance while uploads use the local persistent disk; move media to object storage before horizontal scaling.

### Temporary free-tier admin bootstrap

For a short-lived Render Free preview without Shell access, set `DJANGO_ALLOW_EPHEMERAL_SQLITE=True` and all three `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` variables. Add `python manage.py ensure_superuser` after `migrate` in the Start Command. This is only for previews: data and uploaded files remain ephemeral. Remove the bootstrap password variable after the account is created.
