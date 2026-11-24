from django.db import IntegrityError, transaction

from store.models import Cart, CartItem, Product, ProductVariant


MAX_CART_QUANTITY = 20


def line_key(product_id, variant_id=None):
    return f"{product_id}:v{variant_id}" if variant_id else str(product_id)


def _locked_cart(user):
    try:
        Cart.objects.get_or_create(user=user)
    except IntegrityError:
        pass
    return Cart.objects.select_for_update().get(user=user)


def _payload(cart):
    CartItem.objects.filter(cart=cart, product__is_active=False).delete()
    CartItem.objects.filter(cart=cart, variant__isnull=False, variant__is_active=False).delete()
    items = CartItem.objects.filter(cart=cart, product__is_active=True).select_related("product", "variant").order_by("id")
    return {
        "version": cart.version,
        "items": [
            {
                "id": line_key(item.product_id, item.variant_id),
                "product_id": str(item.product_id),
                "variant_id": str(item.variant_id) if item.variant_id else "",
                "name": item.product.name + (f" — {item.variant.name}" if item.variant_id else ""),
                "variant_name": item.variant.name if item.variant_id else "",
                "price": str(item.variant.price if item.variant_id else item.product.price),
                "image": item.product.display_image_url,
                "quantity": item.quantity,
            }
            for item in items
        ],
    }


def merge_guest_cart(user, lines):
    """Merge a guest device cart without doubling an identical product option."""
    with transaction.atomic():
        cart = _locked_cart(user)
        product_ids = {product_id for product_id, _ in lines}
        variant_ids = {variant_id for _, variant_id in lines if variant_id}
        products = {p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids, is_active=True)}
        variants = {v.id: v for v in ProductVariant.objects.select_for_update().filter(id__in=variant_ids, is_active=True)}
        existing = {(item.product_id, item.variant_id): item for item in CartItem.objects.select_for_update().filter(cart=cart)}
        changed = False
        for (product_id, variant_id), quantity in lines.items():
            product = products.get(product_id)
            variant = variants.get(variant_id) if variant_id else None
            if not product or (variant_id and (not variant or variant.product_id != product_id)):
                continue
            item = existing.get((product_id, variant_id))
            if item:
                merged = max(item.quantity, quantity)
                if item.quantity != merged:
                    item.quantity = merged
                    item.save(update_fields=["quantity", "updated_at"])
                    changed = True
            else:
                CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=quantity)
                changed = True
        if changed:
            cart.version += 1
            cart.save(update_fields=["version", "updated_at"])
        return _payload(cart)


def mutate(user, *, action, product_id, variant_id, quantity, expected_version):
    with transaction.atomic():
        cart = _locked_cart(user)
        if expected_version != cart.version:
            return None, _payload(cart)
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        variant = ProductVariant.objects.filter(pk=variant_id, product_id=product_id, is_active=True).first() if variant_id else None
        if not product or (variant_id and not variant):
            raise ValueError("This product option is no longer available.")
        item = CartItem.objects.select_for_update().filter(cart=cart, product=product, variant=variant).first()
        if action == "add":
            if item:
                item.quantity = min(MAX_CART_QUANTITY, item.quantity + 1)
                item.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=1)
        elif action == "set":
            if not 0 <= quantity <= MAX_CART_QUANTITY:
                raise ValueError("Invalid cart quantity.")
            if quantity == 0:
                if item:
                    item.delete()
            elif item:
                item.quantity = quantity
                item.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(cart=cart, product=product, variant=variant, quantity=quantity)
        else:
            raise ValueError("Invalid cart action.")
        cart.version += 1
        cart.save(update_fields=["version", "updated_at"])
        return _payload(cart), None


def remove_checked_out_quantities(user, lines):
    with transaction.atomic():
        cart = Cart.objects.select_for_update().filter(user=user).first()
        if not cart:
            return
        items = {(item.product_id, item.variant_id): item for item in CartItem.objects.select_for_update().filter(cart=cart)}
        changed = False
        for key, ordered in lines.items():
            item = items.get(key)
            if not item:
                continue
            remaining = item.quantity - ordered
            if remaining > 0:
                item.quantity = remaining
                item.save(update_fields=["quantity", "updated_at"])
            else:
                item.delete()
            changed = True
        if changed:
            cart.version += 1
            cart.save(update_fields=["version", "updated_at"])
