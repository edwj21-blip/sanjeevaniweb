/* SANJEEVANI front-end: call flow, real-time popups (AJAX polling), DOB check, web push. */
(function () {
  'use strict';
  const SJ = window.SJ || { i18n: {}, urls: {} };
  const T = SJ.i18n;

  function csrf() {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }
  async function post(url, data, json) {
    const opts = { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf() } };
    if (json) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(data || {}); }
    else { opts.body = new URLSearchParams(data || {}); }
    const r = await fetch(url, opts);
    let body = {};
    try { body = await r.json(); } catch (e) { /* non-JSON */ }
    return { ok: r.ok, status: r.status, body };
  }
  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v; else n.setAttribute(k, v);
    });
    (children || []).forEach(c => n.appendChild(c));
    return n;
  }
  function modal(id) { return bootstrap.Modal.getOrCreateInstance(document.getElementById(id)); }
  window.SJ_post = post;

  /* ───────── 1. Receiver: Call Now → dialer → "Did you connect?" ───────── */
  let callReady = false;       // true once the user has come back from the dialer
  let callShown = false;
  let pendingCall = null;

  function showCallConfirm(info) {
    if (callShown || !info) return;
    callShown = true; pendingCall = info;
    document.getElementById('callConfirmName').textContent = info.name || '';
    modal('callConfirmModal').show();
  }

  document.addEventListener('click', async function (e) {
    const btn = e.target.closest('.js-call-btn');
    if (!btn) return;
    e.preventDefault();
    btn.disabled = true;
    try {
      const res = await post(btn.dataset.url, {});
      if (!res.ok || !res.body.ok) { alert(res.body.error || T.errorGeneric); return; }
      if (res.body.duplicate) { alert(T.requestExists); return; }
      sessionStorage.setItem('sj_dialed', '1');
      callReady = false;
      let wasHidden = false;
      const onVis = () => {
        if (document.visibilityState === 'hidden') wasHidden = true;
        else if (wasHidden) { callReady = true; poll(); document.removeEventListener('visibilitychange', onVis); }
      };
      document.addEventListener('visibilitychange', onVis);
      setTimeout(() => { callReady = true; poll(); }, 8000);   // desktop / no dialer fallback
      window.location.href = res.body.tel;                       // opens the native dialer
    } catch (err) { alert(T.errorGeneric); }
    finally { setTimeout(() => { btn.disabled = false; }, 1500); }
  });

  const callYes = document.getElementById('callYes');
  const callNo = document.getElementById('callNo');
  async function answerCall(connected) {
    if (!pendingCall) return;
    callYes.disabled = callNo.disabled = true;
    try { await post('/api/call-confirm/' + pendingCall.id + '/', { connected: connected ? 'yes' : 'no' }); }
    finally {
      callYes.disabled = callNo.disabled = false;
      modal('callConfirmModal').hide(); callShown = false; pendingCall = null;
      sessionStorage.removeItem('sj_dialed');
    }
  }
  if (callYes) { callYes.addEventListener('click', () => answerCall(true)); callNo.addEventListener('click', () => answerCall(false)); }

  /* ───────── 2. Donor popup ───────── */
  let donorShownId = null;
  function showDonorRequest(r) {
    if (donorShownId === r.id) return;
    donorShownId = r.id;
    document.getElementById('donorUnavailNote').classList.toggle('d-none', r.can_accept);
    document.getElementById('donorAccept').disabled = !r.can_accept;
    modal('donorRequestModal').show();
  }
  async function donorAnswer(action) {
    const id = donorShownId; if (!id) return;
    const a = document.getElementById('donorAccept'), d = document.getElementById('donorDecline');
    a.disabled = d.disabled = true;
    const res = await post('/api/respond/' + id + '/', { action });
    if (!res.ok && res.body.error) alert(res.body.error);
    modal('donorRequestModal').hide();
    donorShownId = null; a.disabled = d.disabled = false;
    poll();
  }
  const dAcc = document.getElementById('donorAccept'), dDec = document.getElementById('donorDecline');
  if (dAcc) { dAcc.addEventListener('click', () => donorAnswer('accept')); dDec.addEventListener('click', () => donorAnswer('decline')); }

  /* ───────── 3. Receiver result popup ───────── */
  let resultShownId = null;
  function row(k, v) { return el('div', { class: 'info-row' }, [el('span', { class: 'k', text: k }), el('strong', { text: v })]); }
  function showReceiverResult(u) {
    if (resultShownId === u.id) return;
    resultShownId = u.id;
    const body = document.getElementById('receiverResultBody');
    body.replaceChildren();
    const ack = () => post('/api/ack/' + u.id + '/', {}).catch(() => {});
    if (u.status === 'donor_confirmed') {
      body.appendChild(el('i', { class: 'bi bi-check-circle-fill fs-1 text-success' }));
      body.appendChild(el('h4', { class: 'mt-2 text-success', text: T.donorConfirmed }));
      body.appendChild(el('p', { text: T.donorConfirmedMsg }));
      const box = el('div', { class: 'text-start mb-3' }, [
        row(u.name, u.blood_group), row(T.locality, u.locality + ', ' + u.district),
        row(T.mobile, u.mobile), row(T.status, T.confirmedStatus)]);
      body.appendChild(box);
      const go = el('a', { class: 'btn btn-sj btn-lg w-100 mb-2', href: u.hospital_url, text: T.selectHospital });
      go.addEventListener('click', e => { e.preventDefault(); ack().finally(() => { window.location.href = u.hospital_url; }); });
      body.appendChild(go);
      const later = el('button', { class: 'btn btn-link text-muted', type: 'button', text: T.ok });
      later.addEventListener('click', () => { ack(); modal('receiverResultModal').hide(); resultShownId = null; });
      body.appendChild(later);
    } else {
      body.appendChild(el('i', { class: 'bi bi-x-circle-fill fs-1 text-danger' }));
      body.appendChild(el('h5', { class: 'mt-2', text: T.donorDeclinedMsg }));
      const ok = el('button', { class: 'btn btn-sj btn-lg w-100 mt-3', type: 'button', text: T.ok });
      ok.addEventListener('click', () => { ack(); modal('receiverResultModal').hide(); });
      body.appendChild(ok);
    }
    modal('receiverResultModal').show();
  }

  /* ───────── polling ───────── */
  let polling = false;
  async function poll() {
    if (!SJ.authenticated || polling || document.visibilityState === 'hidden') return;
    polling = true;
    try {
      const r = await fetch(SJ.urls.poll, { credentials: 'same-origin' });
      if (!r.ok) return;
      const d = await r.json();
      const badge = document.getElementById('notifBadge');
      if (badge) { badge.textContent = d.unread; badge.classList.toggle('d-none', !d.unread); }
      if (d.donor_requests.length) showDonorRequest(d.donor_requests[0]);
      else if (d.receiver_updates.length) showReceiverResult(d.receiver_updates[0]);
      else if (d.call_pending && (callReady || firstPoll)) showCallConfirm(d.call_pending);
    } catch (e) { /* offline – try again next tick */ }
    finally { polling = false; firstPoll = false; }
  }
  let firstPoll = true;
  if (SJ.authenticated) {
    poll();
    setInterval(poll, 5000);
    document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') poll(); });
  }

  /* ───────── DOB: live exact-age check (server re-validates) ───────── */
  const dob = document.getElementById('id_date_of_birth');
  if (dob) {
    const live = document.getElementById('dobLive');
    const calc = (s) => {
      const p = s.split('-'); if (p.length !== 3) return null;
      const b = new Date(+p[0], +p[1] - 1, +p[2]), n = new Date();
      let age = n.getFullYear() - b.getFullYear();
      if (n.getMonth() < b.getMonth() || (n.getMonth() === b.getMonth() && n.getDate() < b.getDate())) age--;
      return age;
    };
    const check = () => {
      if (!dob.value) { if (live) live.textContent = ''; return true; }
      const age = calc(dob.value);
      const bad = age === null || age < 18;
      if (live) { live.className = 'dob-live ' + (bad ? 'bad' : 'ok'); live.textContent = bad ? T.under18 : (T.age || 'Age') + ': ' + age; }
      dob.setCustomValidity(bad ? T.under18 : '');
      return !bad;
    };
    dob.addEventListener('input', check); dob.addEventListener('change', check); check();
    dob.form.addEventListener('submit', e => { if (!check()) { e.preventDefault(); dob.reportValidity(); } });
  }

  /* ───────── Web Push (optional, never forced) ───────── */
  function b64ToUint8(b64) {
    const pad = '='.repeat((4 - b64.length % 4) % 4);
    const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  }
  const pushOn = document.getElementById('pushEnable'), pushOff = document.getElementById('pushDisable');
  const pushMsg = document.getElementById('pushMsg');
  function say(t) { if (pushMsg) pushMsg.textContent = t; }
  if (pushOn) {
    pushOn.addEventListener('click', async () => {
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) return say(T.pushUnsupported);
      try {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') return say(T.pushDenied);
        const reg = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
        await navigator.serviceWorker.ready;
        let sub = await reg.pushManager.getSubscription();
        if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToUint8(pushOn.dataset.key) });
        const res = await post('/push/subscribe/', sub.toJSON(), true);
        say(res.ok ? T.pushOn : T.errorGeneric);
      } catch (err) { say(T.errorGeneric); }
    });
    pushOff.addEventListener('click', async () => {
      try {
        const reg = await navigator.serviceWorker.getRegistration('/');
        const sub = reg && await reg.pushManager.getSubscription();
        if (sub) { await post('/push/unsubscribe/', { endpoint: sub.endpoint }, true); await sub.unsubscribe(); }
        say(T.pushOff);
      } catch (err) { say(T.errorGeneric); }
    });
  }
})();
