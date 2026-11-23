(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

  const THEME_KEY = "imagefinder-theme";
  const FOLDER_KEY = "imagefinder-folder";
  const DATE_FORMAT = new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  const state = {
    csrf: "",
    root: "",
    version: "",
    folders: [],
    totals: { images: 0, bytes: 0, folders: 0 },
    currentFolder: "",
    images: [],
    rendered: [],
    filter: "",
    sort: "recent",
    galleryBytes: 0,
    loadToken: 0,
    jobId: null,
    jobStatus: null,
    jobPanelHidden: false,
    jobAutoHide: null,
    pollTimer: null,
    pollFails: 0,
    filterDebounce: null,
    lightboxIndex: -1,
    lastFocused: null,
    emptyMode: "search",
    folderIntent: "navigate",
    pagination: { page: 1, pageSize: 50, total: 0, totalPages: 1 },
    cache: { count: 0, bytes: 0 },
    virtual: { rendered: 0, batchSize: 12, sentinelObserver: null },
    selection: { paths: new Set(), mode: "browser", folderName: "" },
    inboxMode: false,
    unsplashKeyConfigured: false,
    selectedSources: ["all", "yandex", "commons", "ddg", "openverse", "unsplash"],
  };

  const els = {};

  function cacheElements() {
    els.sidebar = $("#sidebar");
    els.sidebarScrim = $("#sidebarScrim");
    els.sidebarClose = $("#sidebarClose");
    els.menuBtn = $("#menuBtn");
    els.folderList = $("#folderList");
    els.foldersEmpty = $("#foldersEmpty");
    els.folderCount = $("#folderCount");
    els.allCount = $("#allCount");
    els.navAll = $("#navAll");
    els.rootPath = $("#rootPath");
    els.storageLabel = $("#storageLabel");
    els.storageSize = $("#storageSize");
    els.folderSummary = $("#folderSummary");
    els.currentFolderLabel = $("#currentFolderLabel");
    els.themeBtn = $("#themeBtn");
    els.serverStatus = $("#serverStatus");
    els.newFolderBtn = $("#newFolderBtn");
    els.newFolderInline = $("#newFolderInline");
    els.changeRootBtn = $("#changeRootBtn");
    els.searchForm = $("#searchForm");
    els.searchInput = $("#searchInput");
    els.searchBtn = $("#searchBtn");
    els.searchFolder = $("#searchFolder");
    els.searchLimit = $("#searchLimit");
    els.searchSource = $("#sourceTrigger");
    els.sourceMulti = $("#sourceMulti");
    els.sourceList = $("#sourceList");
    els.sourceBadge = $("#sourceBadge");
    els.sourceTriggerText = $("#sourceTriggerText");
    els.sourceCheckboxes = $$("#sourceList input[type=checkbox]");
    els.searchOrientation = $("#searchOrientation");
    els.jobPanel = $("#jobPanel");
    els.jobClose = $("#jobClose");
    els.jobCancel = $("#jobCancel");
    els.jobTitle = $("#jobTitle");
    els.jobMessage = $("#jobMessage");
    els.jobCount = $("#jobCount");
    els.jobElapsed = $("#jobElapsed");
    els.jobProgress = $("#jobProgress");
    els.jobLog = $("#jobLog");
    els.galleryTitle = $("#galleryTitle");
    els.gallerySubtitle = $("#gallerySubtitle");
    els.gallery = $("#gallery");
    els.galleryLoading = $("#galleryLoading");
    els.emptyState = $("#emptyState");
    els.emptyTitle = $("#emptyTitle");
    els.emptyText = $("#emptyText");
    els.emptyAction = $("#emptyAction");
    els.imageFilter = $("#imageFilter");
    els.sortSelect = $("#sortSelect");
    els.refreshBtn = $("#refreshBtn");
    els.pageSizeSelect = $("#pageSizeSelect");
    els.paginationBar = $("#paginationBar");
    els.paginationPrev = $("#paginationPrev");
    els.paginationNext = $("#paginationNext");
    els.paginationInfo = $("#paginationInfo");
    els.paginationPage = $("#paginationPage");
    els.paginationTotalPages = $("#paginationTotalPages");
    els.cacheSummary = $("#cacheSummary");
    els.clearCacheBtn = $("#clearCacheBtn");
    els.selectionBar = $("#selectionBar");
    els.selectionCount = $("#selectionCount");
    els.selectionSelectAll = $("#selectionSelectAll");
    els.selectionDownload = $("#selectionDownload");
    els.selectionDelete = $("#selectionDelete");
    els.selectionDestination = $("#selectionDestination");
    els.selectionFolderName = $("#selectionFolderName");
    els.inboxToggle = $("#inboxToggle");
    els.unsplashKeyField = $("#unsplashKeyField");
    els.unsplashKeyToggle = $("#unsplashKeyToggle");
    els.unsplashKey = $("#unsplashKey");
    els.unsplashKeySave = $("#unsplashKeySave");
    els.unsplashKeyStatus = $("#unsplashKeyStatus");
    els.unsplashKeyBadge = $("#unsplashKeyBadge");
    els.moveBar = $("#moveBar");
    els.moveCount = $("#moveCount");
    els.moveFolderName = $("#moveFolderName");
    els.moveDownload = $("#moveDownload");
    els.folderDialog = $("#folderDialog");
    els.folderForm = $("#folderForm");
    els.folderName = $("#folderName");
    els.folderError = $("#folderError");
    els.folderSubmit = $("#folderSubmit");
    els.rootDialog = $("#rootDialog");
    els.rootForm = $("#rootForm");
    els.rootPathInput = $("#rootPathInput");
    els.rootError = $("#rootError");
    els.rootSubmit = $("#rootSubmit");
    els.rootBrowseBtn = $("#rootBrowseBtn");
    els.confirmDialog = $("#confirmDialog");
    els.confirmTitle = $("#confirmTitle");
    els.confirmMessage = $("#confirmMessage");
    els.confirmOk = $("#confirmOk");
    els.confirmCancel = $("#confirmCancel");
    els.lightbox = $("#lightbox");
    els.lightboxImage = $("#lightboxImage");
    els.lightboxTitle = $("#lightboxTitle");
    els.lightboxMeta = $("#lightboxMeta");
    els.lightboxPath = $("#lightboxPath");
    els.lightboxSource = $("#lightboxSource");
    els.lightboxDownload = $("#lightboxDownload");
    els.lightboxDelete = $("#lightboxDelete");
    els.lightboxClose = $("#lightboxClose");
    els.lightboxPrev = $("#lightboxPrev");
    els.lightboxNext = $("#lightboxNext");
    els.toasts = $("#toasts");
  }

  /* ------------------------------------------------------------
     Utilitaires
     ------------------------------------------------------------ */

  const ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (char) => ESCAPES[char]);
  }

  function icon(name, className = "") {
    return `<svg class="icon ${className}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
  }

  function formatBytes(value) {
    const bytes = Number(value) || 0;
    if (bytes <= 0) return "0 o";
    const units = ["o", "Ko", "Mo", "Go", "To"];
    const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
    const amount = bytes / Math.pow(1024, index);
    const digits = index === 0 ? 0 : amount >= 100 ? 0 : amount >= 10 ? 1 : 2;
    return `${amount.toLocaleString("fr-FR", { maximumFractionDigits: digits })} ${units[index]}`;
  }

  function formatElapsed(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    if (total < 60) return `${total} s`;
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${minutes} min ${String(rest).padStart(2, "0")} s`;
  }

  function formatDate(timestamp) {
    if (!timestamp) return "";
    try {
      return DATE_FORMAT.format(new Date(Number(timestamp) * 1000));
    } catch {
      return "";
    }
  }

  function plural(count, singular, pluralForm) {
    return `${count.toLocaleString("fr-FR")} ${count > 1 ? pluralForm : singular}`;
  }

  function thumbUrl(path, width = 480, version = 0) {
    const params = new URLSearchParams({ path, w: String(width), v: String(version || 0) });
    return `/api/thumb?${params.toString()}`;
  }

  function downloadUrl(path) {
    return `/api/download?path=${encodeURIComponent(path)}`;
  }

  function setConnection(online) {
    if (!els.serverStatus) return;
    els.serverStatus.classList.toggle("offline", !online);
    const label = els.serverStatus.querySelector(".status-text");
    if (label) label.textContent = online ? "En ligne" : "Hors ligne";
    els.serverStatus.title = online ? "Serveur connecté" : "Serveur injoignable";
  }

  async function api(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    let body = options.body;
    if (method !== "GET" && state.csrf) {
      headers.set("X-CSRF-Token", state.csrf);
    }
    if (body && !(body instanceof FormData) && typeof body !== "string") {
      headers.set("Content-Type", "application/json");
      body = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(path, {
        ...options,
        method,
        headers,
        body,
        credentials: "same-origin",
      });
    } catch (error) {
      setConnection(false);
      throw new Error("Impossible de joindre le serveur.");
    }

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    if (!response.ok) {
      if (response.status === 401) {
        throw new Error("Authentification requise.");
      }
      throw new Error(data?.error || `Erreur ${response.status}`);
    }
    setConnection(true);
    return data;
  }

  function showToast(message, type = "success", duration = 4400) {
    const icons = {
      success: "check",
      error: "alert",
      info: "info",
      search: "sparkles",
    };
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <span class="toast-icon">${icon(icons[type] || "info")}</span>
      <span class="toast-body">${escapeHtml(message)}</span>`;
    els.toasts.appendChild(toast);
    while (els.toasts.children.length > 4) {
      els.toasts.firstElementChild?.remove();
    }
    const remove = () => {
      if (!toast.isConnected) return;
      toast.classList.add("leaving");
      window.setTimeout(() => toast.remove(), 240);
    };
    const timer = window.setTimeout(remove, duration);
    toast.addEventListener("mouseenter", () => window.clearTimeout(timer), { once: true });
    toast.addEventListener("click", remove);
  }

  /* ------------------------------------------------------------
     Thème & menu mobile
     ------------------------------------------------------------ */

  function initTheme() {
    let theme = null;
    try {
      theme = localStorage.getItem(THEME_KEY);
    } catch {
      theme = null;
    }
    if (theme !== "light" && theme !== "dark") {
      theme = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
    }
    document.documentElement.dataset.theme = theme;
  }

  function toggleTheme() {
    const current = document.documentElement.dataset.theme || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* stockage indisponible */
    }
  }

  function setSidebar(open) {
    document.body.classList.toggle("sidebar-open", open);
    if (els.sidebarScrim) els.sidebarScrim.hidden = !open;
  }

  /* ------------------------------------------------------------
     État & dossiers
     ------------------------------------------------------------ */

  function applyState(data) {
    state.csrf = data.csrf || state.csrf;
    state.root = data.root || "";
    state.version = data.version || "";
    state.folders = Array.isArray(data.folders) ? data.folders : [];
    state.totals = data.totals || { images: 0, bytes: 0, folders: 0 };

    els.rootPath.textContent = state.root || "—";
    els.rootPath.title = state.root || "";
    els.allCount.textContent = Number(state.totals.images || 0).toLocaleString("fr-FR");
    els.folderCount.textContent = String(state.totals.folders || 0);
    els.storageLabel.textContent = plural(Number(state.totals.images || 0), "image", "images");
    els.storageSize.textContent = formatBytes(state.totals.bytes);
    els.folderSummary.textContent = plural(Number(state.totals.folders || 0), "dossier", "dossiers");
    els.cacheSummary.textContent = `Cache : ${formatBytes(state.cache.bytes)} (${state.cache.count})`;

    if (data.cache) {
      state.cache = {
        count: Number(data.cache.count || 0),
        bytes: Number(data.cache.bytes || 0),
      };
    }

    if (data.inbox_mode !== undefined) {
      state.inboxMode = Boolean(data.inbox_mode);
      if (els.inboxToggle) els.inboxToggle.checked = state.inboxMode;
    }

    if (data.unsplash_key_configured !== undefined) {
      state.unsplashKeyConfigured = Boolean(data.unsplash_key_configured);
      if (els.unsplashKeyStatus) {
        els.unsplashKeyStatus.textContent = state.unsplashKeyConfigured
          ? "Cle Unsplash configuree"
          : "Cle Unsplash non configuree";
      }
      if (state.unsplashKeyConfigured && els.unsplashKeyField) {
        els.unsplashKeyField.querySelector(".field-body").hidden = true;
        els.unsplashKeyToggle.setAttribute("aria-expanded", "false");
        if (els.unsplashKeyBadge) {
          els.unsplashKeyBadge.textContent = "Configuree";
        }
      }
    }

    if (data.pagination) {
      state.pagination = {
        page: Number(data.pagination.page || 1),
        pageSize: Number(data.pagination.page_size || 50),
        total: Number(data.pagination.total || 0),
        totalPages: Number(data.pagination.total_pages || 1),
      };
    }

    if (state.currentFolder && !state.folders.some((folder) => folder.name === state.currentFolder)) {
      state.currentFolder = "";
    }

    renderFolders();
    renderSearchFolders();
    updateActiveFolder();
  }

  function renderFolders() {
    if (!els.folderList) return;
    els.folderList.innerHTML = state.folders
      .map((folder) => {
        const active = folder.name === state.currentFolder ? " active" : "";
        const visual = folder.cover
          ? `<img class="folder-thumb" src="${thumbUrl(folder.cover, 96, folder.updated)}" alt="" loading="lazy">`
          : `<span class="folder-icon">${icon("folder")}</span>`;
        return `
          <div class="folder-item${active}" role="button" tabindex="0" data-folder="${escapeHtml(folder.name)}" title="${escapeHtml(folder.name)}">
            ${visual}
            <span class="folder-name">${escapeHtml(folder.name)}</span>
            <span class="folder-count">${Number(folder.count || 0).toLocaleString("fr-FR")}</span>
            <button class="folder-delete" type="button" data-folder="${escapeHtml(folder.name)}" title="Supprimer le dossier" aria-label="Supprimer le dossier ${escapeHtml(folder.name)}">
              ${icon("trash")}
            </button>
          </div>`;
      })
      .join("");
    els.foldersEmpty.hidden = state.folders.length > 0;
  }

  function renderSearchFolders() {
    if (!els.searchFolder) return;
    const previous = els.searchFolder.value;
    const options = ['<option value="">Automatique</option>'];
    for (const folder of state.folders) {
      options.push(
        `<option value="${escapeHtml(folder.name)}">${escapeHtml(folder.name)} (${folder.count})</option>`
      );
    }
    els.searchFolder.innerHTML = options.join("");
    if (state.folders.some((folder) => folder.name === previous) || previous === "") {
      els.searchFolder.value = previous;
    } else {
      els.searchFolder.value = "";
    }
  }

  function updateActiveFolder() {
    const folder = state.currentFolder;
    els.navAll.classList.toggle("active", !folder);
    $$(".folder-item", els.folderList).forEach((item) => {
      item.classList.toggle("active", item.dataset.folder === folder);
    });
    els.currentFolderLabel.textContent = folder || "Toutes les images";
    els.galleryTitle.textContent = folder || "Toutes les images";
    document.title = folder ? `${folder} — Image Finder` : "Image Finder — bibliothèque visuelle";
  }

  async function selectFolder(folder, { scroll = false } = {}) {
    state.currentFolder = folder || "";
    state.filter = "";
    state.pagination.page = 1;
    if (els.imageFilter) els.imageFilter.value = "";
    try {
      localStorage.setItem(FOLDER_KEY, state.currentFolder);
    } catch {
      /* stockage indisponible */
    }
    updateActiveFolder();
    els.searchFolder.value = state.currentFolder;
    setSidebar(false);
    if (scroll) {
      $(".gallery-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    await loadImages();
  }

  async function loadState() {
    const data = await api("/api/state");
    applyState(data);
    return data;
  }

  async function refreshData({ scroll = false } = {}) {
    try {
      const data = await loadState();
      if (
        state.currentFolder &&
        !data.folders.some((folder) => folder.name === state.currentFolder)
      ) {
        state.currentFolder = "";
      }
      applyState(data);
      if (scroll) {
        $(".gallery-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      await loadImages();
    } catch (error) {
      showToast(error.message, "error");
    }
  }

  function showGalleryLoading() {
    els.emptyState.hidden = true;
    els.gallery.hidden = true;
    els.galleryLoading.hidden = false;
    if (!els.galleryLoading.childElementCount) {
      els.galleryLoading.innerHTML = Array.from(
        { length: 8 },
        () => '<div class="skeleton-card"></div>'
      ).join("");
    }
  }

  async function loadImages() {
    const token = ++state.loadToken;
    const folder = state.currentFolder;
    showGalleryLoading();
    try {
      const params = new URLSearchParams();
      if (folder) params.set("folder", folder);
      params.set("page", String(state.pagination.page));
      params.set("page_size", String(state.pagination.pageSize));
      const data = await api(`/api/images?${params.toString()}`);
      if (token !== state.loadToken) return;
      state.images = Array.isArray(data.images) ? data.images : [];
      state.pagination.total = Number(data.total || 0);
      state.pagination.totalPages = Number(data.total_pages || 1);
      state.pagination.page = Number(data.page || 1);
      state.pagination.pageSize = Number(data.page_size || 50);
      state.galleryBytes = Number(data.bytes || 0);
      els.galleryLoading.hidden = true;
      renderGallery();
      renderPagination();
      setConnection(true);
    } catch (error) {
      if (token !== state.loadToken) return;
      els.galleryLoading.hidden = true;
      state.images = [];
      state.rendered = [];
      state.galleryBytes = 0;
      state.pagination.total = 0;
      state.pagination.totalPages = 1;
      renderGallery(error.message);
      showToast(error.message, "error");
    }
  }

  function gallerySubtitle(filteredCount, filteredBytes) {
    const total = state.images.length;
    if (!total) {
      return state.currentFolder
        ? "Ce dossier ne contient encore aucune image."
        : "Votre bibliothèque, en un coup d'œil.";
    }
    const parts = [];
    if (filteredCount !== total) {
      parts.push(`${filteredCount.toLocaleString("fr-FR")} sur ${total.toLocaleString("fr-FR")} images`);
    } else {
      parts.push(plural(total, "image", "images"));
    }
    parts.push(formatBytes(filteredBytes));
    if (state.currentFolder) parts.push("dossier sélectionné");
    return parts.join(" · ");
  }

  function renderGallery(errorMessage = "") {
    state.selection.paths.clear();
    updateSelectionBar();
    let list = state.images.slice();
    const needle = state.filter.trim().toLowerCase();
    if (needle) {
      list = list.filter((item) =>
        `${item.title} ${item.name} ${item.folder}`.toLowerCase().includes(needle)
      );
    }

    if (state.sort === "name") {
      list.sort((a, b) => String(a.title || a.name).localeCompare(String(b.title || b.name), "fr"));
    } else if (state.sort === "size") {
      list.sort((a, b) => Number(b.size) - Number(a.size));
    } else {
      list.sort((a, b) => Number(b.mtime) - Number(a.mtime));
    }

    state.rendered = list;
    const filteredBytes = list.reduce((sum, item) => sum + (Number(item.size) || 0), 0);
    els.galleryTitle.textContent = state.currentFolder || "Toutes les images";
    els.gallerySubtitle.textContent = gallerySubtitle(list.length, filteredBytes);

    if (errorMessage) {
      showEmptyState(
        "Galerie indisponible",
        errorMessage,
        "Réessayer",
        "retry"
      );
      els.gallery.innerHTML = "";
      return;
    }

    if (!state.images.length) {
      if (state.currentFolder) {
        showEmptyState(
          "Ce dossier est vide",
          "Lancez une recherche pour y télécharger des images, ou choisissez un autre dossier.",
          "Chercher des images",
          "search"
        );
      } else {
        showEmptyState(
          "Votre bibliothèque est vide",
          "Lancez une première recherche : les images seront téléchargées et rangées automatiquement.",
          "Chercher des images",
          "search"
        );
      }
      els.gallery.innerHTML = "";
      return;
    }

    if (!list.length) {
      showEmptyState(
        "Aucune image ne correspond",
        `Aucun résultat pour « ${state.filter.trim()} ». Essayez un autre mot-clé.`,
        "Effacer le filtre",
        "filter"
      );
      els.gallery.innerHTML = "";
      return;
    }

    els.emptyState.hidden = true;
    els.gallery.hidden = false;
    state.virtual.rendered = 0;
    els.gallery.innerHTML = `<div class="gallery-sentinel" id="virtualSentinel"></div>`;
    renderVirtualBatch();
    renderPagination();
  }

  function renderVirtualBatch() {
    const list = state.rendered;
    if (!list.length) return;

    const start = state.virtual.rendered;
    const end = Math.min(start + state.virtual.batchSize, list.length);
    if (start >= end) {
      // Plus rien à rendre, masquer le sentinelle
      const sentinel = $("#virtualSentinel");
      if (sentinel) sentinel.hidden = true;
      return;
    }

    const batch = list.slice(start, end);
    const container = els.gallery;
    const fragment = document.createDocumentFragment();

    batch.forEach((item, index) => {
      const title = item.title && item.title !== "Sans titre" ? item.title : item.name;
      const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "dimensions inconnues";
      const meta = [dimensions, formatBytes(item.size), formatDate(item.mtime)].filter(Boolean).join(" · ");
      const folderBadge = item.folder
        ? `<span class="card-folder" title="${escapeHtml(item.folder)}">${escapeHtml(item.folder)}</span>`
        : "";
      const article = document.createElement("article");
      article.className = "card";
      article.setAttribute("data-path", escapeHtml(item.path));
      article.style.setProperty("--i", String(Math.min(start + index, 20)));
      article.innerHTML = `
        <label class="card-checkbox-wrap">
          <input type="checkbox" class="card-checkbox" data-path="${escapeHtml(item.path)}" ${state.selection.paths.has(item.path) ? "checked" : ""}>
          <svg class="icon check-icon"><use href="#icon-check"/></svg>
        </label>
        <div class="card-media">
          <img class="lazy-thumb progressive-img" data-src="${thumbUrl(item.path, 480, item.mtime)}" alt="${escapeHtml(title)}" decoding="async">
          <div class="card-actions">
            <button class="card-action" type="button" data-action="view" title="Agrandir">${icon("expand")}</button>
            <a class="card-action" href="${downloadUrl(item.path)}" download title="Télécharger">${icon("download")}</a>
            <button class="card-action danger" type="button" data-action="delete" title="Supprimer">${icon("trash")}</button>
          </div>
        </div>
        <div class="card-body">
          <div class="card-info">
            <div class="card-name" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
            <div class="card-meta" title="${escapeHtml(item.name)}">${escapeHtml(meta)}</div>
          </div>
          ${folderBadge}
        </div>`;
      fragment.appendChild(article);
    });

    const sentinel = $("#virtualSentinel");
    container.insertBefore(fragment, sentinel);
    state.virtual.rendered = end;
    observeLazyImages();
    observeVirtualSentinel();
  }

  function initVirtualScroll() {
    if (!window.IntersectionObserver) {
      renderVirtualBatch(); // fallback: tout d'un coup
      return;
    }
    state.virtual.sentinelObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            renderVirtualBatch();
          }
        }
      },
      { rootMargin: "300px", threshold: 0 }
    );
  }

  function observeVirtualSentinel() {
    const sentinel = $("#virtualSentinel");
    if (sentinel && state.virtual.sentinelObserver) {
      state.virtual.sentinelObserver.observe(sentinel);
    }
  }

  function renderPagination() {
    const total = state.pagination.total;
    const totalPages = state.pagination.totalPages;
    const page = state.pagination.page;

    if (total === 0 || totalPages <= 1) {
      els.paginationBar.hidden = true;
      return;
    }

    els.paginationBar.hidden = false;
    els.paginationPage.textContent = String(page);
    els.paginationTotalPages.textContent = String(totalPages);
    els.paginationPrev.disabled = page <= 1;
    els.paginationNext.disabled = page >= totalPages;
  }

  function updateSelectionBar() {
    const count = state.selection.paths.size;
    if (count > 0) {
      els.selectionBar.hidden = false;
      els.selectionCount.textContent = plural(count, "image", "images");
      els.selectionSelectAll.textContent = count === state.rendered.length ? "Tout désélectionner" : "Tout sélectionner";
    } else {
      els.selectionBar.hidden = true;
    }
    updateMoveBar();
  }

  function updateMoveBar() {
    const count = state.selection.paths.size;
    if (state.inboxMode && count > 0) {
      els.moveBar.hidden = false;
      els.moveCount.textContent = plural(count, "image", "images");
    } else {
      els.moveBar.hidden = true;
    }
  }

  function toggleSelectAll() {
    const allPaths = state.rendered.map((item) => item.path);
    if (state.selection.paths.size === allPaths.length) {
      state.selection.paths.clear();
    } else {
      allPaths.forEach((p) => state.selection.paths.add(p));
    }
    // Mettre à jour les checkboxes visibles
    $$(".card-checkbox").forEach((cb) => {
      cb.checked = state.selection.paths.has(cb.dataset.path);
    });
    updateSelectionBar();
  }

  async function downloadSelection() {
    const paths = Array.from(state.selection.paths);
    if (!paths.length) return;

    const destination = state.selection.mode;
    const folderName = state.selection.folderName.trim() || undefined;

    try {
      const data = await api("/api/download-selection", {
        method: "POST",
        body: { paths, destination, folder_name: folderName },
      });

      if (destination === "folder") {
        showToast(
          `${data.copied} image(s) copiée(s) dans « ${data.subfolder} »`,
          "success",
          5000
        );
        state.selection.paths.clear();
        updateSelectionBar();
      } else {
        // Mode navigateur : lancer les téléchargements un par un
        data.urls.forEach((url, index) => {
          setTimeout(() => {
            const a = document.createElement("a");
            a.href = url;
            a.download = "";
            a.style.display = "none";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          }, index * 200);
        });
        showToast(`${data.count} téléchargement(s) lance(s).`, "info", 4000);
        state.selection.paths.clear();
        updateSelectionBar();
      }
    } catch (error) {
      showToast(error.message, "error", 6000);
    }
  }

  async function deleteSelection() {
    const paths = Array.from(state.selection.paths);
    if (!paths.length) return;

    if (
      !window.confirm(
        `Supprimer définitivement ${paths.length} image(s) ? Cette action est irréversible.`
      )
    ) {
      return;
    }

    try {
      const data = await api("/api/delete-selection", {
        method: "POST",
        body: { paths },
      });

      showToast(
        `${data.deleted} image(s) supprimée(s) (${formatBytes(data.freed)} libérés).`,
        "success",
        5000
      );
      state.selection.paths.clear();
      updateSelectionBar();
      await loadState();
    } catch (error) {
      showToast(error.message, "error", 6000);
    }
  }

  function showEmptyState(title, text, actionLabel, mode) {
    state.emptyMode = mode;
    els.emptyTitle.textContent = title;
    els.emptyText.textContent = text;
    els.emptyAction.innerHTML = `${icon(mode === "filter" ? "x" : mode === "retry" ? "refresh" : "search")}<span>${escapeHtml(actionLabel)}</span>`;
    els.emptyState.hidden = false;
    els.gallery.hidden = true;
  }

  /* ------------------------------------------------------------
     Recherche & suivi de tâche
     ------------------------------------------------------------ */

  function setSearchBusy(busy) {
    els.searchBtn.disabled = busy;
    els.searchBtn.innerHTML = busy
      ? `${icon("sparkles")}<span>Recherche en cours…</span>`
      : `${icon("sparkles")}<span>Rechercher</span><kbd>⏎</kbd>`;
  }

  async function startSearch() {
    const query = els.searchInput.value.trim();
    if (!query) {
      els.searchInput.focus();
      showToast("Décrivez d'abord ce que vous cherchez.", "info");
      return;
    }
    if (state.jobId && (state.jobStatus === "queued" || state.jobStatus === "running")) {
      showToast("Une recherche est déjà en cours.", "info");
      return;
    }

    setSearchBusy(true);
    try {
      const data = await api("/api/search", {
        method: "POST",
        body: {
          query,
          folder: els.searchFolder.value,
          limit: Number(els.searchLimit.value) || 10,
          source: state.selectedSources,
          orientation: els.searchOrientation.value,
        },
      });
      attachJob(data.job);
    } catch (error) {
      setSearchBusy(false);
      showToast(error.message, "error", 5600);
    }
  }

  function attachJob(job) {
    if (!job) return;
    window.clearTimeout(state.jobAutoHide);
    state.jobId = job.id;
    state.jobStatus = job.status;
    state.jobPanelHidden = false;
    state.pollFails = 0;
    els.jobPanel.hidden = false;
    renderJob(job);
    setSearchBusy(job.status === "queued" || job.status === "running");
    els.jobPanel.scrollIntoView({ behavior: "smooth", block: "center" });
    if (job.status === "queued" || job.status === "running") {
      schedulePoll(job.id, 1500);
    }
  }

  function schedulePoll(jobId, delay = 1500) {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = window.setTimeout(() => pollJob(jobId), delay);
  }

  async function pollJob(jobId) {
    if (state.jobId !== jobId) return;
    try {
      const data = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (state.jobId !== jobId) return;
      const job = data.job;
      state.pollFails = 0;
      renderJob(job);
      if (job.status === "done") {
        finishJob(job);
        return;
      }
      if (job.status === "error") {
        failJob(job);
        return;
      }
      if (job.status === "cancelled") {
        finishJob(job);
        return;
      }
      schedulePoll(jobId, 800);
    } catch (error) {
      state.pollFails += 1;
      if (state.pollFails < 4) {
        schedulePoll(jobId, 2000);
      } else {
        failJob({ message: error.message || "Connexion perdue avec le serveur." });
      }
    }
  }

  function renderJob(job) {
    const running = job.status === "queued" || job.status === "running";
    els.jobPanel.classList.toggle("is-done", job.status === "done");
    els.jobPanel.classList.toggle("is-error", job.status === "error");
    if (!state.jobPanelHidden) els.jobPanel.hidden = false;

    let title = "Recherche en cours…";
    if (job.status === "queued") title = "Recherche en attente…";
    if (job.status === "done") title = "Recherche terminée";
    if (job.status === "error") title = "Recherche interrompue";
    if (job.status === "cancelled") title = "Recherche annulée";
    els.jobTitle.textContent = title;
    els.jobMessage.textContent = job.error || job.message || "Initialisation…";

    const progress = job.status === "error" ? 100 : Math.max(2, Number(job.progress) || 0);
    els.jobProgress.style.width = `${progress}%`;

    if (job.status === "done") {
      const count = Number(job.result?.count || 0);
      els.jobCount.textContent = count ? plural(count, "image", "images") : "Terminé";
    } else if (job.total) {
      els.jobCount.textContent = `${Number(job.done || 0)} / ${Number(job.total)}`;
    } else {
      els.jobCount.textContent = running ? `${Math.round(progress)} %` : "";
    }
    els.jobElapsed.textContent = job.elapsed ? formatElapsed(job.elapsed) : "";

    const lines = Array.isArray(job.log) ? job.log.slice(-12) : [];
    els.jobLog.textContent = lines.join("\n");
    els.jobLog.scrollTop = els.jobLog.scrollHeight;
  }

  async function finishJob(job) {
    state.jobStatus = "done";
    state.jobId = null;
    window.clearTimeout(state.pollTimer);
    renderJob(job);
    setSearchBusy(false);

    const target = job.result?.folder || job.folder || "";
    const count = Number(job.result?.count || 0);
    showToast(
      count
        ? `${plural(count, "image téléchargée", "images téléchargées")} dans « ${target} ».`
        : "Recherche terminée.",
      "success",
      6000
    );

    try {
      const data = await api("/api/state");
      if (target) state.currentFolder = target;
      state.filter = "";
      if (els.imageFilter) els.imageFilter.value = "";
      applyState(data);
      els.searchFolder.value = state.currentFolder;
      await loadImages();
      $(".gallery-section")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      showToast(error.message, "error");
    }

    state.jobAutoHide = window.setTimeout(() => {
      els.jobPanel.hidden = true;
    }, 9000);
  }

  function failJob(job) {
    state.jobStatus = "error";
    state.jobId = null;
    window.clearTimeout(state.pollTimer);
    if (job.status === "error") {
      renderJob(job);
    } else {
      renderJob({
        status: "error",
        message: job.message,
        error: job.message,
        progress: 100,
        log: [],
      });
    }
    setSearchBusy(false);
    showToast(job.message || "La recherche a échoué.", "error", 7000);
  }

  /* ------------------------------------------------------------
     Dossiers : création / suppression
     ------------------------------------------------------------ */

  function openFolderDialog(intent = "navigate") {
    state.folderIntent = intent;
    els.folderError.hidden = true;
    els.folderName.value = "";
    els.folderDialog.showModal();
    window.setTimeout(() => els.folderName.focus(), 60);
  }

  async function submitFolder(event) {
    event.preventDefault();
    const name = els.folderName.value.trim();
    if (!name) {
      els.folderError.textContent = "Indiquez un nom de dossier.";
      els.folderError.hidden = false;
      return;
    }
    els.folderError.hidden = true;
    els.folderSubmit.disabled = true;
    els.folderSubmit.textContent = "Création…";
    try {
      const data = await api("/api/folders", { method: "POST", body: { name } });
      els.folderDialog.close();
      showToast(`Le dossier « ${data.folder} » est prêt.`);
      await loadState();
      if (state.folderIntent === "search") {
        els.searchFolder.value = data.folder;
        els.searchInput.focus();
      } else {
        await selectFolder(data.folder, { scroll: true });
      }
    } catch (error) {
      els.folderError.textContent = error.message;
      els.folderError.hidden = false;
    } finally {
      els.folderSubmit.disabled = false;
      els.folderSubmit.textContent = "Créer le dossier";
    }
  }

  async function deleteFolder(name) {
    const folder = state.folders.find((item) => item.name === name);
    const count = Number(folder?.count || 0);
    const detail = count
      ? `Le dossier « ${name} » et ses ${plural(count, "image", "images")} seront définitivement supprimés.`
      : `Le dossier « ${name} » sera définitivement supprimé.`;
    const confirmed = await confirmAction({
      title: "Supprimer ce dossier ?",
      message: detail,
      confirmLabel: "Supprimer le dossier",
    });
    if (!confirmed) return;

    try {
      await api("/api/folders", {
        method: "DELETE",
        body: { path: name, confirm: true },
      });
      showToast(`Le dossier « ${name} » a été supprimé.`);
      if (state.currentFolder === name) state.currentFolder = "";
      closeLightbox();
      await refreshData();
    } catch (error) {
      showToast(error.message, "error", 6000);
    }
  }

  /* ------------------------------------------------------------
     Suppression d'image
     ------------------------------------------------------------ */

  function findImage(path) {
    return state.images.find((item) => item.path === path) || null;
  }

  async function deleteImage(path) {
    const image = findImage(path);
    const label = image ? image.title || image.name : path;
    const confirmed = await confirmAction({
      title: "Supprimer cette image ?",
      message: `« ${label} » sera définitivement supprimée de votre bibliothèque.`,
      confirmLabel: "Supprimer l'image",
    });
    if (!confirmed) return;

    try {
      const data = await api("/api/images", {
        method: "DELETE",
        body: { path, confirm: true },
      });
      closeLightbox();
      showToast(`Image supprimée (${formatBytes(data.freed)} libérés).`);
      await refreshData();
    } catch (error) {
      showToast(error.message, "error", 6000);
    }
  }

  function confirmAction({ title, message, confirmLabel = "Supprimer" }) {
    els.confirmTitle.textContent = title;
    els.confirmMessage.textContent = message;
    els.confirmOk.textContent = confirmLabel;
    els.confirmCancel.focus();
    return new Promise((resolve) => {
      const dialog = els.confirmDialog;
      const onClose = () => {
        dialog.removeEventListener("close", onClose);
        resolve(dialog.returnValue === "confirm");
      };
      dialog.addEventListener("close", onClose);
      dialog.showModal();
    });
  }

  /* ------------------------------------------------------------
     Lightbox
     ------------------------------------------------------------ */

  function openLightbox(path) {
    const index = state.rendered.findIndex((item) => item.path === path);
    if (index < 0) return;
    state.lightboxIndex = index;
    state.lastFocused = document.activeElement;
    els.lightbox.hidden = false;
    document.body.classList.add("lightbox-open");
    renderLightbox();
    els.lightboxClose.focus();
  }

  function renderLightbox() {
    const item = state.rendered[state.lightboxIndex];
    if (!item) {
      closeLightbox();
      return;
    }
    const title = item.title && item.title !== "Sans titre" ? item.title : item.name;
    els.lightboxImage.src = thumbUrl(item.path, 1600, item.mtime);
    els.lightboxImage.alt = title;
    els.lightboxTitle.textContent = title;
    const dimensions = item.width && item.height ? `${item.width} × ${item.height}` : "dimensions inconnues";
    const meta = [
      dimensions,
      formatBytes(item.size),
      item.provider,
      formatDate(item.mtime),
    ].filter(Boolean);
    els.lightboxMeta.textContent = meta.join(" · ");
    els.lightboxPath.textContent = item.path;
    if (item.source_url) {
      els.lightboxSource.href = item.source_url;
      els.lightboxSource.hidden = false;
    } else {
      els.lightboxSource.hidden = true;
      els.lightboxSource.href = "#";
    }
    els.lightboxDownload.href = downloadUrl(item.path);
    els.lightboxDownload.setAttribute("download", item.name);
    els.lightboxDelete.dataset.path = item.path;
    els.lightboxPrev.disabled = state.rendered.length <= 1;
    els.lightboxNext.disabled = state.rendered.length <= 1;
  }

  function stepLightbox(direction) {
    if (!state.rendered.length) return;
    const length = state.rendered.length;
    state.lightboxIndex = (state.lightboxIndex + direction + length) % length;
    renderLightbox();
  }

  function closeLightbox() {
    if (els.lightbox.hidden) return;
    els.lightbox.hidden = true;
    document.body.classList.remove("lightbox-open");
    els.lightboxImage.removeAttribute("src");
    state.lightboxIndex = -1;
    if (state.lastFocused && typeof state.lastFocused.focus === "function") {
      state.lastFocused.focus();
    }
  }

  async function browseFolder() {
    if (!window.showDirectoryPicker) {
      showToast(
        "Le sélecteur de dossier natif n'est pas supporté par ce navigateur. Copiez-collez le chemin manuellement.",
        "info",
        6000
      );
      return;
    }
    try {
      const handle = await window.showDirectoryPicker();
      const path = handle.path;
      els.rootPathInput.value = path;
      els.rootError.hidden = true;
    } catch (error) {
      if (error.name !== "AbortError") {
        showToast("Impossible d'ouvrir le sélecteur de dossier.", "error", 5000);
      }
    }
  }

  /* ------------------------------------------------------------
     Changement de racine
     ------------------------------------------------------------ */

  function openRootDialog() {
    els.rootError.hidden = true;
    els.rootPathInput.value = state.root;
    els.rootDialog.showModal();
    window.setTimeout(() => {
      els.rootPathInput.focus();
      els.rootPathInput.select();
    }, 60);
  }

  async function submitRoot(event) {
    event.preventDefault();
    const path = els.rootPathInput.value.trim();
    if (!path) {
      els.rootError.textContent = "Indiquez un chemin.";
      els.rootError.hidden = false;
      return;
    }
    els.rootError.hidden = true;
    els.rootSubmit.disabled = true;
    els.rootSubmit.textContent = "Application…";
    try {
      const data = await api("/api/root", { method: "POST", body: { path } });
      els.rootDialog.close();
      state.currentFolder = "";
      state.filter = "";
      if (els.imageFilter) els.imageFilter.value = "";
      applyState(data);
      els.searchFolder.value = "";
      await loadImages();
      setSidebar(false);
      showToast("Répertoire de la bibliothèque mis à jour.");
    } catch (error) {
      els.rootError.textContent = error.message;
      els.rootError.hidden = false;
    } finally {
      els.rootSubmit.disabled = false;
      els.rootSubmit.textContent = "Appliquer";
    }
  }

  /* ------------------------------------------------------------
     Événements
     ------------------------------------------------------------ */

  function bindEvents() {
    els.searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      startSearch();
    });

    $$(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        els.searchInput.value = chip.dataset.query || chip.textContent.trim();
        els.searchInput.focus();
        startSearch();
      });
    });

    els.newFolderBtn.addEventListener("click", () => openFolderDialog("navigate"));
    els.newFolderInline.addEventListener("click", () => openFolderDialog("search"));
    els.folderForm.addEventListener("submit", submitFolder);
    els.folderDialog.addEventListener("close", () => {
      els.folderError.hidden = true;
    });

    els.folderList.addEventListener("click", (event) => {
      const deleteButton = event.target.closest(".folder-delete");
      if (deleteButton) {
        event.stopPropagation();
        deleteFolder(deleteButton.dataset.folder);
        return;
      }
      const item = event.target.closest(".folder-item");
      if (item) selectFolder(item.dataset.folder, { scroll: true });
    });

    els.folderList.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const item = event.target.closest(".folder-item");
      if (!item || event.target.closest(".folder-delete")) return;
      event.preventDefault();
      selectFolder(item.dataset.folder, { scroll: true });
    });

    els.navAll.addEventListener("click", () =>
      selectFolder("", { scroll: true })
    );

    els.themeBtn.addEventListener("click", toggleTheme);
    els.menuBtn.addEventListener("click", () => setSidebar(true));
    els.sidebarClose.addEventListener("click", () => setSidebar(false));
    els.sidebarScrim.addEventListener("click", () => setSidebar(false));

    els.changeRootBtn.addEventListener("click", openRootDialog);
    els.rootBrowseBtn.addEventListener("click", browseFolder);
    els.rootForm.addEventListener("submit", submitRoot);
    els.rootDialog.addEventListener("close", () => {
      els.rootError.hidden = true;
    });

    els.imageFilter.addEventListener("input", () => {
      state.filter = els.imageFilter.value;
      window.clearTimeout(state.filterDebounce);
      state.filterDebounce = window.setTimeout(() => {
        renderGallery();
      }, 150);
    });

    els.sortSelect.addEventListener("change", () => {
      state.sort = els.sortSelect.value;
      renderGallery();
    });

    els.refreshBtn.addEventListener("click", async () => {
      els.refreshBtn.classList.add("spinning");
      try {
        await refreshData();
        showToast("Galerie actualisée.", "info", 2200);
      } finally {
        els.refreshBtn.classList.remove("spinning");
      }
    });

    els.pageSizeSelect.addEventListener("change", () => {
      state.pagination.pageSize = Number(els.pageSizeSelect.value) || 50;
      state.pagination.page = 1;
      loadImages();
    });

    els.paginationPrev.addEventListener("click", () => {
      if (state.pagination.page > 1) {
        state.pagination.page -= 1;
        loadImages();
      }
    });

    els.paginationNext.addEventListener("click", () => {
      if (state.pagination.page < state.pagination.totalPages) {
        state.pagination.page += 1;
        loadImages();
      }
    });

    els.clearCacheBtn.addEventListener("click", async () => {
      try {
        const data = await api("/api/cache/clear", { method: "POST" });
        showToast(`Cache vidé : ${formatBytes(data.freed)} libérés (${data.count} fichiers).`);
        await loadState();
      } catch (error) {
        showToast(error.message, "error", 6000);
      }
    });

    els.inboxToggle.addEventListener("change", async () => {
      state.inboxMode = els.inboxToggle.checked;
      try {
        const data = await api("/api/config/inbox", {
          method: "POST",
          body: { inbox_mode: state.inboxMode },
        });
        state.inboxMode = Boolean(data.inbox_mode);
        els.inboxToggle.checked = state.inboxMode;
        showToast(
          state.inboxMode
            ? "Mode Inbox active : les recherches iront dans le dossier inbox/"
            : "Mode Inbox desactive : les recherches iront directement dans les dossiers",
          "info",
          4000
        );
      } catch (error) {
        showToast(error.message, "error", 6000);
        els.inboxToggle.checked = !state.inboxMode;
        state.inboxMode = els.inboxToggle.checked;
      }
    });

    els.unsplashKeyToggle.addEventListener("click", () => {
      const expanded = els.unsplashKeyToggle.getAttribute("aria-expanded") === "true";
      const body = els.unsplashKeyField.querySelector(".field-body");
      els.unsplashKeyToggle.setAttribute("aria-expanded", String(!expanded));
      body.hidden = expanded;
    });

    els.unsplashKeySave.addEventListener("click", async () => {
      const key = (els.unsplashKey.value || "").trim();
      try {
        const data = await api("/api/config/unsplash", {
          method: "POST",
          body: { unsplash_access_key: key },
        });
        state.unsplashKeyConfigured = Boolean(data.configured);
        const body = els.unsplashKeyField.querySelector(".field-body");
        body.hidden = true;
        els.unsplashKeyToggle.setAttribute("aria-expanded", "false");
        if (els.unsplashKeyBadge) {
          els.unsplashKeyBadge.textContent = state.unsplashKeyConfigured
            ? "Configuree"
            : "";
        }
        if (els.unsplashKeyStatus) {
          els.unsplashKeyStatus.textContent = state.unsplashKeyConfigured
            ? "Cle Unsplash enregistree"
            : "Cle Unsplash supprimee";
        }
        showToast(
          state.unsplashKeyConfigured
            ? "Cle Unsplash enregistree (source Unsplash disponible)"
            : "Cle Unsplash supprimee",
          "info",
          4000
        );
      } catch (error) {
        showToast(error.message, "error", 6000);
      }
    });

    function updateSourceUI() {
      const all = state.selectedSources.includes("all");
      const individual = state.selectedSources.filter((s) => s !== "all");
      const count = all ? 6 : individual.length;

      els.sourceCheckboxes.forEach((cb) => {
        if (cb.value === "all") cb.checked = all;
        else cb.checked = individual.includes(cb.value);
      });

      els.sourceBadge.textContent = String(count);
      els.sourceTriggerText.textContent = all ? "Toutes" : individual.join(", ") || "Aucune";
    }

    els.searchSource.addEventListener("click", () => {
      const expanded = els.searchSource.getAttribute("aria-expanded") === "true";
      els.searchSource.setAttribute("aria-expanded", String(!expanded));
      els.sourceList.hidden = expanded;
    });

    document.addEventListener("click", (event) => {
      if (!els.sourceMulti.contains(event.target)) {
        els.searchSource.setAttribute("aria-expanded", "false");
        els.sourceList.hidden = true;
      }
    });

    els.sourceCheckboxes.forEach((cb) => {
      cb.addEventListener("change", () => {
        if (cb.value === "all") {
          if (cb.checked) {
            state.selectedSources = ["all", "yandex", "commons", "ddg", "openverse", "unsplash"];
          } else {
            state.selectedSources = state.selectedSources.filter((s) => s !== "all");
          }
        } else {
          if (cb.checked) {
            if (!state.selectedSources.includes(cb.value)) {
              state.selectedSources.push(cb.value);
            }
            if (state.selectedSources.filter((s) => s !== "all").length === 5) {
              state.selectedSources = ["all", "yandex", "commons", "ddg", "openverse", "unsplash"];
            }
          } else {
            state.selectedSources = state.selectedSources.filter((s) => s !== cb.value);
            state.selectedSources = state.selectedSources.filter((s) => s !== "all");
          }
        }
        updateSourceUI();
      });
    });

    els.selectionSelectAll.addEventListener("click", toggleSelectAll);

    els.selectionDownload.addEventListener("click", downloadSelection);

    els.selectionDelete.addEventListener("click", deleteSelection);

    els.selectionDestination.addEventListener("change", () => {
      state.selection.mode = els.selectionDestination.value;
      const folderInput = els.selectionFolderName;
      if (state.selection.mode === "folder") {
        folderInput.disabled = false;
      } else {
        folderInput.disabled = true;
      }
    });

    els.selectionFolderName.addEventListener("input", () => {
      state.selection.folderName = els.selectionFolderName.value;
    });

    els.moveDownload.addEventListener("click", async () => {
      const paths = Array.from(state.selection.paths);
      if (!paths.length) return;
      const folderName = els.moveFolderName.value.trim();
      if (!folderName) {
        showToast("indiquez un nom de dossier de destination", "error", 4000);
        return;
      }
      try {
        const data = await api("/api/move-selection", {
          method: "POST",
          body: { paths, folder_name: folderName },
        });
        showToast(
          `${data.moved} image(s) deplacee(s) vers « ${data.folder} »`,
          "success",
          5000
        );
        state.selection.paths.clear();
        updateSelectionBar();
        updateMoveBar();
        await loadState();
      } catch (error) {
        showToast(error.message, "error", 6000);
      }
    });

    els.emptyAction.addEventListener("click", () => {
      if (state.emptyMode === "filter") {
        els.imageFilter.value = "";
        state.filter = "";
        renderGallery();
        els.imageFilter.focus();
      } else if (state.emptyMode === "retry") {
        loadImages();
      } else {
        els.searchInput.focus();
        els.searchInput.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });

    els.gallery.addEventListener("click", (event) => {
      const checkbox = event.target.closest(".card-checkbox");
      if (checkbox) {
        event.stopPropagation();
        const path = checkbox.dataset.path;
        if (state.selection.paths.has(path)) {
          state.selection.paths.delete(path);
        } else {
          state.selection.paths.add(path);
        }
        checkbox.checked = state.selection.paths.has(path);
        updateSelectionBar();
        return;
      }
      if (event.target.closest("a.card-action")) return;
      const card = event.target.closest(".card");
      if (!card) return;
      const deleteButton = event.target.closest('[data-action="delete"]');
      if (deleteButton) {
        deleteImage(card.dataset.path);
        return;
      }
      if (event.target.closest(".card-media") || event.target.closest('[data-action="view"]')) {
        openLightbox(card.dataset.path);
      }
    });

    els.lightboxClose.addEventListener("click", closeLightbox);
    els.lightboxPrev.addEventListener("click", () => stepLightbox(-1));
    els.lightboxNext.addEventListener("click", () => stepLightbox(1));
    els.lightboxDelete.addEventListener("click", () => {
      const path = els.lightboxDelete.dataset.path;
      if (path) deleteImage(path);
    });
    $$("[data-close-lightbox]").forEach((element) =>
      element.addEventListener("click", closeLightbox)
    );

    els.jobClose.addEventListener("click", () => {
      state.jobPanelHidden = true;
      els.jobPanel.hidden = true;
    });

    els.jobCancel.addEventListener("click", async () => {
      if (!state.jobId) return;
      try {
        window.clearTimeout(state.pollTimer);
        await api(`/api/jobs/${encodeURIComponent(state.jobId)}/cancel`, {
          method: "POST",
        });
        state.jobId = null;
        state.jobStatus = null;
        state.jobPanelHidden = true;
        els.jobPanel.hidden = true;
        els.searchBtn.disabled = false;
        els.searchBtn.innerHTML = `<svg class="icon"><use href="#icon-sparkles"/></svg><span>Rechercher</span>`;
        showToast("Recherche annulee", "info", 3000);
      } catch (error) {
        showToast(error.message, "error", 6000);
      }
    });

    document.addEventListener("click", (event) => {
      const closeButton = event.target.closest("[data-close-dialog]");
      if (closeButton) {
        const dialog = document.getElementById(closeButton.dataset.closeDialog);
        if (dialog) dialog.close();
      }
    });

    $$("dialog").forEach((dialog) => {
      dialog.addEventListener("click", (event) => {
        if (event.target === dialog) dialog.close("cancel");
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!els.lightbox.hidden) {
          closeLightbox();
          return;
        }
        if (document.body.classList.contains("sidebar-open")) {
          setSidebar(false);
          return;
        }
      }

      if (!els.lightbox.hidden) {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          stepLightbox(-1);
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          stepLightbox(1);
        }
        return;
      }

      const target = event.target;
      const typing =
        target instanceof HTMLElement &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);
      if (
        !typing &&
        (event.key === "/" || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k")) &&
        !document.querySelector("dialog[open]")
      ) {
        event.preventDefault();
        els.searchInput.focus();
        els.searchInput.select();
      }
    });

    window.addEventListener("resize", () => {
      if (window.innerWidth > 960) setSidebar(false);
    });
  }

  /* ------------------------------------------------------------
     Lazy loading des miniatures
     ------------------------------------------------------------ */

  let lazyObserver = null;

  function initLazyLoading() {
    if (!window.IntersectionObserver) return;
    lazyObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const img = entry.target;
          if (img.dataset.src) {
            img.src = img.dataset.src;
            img.removeAttribute("data-src");
            lazyObserver.unobserve(img);
            img.addEventListener(
              "load",
              () => img.classList.add("loaded"),
              { once: true }
            );
            img.addEventListener(
              "error",
              () => img.classList.add("loaded"),
              { once: true }
            );
          }
        }
      },
      { rootMargin: "200px", threshold: 0 }
    );
  }

  function observeLazyImages() {
    if (!lazyObserver) return;
    $$(".lazy-thumb").forEach((img) => {
      if (!img.src || img.src.includes("data:")) {
        lazyObserver.observe(img);
      }
    });
    $$(".progressive-img").forEach((img) => {
      if (img.complete && img.src && !img.src.includes("data:")) {
        img.classList.add("loaded");
      } else if (!img.classList.contains("loaded")) {
        img.addEventListener(
          "load",
          () => img.classList.add("loaded"),
          { once: true }
        );
        img.addEventListener(
          "error",
          () => img.classList.add("loaded"),
          { once: true }
        );
      }
    });
  }

  /* ------------------------------------------------------------
     Démarrage
     ------------------------------------------------------------ */

  async function init() {
    cacheElements();
    initTheme();
    bindEvents();
    initLazyLoading();
    initVirtualScroll();

    try {
      const data = await loadState();
      const saved = (() => {
        try {
          return localStorage.getItem(FOLDER_KEY) || "";
        } catch {
          return "";
        }
      })();
      const initialFolder = data.folders.some((folder) => folder.name === saved) ? saved : "";
      state.currentFolder = initialFolder;
      updateActiveFolder();
      els.searchFolder.value = initialFolder;

      if (data.active_job) {
        attachJob(data.active_job);
      }
      await loadImages();
    } catch (error) {
      showGalleryLoading();
      els.galleryLoading.hidden = true;
      renderGallery(error.message || "Impossible de joindre le serveur.");
      showToast(error.message || "Impossible de joindre le serveur.", "error", 7000);
    }
  }

  init();
  updateSourceUI();
})();
