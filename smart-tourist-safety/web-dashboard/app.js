// Maharashtra Tourist Safety — Control Room Dashboard
// Reads from Firebase Realtime DB paths written by the Android app:
//   Tourists/{id}         → { status, createdAt }
//   LiveLocation/{id}     → { latitude, longitude, time, status, safetyScore, safetyLabel, zoneRiskLevel }
//   SOS/{id}              → { latitude, longitude, time, status }
//   Alerts (list)         → { touristId, type, risk, latitude, longitude, time, zoneName }

const firebaseConfig = {
    apiKey: "AIzaSyDpy5go8R4gzuuXrrInf9lOELHsSoZC_0I",
    authDomain: "tourist-safety-sys.firebaseapp.com",
    databaseURL: "https://tourist-safety-sys-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "tourist-safety-sys",
    storageBucket: "tourist-safety-sys.firebasestorage.app",
    messagingSenderId: "685468662266",
    appId: "1:685468662266:android:0e4db5d028c7f24ef00c43"
};

firebase.initializeApp(firebaseConfig);
const db = firebase.database();

// ── Map setup ────────────────────────────────────────────────────────────────
const map = L.map('map').setView([19.7515, 75.7139], 7); // centred on Maharashtra
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// ── State ────────────────────────────────────────────────────────────────────
const tourists   = {};   // id → { status, name, lat, lng, score, label, time }
const markers    = {};   // id → Leaflet marker
const alerts     = [];   // recent alerts array
let   historyMap = null; // mini-map in modal

// ── Icon factory ─────────────────────────────────────────────────────────────
function markerIcon(status) {
    const colors = { SAFE: '#00C853', CAUTION: '#FF6D00', DANGER: '#D50000', SOS: '#D50000', OFFLINE: '#757575' };
    const color = colors[status] || '#757575';
    return L.divIcon({
        className: '',
        html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #fff;box-shadow:0 0 4px rgba(0,0,0,.5)"></div>`,
        iconSize: [14, 14],
        iconAnchor: [7, 7]
    });
}

// ── Tourists listener ─────────────────────────────────────────────────────────
db.ref('Tourists').on('value', snap => {
    const data = snap.val() || {};
    Object.entries(data).forEach(([id, t]) => {
        if (!tourists[id]) tourists[id] = { id };
        tourists[id].status = t.status || 'OFFLINE';
        tourists[id].name   = t.name   || null;
    });
    renderAll();
    updateConnectionStatus(true);
}, () => updateConnectionStatus(false));

// ── LiveLocation listener ─────────────────────────────────────────────────────
db.ref('LiveLocation').on('value', snap => {
    const data = snap.val() || {};
    Object.entries(data).forEach(([id, loc]) => {
        if (!tourists[id]) tourists[id] = { id };
        Object.assign(tourists[id], {
            lat:   loc.latitude,
            lng:   loc.longitude,
            time:  loc.time,
            status: loc.status || tourists[id].status || 'SAFE',
            score:  loc.safetyScore,
            label:  loc.safetyLabel,
            zone:   loc.zoneRiskLevel
        });
        updateMarker(id);
    });
    renderAll();
});

// ── SOS listener ─────────────────────────────────────────────────────────────
db.ref('SOS').on('value', snap => {
    const data = snap.val() || {};
    const sosList = document.getElementById('sosList');
    sosList.innerHTML = '';

    if (Object.keys(data).length === 0) {
        sosList.innerHTML = '<div class="empty-state">No active SOS</div>';
        return;
    }

    Object.entries(data).forEach(([id, sos]) => {
        if (tourists[id]) tourists[id].status = 'SOS';
        const el = document.createElement('div');
        el.className = 'alert-item sos-item';
        el.innerHTML = `
            <div class="alert-icon">🆘</div>
            <div class="alert-body">
                <strong>${id.slice(0, 8)}…</strong>
                <div class="alert-meta">${formatTime(sos.time)} · ${sos.latitude?.toFixed(4)}, ${sos.longitude?.toFixed(4)}</div>
            </div>
            <button class="btn-resolve" onclick="focusTourist('${id}')">Locate</button>
        `;
        sosList.appendChild(el);
        playAlert();
    });
    renderAll();
});

