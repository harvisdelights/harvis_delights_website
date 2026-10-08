# Harvi's Delights

Database-driven storefront for Harvi's Delights. It includes a public product catalogue, persistent browser cart (no checkout/order flow), Django seller administration, product gallery uploads, and a read-only REST API.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Create the database: `python manage.py migrate`
4. Create the seller account: `python manage.py createsuperuser`
5. Start the site: `python manage.py runserver`

Open `/admin/` to add categories, products, primary photos, extra gallery photos, descriptions, prices, weights, Flipkart/Meesho marketplace links, and featured status. The API is available at `/api/products/` and `/api/categories/`.
