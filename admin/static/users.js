const config = window.__ADMIN_CONFIG__ || {};

const state = {
  users: [],
  selectedUserId: null,
  userDetails: null,
  loadingUsers: false,
  loadingDetails: false,
};

const elements = {
  usersList: document.getElementById("usersList"),
  usersCount: document.getElementById("usersCount"),
  userSearch: document.getElementById("userSearch"),
  refreshUsers: document.getElementById("refreshUsers"),
  userEmail: document.getElementById("userEmail"),
  userName: document.getElementById("userName"),
  userCredits: document.getElementById("userCredits"),
  userRevenuecat: document.getElementById("userRevenuecat"),
  userCreated: document.getElementById("userCreated"),
  userLastLogin: document.getElementById("userLastLogin"),
  userToursCount: document.getElementById("userToursCount"),
  userId: document.getElementById("userId"),
  toursList: document.getElementById("toursList"),
  toursSummary: document.getElementById("toursSummary"),
};

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    ...options,
  });
  if (response.status === 401) {
    window.location.href = "/admin/login";
    return Promise.reject(new Error("Non authentifié"));
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload?.message || payload?.error || "Erreur inconnue";
    throw new Error(message);
  }
  return payload;
}

function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("fr-FR", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatMinutes(mins) {
  if (mins == null) return "—";
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  if (h <= 0) return `${m} min`;
  return `${h} h ${m} min`;
}

function formatProgress(percent) {
  if (percent == null) return "—";
  const clamped = Math.min(100, Math.max(0, Number(percent)));
  return `${clamped}%`;
}

function summarizeObject(obj) {
  if (!obj || typeof obj !== "object") return "";
  if (obj.message) return String(obj.message);
  const parts = [];
  if (obj.status) parts.push(`Statut: ${obj.status}`);
  if (obj.completed_points != null && obj.total_points != null) {
    parts.push(`${obj.completed_points}/${obj.total_points} points`);
  }
  if (obj.progress_percent != null) parts.push(`Progression: ${obj.progress_percent}%`);
  if (!parts.length) {
    const entries = Object.entries(obj).filter(([_, v]) => typeof v !== "object");
    if (entries.length) {
      parts.push(entries.map(([k, v]) => `${k}: ${v}`).join(" · "));
    }
  }
  return parts.join(" · ");
}

function coercePrimitiveValue(value) {
  const str = String(value ?? "").trim();
  if (!str) return "";
  if (/^(null|none)$/i.test(str)) return null;
  if (/^(true)$/i.test(str)) return true;
  if (/^(false)$/i.test(str)) return false;
  const numeric = Number(str);
  if (!Number.isNaN(numeric)) return numeric;
  return str.replace(/^["']|["']$/g, "");
}

function parseStatusRaw(raw) {
  if (!raw) return {};
  if (typeof raw === "object") return raw;
  if (typeof raw === "string") {
    const trimmed = raw.trim();
    if (!trimmed) return {};
    const candidates = [trimmed];
    const normalizedQuotes = trimmed.replace(/'/g, '"');
    if (normalizedQuotes !== trimmed) candidates.push(normalizedQuotes);
    const pythonish = normalizedQuotes.replace(/\bNone\b/gi, "null").replace(/\bTrue\b/g, "true").replace(/\bFalse\b/g, "false");
    if (pythonish !== normalizedQuotes) candidates.push(pythonish);
    for (const candidate of candidates) {
      try {
        const parsed = JSON.parse(candidate);
        if (parsed && typeof parsed === "object") return parsed;
      } catch (e) {
        // ignore parse errors, fall through
      }
    }
    const kvMatches = pythonish.match(/([a-zA-Z0-9_]+)\s*:\s*([^,{}]+)/g);
    if (kvMatches) {
      const obj = {};
      kvMatches.forEach((pair) => {
        const [keyPart, valuePart = ""] = pair.split(":");
        const key = keyPart.trim().replace(/^["']|["']$/g, "");
        obj[key] = coercePrimitiveValue(valuePart.trim());
      });
      if (Object.keys(obj).length) return obj;
    }
    return {};
  }
  return {};
}

function escapeHtml(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function normalizeMessage(msg) {
  if (msg == null) return "";
  if (typeof msg === "string") {
    const trimmed = msg.trim();
    // Essayer d'extraire un JSON ou pseudo-JSON, même s'il est encapsulé dans un texte
    const directSummary = summarizeObject(parseStatusRaw(trimmed));
    if (directSummary) return directSummary;
    if (trimmed.length < 800) {
      const start = trimmed.indexOf("{");
      const end = trimmed.lastIndexOf("}");
      if (start !== -1 && end > start) {
        const inner = trimmed.slice(start, end + 1);
        const innerSummary = summarizeObject(parseStatusRaw(inner));
        if (innerSummary) return innerSummary;
      }
    }
    return trimmed;
  }
  if (typeof msg === "object") {
    const summary = summarizeObject(msg);
    if (summary) return summary;
    return "";
  }
  return String(msg);
}

function firstDefined(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== "") {
      return value;
    }
  }
  return undefined;
}

function buildStatusSummary(info) {
  if (!info) return "";
  const status = info.status;
  const completed = info.completed;
  const total = info.total;
  const progress = info.progress;
  const lang = info.language;
  const narration = info.narration;
  const msg = info.message;
  const parts = [];
  if (status) parts.push(`Statut: ${status}`);
  if (msg) parts.push(msg);
  if (completed != null && total != null) parts.push(`${completed}/${total} points`);
  if (progress != null) parts.push(`Progression: ${progress}%`);
  if (lang) parts.push(`Langue: ${lang}`);
  if (narration) parts.push(`Narration: ${narration}`);
  return parts.join(" · ");
}

function normalizeStatusInfo(tour) {
  const info = tour.status_info || {};
  const raw = parseStatusRaw(info.raw ?? tour.status_raw);
  const status = firstDefined(info.status, tour.status, raw.status);
  const completed = firstDefined(info.completed_points, raw.completed_points, tour.completed_points);
  const total = firstDefined(info.total_points, raw.total_points, tour.total_points, tour.point_count);
  const progress = firstDefined(info.progress_percent, raw.progress_percent, tour.progress_percent);
  const lang = firstDefined(info.language_code, raw.language_code, tour.language_code);
  const narration = firstDefined(info.narration_type, raw.narration_type, tour.narration_type);
  const message = normalizeMessage(firstDefined(info.message, info.status_message, raw.message, raw.status_message, tour.status_message));
  const requestedAt = firstDefined(info.requested_at, raw.requested_at, tour.requested_at);
  const ownedLanguages = Array.isArray(info.owned_languages)
    ? info.owned_languages
    : Array.isArray(raw.owned_languages)
      ? raw.owned_languages
      : Array.isArray(tour.owned_languages)
        ? tour.owned_languages
        : [];
  const userHasPurchase = firstDefined(info.user_has_purchase, raw.user_has_purchase, tour.user_has_purchase);

  const summary = buildStatusSummary({
    status,
    completed,
    total,
    progress,
    language: lang,
    narration,
    message
  });

  return {
    raw,
    status: status || "unknown",
    completed,
    total,
    progress,
    language: lang,
    narration,
    message,
    requestedAt,
    ownedLanguages,
    userHasPurchase,
    summary
  };
}

function statusStyle(status) {
  const key = (status || "").toLowerCase();
  switch (key) {
    case "ready":
      return { badge: "bg-emerald-500/15 text-emerald-200 border border-emerald-400/40", tone: "text-emerald-300" };
    case "processing":
      return { badge: "bg-yellow-500/15 text-yellow-200 border border-yellow-400/40", tone: "text-yellow-200" };
    case "error":
      return { badge: "bg-red-500/15 text-red-200 border border-red-400/40", tone: "text-red-300" };
    case "not_started":
      return { badge: "bg-orange-500/15 text-orange-200 border border-orange-400/40", tone: "text-orange-200" };
    default:
      return { badge: "bg-slate-800 text-slate-200 border border-slate-700", tone: "text-slate-200" };
  }
}

function setUsersLoading(isLoading) {
  state.loadingUsers = isLoading;
  if (isLoading) {
    elements.usersList.innerHTML = `<p class="text-slate-500 text-sm">Chargement…</p>`;
  }
}

function setDetailsLoading(isLoading) {
  state.loadingDetails = isLoading;
  if (isLoading) {
    elements.toursList.innerHTML = `<p class="text-slate-500 text-sm">Chargement…</p>`;
  }
}

function renderUsersList() {
  const { users, selectedUserId } = state;
  elements.usersCount.textContent = `${users.length} utilisateur(s)`;
  elements.usersList.innerHTML = "";

  if (!users.length) {
    elements.usersList.innerHTML = `<p class="text-slate-500 text-sm">Aucun utilisateur trouvé.</p>`;
    return;
  }

  users.forEach((user) => {
    const btn = document.createElement("button");
    const isActive = user.id === selectedUserId;
    btn.className = [
      "w-full text-left px-3 py-2 rounded-xl border",
      isActive ? "border-emerald-400/70 bg-emerald-500/10" : "border-slate-800 bg-slate-900 hover:border-emerald-400/60",
    ].join(" ");
    const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
    btn.innerHTML = `
      <p class="text-sm font-semibold text-white">${user.email}</p>
      <p class="text-xs text-slate-400">${name || "—"}</p>
      <p class="text-xs text-emerald-300 mt-1">Crédits: ${user.credits ?? 0}</p>
    `;
    btn.addEventListener("click", () => selectUser(user.id));
    elements.usersList.appendChild(btn);
  });
}

function renderUserDetails() {
  const details = state.userDetails;
  if (!details) {
    elements.userEmail.textContent = "Sélectionnez un utilisateur";
    elements.userName.textContent = "—";
    elements.userCredits.textContent = "—";
    elements.userRevenuecat.textContent = "—";
    elements.userCreated.textContent = "—";
    elements.userLastLogin.textContent = "—";
    elements.userToursCount.textContent = "—";
    elements.userId.textContent = "—";
    elements.toursList.innerHTML = `<p class="text-slate-500 text-sm">Sélectionnez un utilisateur pour afficher ses tours.</p>`;
    elements.toursSummary.textContent = "—";
    return;
  }

  const user = details.user || {};
  const tours = details.tours || [];

  elements.userEmail.textContent = user.email || "—";
  const name = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  elements.userName.textContent = name || "—";
  elements.userCredits.textContent = user.credits ?? "0";
  elements.userRevenuecat.textContent = user.revenuecat_user_id || "RevenueCat: —";
  elements.userCreated.textContent = formatDate(user.created_at);
  elements.userLastLogin.textContent = formatDate(user.last_login);
  elements.userToursCount.textContent = tours.length;
  elements.userId.textContent = user.id || "—";
  elements.toursSummary.textContent = `${tours.length} tour(s) actif(s)`;

  if (!tours.length) {
    elements.toursList.innerHTML = `<p class="text-slate-500 text-sm">Aucun tour actif pour cet utilisateur.</p>`;
    return;
  }

  elements.toursList.innerHTML = "";
  tours.forEach((tour) => {
    const card = document.createElement("div");
    const statusInfo = normalizeStatusInfo(tour);
    const statusValue = statusInfo.status || "—";
    const status = statusValue.toLowerCase();
    const { badge } = statusStyle(status);
    card.className = `border border-slate-800 bg-slate-900/60 rounded-xl p-4 space-y-3`;

    const progressValue = statusInfo.progress != null ? Math.round(Number(statusInfo.progress)) : null;
    const progressLabel = statusInfo.progress != null ? formatProgress(statusInfo.progress) : null;
    const hasProgress = status === "processing" && progressValue != null;
    const totalPts = statusInfo.total ?? tour.point_count ?? null;
    const completedPts = statusInfo.completed ?? tour.completed_points ?? 0;
    const totalPtsNumber = totalPts != null ? Number(totalPts) : null;
    const completedPtsNumber = completedPts != null ? Number(completedPts) : 0;
    const pointsProgress = totalPtsNumber ? Math.min(100, Math.round((completedPtsNumber / totalPtsNumber) * 100)) : 0;
    const ownedLangs = statusInfo.ownedLanguages;
    const statusSummary = statusInfo.summary;
    const messageChip = statusInfo.message || statusSummary;
    const userHasPurchase = statusInfo.userHasPurchase;
    const hasStatusDetails = Boolean(
      (statusInfo.completed != null && statusInfo.total != null) ||
      statusInfo.progress != null ||
      statusInfo.language ||
      statusInfo.narration ||
      statusInfo.message
    );

    card.innerHTML = `
      <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <div>
          <div class="flex flex-wrap gap-2 items-center">
            <span class="px-2 py-1 rounded-lg text-[11px] uppercase tracking-wide bg-slate-800 border border-slate-700">${tour.tour_type === "custom" ? "Custom" : "Auto"}</span>
            <span class="px-2 py-1 rounded-lg text-[11px] uppercase tracking-wide bg-slate-800 border border-slate-700">Lang: ${statusInfo.language || "—"}</span>
            <span class="px-2 py-1 rounded-lg text-[11px] uppercase tracking-wide bg-slate-800 border border-slate-700">Narration: ${statusInfo.narration || "standard"}</span>
          </div>
          <h4 class="text-lg font-semibold text-white">${tour.tour_name || "Tour sans nom"}</h4>
          <p class="text-slate-400 text-sm">${tour.city || "Ville inconnue"}${tour.country ? " · " + tour.country : ""}</p>
        </div>
        <div class="text-right">
          <div class="inline-flex items-center gap-2 ${badge} px-3 py-1 rounded-xl text-sm">
            <span class="font-semibold">${statusValue || "—"}</span>
            ${hasProgress && progressLabel ? `<span class="text-xs text-slate-300">${progressLabel}</span>` : ""}
          </div>
        <p class="text-xs text-slate-400 mt-1 max-w-[260px]">${escapeHtml(statusSummary) || ""}</p>
          ${statusInfo.requestedAt ? `<p class="text-[11px] text-slate-500 mt-1">Demande: ${formatDate(statusInfo.requestedAt)}</p>` : ""}
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-sm">
        <div>
          <p class="text-slate-500">Points complétés</p>
          <p class="text-white font-semibold">${completedPts ?? 0} / ${totalPts ?? "?"}</p>
          ${totalPtsNumber ? `<div class="h-1.5 bg-slate-800 rounded-full mt-1 overflow-hidden"><div class="h-full bg-emerald-400" style="width:${pointsProgress}%;"></div></div>` : ""}
        </div>
        <div>
          <p class="text-slate-500">Distance</p>
          <p class="text-white">${tour.total_distance ? `${(tour.total_distance / 1000).toFixed(1)} km` : "—"}</p>
        </div>
        <div>
          <p class="text-slate-500">Durée</p>
          <p class="text-white">${formatMinutes(tour.estimated_walking_time)}</p>
        </div>
        <div>
          <p class="text-slate-500">Achat</p>
          <p class="text-white">${formatDate(tour.purchase_date)}</p>
        </div>
      </div>
      <div class="flex flex-wrap gap-2 mt-3 text-xs text-slate-300">
        <span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Source: ${tour.source || "—"}</span>
        <span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Points: ${totalPts ?? tour.point_count ?? "?"}</span>
        ${progressLabel ? `<span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Progression: ${progressLabel}</span>` : ""}
        ${ownedLangs.length ? `<span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Langues possédées: ${ownedLangs.map((l) => l.language_code).join(", ")}</span>` : ""}
      </div>
      ${hasProgress ? `
        <div class="w-full h-2 bg-slate-800 rounded-full overflow-hidden mt-1">
          <div class="h-full bg-yellow-300" style="width:${Math.min(100, Math.max(3, progressValue))}%;"></div>
        </div>` : ""}
        ${ownedLangs.length || userHasPurchase != null ? `
        <div class="flex flex-wrap gap-2 mt-2 text-[11px] text-slate-200">
          ${userHasPurchase != null ? `<span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Achat existant: ${userHasPurchase ? "oui" : "non"}</span>` : ""}
          ${ownedLangs.map((l) => `<span class="px-2 py-1 rounded-lg bg-slate-800 border border-slate-700">Langue ${l.language_code}${l.purchase_id ? ` (purchase ${String(l.purchase_id).slice(0, 8)}…)` : ""}</span>`).join("")}
        </div>
      ` : ""}
      ${hasStatusDetails ? `
        <div class="mt-2 text-[11px] text-slate-400 space-y-1">
          ${statusInfo.completed != null && statusInfo.total != null ? `<div><span class="px-2 py-1 rounded bg-slate-900 border border-slate-800 inline-block mr-2 mb-1">Points générés: ${completedPtsNumber}/${totalPtsNumber}</span></div>` : ""}
          ${statusInfo.progress != null ? `<div><span class="px-2 py-1 rounded bg-slate-900 border border-slate-800 inline-block mr-2 mb-1">Progression: ${progressLabel}</span></div>` : ""}
          ${statusInfo.language ? `<div><span class="px-2 py-1 rounded bg-slate-900 border border-slate-800 inline-block mr-2 mb-1">Langue: ${statusInfo.language}</span></div>` : ""}
          ${statusInfo.narration ? `<div><span class="px-2 py-1 rounded bg-slate-900 border border-slate-800 inline-block mr-2 mb-1">Narration: ${statusInfo.narration}</span></div>` : ""}
          ${messageChip ? `<div><span class="px-2 py-1 rounded bg-slate-900 border border-slate-800 inline-block mr-2 mb-1">Résumé: ${escapeHtml(messageChip)}</span></div>` : ""}
        </div>
      ` : ""}
    `;
    elements.toursList.appendChild(card);
  });
}

let searchDebounce;
function handleSearchInput() {
  clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    loadUsers(state.userSearchValue || elements.userSearch.value || "");
  }, 300);
}

async function loadUsers(search = "") {
  if (!config.supabaseReady) {
    elements.usersList.innerHTML = `<p class="text-red-300 text-sm">Supabase non configuré.</p>`;
    return;
  }
  setUsersLoading(true);
  try {
    const data = await fetchJSON(`/admin/api/users?search=${encodeURIComponent(search)}`);
    state.users = data.users || [];
    setUsersLoading(false);
    renderUsersList();
    if (state.users.length && !state.selectedUserId) {
      selectUser(state.users[0].id);
    } else if (!state.users.length) {
      state.userDetails = null;
      renderUserDetails();
    }
  } catch (err) {
    setUsersLoading(false);
    elements.usersList.innerHTML = `<p class="text-red-300 text-sm">Erreur: ${err.message}</p>`;
  }
}

async function selectUser(userId) {
  state.selectedUserId = userId;
  renderUsersList();
  setDetailsLoading(true);
  try {
    const data = await fetchJSON(`/admin/api/users/${userId}`);
    state.userDetails = data;
    renderUserDetails();
  } catch (err) {
    elements.toursList.innerHTML = `<p class="text-red-300 text-sm">Erreur: ${err.message}</p>`;
  } finally {
    setDetailsLoading(false);
  }
}

function wireEvents() {
  elements.userSearch.addEventListener("input", handleSearchInput);
  elements.refreshUsers.addEventListener("click", () => loadUsers(elements.userSearch.value || ""));
}

function init() {
  renderUserDetails();
  wireEvents();
  loadUsers();
}

init();
