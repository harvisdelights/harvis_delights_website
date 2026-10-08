(() => {
  const key = "harvis-cart";
  const read = () => JSON.parse(localStorage.getItem(key) || "[]");
  const save = cart => localStorage.setItem(key, JSON.stringify(cart));
  const money = value => `₹${Number(value).toFixed(2)}`;
  const render = () => {
    const cart = read(), target = document.querySelector("[data-cart-items]");
    document.querySelectorAll("[data-cart-count]").forEach(x => x.textContent = cart.reduce((n, p) => n + p.quantity, 0));
    document.querySelector("[data-cart-total]").textContent = money(cart.reduce((n, p) => n + p.price * p.quantity, 0));
    target.innerHTML = cart.length ? cart.map(p => `<div class="cart-item">${p.image ? `<img src="${p.image}" alt="">` : `<span class="cart-thumb">${p.name[0]}</span>`}<div><b>${p.name}</b><span>${p.quantity} × ${money(p.price)}</span></div><button data-remove="${p.id}">Remove</button></div>`).join("") : '<p class="cart-note">Your cart is empty. Add something delightful.</p>';
    target.querySelectorAll("[data-remove]").forEach(button => button.onclick = () => { save(read().filter(p => p.id !== button.dataset.remove)); render(); });
  };
  const open = () => { document.querySelector("[data-cart]").classList.add("open"); document.querySelector(".cart-scrim").classList.add("open"); };
  const close = () => { document.querySelector("[data-cart]").classList.remove("open"); document.querySelector(".cart-scrim").classList.remove("open"); };
  document.querySelectorAll("[data-cart-open]").forEach(x => x.onclick = open);
  document.querySelectorAll("[data-cart-close]").forEach(x => x.onclick = close);
  document.querySelectorAll("[data-add]").forEach(button => button.onclick = () => {
    const cart = read(), item = cart.find(p => p.id === button.dataset.id);
    if (item) item.quantity += 1;
    else cart.push({id: button.dataset.id, name: button.dataset.name, price: Number(button.dataset.price), image: button.dataset.image || "", quantity: 1});
    save(cart); render(); open();
  });
  document.querySelectorAll("[data-filter]").forEach(button => button.onclick = () => { document.querySelectorAll("[data-filter]").forEach(x => x.classList.remove("active")); button.classList.add("active"); document.querySelectorAll("[data-category]").forEach(card => card.hidden = button.dataset.filter !== "all" && card.dataset.category !== button.dataset.filter); });
  render();
})();
