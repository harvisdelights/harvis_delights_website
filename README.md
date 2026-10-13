# Harvi's Delights

Database-driven storefront for Harvi's Delights. It includes a public product catalogue, browser cart, customer accounts, checkout order requests, Django seller administration, product gallery uploads, and a read-only REST API.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Create the database: `python manage.py migrate`
4. Create the seller account: `python manage.py createsuperuser`
5. Start the site: `python manage.py runserver`

Open `/admin/` to add categories, products, primary photos, extra gallery photos, descriptions, prices, weights, Flipkart/Meesho marketplace links, and featured status. The API is available at `/api/products/` and `/api/categories/`.

## Customer accounts

Customers can register and sign in with their email address at `/signup/` and `/login/`. Accounts use Django's built-in authentication tables in the configured database (Render PostgreSQL in production). Customers can view their account and change their password; email-based password recovery is intentionally deferred until email delivery is configured.

## Orders and delivery estimates

Customers must sign in before checkout. Their delivery address, order, and immutable product/price snapshots are stored in the configured database. Seller staff can review every order and update its status from `/admin/`. There is deliberately no payment collection or automatic shipment creation yet; each order remains an order request until Harvi's Delights confirms it.

The checkout estimate starts from **Harvi's Delights, Nizampet, 500090**. Add either `SHIPROCKET_API_TOKEN` or both `SHIPROCKET_EMAIL` and `SHIPROCKET_PASSWORD` as secret Render environment variables to enable Shiprocket serviceability and estimated delivery times. Without those credentials, checkout continues to work and displays a standard 4-7 business-day estimate. This integration is read-only: it does not create Shiprocket shipments, charges, or pickup locations.

Before dispatching live Shiprocket orders, create the pickup location in Shiprocket with the seller's complete street address, city/state, contact name, and phone number. Do not commit Shiprocket credentials to Git.

## Render deployment

The included `render.yaml` creates a Django web service and managed PostgreSQL database. Render wires `DATABASE_URL` privately, runs migrations before each deploy, and stores product uploads on a 1 GB persistent disk mounted at `/var/data`. Production refuses to start without `DATABASE_URL`, ensuring it never falls back to SQLite.

After applying the Blueprint, add your custom domain in the Render Dashboard and update `DJANGO_ALLOWED_HOSTS` plus `DJANGO_CSRF_TRUSTED_ORIGINS` with that domain. The generated `DJANGO_SECRET_KEY` is managed by Render. Keep one web instance while uploads use the local persistent disk; move media to object storage before horizontal scaling.

### Temporary free-tier admin bootstrap

For a short-lived Render Free preview without Shell access, set `DJANGO_ALLOW_EPHEMERAL_SQLITE=True` and all three `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` variables. Add `python manage.py ensure_superuser` after `migrate` in the Start Command. This is only for previews: data and uploaded files remain ephemeral. Remove the bootstrap password variable after the account is created.
