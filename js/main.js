document.addEventListener("DOMContentLoaded", () => {
  initNavbar();
  initCart();
  initWhatsApp();
  initProductModal();
  initNewsletter();
  initHero();
});

function initNavbar() {
  const toggle = document.getElementById("navToggle");
  const links = document.getElementById("navLinks");
  if (toggle && links) {
    toggle.addEventListener("click", () => links.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".navbar")) links.classList.remove("open");
    });
  }
}

function formatPrice(price) {
  return "$" + Math.round(price).toLocaleString("es-CO") + " COP";
}

function getWhatsAppLink(message) {
  const encoded = typeof message === "string" && message.includes("%")
    ? message
    : encodeURIComponent(message);
  return `https://wa.me/${CONFIG.WHATSAPP_NUMBER}?text=${encoded}`;
}

const WHATSAPP_LINK = getWhatsAppLink(CONFIG.WHATSAPP_MESSAGE);

function initWhatsApp() {
  document.querySelectorAll(
    '[id$="WhatsApp"], [id^="whatsapp"], [id^="heroWhatsApp"], [id^="aboutWhatsApp"], #whatsappFloat'
  ).forEach(el => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      window.open(WHATSAPP_LINK, "_blank");
    });
  });

  document.getElementById("whatsappCheckoutBtn")?.addEventListener("click", async (e) => {
    e.preventDefault();
    const cart = getCart();
    if (cart.length === 0) return;
    await checkoutWhatsApp(cart);
  });
}

function initHero() {
  document.getElementById("heroWhatsApp")?.addEventListener("click", (e) => {
    e.preventDefault();
    window.open(WHATSAPP_LINK, "_blank");
  });
}

function initNewsletter() {
  const form = document.getElementById("newsletterForm");
  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      showToast("📬", "¡Gracias por suscribirte!");
      form.querySelector("input").value = "";
    });
  }
}

/* ── CART ── */
function getCart() {
  try { return JSON.parse(localStorage.getItem("cafeCart") || "[]"); } catch { return []; }
}

function setCart(cart) {
  localStorage.setItem("cafeCart", JSON.stringify(cart));
}

function updateCartUI() {
  const cart = getCart();
  const badge = document.getElementById("cartBadge");
  const items = document.getElementById("cartItems");
  const footer = document.getElementById("cartFooter");

  const count = cart.reduce((s, i) => s + i.cantidad, 0);
  if (badge) {
    if (count > 0) {
      badge.textContent = count;
      badge.classList.remove("hidden");
    } else {
      badge.classList.add("hidden");
    }
  }

  if (items) {
    if (cart.length === 0) {
      items.innerHTML = `<div class="cart-empty"><span class="empty-icon">🛒</span><p>Tu carrito está vacío</p></div>`;
      if (footer) footer.style.display = "none";
      return;
    }

    if (footer) footer.style.display = "block";

    items.innerHTML = cart.map(item => `
      <div class="cart-item">
        <img class="cart-item-img" src="${item.imagen}" alt="${item.nombre}" loading="lazy">
        <div class="cart-item-info">
          <div class="cart-item-nombre">${item.nombre}</div>
          <div class="cart-item-precio">${formatPrice(item.precio)} c/u</div>
          <div class="cart-item-cantidad">
            <button onclick="cambiarCantidad(${item.id}, -1)">−</button>
            <span>${item.cantidad}</span>
            <button onclick="cambiarCantidad(${item.id}, 1)">+</button>
            <button class="cart-item-eliminar" onclick="eliminarDelCarrito(${item.id})">✕</button>
          </div>
        </div>
      </div>
    `).join("");
  }

  updateTotal();
}

function updateTotal() {
  const cart = getCart();
  const total = cart.reduce((s, i) => s + i.precio * i.cantidad, 0);
  const totalEl = document.getElementById("cartTotal");
  if (totalEl) totalEl.textContent = formatPrice(total);
}

function agregarAlCarrito(producto) {
  if (producto.stock === false) {
    showToast("⚠️", "Producto agotado");
    return;
  }
  const cart = getCart();
  const existing = cart.find(i => i.id === producto.id);
  if (existing) {
    existing.cantidad += 1;
  } else {
    cart.push({ ...producto, cantidad: 1 });
  }
  setCart(cart);
  updateCartUI();
  showToast("☕", `${producto.nombre} agregado al carrito`);
}

window.cambiarCantidad = function(id, delta) {
  const cart = getCart();
  const item = cart.find(i => i.id === id);
  if (!item) return;
  item.cantidad += delta;
  if (item.cantidad <= 0) {
    cart.splice(cart.indexOf(item), 1);
  }
  setCart(cart);
  updateCartUI();
};

