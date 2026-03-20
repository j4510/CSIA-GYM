const TOUR_STEPS = [
  {
    selector: 'nav a[href*="challenges"]',
    title: 'Challenges',
    text: 'Browse and solve CTF challenges here to earn points.',
  },
  {
    selector: 'nav a[href*="scoreboard"]',
    title: 'Scoreboard',
    text: 'See how you rank against other players. Earn points to climb the leaderboard and unlock ranks.',
  },
  {
    selector: 'nav a[href*="submit"]',
    title: 'Submit a Challenge',
    text: 'Have a challenge idea? Submit it here for admin review. Approved challenges go live for everyone.',
  },
  {
    selector: 'nav a[href*="community"]',
    title: 'Community',
    text: 'Share writeups, ask questions, and discuss with others. Post with flairs and react to comments.',
  },
  {
    selector: 'nav .relative button',
    title: 'Notifications',
    text: 'Get notified about new challenges, post replies, badge awards, first bloods, and more. Manage preferences in Settings.',
  },
  {
    // User dropdown trigger button (the username ▾ button)
    selector: 'nav .site-nav-links > div:last-child > button',
    title: 'Your Account Menu',
    text: 'Click here to access your Account, Settings, My Submissions, and Logout.',
    openDropdown: true,
  },
  {
    selector: 'nav a[href*="/account"]',
    title: 'Your Account',
    text: 'View your profile, solve stats, rank percentile, and earned badges.',
    insideDropdown: true,
  },
  {
    selector: 'nav a[href*="settings"]',
    title: 'Settings',
    text: 'Update your profile, change your password, set notification preferences, and upload a custom avatar.',
    insideDropdown: true,
  },
  {
    selector: 'nav a[href*="my-submissions"]',
    title: 'My Submissions',
    text: 'Track the status of challenges you have submitted for review — pending, approved, or rejected.',
    insideDropdown: true,
  },
];

(function () {
  let step = 0;
  let overlay, spotlight, tooltip;
  let dropdownOpen = false;

  function getDropdownContainer() {
    // The last .relative div in .site-nav-links is the user dropdown wrapper
    const links = document.querySelector('.site-nav-links');
    if (!links) return null;
    const divs = links.querySelectorAll(':scope > div');
    return divs[divs.length - 1] || null;
  }

  function openUserDropdown() {
    const container = getDropdownContainer();
    if (!container) return;
    // Trigger Alpine's open state by dispatching mouseenter
    container.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
    // Also set x-data open directly if accessible
    const btn = container.querySelector('button');
    if (btn) btn.click();
    dropdownOpen = true;
  }

  function closeUserDropdown() {
    if (!dropdownOpen) return;
    const container = getDropdownContainer();
    if (!container) return;
    container.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true }));
    dropdownOpen = false;
  }

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
      <div style="font-weight:700;font-size:1rem;margin-bottom:6px;color:#dc2626" id="tour-title"></div>
      <div style="font-size:0.875rem;line-height:1.5;margin-bottom:14px" id="tour-text"></div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="font-size:0.75rem;color:#808080" id="tour-counter"></span>
        <div style="display:flex;gap:8px">
          <button id="tour-skip" style="background:transparent;border:1px solid #555;color:#aaa;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem">Skip</button>
          <button id="tour-next" style="background:#dc2626;border:none;color:#fff;padding:5px 14px;border-radius:4px;cursor:pointer;font-weight:600;font-size:0.8rem">Next</button>
        </div>
      </div>`;

    document.body.append(overlay, spotlight, tooltip);

    tooltip.querySelector('#tour-skip').addEventListener('click', endTour);
    tooltip.querySelector('#tour-next').addEventListener('click', nextStep);

    showStep(0);
  }

  function positionTooltip(r, pad) {
    const tw = 316, th = 170;
    const vw = window.innerWidth, vh = window.innerHeight;

    // Prefer below, fall back to above
    let top;
    const spaceBelow = vh - r.bottom - pad;
    if (spaceBelow >= th) {
      top = r.bottom + pad + 8;
    } else {
      top = r.top - pad - th - 8;
    }
    top = Math.max(8, Math.min(top, vh - th - 8));

    // Align left edge with element, but keep fully on screen
    let left = r.left - pad;
    left = Math.max(8, Math.min(left, vw - tw - 8));

    Object.assign(tooltip.style, { top: top + 'px', left: left + 'px' });
  }

  function showStep(i) {
    const s = TOUR_STEPS[i];

    // Open dropdown before measuring items inside it
    if (s.openDropdown) {
      openUserDropdown();
    } else if (!s.insideDropdown) {
      closeUserDropdown();
    }

    const delay = (s.openDropdown || s.insideDropdown) ? 250 : 50;

    setTimeout(() => {
      const el = document.querySelector(s.selector);
      if (!el) { nextStep(); return; }

      // Check if element is actually visible (not hidden by display:none)
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 && rect.height === 0) {
        // Element not visible — skip
        nextStep(); return;
      }

      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

      setTimeout(() => {
        const r = el.getBoundingClientRect();
        const pad = 8;
        Object.assign(spotlight.style, {
          top:    (r.top  - pad) + 'px',
          left:   (r.left - pad) + 'px',
          width:  (r.width  + pad * 2) + 'px',
          height: (r.height + pad * 2) + 'px',
        });

        tooltip.querySelector('#tour-title').textContent   = s.title;
        tooltip.querySelector('#tour-text').textContent    = s.text;
        tooltip.querySelector('#tour-counter').textContent = `${i + 1} / ${TOUR_STEPS.length}`;
        tooltip.querySelector('#tour-next').textContent    = i === TOUR_STEPS.length - 1 ? 'Finish \u2713' : 'Next \u2192';

        positionTooltip(r, pad);
      }, 80);
    }, delay);
  }

  function nextStep() {
    step++;
    if (step >= TOUR_STEPS.length) { endTour(); return; }
    showStep(step);
  }

  function endTour() {
    closeUserDropdown();
    [overlay, spotlight, tooltip].forEach(el => el.remove());
    fetch('/tour-done', { method: 'POST', credentials: 'same-origin' });
  }

  document.addEventListener('DOMContentLoaded', init);
})();
