const config = window.__ADMIN_CONFIG__ || {};

const state = {
  cities: [],
  tours: [],
  selectedCity: null,
  selectedTour: null,
  originalOrder: [],
  map: null,
  markers: [],
  polylines: [],
};

const elements = {
  citySelect: document.getElementById("citySelect"),
  toursInfo: document.getElementById("toursInfo"),
  toursList: document.getElementById("toursList"),
  noToursMessage: document.getElementById("noToursMessage"),
  statusMessage: document.getElementById("statusMessage"),
  attractionList: document.getElementById("attractionList"),
  saveOrderBtn: document.getElementById("saveOrderBtn"),
  resetOrderBtn: document.getElementById("resetOrderBtn"),
  mapStatus: document.getElementById("mapStatus"),
  tourDistance: document.getElementById("tourDistance"),
  tourDuration: document.getElementById("tourDuration"),
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

function setStatus(message, tone = "info") {
  const toneClass = {
    info: "text-emerald-300",
    warning: "text-yellow-300",
    error: "text-red-400",
  }[tone];
  elements.statusMessage.textContent = message;
  elements.statusMessage.className = `${toneClass} text-base`;
}

function formatDistance(meters) {
  if (!meters || meters <= 0) return "—";
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }
  return `${meters} m`;
}

function formatDuration(minutes) {
  if (minutes == null) return "—";
  const hrs = Math.floor(minutes / 60);
  const mins = minutes % 60;
  if (hrs <= 0) return `${mins} min`;
  return `${hrs} h ${mins} min`;
}

function clearMap() {
  state.markers.forEach((marker) => marker.setMap(null));
  state.polylines.forEach((poly) => poly.setMap(null));
  state.markers = [];
  state.polylines = [];
}

function focusMapOn(points) {
  if (!state.map || !points.length) return;
  const bounds = new google.maps.LatLngBounds();
  points.forEach((point) => {
    bounds.extend(point);
  });
  state.map.fitBounds(bounds);
}

function renderMap(tour) {
  if (!state.map) {
    elements.mapStatus.textContent = config.mapsDisabled
      ? "Google Maps JS API non configuré."
      : "Carte en initialisation...";
    return;
  }
  clearMap();

  const pathSegments = tour.walking_paths || [];
  const attractionPoints = (tour.points || []).map((entry, index) => {
    const attr = entry.attraction;
    return {
      position: {
        lat: Number(attr.location.lat),
        lng: Number(attr.location.lng),
      },
      label: String(index + 1),
      title: attr.name,
    };
  });

  attractionPoints.forEach((point) => {
    const marker = new google.maps.Marker({
      ...point,
      map: state.map,
    });
    state.markers.push(marker);
  });

  pathSegments.forEach((segment) => {
    const coords = (segment.path_coordinates || []).map((coord) => ({
      lat: Number(coord.lat),
      lng: Number(coord.lng),
    }));
    if (coords.length < 2) return;
    const polyline = new google.maps.Polyline({
      path: coords,
      strokeColor: "#34d399",
      strokeOpacity: 0.8,
      strokeWeight: 4,
      map: state.map,
    });
    state.polylines.push(polyline);
  });

  const positions = attractionPoints.map((p) => p.position);
  if (positions.length) {
    focusMapOn(positions);
    elements.mapStatus.textContent = `${attractionPoints.length} points affichés`;
  } else {
    elements.mapStatus.textContent = "Pas de points à afficher.";
  }
}

function renderTourList() {
  const tours = state.tours || [];
  elements.toursInfo.textContent = `${tours.length} tour(s)`;
  elements.noToursMessage.classList.toggle("hidden", tours.length > 0);
  elements.toursList.innerHTML = "";
  tours.forEach((tour) => {
    const card = document.createElement("button");
    card.className =
      "bg-slate-900 border border-slate-800 rounded-xl p-4 text-left hover:border-emerald-400 transition";
    card.innerHTML = `
      <p class="text-xs uppercase tracking-widest text-slate-500">${tour.id.slice(0, 8)}</p>
      <h3 class="text-lg font-semibold text-white mt-1">${tour.tour_name}</h3>
      <div class="mt-3 text-sm text-slate-400 flex flex-wrap gap-3">
        <span>${tour.point_count || 0} points</span>
        <span>${formatDistance(tour.total_distance)}</span>
        <span>${formatDuration(tour.estimated_walking_time)}</span>
      </div>
    `;
    card.addEventListener("click", () => selectTour(tour.id));
    elements.toursList.appendChild(card);
  });
}

