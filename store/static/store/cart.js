(() => {
  const key = 'harvis-cart';
  const ownerKey = 'harvis-cart-owner';
  const config = window.cartConfig || {};
  const authenticated = Boolean(config.authenticated && config.userId);
  const status = document.querySelector('[data-cart-status]');
  let serverVersion = null;
  let cartReady = Promise.resolve();
  let mutationQueue = Promise.resolve();

  const read = () => {
    try {
      const cart = JSON.parse(localStorage.getItem(key) || '[]');
      return Array.isArray(cart) ? cart : [];
    } catch (_) { return []; }
  };
  const save = cart => {
    localStorage.setItem(key, JSON.stringify(cart));
    window.dispatchEvent(new Event('harvis-cart-changed'));
  };
  const money = value => `₹${Number(value).toFixed(2)}`;
  const message = value => { if (status) status.textContent = value || ''; };
  const formData = fields => {
    const data = new FormData();
    Object.entries(fields).forEach(([name, value]) => data.append(name, value));
    return data;
  };
  const applyServer = payload => {
    serverVersion = payload.version;
    save((payload.items || []).map(item => ({...item, price: Number(item.price), quantity: Number(item.quantity)})));
    localStorage.setItem(ownerKey, String(config.userId));
  };
  const render = () => {
    const cart = read(), target = document.querySelector('[data-cart-items]');
    document.querySelectorAll('[data-cart-count]').forEach(x => x.textContent = cart.reduce((n, p) => n + p.quantity, 0));
    document.querySelector('[data-cart-total]').textContent = money(cart.reduce((n, p) => n + p.price * p.quantity, 0));
    target.innerHTML = cart.length ? cart.map(p => `<div class="cart-item">${p.image ? `<img src="${p.image}" alt="">` : `<span class="cart-thumb">${p.name[0]}</span>`}<div><b>${p.name}</b><span>${money(p.price)} each</span><span class="cart-quantity"><button type="button" data-decrease="${p.id}" aria-label="Decrease ${p.name} quantity">-</button><em>${p.quantity}</em><button type="button" data-increase="${p.id}" aria-label="Increase ${p.name} quantity">+</button></span></div><button data-remove="${p.id}">Remove</button></div>`).join('') : '<p class="cart-note">Your cart is empty. Add something delightful.</p>';
    target.querySelectorAll('[data-remove]').forEach(button => button.onclick = () => updateQuantity(button.dataset.remove, 0));
    target.querySelectorAll('[data-increase]').forEach(button => button.onclick = () => {
      const item = read().find(entry => entry.id === button.dataset.increase);
      if (item) updateQuantity(item.id, item.quantity + 1);
    });
    target.querySelectorAll('[data-decrease]').forEach(button => button.onclick = () => {
      const item = read().find(entry => entry.id === button.dataset.decrease);
      if (item) updateQuantity(item.id, item.quantity - 1);
    });
  };
  const open = () => { document.querySelector('[data-cart]').classList.add('open'); document.querySelector('.cart-scrim').classList.add('open'); };
  const close = () => { document.querySelector('[data-cart]').classList.remove('open'); document.querySelector('.cart-scrim').classList.remove('open'); };

  async function mutate(action, productId, quantity = 0) {
    const perform = async () => {
      await cartReady;
      if (!authenticated) return false;
      try {
        const response = await fetch(config.mutateUrl, {method: 'POST', headers: {'X-CSRFToken': config.csrfToken}, body: formData({action, product_id: productId, quantity, version: serverVersion})});
        const payload = await response.json();
        if (!response.ok) {
          if (response.status === 409 && payload.items) {
            applyServer(payload);
            render();
          }
          message(payload.detail || 'Your cart could not be updated.');
          return false;
        }
        applyServer(payload);
        message('');
        render();
        return true;
      } catch (_) {
        message('Could not update your saved cart. Please try again.');
        return false;
      }
    };
    const queued = mutationQueue.then(perform, perform);
    mutationQueue = queued.catch(() => {});
    return queued;
  }

  async function updateQuantity(productId, quantity) {
    if (authenticated) {
      await mutate('set', productId, Math.max(0, Math.min(20, quantity)));
      return;
    }
    const cart = read(), item = cart.find(entry => entry.id === productId);
    if (!item) return;
    item.quantity = quantity;
    save(cart.filter(entry => entry.quantity > 0));
    render();
  }

  async function add(metadata) {
    if (authenticated) return mutate('add', metadata.id);
    const cart = read(), item = cart.find(entry => entry.id === metadata.id);
    if (item) item.quantity = Math.min(20, item.quantity + 1);
    else cart.push({...metadata, price: Number(metadata.price), quantity: 1});
    save(cart);
    render();
    return true;
  }

  async function initialiseAccountCart() {
    if (!authenticated) {
      if (localStorage.getItem(ownerKey)) {
        localStorage.removeItem(ownerKey);
        save([]);
      }
      render();
      return;
    }
    let guestCart = read();
    const owner = localStorage.getItem(ownerKey);
    if (owner && owner !== String(config.userId)) {
      guestCart = [];
      save([]);
    } else if (owner === String(config.userId)) {
      // This browser already has an account cache. Load the authoritative
      // server cart instead of re-merging stale cached items from this device.
      guestCart = [];
    }
    try {
      const response = await fetch(config.mergeUrl, {method: 'POST', headers: {'X-CSRFToken': config.csrfToken}, body: formData({cart_payload: JSON.stringify(guestCart)})});
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail);
      applyServer(payload);
      message('');
    } catch (_) {
      message('Your saved cart could not be loaded. This device cart is still available.');
    }
    render();
    window.dispatchEvent(new Event('harvis-cart-synchronised'));
  }

  document.querySelectorAll('[data-cart-open]').forEach(x => x.onclick = open);
  document.querySelectorAll('[data-cart-close]').forEach(x => x.onclick = close);
  document.querySelectorAll('[data-add]').forEach(button => button.onclick = async () => {
    button.disabled = true;
    await add({id: button.dataset.id, name: button.dataset.name, price: button.dataset.price, image: button.dataset.image || ''});
    button.disabled = false;
    open();
  });
  document.querySelectorAll('[data-filter]').forEach(button => button.onclick = () => { document.querySelectorAll('[data-filter]').forEach(x => x.classList.remove('active')); button.classList.add('active'); document.querySelectorAll('[data-category]').forEach(card => card.hidden = button.dataset.filter !== 'all' && card.dataset.category !== button.dataset.filter); });

  cartReady = initialiseAccountCart();
})();