// ── Alerts listener ───────────────────────────────────────────────────────────
db.ref('Alerts').limitToLast(50).on('value', snap => {
    const data = snap.val() || {};
    const dangerList  = document.getElementById('dangerList');
    const anomalyList = document.getElementById('anomalyList');
    dangerList.innerHTML  = '';
    anomalyList.innerHTML = '';

    const zoneAlerts    = [];
    const anomalyAlerts = [];

    Object.values(data).forEach(a => {
        if (a.type === 'ZONE_ENTRY') zoneAlerts.push(a);
        else anomalyAlerts.push(a);
    });

    if (zoneAlerts.length === 0) dangerList.innerHTML = '<div class="empty-state">No zone alerts</div>';
    zoneAlerts.slice(-10).reverse().forEach(a => {
        const el = document.createElement('div');
        el.className = `alert-item ${a.risk === 'HIGH' || a.risk === 'RESTRICTED' ? 'danger-item' : ''}`;
        el.innerHTML = `
            <div class="alert-icon">🔴</div>
            <div class="alert-body">
                <strong>${a.touristId?.slice(0, 8)}…</strong> entered <em>${a.zoneName || 'zone'}</em>
                <div class="alert-meta">${a.risk} · ${formatTime(a.time)}</div>
            </div>
        `;
        dangerList.appendChild(el);
    });

    if (anomalyAlerts.length === 0) anomalyList.innerHTML = '<div class="empty-state">No anomalies</div>';
    anomalyAlerts.slice(-10).reverse().forEach(a => {
        const el = document.createElement('div');
        el.className = 'alert-item';
        el.innerHTML = `
            <div class="alert-icon">📊</div>
            <div class="alert-body">
                <strong>${a.touristId?.slice(0, 8)}…</strong> — ${a.type}
                <div class="alert-meta">${formatTime(a.time)}</div>
            </div>
        `;
        anomalyList.appendChild(el);
    });
});

// ── Render tourist cards ──────────────────────────────────────────────────────
function renderAll() {
    const container = document.getElementById('touristCards');
    const filtered  = getFiltered();

    updateCounts();

    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state">No tourists match filters</div>';
        return;
    }

    container.innerHTML = '';
    filtered.forEach(t => {
        const card = document.createElement('div');
        const statusLower = (t.status || 'offline').toLowerCase();
        card.className = `tourist-card status-${statusLower}`;
        card.onclick = () => showDetail(t.id);
        const displayName = t.name || t.id.slice(0, 12) + '…';
        card.innerHTML = `
            <div class="card-header">
                <span class="card-name">${displayName}</span>
                <span class="status-badge status-${statusLower}">${t.status || 'OFFLINE'}</span>
            </div>
            <div class="card-meta">
                ${t.lat != null ? `📍 ${t.lat.toFixed(4)}, ${t.lng.toFixed(4)}` : 'No location yet'}
            </div>
            <div class="card-meta">
                ${t.score != null ? `Safety: ${t.score} — ${t.label}` : ''}
                ${t.time  ? `· ${formatTime(t.time)}` : ''}
            </div>
        `;
        container.appendChild(card);
    });

    document.getElementById('touristCount').textContent = filtered.length;
}

function getFiltered() {
    const region    = document.getElementById('filterRegion').value;
    const risk      = document.getElementById('filterRisk').value;
    const alertType = document.getElementById('filterAlertType').value;

    return Object.values(tourists).filter(t => {
        if (risk && t.label && t.label !== risk) return false;
        if (alertType === 'SOS' && t.status !== 'SOS') return false;
        return true;
    });
}

function applyFilters() { renderAll(); }

// ── Map markers ───────────────────────────────────────────────────────────────
function updateMarker(id) {
    const t = tourists[id];
    if (!t || t.lat == null) return;

    const displayName = t.name || id.slice(0, 8);
    const popup = `<b>${displayName}</b><br>Status: ${t.status}<br>Score: ${t.score ?? '—'} ${t.label ?? ''}<br>${formatTime(t.time)}`;

    if (markers[id]) {
        markers[id].setLatLng([t.lat, t.lng]).setIcon(markerIcon(t.status)).setPopupContent(popup);
    } else {
        markers[id] = L.marker([t.lat, t.lng], { icon: markerIcon(t.status) })
            .bindPopup(popup)
            .addTo(map);
        markers[id].on('click', () => showDetail(id));
    }
}

function focusTourist(id) {
    const t = tourists[id];
    if (t?.lat) map.setView([t.lat, t.lng], 14);
}

function resetMapView() { map.setView([19.7515, 75.7139], 7); }

// ── Tourist detail modal ──────────────────────────────────────────────────────
function showDetail(id) {
    const t = tourists[id] || {};
    const displayName = t.name || id;
    document.getElementById('modalTitle').textContent = `Tourist: ${displayName}`;
    document.getElementById('detailBody').innerHTML = `
        <table class="detail-table">
            <tr><td>ID</td><td>${id}</td></tr>
            <tr><td>Name</td><td>${t.name || '—'}</td></tr>
            <tr><td>Status</td><td><span class="status-badge ${(t.status||'').toLowerCase()}">${t.status || '—'}</span></td></tr>
            <tr><td>Safety Score</td><td>${t.score ?? '—'} (${t.label ?? '—'})</td></tr>
            <tr><td>Zone Risk</td><td>${t.zone || '—'}</td></tr>
            <tr><td>Last Location</td><td>${t.lat?.toFixed(5) ?? '—'}, ${t.lng?.toFixed(5) ?? '—'}</td></tr>
            <tr><td>Last Update</td><td>${formatTime(t.time)}</td></tr>
        </table>
    `;
    document.getElementById('detailModal').classList.remove('hidden');

    // Mini history map
    setTimeout(() => {
        if (historyMap) { historyMap.remove(); historyMap = null; }
        if (t.lat) {
            historyMap = L.map('historyMap').setView([t.lat, t.lng], 13);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(historyMap);
            L.marker([t.lat, t.lng], { icon: markerIcon(t.status) }).addTo(historyMap);

            // Load location history
            db.ref(`LocationHistory/${id}`).limitToLast(30).once('value', snap => {
                const pts = Object.values(snap.val() || {}).map(e => [e.latitude, e.longitude]);
                if (pts.length > 1) L.polyline(pts, { color: '#1565C0', weight: 2 }).addTo(historyMap);
            });
        }
    }, 100);
}

