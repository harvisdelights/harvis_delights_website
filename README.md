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

Customers can register and sign in with their email address at `/signup/` and `/login/`. Accounts use Django's built-in authentication tables in the configured database (Render PostgreSQL in production). Customers can view their account and change their password. Password recovery becomes available after ZeptoMail and `PUBLIC_SITE_URL` are configured.

## Transactional email

Order requests, seller order alerts, confirmed/shipped/cancelled status updates and password recovery use ZeptoMail's HTTPS Send API. Configure ZeptoMail's verified domain and Mail Agent first. In Render's Environment settings set `ZEPTOMAIL_API_URL` to the exact HTTPS Send Email endpoint provided by the agent (for example `https://api.zeptomail.com/v1.1/email`), `ZEPTOMAIL_API_KEY` to its Send API key, and `PUBLIC_SITE_URL` to the customer-facing HTTPS origin (for example `https://harvisdelights.com`). `DEFAULT_FROM_EMAIL` and `SELLER_NOTIFICATION_EMAIL` default to `hdcare@harvisdelights.com`. Use only a verified sender. Keep the API key out of Git and chat.

The Django migration must run before enabling this version. Order notifications are stored in the configured database, and are attempted after the order or status change commits. In seller admin, **Order emails** shows pending, failed, sending, and provider-accepted messages; use the retry action for pending/failed items. Retry is manual: there is no background worker or automatic retry. A provider-accepted message is not proof of inbox delivery; use ZeptoMail logs to investigate bounces. If the process stops while sending, the status can remain `sending`; inspect provider logs before deciding whether to resend, because an ambiguous timeout can result in duplicate delivery. Password reset emails are not stored in this outbox; users can request another link if needed. Password recovery is disabled until the API settings and public URL are present. The email integration does not provide SMS or WhatsApp.

## Orders and delivery estimates

Customers must sign in before checkout. Their delivery address, order, and immutable product/price snapshots are stored in the configured database. New orders are automatically marked confirmed; this does not mean payment was made or captured. Seller staff can review orders and payment status in `/admin/`. Never dispatch based on order status alone. There is no automatic shipment creation.

### Razorpay payments

Live mode is opt-in: set `RAZORPAY_MODE=live` and `RAZORPAY_LIVE_ENABLED=true` together with matching live credentials. This makes real charges possible for all customers using the deployment. Keep test mode for normal QA; do not use test cards in live mode. Delivery is free; COD is unavailable. Order status and payment status are separate; only a captured payment verified against the order amount and currency is marked paid. Never dispatch based on order status alone.

1. Create a Razorpay account, switch to test mode, generate test API keys, and configure automatic capture in the Razorpay dashboard.
2. Configure a webhook in the relevant Razorpay mode at `https://YOUR-SITE/payments/razorpay/webhook/` for `payment.captured`, `refund.created`, `refund.processed`, and `refund.failed`, with a separate strong webhook secret. Use the real public HTTPS site origin. Test and live webhooks and secrets are separate; this application accepts only the currently configured mode.
3. Privately set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in the Render web service, or in the ignored local `.env` file for local testing. Environment variables take precedence over `.env`. Never commit or share secrets. A test key ID must start with `rzp_test_`. All three values are required; the webhook secret is the value you choose when configuring the webhook, not the API key secret.
4. Deploy with migrations, then place an order request and test successful, failed and abandoned payments using Razorpay test data. Check Payments in seller admin and the Razorpay test dashboard. Webhooks may arrive after the customer closes checkout.

If gateway order creation times out, the record is marked for manual review and cannot be retried automatically because the remote order may already exist. Compare the order reference with the Razorpay dashboard and contact support/developers; do not delete payment records to force retries. In Payments admin, the check action queries Razorpay for awaiting or captured payments; ambiguous or refunded payments require manual review. Refunds are initiated in the Razorpay dashboard, not this site; refund events flag the payment for review, including failed or partial refunds. Check the gateway before any fulfillment. Webhook delivery, refund and reconciliation procedures must be verified end-to-end before taking customer payments.

Existing payment records are marked "Legacy / unverified" because their original environment cannot be established safely from the database alone. New payments are labelled with their configured environment.

Pre-existing orders are labelled "Legacy / unverified". Live checkout rejects legacy and test orders. Admin fulfillment transitions for live orders require a captured live payment; staff must still check for refunds and disputes in Razorpay immediately before dispatch, especially if webhook delivery is delayed or unavailable.

The checkout estimate starts from **Harvi's Delights, Nizampet, 500090**. Add either `SHIPROCKET_API_TOKEN` or both `SHIPROCKET_EMAIL` and `SHIPROCKET_PASSWORD` as secret Render environment variables to enable Shiprocket serviceability and estimated delivery times. Without those credentials, checkout continues to work and displays a standard 4-7 business-day estimate. This integration is read-only: it does not create Shiprocket shipments, charges, or pickup locations.

Before dispatching live Shiprocket orders, create the pickup location in Shiprocket with the seller's complete street address, city/state, contact name, and phone number. Do not commit Shiprocket credentials to Git.

## Render deployment

The included `render.yaml` creates a Django web service and managed PostgreSQL database. Render wires `DATABASE_URL` privately, runs migrations before each deploy, and stores product uploads on a 1 GB persistent disk mounted at `/var/data`. Production refuses to start without `DATABASE_URL`, ensuring it never falls back to SQLite.

After applying the Blueprint, add your custom domain in the Render Dashboard and update `DJANGO_ALLOWED_HOSTS` plus `DJANGO_CSRF_TRUSTED_ORIGINS` with that domain. The generated `DJANGO_SECRET_KEY` is managed by Render. Keep one web instance while uploads use the local persistent disk; move media to object storage before horizontal scaling.

### Temporary free-tier admin bootstrap

For a short-lived Render Free preview without Shell access, set `DJANGO_ALLOW_EPHEMERAL_SQLITE=True` and all three `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` variables. Add `python manage.py ensure_superuser` after `migrate` in the Start Command. This is only for previews: data and uploaded files remain ephemeral. Remove the bootstrap password variable after the account is created.
