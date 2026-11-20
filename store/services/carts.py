from django.db import IntegrityError, transaction

from store.models import Cart, CartItem, Product


MAX_CART_QUANTITY = 20


def _locked_cart(user):
    try:
        Cart.objects.get_or_create(user=user)
    except IntegrityError:
        # A simultaneous first request created this user's one-to-one cart.
        pass
    return Cart.objects.select_for_update().get(user=user)


def _payload(cart):
    CartItem.objects.filter(cart=cart, product__is_active=False).delete()
    items = CartItem.objects.filter(cart=cart, product__is_active=True).select_related("product").order_by("id")
    return {
        "version": cart.version,
        "items": [
            {
                "id": str(item.product_id),
                "name": item.product.name,
                "price": str(item.product.price),
                "image": item.product.display_image_url,
                "quantity": item.quantity,
            }
            for item in items
        ],
    }


def snapshot(user):
    with transaction.atomic():
        cart = _locked_cart(user)
        return _payload(cart)


def merge_guest_cart(user, quantities):
    """Merge a guest device cart without accidentally doubling equal items."""
    with transaction.atomic():
        cart = _locked_cart(user)
        products = {
            product.id: product
            for product in Product.objects.select_for_update().filter(id__in=quantities, is_active=True)
        }
        existing = {
            item.product_id: item
            for item in CartItem.objects.select_for_update().filter(cart=cart)
        }
        changed = False
        for product_id, quantity in quantities.items():
            if product_id not in products:
                continue
            item = existing.get(product_id)
            if item:
                merged_quantity = max(item.quantity, quantity)
                if item.quantity != merged_quantity:
                    item.quantity = merged_quantity
                    item.save(update_fields=["quantity", "updated_at"])
                    changed = True
            else:
                CartItem.objects.create(cart=cart, product_id=product_id, quantity=quantity)
                changed = True
        if changed:
            cart.version += 1
            cart.save(update_fields=["version", "updated_at"])
        return _payload(cart)


def mutate(user, *, action, product_id, quantity, expected_version):
    """Apply one cart operation with optimistic concurrency protection."""
    with transaction.atomic():
        cart = _locked_cart(user)
        if expected_version != cart.version:
            return None, _payload(cart)
        product = Product.objects.filter(pk=product_id, is_active=True).first()
        if not product:
            raise ValueError("This product is no longer available.")
        item = CartItem.objects.select_for_update().filter(cart=cart, product=product).first()
        if action == "add":
            if item:
                item.quantity = min(MAX_CART_QUANTITY, item.quantity + 1)
                item.save(update_fields=["quantity", "updated_at"])
            else:
                CartItem.objects.create(cart=cart, product=product, quantity=1)
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
                CartItem.objects.create(cart=cart, product=product, quantity=quantity)
        else:
            raise ValueError("Invalid cart action.")
        cart.version += 1
        cart.save(update_fields=["version", "updated_at"])
        return _payload(cart), None


def remove_checked_out_quantities(user, quantities):
    """Remove only checked-out quantities, preserving later additions on another device."""
    with transaction.atomic():
        cart = Cart.objects.select_for_update().filter(user=user).first()
        if not cart:
            return
        items = {
            item.product_id: item
            for item in CartItem.objects.select_for_update().filter(cart=cart, product_id__in=quantities)
        }
        changed = False
        for product_id, ordered_quantity in quantities.items():
            item = items.get(product_id)
            if not item:
                continue
            remaining = item.quantity - ordered_quantity
            if remaining > 0:
                item.quantity = remaining
                item.save(update_fields=["quantity", "updated_at"])
            else:
                item.delete()
            changed = True
        if changed:
            cart.version += 1
            cart.save(update_fields=["version", "updated_at"])
