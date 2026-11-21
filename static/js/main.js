/* Sanjeevani – Main JavaScript */

// ── CSRF helper ──
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    document.cookie.split(';').forEach(cookie => {
      cookie = cookie.trim();
      if (cookie.startsWith(name + '=')) {
        cookieValue = decodeURIComponent(cookie.slice(name.length + 1));
      }
    });
  }
  return cookieValue;
}
const csrfToken = getCookie('csrftoken');

// ── Auto-dismiss alerts ──
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.sj-alert').forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      if (bsAlert) bsAlert.close();
    }, 6000);
  });
});

// ── Smooth scroll for anchor links ──
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function(e) {
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── Blood group hero cards link to directory ──
document.querySelectorAll('.sj-float-card').forEach(card => {
  card.addEventListener('click', () => {
    const bg = card.textContent.trim();
    window.location.href = `/donors/?blood_group=${encodeURIComponent(bg)}&available_only=on`;
  });
});

// ── Mark notification as read on click ──
document.querySelectorAll('[data-notif-id]').forEach(el => {
  el.addEventListener('click', () => {
    const id = el.dataset.notifId;
    fetch(`/notifications/mark-read/${id}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrfToken }
    });
  });
});

// ── Confirm call button spinner ──
document.querySelectorAll('#confirmCallBtn').forEach(btn => {
  btn.addEventListener('click', function() {
    this.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span> Confirming...`;
    this.disabled = true;
  });
});

// ── Form validation feedback ──
(function() {
  const forms = document.querySelectorAll('form[novalidate]');
  forms.forEach(form => {
    form.addEventListener('submit', function(e) {
      if (!form.checkValidity()) {
        e.preventDefault();
        e.stopPropagation();
      }
      form.classList.add('was-validated');
    });
  });
})();

// ── Hospital location Google Maps validator ──
const mapsInput = document.querySelector('[name="google_maps_link"]');
if (mapsInput) {
  mapsInput.addEventListener('blur', function() {
    const val = this.value.trim();
    const validPrefixes = [
      'https://maps.google.com',
      'https://www.google.com/maps',
      'https://goo.gl/maps',
      'https://maps.app.goo.gl'
    ];
    const isValid = validPrefixes.some(p => val.startsWith(p));
    this.setCustomValidity(isValid || val === '' ? '' : 'Please enter a valid Google Maps link.');
  });
}

// ── Navbar active state on scroll ──
window.addEventListener('scroll', function() {
  const navbar = document.querySelector('.sj-navbar');
  if (navbar) {
    navbar.style.boxShadow = window.scrollY > 20
      ? '0 4px 20px rgba(0,0,0,0.2)'
      : '0 2px 15px rgba(0,0,0,0.15)';
  }
});

// ── Log call interaction ──
function logCall(donorId) {
  fetch(`/contact/${donorId}/`, {
    method: 'GET',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }
  }).catch(() => {});
}

// ── Tooltip init ──
document.addEventListener('DOMContentLoaded', () => {
  const tooltipEls = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  tooltipEls.forEach(el => new bootstrap.Tooltip(el));
});
