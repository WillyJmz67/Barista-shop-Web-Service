document.addEventListener("DOMContentLoaded", async () => {
  try {
    const res = await fetch("/api/productos/destacados");
    const destacados = await res.json();
    renderProductos(destacados, "destacadosGrid");
  } catch (e) {
    console.error("Error cargando destacados:", e);
  }
});
