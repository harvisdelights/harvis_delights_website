(() => {
  const key = 'harvis-cart';
  const form = document.querySelector('#checkout-form');
  const payload = document.querySelector('#cart-payload');
  const quote = document.querySelector('#cart-quote');
  const submit = document.querySelector('#checkout-submit');
  const items = document.querySelector('#checkout-items');
  const total = document.querySelector('#checkout-total');
  const message = document.querySelector('#cart-review-message');
  const estimate = document.querySelector('#estimate-result');
  const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
  const money = value => `₹${Number(value).toFixed(2)}`;
  let reviewVersion = 0;
  // Reuse a pending request after a lost response or page reload for the same cart.
  const pending = sessionStorage.getItem('harvis-checkout-active');
  if (pending && sessionStorage.getItem(`harvis-checkout:${pending}`) === localStorage.getItem(key)) {
    document.querySelector('#checkout-id').value = pending;
  }

  async function reviewCart() {
    const version = ++reviewVersion;
    submit.disabled = true;
    quote.value = '';
    const raw = localStorage.getItem(key) || '[]';
    payload.value = raw;
    let cart;
    try { cart = JSON.parse(raw); } catch (_) { cart = []; }
    items.replaceChildren();
    total.textContent = money(0);
    if (!Array.isArray(cart) || !cart.length) {
      message.textContent = 'Your cart is empty or invalid. Please return to the shop.';
      return;
    }
    message.textContent = 'Checking current products and prices...';
    const data = new FormData();
    data.append('cart_payload', raw);
    try {
      const response = await fetch(window.checkoutConfig.reviewUrl, {method: 'POST', headers: {'X-CSRFToken': csrf}, body: data});
      const result = await response.json();
      if (version !== reviewVersion) return;
      if (!response.ok) {
        const unavailable = (result.unavailable_ids || []).map(id => {
          const item = cart.find(entry => String(entry.id) === String(id));
          return item ? item.name : `Product ${id}`;
        });
        message.textContent = result.detail + (unavailable.length ? ` Unavailable: ${unavailable.join(', ')}. Open your cart to remove them.` : '');
        return;
      }
      const idField = document.querySelector('#checkout-id');
      const previouslySubmitted = sessionStorage.getItem(`harvis-checkout:${idField.value}`);
      if (previouslySubmitted !== null && previouslySubmitted !== raw) idField.value = result.checkout_id;
      for (const item of result.items) {
        const row = document.createElement('div');
        row.className = 'summary-item';
        const description = document.createElement('span');
        description.textContent = `${item.name} × ${item.quantity} (${money(item.price)} each)`;
        const price = document.createElement('b');
        price.textContent = money(item.line_total);
        row.append(description, price);
        items.append(row);
      }
      total.textContent = money(result.total);
      const changed = result.items.some(item => {
        const previous = cart.find(entry => String(entry.id) === String(item.id));
        return !previous || Number(previous.price) !== Number(item.price);
      });
      message.textContent = changed ? 'Prices have changed since you added items. Please review the updated total before ordering.' : 'Current prices verified. Please review your order.';
      quote.value = result.quote;
      submit.disabled = false;
    } catch (_) {
      if (version === reviewVersion) message.textContent = 'Could not review your cart. Please reload this page and try again.';
    }
  }

  document.querySelector('#estimate-button').addEventListener('click', async () => {
    const pincode = document.querySelector('#id_pincode').value;
    if (!quote.value || !pincode) { estimate.textContent = 'Review your cart and enter a pincode first.'; return; }
    estimate.textContent = 'Checking delivery...';
    const data = new FormData();
    data.append('pincode', pincode);
    data.append('cart_payload', payload.value);
    try {
      const response = await fetch(window.checkoutConfig.estimateUrl, {method: 'POST', headers: {'X-CSRFToken': csrf}, body: data});
      const result = await response.json();
      estimate.textContent = result.message || result.detail || 'Unable to check delivery at the moment.';
    } catch (_) { estimate.textContent = 'Unable to check delivery at the moment.'; }
  });

  form.addEventListener('submit', event => {
    const current = localStorage.getItem(key) || '[]';
    if (!quote.value || current !== payload.value) {
      event.preventDefault();
      reviewCart();
      return;
    }
    const checkoutId = document.querySelector('#checkout-id').value;
    sessionStorage.setItem(`harvis-checkout:${checkoutId}`, current);
    sessionStorage.setItem('harvis-checkout-active', checkoutId);
    submit.disabled = true;
    submit.textContent = 'Placing order...';
  });
  window.addEventListener('harvis-cart-changed', reviewCart);
  window.addEventListener('storage', event => { if (event.key === key) reviewCart(); });
  reviewCart();
})();