function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
    if (id === 'detailModal' && historyMap) { historyMap.remove(); historyMap = null; }
}

// ── Incident creation ─────────────────────────────────────────────────────────
function showCreateIncident() { document.getElementById('incidentModal').classList.remove('hidden'); }

function submitIncident() {
    const touristId = document.getElementById('incTouristId').value.trim();
    const sosId     = document.getElementById('incSosId').value.trim();
    if (!touristId) { alert('Tourist ID is required'); return; }

    db.ref('Incidents').push({
        touristId,
        sosId: sosId || null,
        status: 'OPEN',
        createdAt: Date.now()
    }).then(() => {
        closeModal('incidentModal');
        loadIncidents();
    });
}

function loadIncidents() {
    db.ref('Incidents').orderByChild('status').equalTo('OPEN').limitToLast(20).on('value', snap => {
        const list = document.getElementById('incidentList');
        const data = snap.val() || {};
        list.innerHTML = '';
        if (Object.keys(data).length === 0) {
            list.innerHTML = '<div class="empty-state">No open incidents</div>';
            return;
        }
        Object.entries(data).forEach(([key, inc]) => {
            const el = document.createElement('div');
            el.className = 'alert-item';
            el.innerHTML = `
                <div class="alert-body">
                    <strong>${inc.touristId?.slice(0, 10)}…</strong>
                    <div class="alert-meta">${formatTime(inc.createdAt)}</div>
                </div>
                <button class="btn-resolve" onclick="resolveIncident('${key}')">Resolve</button>
            `;
            list.appendChild(el);
        });
    });
}

function resolveIncident(key) {
    db.ref(`Incidents/${key}`).update({ status: 'RESOLVED', resolvedAt: Date.now() });
}

// ── Counts ────────────────────────────────────────────────────────────────────
function updateCounts() {
    const all = Object.values(tourists);
    document.getElementById('countActive').textContent  = all.filter(t => t.status === 'SAFE').length;
    document.getElementById('countCaution').textContent = all.filter(t => t.status === 'CAUTION').length;
    document.getElementById('countDanger').textContent  = all.filter(t => t.status === 'DANGER').length;
    document.getElementById('countSos').textContent     = all.filter(t => t.status === 'SOS').length;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function formatTime(ms) {
    if (!ms) return '—';
    return new Date(ms).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function updateConnectionStatus(online, label) {
    const el  = document.getElementById('connectionStatus');
    el.innerHTML = online
        ? '<span class="dot online"></span> Live'
        : `<span class="dot offline"></span> ${label || 'Disconnected'}`;
}

function clearAlerts() {
    document.getElementById('dangerList').innerHTML  = '<div class="empty-state">Cleared</div>';
    document.getElementById('anomalyList').innerHTML = '<div class="empty-state">Cleared</div>';
}

let alertPlayed = 0;
function playAlert() {
    const now = Date.now();
    if (now - alertPlayed > 5000) {
        document.getElementById('alertSound').play().catch(() => {});
        alertPlayed = now;
    }
}

// ── REST API polling (fallback + enrichment) ──────────────────────────────
const BACKEND_URL = 'http://localhost:8000'; // change to your backend IP if needed

async function pollRestApi() {
    try {
        const res = await fetch(`${BACKEND_URL}/api/v1/tourists/live`);
        if (!res.ok) return;
        const data = await res.json();

        // Merge REST data into tourists state (REST has name + score from DB)
        (data.tourists || []).forEach(t => {
            if (!tourists[t.touristId]) tourists[t.touristId] = { id: t.touristId };
            Object.assign(tourists[t.touristId], {
                name:   t.name   || tourists[t.touristId].name,
                lat:    t.latitude  || tourists[t.touristId].lat,
                lng:    t.longitude || tourists[t.touristId].lng,
                status: t.status || tourists[t.touristId].status || 'SAFE',
                score:  t.safetyScore,
                label:  t.safetyLabel,
                zone:   t.zoneName,
            });
            updateMarker(t.touristId);
        });

        // Merge REST alerts
        (data.alerts || []).forEach(a => {
            const dangerList  = document.getElementById('dangerList');
            const anomalyList = document.getElementById('anomalyList');
            if (a.type === 'ZONE_ENTRY' && dangerList.querySelector('.empty-state')) {
                dangerList.innerHTML = '';
            }
        });

        if (data.source === 'demo') {
            updateConnectionStatus(false, 'Demo mode');
        } else {
            updateConnectionStatus(true);
        }
        renderAll();
    } catch (e) {
        // Backend unreachable — Firebase direct is still running
    }
}

// Poll REST every 10 seconds
setInterval(pollRestApi, 10_000);
pollRestApi(); // immediate first call

// Init
loadIncidents();
