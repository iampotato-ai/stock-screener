/* Accessibility helper – adds descriptive tooltips to icon‑only buttons */
document.addEventListener('DOMContentLoaded', () => {
  const btns = document.querySelectorAll('.btn-icon, .btn-primary, .btn-secondary');
  btns.forEach(btn => {
    if (!btn.getAttribute('title') && btn.getAttribute('aria-label')) {
      btn.setAttribute('title', btn.getAttribute('aria-label'));
    }
    // Fallback: infer from class name if possible
    if (!btn.getAttribute('title')) {
      const classList = Array.from(btn.classList);
      const known = classList.find(c => c.startsWith('btn-') && c !== 'btn-icon');
      if (known) {
        const label = known.replace('btn-', '').replace(/-/g, ' ');
        btn.setAttribute('title', label.charAt(0).toUpperCase() + label.slice(1));
      }
    }
  });
});
