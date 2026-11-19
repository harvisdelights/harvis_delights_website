(() => {
  document.querySelectorAll('[data-copy-coupon]').forEach(button => {
    button.addEventListener('click', async () => {
      const code = button.dataset.copyCoupon;
      try {
        await navigator.clipboard.writeText(code);
        button.textContent = 'Copied';
      } catch (_) {
        button.textContent = code;
      }
      window.setTimeout(() => { button.textContent = 'Copy code'; }, 1800);
    });
  });
})();
