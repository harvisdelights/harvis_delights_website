# Product images managed through Git

Place product assets in a category subfolder and commit them with the website.

Example paths:

    product-images/almonds/california-almonds-main.webp
    product-images/almonds/california-almonds-side.webp
    product-images/raisins/afghani-black-raisins-main.webp

In Django admin, paste the relative path beginning with product-images/ into
Static image path. Use .webp, .jpg, .jpeg, .png, .gif, or .avif.

Do not begin the value with /, store/, or static/.
