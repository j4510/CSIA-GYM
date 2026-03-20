/**
 * pageTour(steps, storageKey)
 * Runs a one-time spotlight tour for a page.
 * steps: [{ selector, title, text }]
 * storageKey: localStorage key — tour won't re-run once dismissed.
 */
function pageTour(steps, storageKey) {
  if (localStorage.getItem(storageKey)) return;

  let step = 0;
  let overlay, spotlight, tooltip;

  function init() {
    overlay = document.createElement('div');
    Object.assign(overlay.style, {
      position: 'fixed', inset: '0', background: 'rgba(0,0,0,0.75)',
      zIndex: '9998', pointerEvents: 'none',
    });

    spotlight = document.createElement('div');
    Object.assign(spotlight.style, {
      position: 'fixed', zIndex: '9999', borderRadius: '6px',
      boxShadow: '0 0 0 9999px rgba(0,0,0,0.75)',
      transition: 'all 0.25s ease', pointerEvents: 'none',
      outline: '3px solid #dc2626',
    });

    tooltip = document.createElement('div');
    Object.assign(tooltip.style, {
      position: 'fixed', zIndex: '10000', background: '#1a1a1a',
      border: '2px solid #dc2626', borderRadius: '8px', padding: '16px 20px',
      width: '300px', color: '#f5f5f5', fontFamily: 'sans-serif',
      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
    });
    tooltip.innerHTML = `
      <div style="font-weight:700;font-size:1rem;margin-bottom:6px;color:#dc2626" id="pt-title"></div>
      <div style="font-size:0.875rem;line-height:1.5;margin-bottom:14px" id="pt-text"></div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:0.75rem;color:#808080" id="pt-counter"></span>
        <div style="display:flex;gap:8px">
          <button id="pt-skip" style="background:transparent;border:1px solid #555;color:#aaa;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem">Skip</button>
          <button id="pt-next" style="background:#dc2626;border:none;color:#fff;padding:5px 14px;border-radius:4px;cursor:pointer;font-weight:600;font-size:0.8rem">Next →</button>
        </div>
      </div>`;

    document.body.append(overlay, spotlight, tooltip);
    tooltip.querySelector('#pt-skip').addEventListener('click', endTour);
    tooltip.querySelector('#pt-next').addEventListener('click', nextStep);
    showStep(0);
  }

  function positionTooltip(r, pad) {
    const tw = 316, th = 170;
    const vw = window.innerWidth, vh = window.innerHeight;

    // Prefer below the element, fall back to above
    let top;
    if (vh - r.bottom - pad >= th) {
      top = r.bottom + pad + 8;
    } else {
      top = r.top - pad - th - 8;
    }
    top = Math.max(8, Math.min(top, vh - th - 8));

    // Align with element's left edge, clamped to viewport
    let left = r.left - pad;
    left = Math.max(8, Math.min(left, vw - tw - 8));

    Object.assign(tooltip.style, { top: top + 'px', left: left + 'px' });
  }

  function showStep(i) {
    const { selector, title, text } = steps[i];
    const el = document.querySelector(selector);

    if (!el) { nextStep(); return; }

    // Skip elements that are not rendered/visible
    const check = el.getBoundingClientRect();
    if (check.width === 0 && check.height === 0) { nextStep(); return; }

    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    setTimeout(() => {
      const r = el.getBoundingClientRect();
      const pad = 8;

      Object.assign(spotlight.style, {
        top:    (r.top  - pad) + 'px',
        left:   (r.left - pad) + 'px',
        width:  (r.width  + pad * 2) + 'px',
        height: (r.height + pad * 2) + 'px',
      });

      tooltip.querySelector('#pt-title').textContent   = title;
      tooltip.querySelector('#pt-text').textContent    = text;
      tooltip.querySelector('#pt-counter').textContent = `${i + 1} / ${steps.length}`;
      tooltip.querySelector('#pt-next').textContent    = i === steps.length - 1 ? 'Finish ✓' : 'Next →';

      positionTooltip(r, pad);
    }, 150);
  }

  function nextStep() {
    step++;
    if (step >= steps.length) { endTour(); return; }
    showStep(step);
  }

  function endTour() {
    [overlay, spotlight, tooltip].forEach(el => el.remove());
    localStorage.setItem(storageKey, '1');
  }

  document.addEventListener('DOMContentLoaded', init);
}