window.eliminarDelCarrito = function(id) {
  setCart(getCart().filter(i => i.id !== id));
  updateCartUI();
};

function initCart() {
  const toggle = document.getElementById("cartToggle");
  const overlay = document.getElementById("cartOverlay");
  const sidebar = document.getElementById("cartSidebar");
  const close = document.getElementById("cartClose");

  function closeCartSidebar() {
    overlay?.classList.remove("open");
    sidebar?.classList.remove("open");
    document.body.style.overflow = "";
  }

  window.closeCartSidebar = closeCartSidebar;

  if (toggle) toggle.addEventListener("click", (e) => {
    e.preventDefault();
    overlay?.classList.add("open");
    sidebar?.classList.add("open");
    document.body.style.overflow = "hidden";
  });
  if (overlay) overlay.addEventListener("click", closeCartSidebar);
  if (close) close.addEventListener("click", closeCartSidebar);

  const checkoutBtn = document.getElementById("checkoutBtn");
  if (checkoutBtn) {
    if (CONFIG.HAS_MERCADOPAGO) {
      checkoutBtn.style.display = "block";
      checkoutBtn.addEventListener("click", () => {
        const cart = getCart();
        if (cart.length === 0) return;
        openShippingModal(cart);
      });
    } else {
      checkoutBtn.style.display = "none";
    }
  }

  updateCartUI();
}

async function checkoutWhatsApp(cart, shipping = null) {
  if (!shipping) {
    try { shipping = JSON.parse(localStorage.getItem("lastShipping") || "{}"); } catch { shipping = {}; }
  }

  const btn = document.getElementById("whatsappCheckoutBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Abriendo WhatsApp...";
  }

  try {
    const res = await fetch("/api/whatsapp-order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: cart, shipping }),
    });
    const data = await res.json();

    if (data.url) {
      setCart([]);
      updateCartUI();
      window.closeCartSidebar?.();
      closeShippingModal();
      window.open(data.url, "_blank");
    } else {
      showToast("⚠️", "No se pudo generar el pedido. Intenta de nuevo.");
    }
  } catch {
    showToast("⚠️", "Error de conexión. Intenta de nuevo.");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Pedir por WhatsApp";
    }
  }
}

/* ── SHIPPING MODAL ── */
let shippingCart = null;

function openShippingModal(cart) {
  shippingCart = cart;
  if (!document.getElementById("shippingModal")) createShippingModal();
  document.getElementById("shippingModal").classList.add("open");
}

window.closeShippingModal = function() {
  document.getElementById("shippingModal")?.classList.remove("open");
  shippingCart = null;
};

function createShippingModal() {
  const html = `
  <div class="modal-overlay" id="shippingModal">
    <div class="modal" style="max-width:500px">
      <button class="modal-close" onclick="closeShippingModal()">✕</button>
      <h3 style="margin-bottom:0.5rem;color:var(--color-primary)">Datos de envío</h3>
      <p style="color:var(--color-text-light);font-size:0.85rem;margin-bottom:1.5rem">
        Completa tus datos para continuar con el pago
      </p>
      <form id="shippingForm">
        <div class="form-group">
          <label>Nombre completo *</label>
          <input type="text" name="name" required placeholder="Juan Pérez">
        </div>
        <div class="form-group">
          <label>Email *</label>
          <input type="email" name="email" required placeholder="juan@email.com">
        </div>
        <div class="form-group">
          <label>Teléfono *</label>
          <input type="tel" name="phone" required placeholder="+57 300 123 4567">
        </div>
        <div class="form-group">
          <label>Dirección completa *</label>
          <textarea name="address" rows="3" required placeholder="Calle 123 #45-67, Barrio, Ciudad"></textarea>
        </div>
        <div class="form-group">
          <label>Ciudad *</label>
          <input type="text" name="city" required placeholder="Bogotá, Medellín, Cali...">
        </div>
        <div style="display:flex;gap:0.75rem;margin-top:1rem">
          <button type="button" class="btn btn-secondary" onclick="closeShippingModal()" style="flex:1">Cancelar</button>
          <button type="submit" class="btn btn-primary" style="flex:1">Continuar al pago</button>
        </div>
      </form>
    </div>
  </div>`;
  document.body.insertAdjacentHTML("beforeend", html);
  document.getElementById("shippingForm").addEventListener("submit", handleShippingSubmit);
  document.getElementById("shippingModal").addEventListener("click", (e) => {
    if (e.target.id === "shippingModal") closeShippingModal();
  });
}

