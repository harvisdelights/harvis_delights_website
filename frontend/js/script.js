document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".nav");
  if (toggle && nav) toggle.addEventListener("click", () => nav.classList.toggle("open"));

  // Temporary Flipkart placeholders. Replace each href with the actual product URL.
  document.querySelectorAll("[data-flipkart]").forEach(btn => {
    btn.addEventListener("click", e => {
      e.preventDefault();
      alert("Flipkart product link will be added here.");
    });
  });
});