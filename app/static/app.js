const libraryList = document.getElementById("libraryList");
const catalogList = document.getElementById("catalogList");
const libraryForm = document.getElementById("libraryForm");
const refreshCatalogButton = document.getElementById("refreshCatalog");
const catalogStatus = document.getElementById("catalogStatus");
const reloadLibrary = document.getElementById("reloadLibrary");
const reloadCatalog = document.getElementById("reloadCatalog");

const renderLibrary = (entries) => {
  if (!entries.length) {
    libraryList.innerHTML = "<p class=\"empty\">No entries yet.</p>";
    return;
  }
  libraryList.innerHTML = entries
    .map(
      (entry) => `
      <article class="card">
        <header>
          <h3>${entry.title}</h3>
          <span class="status">${entry.status}</span>
        </header>
        <p>${entry.notes || "No notes yet."}</p>
        <div class="pill-row">
          <span class="pill">Downloaded: ${entry.downloaded ? "Yes" : "No"}</span>
          <span class="pill">Watched: ${entry.watched ? "Yes" : "No"}</span>
        </div>
      </article>
    `
    )
    .join("");
};

const renderCatalog = (titles) => {
  if (!titles.length) {
    catalogList.innerHTML = "<p class=\"empty\">Catalog is empty.</p>";
    return;
  }
  catalogList.innerHTML = titles
    .slice(0, 30)
    .map(
      (title) => `
      <article class="card">
        <header>
          <h3>${title.title}</h3>
          <span class="status">${title.media_type}</span>
        </header>
        <p>Source: ${title.source} ${title.year ? `(${title.year})` : ""}</p>
      </article>
    `
    )
    .join("");
};

const fetchLibrary = async () => {
  const response = await fetch("/api/library");
  const entries = await response.json();
  renderLibrary(entries);
};

const fetchCatalog = async () => {
  const response = await fetch("/api/catalog");
  const titles = await response.json();
  renderCatalog(titles);
};

libraryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(libraryForm);
  const payload = Object.fromEntries(formData.entries());
  payload.downloaded = formData.get("downloaded") === "on";
  payload.watched = formData.get("watched") === "on";

  await fetch("/api/library", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  libraryForm.reset();
  fetchLibrary();
});

refreshCatalogButton.addEventListener("click", async () => {
  catalogStatus.textContent = "Refreshing...";
  const response = await fetch("/api/catalog/refresh", { method: "POST" });
  const data = await response.json();
  catalogStatus.textContent = `Added ${data.added} items`;
  fetchCatalog();
});

reloadLibrary.addEventListener("click", fetchLibrary);
reloadCatalog.addEventListener("click", fetchCatalog);

fetchLibrary();
fetchCatalog();