async function handleShippingSubmit(e) {
  e.preventDefault();
  const form = e.target;
  const shipping = Object.fromEntries(new FormData(form));
  localStorage.setItem("lastShipping", JSON.stringify(shipping));

  const btn = form.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.textContent = "Procesando...";

  try {
    const res = await fetch("/api/create_preference", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: shippingCart, shipping }),
    });
    const data = await res.json();

    if (data.init_point) {
      setCart([]);
      updateCartUI();
      closeShippingModal();
      window.closeCartSidebar?.();
      window.open(data.init_point, "_blank");
    } else if (data.url) {
      setCart([]);
      updateCartUI();
      closeShippingModal();
      window.closeCartSidebar?.();
      window.open(data.url, "_blank");
    } else {
      showToast("⚠️", "Error al procesar. Intenta por WhatsApp.");
    }
  } catch {
    showToast("⚠️", "Error de conexión. Intenta por WhatsApp.");
  } finally {
    btn.disabled = false;
    btn.textContent = "Continuar al pago";
  }
}

/* ── PRODUCT MODAL ── */
let modalProducto = null;

function initProductModal() {
  const overlay = document.getElementById("productModal");
  const closeBtn = document.getElementById("modalClose");
  const agregarBtn = document.getElementById("modalAgregar");
  const whatsappBtn = document.getElementById("modalWhatsApp");

  if (closeBtn) closeBtn.addEventListener("click", () => overlay.classList.remove("open"));
  if (overlay) overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.classList.remove("open");
  });

  if (agregarBtn) {
    agregarBtn.addEventListener("click", () => {
      if (modalProducto) {
        agregarAlCarrito(modalProducto);
        overlay.classList.remove("open");
      }
    });
  }

  if (whatsappBtn) {
    whatsappBtn.addEventListener("click", () => {
      if (modalProducto) {
        const msg = encodeURIComponent(
          `Hola, quiero información sobre ${modalProducto.nombre} (${formatPrice(modalProducto.precio)})`
        );
        window.open(getWhatsAppLink(msg), "_blank");
      }
    });
  }
}

window.abrirModal = function(producto) {
  modalProducto = producto;
  document.getElementById("modalImg").src = producto.imagen;
  document.getElementById("modalImg").alt = producto.nombre;
  document.getElementById("modalNombre").textContent = producto.nombre;
  document.getElementById("modalDesc").textContent = producto.descripcion || producto.descripcion_corta;
  document.getElementById("modalPrecio").textContent = formatPrice(producto.precio);

  const agregarBtn = document.getElementById("modalAgregar");
  if (agregarBtn) {
    const sinStock = producto.stock === false;
    agregarBtn.disabled = sinStock;
    agregarBtn.textContent = sinStock ? "Agotado" : "Agregar al carrito";
  }

  document.getElementById("productModal").classList.add("open");
};

/* ── TOAST ── */
function showToast(icon, message) {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-message">${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

/* ── RENDER PRODUCT CARDS ── */
window.renderProductos = function(productos, containerId = "productosGrid") {
  const grid = document.getElementById(containerId);
  if (!grid) return;

  if (productos.length === 0) {
    grid.innerHTML = `<p style="text-align:center;color:var(--color-text-light);grid-column:1/-1">No hay productos en esta categoría.</p>`;
    return;
  }

  grid.innerHTML = productos.map((p, i) => {
    const sinStock = p.stock === false;
    return `
    <div class="producto-card${sinStock ? " sin-stock" : ""}" data-idx="${i}" role="button" tabindex="0">
      <img class="producto-img" src="${p.imagen}" alt="${p.nombre}" loading="lazy">
      <div class="producto-info">
        <span class="producto-categoria">${p.categoria}</span>
        <h3 class="producto-nombre">${p.nombre}</h3>
        <p class="producto-descripcion">${p.descripcion_corta}</p>
        <div class="producto-footer">
          <span class="producto-precio">${Math.round(p.precio).toLocaleString("es-CO")}</span>
          <button class="btn-agregar${sinStock ? " agotado" : ""}" data-idx="${i}" ${sinStock ? "disabled" : ""}>
            ${sinStock ? "Agotado" : "+ Agregar"}
          </button>
        </div>
      </div>
    </div>`;
  }).join("");

  grid._productos = productos;

  grid.querySelectorAll(".producto-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".btn-agregar")) return;
      abrirModal(productos[parseInt(card.dataset.idx)]);
    });
  });

  grid.querySelectorAll(".btn-agregar:not(.agotado)").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      agregarAlCarrito(productos[parseInt(btn.dataset.idx)]);
    });
  });
};
