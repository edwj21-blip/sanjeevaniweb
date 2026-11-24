/* Hospital selection inside SANJEEVANI using the Google Maps JavaScript API,
   Places (Place.searchByText / searchNearby) and Geocoding. */
(function () {
  'use strict';
  const app = document.getElementById('hospitalApp');
  if (!app) return;
  const I = window.SJ.i18n, H = JSON.parse(document.getElementById('hospitalI18n').textContent);
  const $ = id => document.getElementById(id);
  const KERALA = { lat: 10.5, lng: 76.3 };
  let map, marker, geocoder, PlaceLib;
  let selected = { name: '', address: '', lat: null, lng: null, place_id: '' };

  function setStatus(msg, kind) {
    const s = $('hospMsg'); s.className = 'alert alert-' + (kind || 'info') + (msg ? '' : ' d-none'); s.textContent = msg || '';
  }
  function render() {
    $('hName').value = selected.name; $('hAddress').value = selected.address;
    $('hLat').value = selected.lat === null ? '' : Number(selected.lat).toFixed(6);
    $('hLng').value = selected.lng === null ? '' : Number(selected.lng).toFixed(6);
    $('confirmBtn').disabled = !(selected.name && selected.address && selected.lat !== null && selected.lng !== null);
  }
  function placeMarker(lat, lng, pan) {
    selected.lat = lat; selected.lng = lng;
    if (map) {
      const pos = { lat, lng };
      if (!marker) {
        marker = new google.maps.Marker({ map, position: pos, draggable: true });
        marker.addListener('dragend', () => { const p = marker.getPosition(); reverse(p.lat(), p.lng()); });
      } else { marker.setPosition(pos); }
      if (pan) { map.panTo(pos); map.setZoom(16); }
    }
    render();
  }
  function reverse(lat, lng) {
    selected.lat = lat; selected.lng = lng; selected.place_id = '';
    if (!geocoder) return render();
    geocoder.geocode({ location: { lat, lng } }, (res, st) => {
      if (st === 'OK' && res[0]) selected.address = res[0].formatted_address;
      render();
    });
  }
  function choose(place, item) {
    document.querySelectorAll('.result-item').forEach(n => n.classList.remove('active'));
    if (item) item.classList.add('active');
    selected.name = place.displayName || ''; selected.address = place.formattedAddress || '';
    selected.place_id = place.id || '';
    placeMarker(place.location.lat(), place.location.lng(), true);
  }
  function showResults(places) {
    const box = $('results'); box.replaceChildren();
    if (!places || !places.length) { setStatus(H.noResults, 'warning'); return; }
    setStatus('');
    const bounds = new google.maps.LatLngBounds();
    places.forEach(p => {
      bounds.extend(p.location);
      new google.maps.Marker({ map, position: p.location, title: p.displayName });
      const d = document.createElement('div'); d.className = 'result-item';
      const a = document.createElement('strong'); a.textContent = p.displayName;
      const b = document.createElement('div'); b.className = 'small text-muted'; b.textContent = p.formattedAddress || '';
      d.append(a, b); d.addEventListener('click', () => choose(p, d)); box.appendChild(d);
    });
    map.fitBounds(bounds);
  }
  const FIELDS = ['displayName', 'formattedAddress', 'location', 'id'];

  async function search() {
    const q = $('hSearch').value.trim(); if (!q) return;
    setStatus(H.searching);
    try {
      const { places } = await PlaceLib.Place.searchByText({
        textQuery: q, fields: FIELDS, includedType: 'hospital', useStrictTypeFiltering: false,
        locationBias: map.getCenter(), maxResultCount: 10, region: 'in' });
      showResults(places);
    } catch (e) { setStatus(H.apiError, 'danger'); }
  }
  function nearby() {
    if (!navigator.geolocation) return setStatus(H.noGeo, 'warning');
    setStatus(H.searching);
    navigator.geolocation.getCurrentPosition(async pos => {
      const c = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      map.setCenter(c); map.setZoom(14);
      try {
        const { places } = await PlaceLib.Place.searchNearby({
          fields: FIELDS, locationRestriction: { center: c, radius: 5000 },
          includedPrimaryTypes: ['hospital'], maxResultCount: 10 });
        showResults(places);
      } catch (e) { setStatus(H.apiError, 'danger'); }
    }, () => setStatus(H.noGeo, 'warning'), { timeout: 10000 });
  }

  async function save() {
    selected.name = $('hName').value.trim(); selected.address = $('hAddress').value.trim();
    const lat = parseFloat($('hLat').value), lng = parseFloat($('hLng').value);
    if (!selected.name || !selected.address || isNaN(lat) || isNaN(lng)) return setStatus(H.incomplete, 'warning');
    $('confirmBtn').disabled = true;
    const res = await window.SJ_post(app.dataset.saveUrl,
      { name: selected.name, address: selected.address, lat, lng, place_id: selected.place_id }, true);
    if (res.ok && res.body.ok) { window.location.href = res.body.redirect; }
    else { setStatus((res.body && res.body.error) || I.errorGeneric, 'danger'); $('confirmBtn').disabled = false; }
  }

  ['hName', 'hAddress'].forEach(id => $(id).addEventListener('input', () => {
    selected.name = $('hName').value; selected.address = $('hAddress').value; render(); }));
  ['hLat', 'hLng'].forEach(id => $(id).addEventListener('change', () => {
    const lat = parseFloat($('hLat').value), lng = parseFloat($('hLng').value);
    if (!isNaN(lat) && !isNaN(lng)) { selected.place_id = ''; placeMarker(lat, lng, true); }
  }));
  $('confirmBtn').addEventListener('click', save);
  $('hSearchBtn').addEventListener('click', search);
  $('hSearch').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); search(); } });
  $('hNearbyBtn').addEventListener('click', nearby);

  // existing selection (Change Location)
  if (app.dataset.name) {
    selected = { name: app.dataset.name, address: app.dataset.address, lat: parseFloat(app.dataset.lat),
                 lng: parseFloat(app.dataset.lng), place_id: app.dataset.placeId || '' };
  }
  render();

  window.gm_authFailure = function () { disableMap(H.authFail); };
  function disableMap(msg) {
    setStatus(msg, 'danger');
    $('map').classList.add('d-none');
    ['hSearch', 'hSearchBtn', 'hNearbyBtn'].forEach(id => { $(id).disabled = true; });
    $('manualNote').classList.remove('d-none');
  }
  if (!app.dataset.hasKey) { disableMap(H.noKey); }

  window.initHospitalMap = async function () {
    try {
      PlaceLib = await google.maps.importLibrary('places');
      await google.maps.importLibrary('geocoding');
      geocoder = new google.maps.Geocoder();
      const start = selected.lat !== null && !isNaN(selected.lat) ? { lat: selected.lat, lng: selected.lng } : KERALA;
      map = new google.maps.Map($('map'), { center: start, zoom: selected.lat !== null && !isNaN(selected.lat) ? 16 : 8,
        mapTypeControl: false, streetViewControl: false });
      map.addListener('click', e => reverse(e.latLng.lat(), e.latLng.lng()) || placeMarker(e.latLng.lat(), e.latLng.lng(), false));
      if (selected.lat !== null && !isNaN(selected.lat)) placeMarker(selected.lat, selected.lng, false);
    } catch (e) { disableMap(H.apiError); }
  };
})();
