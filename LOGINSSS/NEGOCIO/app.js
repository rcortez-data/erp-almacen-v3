const products = [
  { id: 1, name: "Coca-Cola 600 ml", category: "Bebidas", price: 18, stock: 24, emoji: "🥤", tone: "coral", favorite: true },
  { id: 2, name: "Papas clásicas", category: "Botanas", price: 21, stock: 12, emoji: "🥔", tone: "yellow", favorite: true },
  { id: 3, name: "Pan dulce", category: "Despensa", price: 12, stock: 8, emoji: "🥐", tone: "yellow", favorite: true },
  { id: 4, name: "Agua natural 1 L", category: "Bebidas", price: 14, stock: 31, emoji: "💧", tone: "blue", favorite: true },
  { id: 5, name: "Leche entera 1 L", category: "Refrigerados", price: 28, stock: 7, emoji: "🥛", tone: "blue", favorite: false },
  { id: 6, name: "Galletas de chocolate", category: "Botanas", price: 17, stock: 16, emoji: "🍪", tone: "coral", favorite: false },
  { id: 7, name: "Huevo · 1 pieza", category: "Despensa", price: 4, stock: 42, emoji: "🥚", tone: "yellow", favorite: false },
  { id: 8, name: "Jabón de tocador", category: "Limpieza", price: 16, stock: 3, emoji: "🧼", tone: "lime", favorite: false },
  { id: 9, name: "Café soluble sobre", category: "Despensa", price: 9, stock: 25, emoji: "☕", tone: "coral", favorite: false },
  { id: 10, name: "Chicles de menta", category: "Botanas", price: 2, stock: 60, emoji: "🌿", tone: "lime", favorite: false },
  { id: 11, name: "Atún en lata", category: "Despensa", price: 24, stock: 10, emoji: "🐟", tone: "blue", favorite: false },
  { id: 12, name: "Suavizante 250 ml", category: "Limpieza", price: 19, stock: 5, emoji: "🫧", tone: "blue", favorite: false }
];

const state = {
  category: "Favoritos",
  query: "",
  cart: loadCart(),
  paymentMethod: "efectivo",
  saleNumber: Number(localStorage.getItem("negocio-sale-number") || 428)
};

const money = value => `$${value.toFixed(2)}`;
const $ = selector => document.querySelector(selector);

function loadCart() {
  try { return JSON.parse(localStorage.getItem("negocio-cart") || "{}"); }
  catch { return {}; }
}

function saveCart() { localStorage.setItem("negocio-cart", JSON.stringify(state.cart)); }

function categories() { return ["Favoritos", ...new Set(products.map(product => product.category))]; }

function renderCategories() {
  $("#categoryStrip").innerHTML = categories().map(category => `
    <button class="category-chip ${category === state.category ? "is-active" : ""}" type="button" data-category="${category}">${category}</button>
  `).join("");
  document.querySelectorAll("[data-category]").forEach(button => button.addEventListener("click", () => {
    state.category = button.dataset.category;
    render();
  }));
}

function filteredProducts() {
  const query = state.query.trim().toLocaleLowerCase("es-MX");
  return products.filter(product => {
    const inCategory = query ? true : state.category === "Favoritos" ? product.favorite : product.category === state.category;
    const matchesQuery = !query || `${product.name} ${product.category}`.toLocaleLowerCase("es-MX").includes(query);
    return inCategory && matchesQuery;
  });
}

function renderProducts() {
  const visible = filteredProducts();
  $("#productHeading").textContent = state.query ? "Resultados" : state.category === "Favoritos" ? "Favoritos de la casa" : state.category;
  $("#productCount").textContent = `${visible.length} producto${visible.length === 1 ? "" : "s"}`;
  $("#productGrid").innerHTML = visible.length ? visible.map(product => `
    <button class="product-card" type="button" data-product-id="${product.id}" data-tone="${product.tone}" aria-label="Agregar ${product.name}">
      <span class="product-art">${product.emoji}</span>
      <span class="product-meta"><span class="product-name">${product.name}</span><span class="product-detail"><span class="product-price">${money(product.price)}</span><span class="product-stock ${product.stock <= 5 ? "low" : ""}">${product.stock <= 5 ? `quedan ${product.stock}` : `${product.stock} disp.`}</span></span></span>
    </button>
  `).join("") : `<div class="no-results">No encontramos ese producto. Prueba con otro nombre o categoría.</div>`;
  document.querySelectorAll("[data-product-id]").forEach(button => button.addEventListener("click", () => addToCart(Number(button.dataset.productId))));
}

function cartEntries() {
  return Object.entries(state.cart).map(([id, quantity]) => ({ product: products.find(product => product.id === Number(id)), quantity })).filter(item => item.product);
}

function totals() {
  const subtotal = cartEntries().reduce((sum, item) => sum + item.product.price * item.quantity, 0);
  return { subtotal, discount: 0, total: subtotal };
}