function renderAttractionList(tour) {
  const points = tour.points || [];
  elements.attractionList.innerHTML = "";
  if (!points.length) {
    elements.attractionList.innerHTML = '<li class="text-slate-500 text-sm">Ce tour ne contient aucun point.</li>';
    elements.saveOrderBtn.disabled = true;
    elements.resetOrderBtn.disabled = true;
    return;
  }

  points.forEach((item, index) => {
    const li = document.createElement("li");
    li.className =
      "flex items-center gap-3 p-3 bg-slate-900/60 border border-slate-800 rounded-xl cursor-grab group";
    li.draggable = true;
    li.dataset.attractionId = item.attraction.id;
    li.innerHTML = `
      <div class="flex-shrink-0 w-8 h-8 rounded-full bg-slate-800 text-center leading-8 text-white font-semibold">${index + 1}</div>
      <div class="flex-1">
        <p class="font-medium text-white">${item.attraction.name}</p>
        <p class="text-xs text-slate-400">${item.attraction.formatted_address || ""}</p>
      </div>
      <button class="text-xs text-red-300 px-3 py-1 border border-red-400/40 rounded-lg opacity-0 group-hover:opacity-100 transition delete-btn">
        Supprimer
      </button>
    `;
    elements.attractionList.appendChild(li);
  });

  attachDragAndDrop();

  elements.saveOrderBtn.disabled = true;
  elements.resetOrderBtn.disabled = false;
}

function attachDragAndDrop() {
  let dragged;

  elements.attractionList.querySelectorAll("li").forEach((item) => {
    item.addEventListener("dragstart", (event) => {
      dragged = event.currentTarget;
      event.dataTransfer.effectAllowed = "move";
      event.currentTarget.classList.add("opacity-50");
    });

    item.addEventListener("dragend", (event) => {
      event.currentTarget.classList.remove("opacity-50");
      dragged = null;
    });

    item.addEventListener("dragover", (event) => {
      event.preventDefault();
    });

    item.addEventListener("drop", (event) => {
      event.preventDefault();
      if (!dragged || dragged === event.currentTarget) return;
      const list = elements.attractionList;
      const items = Array.from(list.children);
      const draggedIndex = items.indexOf(dragged);
      const targetIndex = items.indexOf(event.currentTarget);
      if (draggedIndex < targetIndex) {
        list.insertBefore(dragged, event.currentTarget.nextSibling);
      } else {
        list.insertBefore(dragged, event.currentTarget);
      }
      Array.from(list.children).forEach((child, idx) => {
        const badge = child.querySelector(".flex-shrink-0");
        if (badge) badge.textContent = String(idx + 1);
      });
      elements.saveOrderBtn.disabled = false;
    });

    item.querySelector(".delete-btn").addEventListener("click", () => {
      const attractionId = item.dataset.attractionId;
      const attractionName = item.querySelector("p").textContent;
      if (confirm(`Supprimer définitivement "${attractionName}" ?`)) {
        deleteAttraction(attractionId);
      }
    });
  });
}

function getCurrentOrder() {
  return Array.from(elements.attractionList.querySelectorAll("li")).map(
    (item) => item.dataset.attractionId
  );
}

