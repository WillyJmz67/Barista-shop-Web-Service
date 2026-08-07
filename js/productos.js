document.addEventListener("DOMContentLoaded", async () => {
  const productos = await cargarProductos();
  if (!productos) return;

  const params = new URLSearchParams(window.location.search);
  const catInicial = params.get("cat") || "todas";

  const btns = document.querySelectorAll(".filtro-btn");
  btns.forEach(btn => {
    btn.addEventListener("click", () => {
      btns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const cat = btn.dataset.cat;
      const url = new URL(window.location);
      if (cat === "todas") url.searchParams.delete("cat");
      else url.searchParams.set("cat", cat);
      window.history.replaceState({}, "", url);
      filtrarYRenderizar(productos, cat);
    });
  });

  btns.forEach(b => b.classList.remove("active"));
  const activeBtn = document.querySelector(`.filtro-btn[data-cat="${catInicial}"]`);
  if (activeBtn) activeBtn.classList.add("active");
  filtrarYRenderizar(productos, catInicial);
});

async function cargarProductos() {
  try {
    const res = await fetch("/api/productos");
    return await res.json();
  } catch (e) {
    console.error("Error cargando productos:", e);
    return null;
  }
}

function filtrarYRenderizar(productos, categoria) {
  const filtrados = categoria === "todas"
    ? productos
    : productos.filter(p => p.categoria === categoria);
  renderProductos(filtrados, "productosGrid");
}