function renderCart() {
  const entries = cartEntries();
  const { subtotal, discount, total } = totals();
  $("#cartCount").textContent = entries.reduce((sum, item) => sum + item.quantity, 0);
  $("#cartItems").innerHTML = entries.length ? entries.map(({ product, quantity }) => `
    <div class="cart-item">
      <span class="cart-item-art" style="background:${product.tone === "coral" ? "#ffd7c9" : product.tone === "lime" ? "#e2efb7" : product.tone === "yellow" ? "#ffedb4" : "#d8e3ff"}">${product.emoji}</span>
      <div><p class="cart-item-name">${product.name}</p><span class="cart-item-price">${money(product.price)} c/u</span></div>
      <div><div class="qty-control"><button type="button" data-action="decrease" data-id="${product.id}" aria-label="Quitar uno">−</button><span>${quantity}</span><button type="button" data-action="increase" data-id="${product.id}" aria-label="Agregar uno">+</button></div><div class="cart-item-total">${money(product.price * quantity)}</div></div>
    </div>
  `).join("") : `<div class="empty-cart"><span class="empty-basket">⌁</span><strong>La bolsa está lista</strong><p>Toca un producto para empezar la venta.</p></div>`;
  $("#subtotal").textContent = money(subtotal);
  $("#discount").textContent = `-${money(discount)}`;
  $("#total").textContent = money(total);
  $("#chargeButton").disabled = !entries.length;
  document.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", () => {
    const id = Number(button.dataset.id);
    if (button.dataset.action === "increase") addToCart(id); else changeQuantity(id, -1);
  }));
}

function addToCart(id) {
  const product = products.find(item => item.id === id);
  if (!product) return;
  const next = (state.cart[id] || 0) + 1;
  if (next > product.stock) return showToast("No hay más piezas disponibles de este producto.");
  state.cart[id] = next;
  saveCart(); renderCart(); showToast(`${product.name} se agregó a la bolsa`);
}

function changeQuantity(id, delta) {
  state.cart[id] = (state.cart[id] || 0) + delta;
  if (state.cart[id] <= 0) delete state.cart[id];
  saveCart(); renderCart();
}

function openPaymentModal() {
  const { total } = totals();
  $("#modalTotal").textContent = money(total);
  $("#modalSaleNumber").textContent = `#${String(state.saleNumber).padStart(5, "0")}`;
  $("#paymentModal").hidden = false;
  $("#cashInput").value = total.toFixed(2);
  updateChange();
  setTimeout(() => $("#cashInput").focus(), 0);
}

function closePaymentModal() { $("#paymentModal").hidden = true; }

function updateChange() {
  const received = Number($("#cashInput").value || 0);
  const { total } = totals();
  $("#changeAmount").textContent = money(Math.max(0, received - total));
}

function confirmPayment() {
  const { total } = totals();
  const received = Number($("#cashInput").value || 0);
  if (state.paymentMethod === "efectivo" && received < total) return showToast("El efectivo recibido aún no cubre el total.");
  const ticket = String(state.saleNumber).padStart(5, "0");
  const sale = { ticket, total, method: state.paymentMethod, items: cartEntries(), createdAt: new Date().toISOString() };
  localStorage.setItem(`negocio-sale-${ticket}`, JSON.stringify(sale));
  state.saleNumber += 1;
  localStorage.setItem("negocio-sale-number", state.saleNumber);
  state.cart = {};
  saveCart(); closePaymentModal(); render();
  showToast(`Venta #${ticket} guardada · ${money(total)}`);
}

let toastTimer;
function showToast(message) {
  const toast = $("#toast"); toast.textContent = message; toast.classList.add("is-visible");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 3000);
}

function render() {
  $("#saleNumber").textContent = String(state.saleNumber).padStart(5, "0");
  renderCategories(); renderProducts(); renderCart();
}

$("#searchInput").addEventListener("input", event => { state.query = event.target.value; renderProducts(); });
$("#clearCartButton").addEventListener("click", () => { if (!cartEntries().length) return; state.cart = {}; saveCart(); renderCart(); showToast("La bolsa quedó vacía"); });
$("#chargeButton").addEventListener("click", openPaymentModal);
$("#closeModalButton").addEventListener("click", closePaymentModal);
$("#paymentModal").addEventListener("click", event => { if (event.target.id === "paymentModal") closePaymentModal(); });
$("#cashInput").addEventListener("input", updateChange);
$("#confirmPaymentButton").addEventListener("click", confirmPayment);
$("#paymentMethods").addEventListener("click", event => {
  const method = event.target.closest("[data-method]"); if (!method) return;
  state.paymentMethod = method.dataset.method;
  document.querySelectorAll("[data-method]").forEach(button => button.classList.toggle("is-selected", button === method));
  $("#cashEntry").hidden = state.paymentMethod !== "efectivo";
});
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); $("#searchInput").focus(); }
  if (event.key === "Escape") { closePaymentModal(); if (document.activeElement === $("#searchInput")) { $("#searchInput").value = ""; state.query = ""; renderProducts(); } }
  if (event.key === "Enter" && !$("#paymentModal").hidden && document.activeElement !== $("#confirmPaymentButton")) return;
  if (event.key === "Enter" && $("#paymentModal").hidden && !$("#chargeButton").disabled) openPaymentModal();
});

render();