async function deleteAttraction(attractionId) {
  if (!state.selectedTour) return;
  setStatus("Suppression en cours…", "warning");
  try {
    await fetchJSON(`/admin/api/attractions/${attractionId}`, { method: "DELETE" });
    setStatus("Attraction supprimée et tours recalculés.", "info");
    await selectTour(state.selectedTour.id);
    await loadTours(state.selectedCity);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function saveOrder() {
  if (!state.selectedTour) return;
  const orderedIds = getCurrentOrder();
  setStatus("Recalcul des chemins…", "warning");
  try {
    const payload = await fetchJSON(`/admin/api/tours/${state.selectedTour.id}/reorder`, {
      method: "POST",
      body: JSON.stringify({ ordered_attraction_ids: orderedIds }),
    });
    state.selectedTour = payload.tour;
    state.originalOrder = orderedIds;
    renderAttractionList(state.selectedTour);
    renderMap(state.selectedTour);
    elements.saveOrderBtn.disabled = true;
    setStatus("Nouveau parcours enregistré ✔️", "info");
    elements.tourDistance.textContent = formatDistance(state.selectedTour.total_distance);
    elements.tourDuration.textContent = formatDuration(state.selectedTour.estimated_walking_time);
    const tourIndex = state.tours.findIndex((t) => t.id === state.selectedTour.id);
    if (tourIndex !== -1) {
      state.tours[tourIndex] = {
        ...state.tours[tourIndex],
        total_distance: state.selectedTour.total_distance,
        estimated_walking_time: state.selectedTour.estimated_walking_time,
        point_count: (state.selectedTour.points || []).length,
      };
      renderTourList();
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function selectTour(tourId) {
  if (!tourId) return;
  setStatus("Chargement du tour…", "info");
  try {
    const payload = await fetchJSON(`/admin/api/tours/${tourId}`);
    state.selectedTour = payload.tour;
    state.originalOrder = (payload.tour.points || []).map((p) => p.attraction.id);
    renderAttractionList(payload.tour);
    renderMap(payload.tour);
    elements.tourDistance.textContent = formatDistance(payload.tour.total_distance);
    elements.tourDuration.textContent = formatDuration(payload.tour.estimated_walking_time);
    setStatus(`Tour "${payload.tour.tour_name}" chargé.`, "info");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function loadTours(cityId) {
  if (!cityId) return;
  setStatus("Chargement des tours…", "info");
  try {
    const payload = await fetchJSON(`/admin/api/cities/${cityId}/tours`);
    state.tours = payload.tours || [];
    renderTourList();
    setStatus("Tours chargés.");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function loadCities() {
  setStatus("Chargement des villes…", "info");
  try {
    const payload = await fetchJSON("/admin/api/cities");
    state.cities = payload.cities || [];
    elements.citySelect.innerHTML = '<option value="">Choisir une ville</option>';
    state.cities.forEach((city) => {
      const option = document.createElement("option");
      option.value = city.id;
      option.textContent = `${city.city}, ${city.country}`;
      elements.citySelect.appendChild(option);
    });
    setStatus("Sélectionnez une ville pour commencer.");
  } catch (error) {
    setStatus(error.message, "error");
    elements.citySelect.disabled = true;
  }
}

function resetOrder() {
  if (!state.selectedTour) return;
  const listFragment = document.createDocumentFragment();
  state.originalOrder.forEach((attractionId, index) => {
    const item = elements.attractionList.querySelector(
      `li[data-attraction-id="${attractionId}"]`
    );
    if (item) {
      item.querySelector(".flex-shrink-0").textContent = String(index + 1);
      listFragment.appendChild(item);
    }
  });
  elements.attractionList.innerHTML = "";
  elements.attractionList.appendChild(listFragment);
  elements.saveOrderBtn.disabled = true;
}

function bindEvents() {
  elements.citySelect.addEventListener("change", (event) => {
    const cityId = event.target.value;
    state.selectedCity = cityId;
    state.selectedTour = null;
    elements.attractionList.innerHTML =
      '<li class="text-slate-500 text-sm">Choisissez un tour.</li>';
    clearMap();
    elements.tourDistance.textContent = "—";
    elements.tourDuration.textContent = "—";
    if (cityId) {
      loadTours(cityId);
    } else {
      elements.toursList.innerHTML = "";
      elements.toursInfo.textContent = "—";
      elements.noToursMessage.classList.add("hidden");
    }
  });

  elements.saveOrderBtn.addEventListener("click", saveOrder);
  elements.resetOrderBtn.addEventListener("click", resetOrder);
}

function init() {
  if (!config.supabaseReady) {
    setStatus("Supabase indisponible. Configurez les variables serveur.", "error");
    elements.citySelect.disabled = true;
    return;
  }
  bindEvents();
  loadCities();
  if (config.mapsDisabled) {
    elements.mapStatus.textContent = "Google Maps JS API non configuré.";
  }
}

function handleMapReady() {
  if (config.mapsDisabled) return;
  const mapElement = document.getElementById("map");
  if (!mapElement) return;
  state.map = new google.maps.Map(mapElement, {
    center: { lat: 48.8566, lng: 2.3522 },
    zoom: 12,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: false,
  });
  elements.mapStatus.textContent = "Carte prête.";
  if (state.selectedTour) {
    renderMap(state.selectedTour);
  }
}

function registerMapReadyHandler() {
  if (config.mapsDisabled) return;
  if (window.__adminMapsReady) {
    handleMapReady();
  } else {
    window.__adminOnMapsReady = handleMapReady;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  init();
  registerMapReadyHandler();
});
