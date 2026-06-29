/**
 * MomentumScan Landing Page Interactive JavaScript
 * Implements smooth terminal updates, tab switches, count-up numbers, and widget draws.
 */

import { LANDING_DATA } from './landing-data.js';

document.addEventListener('DOMContentLoaded', () => {
  // Add loaded class to body for entrance animations
  document.body.classList.add('page-loaded');

  const isReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // -----------------------------------------------------------
  // 1. LIVE MARKET STATUS CLOCK
  // -----------------------------------------------------------
  function getISTTime() {
    const now = new Date();
    const istOffset = 5.5 * 60 * 60 * 1000;
    return new Date(now.getTime() + (now.getTimezoneOffset() * 60 * 1000) + istOffset);
  }

  function updateLiveClock() {
    const clockEl = document.getElementById('header-live-time');
    if (!clockEl) return;

    const ist = getISTTime();
    let hours = ist.getHours();
    const minutes = ist.getMinutes();
    const seconds = ist.getSeconds();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12; // Hour '0' should be '12'
    
    const hStr = hours < 10 ? '0' + hours : hours;
    const mStr = minutes < 10 ? '0' + minutes : minutes;
    const sStr = seconds < 10 ? '0' + seconds : seconds;
    
    // Simulate seconds ago update (e.g. 3s ago)
    const secsAgo = Math.floor(Math.random() * 5) + 1;
    clockEl.textContent = `(Live IST: ${hStr}:${mStr}:${sStr} ${ampm} · Updated ${secsAgo}s ago)`;
  }

  // Update clock every second
  updateLiveClock();
  setInterval(updateLiveClock, 1000);

  // Helper to color-code scan badges
  function getScanTagClass(tagText) {
    if (!tagText) return 'tag-default';
    const text = tagText.toLowerCase();
    if (text.includes('breakout')) return 'tag-breakout';
    if (text.includes('elite')) return 'tag-elite';
    if (text.includes('strong')) return 'tag-strong';
    if (text.includes('leader')) return 'tag-leader';
    if (text.includes('pullback') || text.includes('support')) return 'tag-pullback';
    return 'tag-default';
  }

  // -----------------------------------------------------------
  // 2. HERO TERMINAL DYNAMIC STOCK LIST
  // -----------------------------------------------------------
  const terminalTableBody = document.getElementById('terminal-stocks-body');
  
  function renderTerminalStocks(stocksList) {
    if (!terminalTableBody) return;
    terminalTableBody.innerHTML = '';

    stocksList.forEach(s => {
      const row = document.createElement('tr');
      row.id = `hero-row-${s.ticker}`;
      
      const changeClass = s.change >= 0 ? 'positive' : 'negative';
      const changeSign = s.change >= 0 ? '+' : '';
      
      row.innerHTML = `
        <td class="mono font-bold"><span class="terminal-stock-ticker">${s.ticker}</span><span class="terminal-stock-name">${s.name}</span></td>
        <td class="mono font-semibold">${s.ltp.toFixed(2)}</td>
        <td class="mono"><span class="change-badge ${changeClass}">${changeSign}${s.change.toFixed(2)}%</span></td>
        <td><span class="scan-tag ${getScanTagClass(s.tag)}">${s.tag}</span></td>
        <td>
          <svg class="sparkline-svg" viewBox="0 0 100 30">
            <path class="sparkline-path" d="${s.sparkline}" style="stroke: ${s.change >= 0 ? '#10b981' : '#ef4444'}"></path>
          </svg>
        </td>
      `;
      terminalTableBody.appendChild(row);
    });
  }

  // Initial draw
  if (typeof LANDING_DATA !== 'undefined' && LANDING_DATA.heroStocks) {
    renderTerminalStocks(LANDING_DATA.heroStocks);
  }

  // Periodically update terminal rows to feel "Live"
  let feedIndex = 0;
  function simulateLiveUpdate() {
    if (isReducedMotion || !terminalTableBody || typeof LANDING_DATA === 'undefined') return;

    // Pick a stock to inject from live feed
    const feedStock = LANDING_DATA.liveFeed[feedIndex];
    feedIndex = (feedIndex + 1) % LANDING_DATA.liveFeed.length;

    // Get active table rows
    const rows = terminalTableBody.querySelectorAll('tr');
    if (rows.length === 0) return;

    // Select a random row to replace
    const replaceIndex = Math.floor(Math.random() * rows.length);
    const oldRow = rows[replaceIndex];

    // Fade out row
    oldRow.style.opacity = '0.3';
    oldRow.style.transition = 'all 0.4s ease';

    setTimeout(() => {
      const changeClass = feedStock.change >= 0 ? 'positive' : 'negative';
      const changeSign = feedStock.change >= 0 ? '+' : '';

      // Update contents
      oldRow.innerHTML = `
        <td class="mono font-bold"><span class="terminal-stock-ticker">${feedStock.ticker}</span><span class="terminal-stock-name">${feedStock.name}</span></td>
        <td class="mono font-semibold">${feedStock.ltp.toFixed(2)}</td>
        <td class="mono"><span class="change-badge ${changeClass}" style="animation: update-flash 1s ease;">${changeSign}${feedStock.change.toFixed(2)}%</span></td>
        <td><span class="scan-tag">${feedStock.tag}</span></td>
        <td>
          <svg class="sparkline-svg" viewBox="0 0 100 30">
            <path class="sparkline-path" d="${feedStock.sparkline}" style="stroke: ${feedStock.change >= 0 ? '#10b981' : '#ef4444'}"></path>
          </svg>
        </td>
      `;
      
      // Reset opacity
      oldRow.style.opacity = '1';
      
      // Update terminal log stream text
      const logMsg = document.getElementById('terminal-log-msg');
      if (logMsg) {
        logMsg.textContent = `CRITERIA MET: ${feedStock.ticker} triggered ${feedStock.tag.toUpperCase()}`;
        logMsg.style.animation = 'none';
        // Trigger reflow to restart animation
        void logMsg.offsetWidth;
        logMsg.style.animation = 'fade-in 0.3s ease';
      }
    }, 400);
  }

  // Set interval for simulated feeds
  if (!isReducedMotion) {
    setInterval(simulateLiveUpdate, 5000);
  }

  // -----------------------------------------------------------
  // 3. METRICS COUNT-UP ANIMATION ON SCROLL
  // -----------------------------------------------------------
  function animateNumber(element, start, end, duration, suffix = '') {
    if (isReducedMotion) {
      element.textContent = end + suffix;
      return;
    }

    let startTimestamp = null;
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const currentVal = Math.floor(progress * (end - start) + start);
      element.textContent = currentVal.toLocaleString() + suffix;
      if (progress < 1) {
        window.requestAnimationFrame(step);
      }
    };
    window.requestAnimationFrame(step);
  }

  const metricsSection = document.getElementById('metrics-strip');
  let metricsAnimated = false;

  if (metricsSection && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && !metricsAnimated) {
          metricsAnimated = true;
          const statNumbers = document.querySelectorAll('.metric-number');
          
          if (typeof LANDING_DATA !== 'undefined' && LANDING_DATA.metrics) {
            statNumbers.forEach((el, index) => {
              const data = LANDING_DATA.metrics[index];
              if (data) {
                animateNumber(el, 0, data.value, 1500, data.suffix);
              }
            });
          }
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    observer.observe(metricsSection);
  }

  // -----------------------------------------------------------
  // 4. SCAN GALLERY TAB CONTROLS
  // -----------------------------------------------------------
  const tabContainer = document.getElementById('gallery-tabs-list');
  const tabCapsule = document.getElementById('tab-sliding-capsule');
  const galleryPane = document.getElementById('gallery-pane-window');
  
  function setTabCapsulePosition(activeTabBtn) {
    if (!tabCapsule || !activeTabBtn) return;
    tabCapsule.style.width = `${activeTabBtn.offsetWidth}px`;
    tabCapsule.style.left = `${activeTabBtn.offsetLeft}px`;
  }

  function renderGalleryTable(scanId) {
    const container = document.getElementById('pane-table-body');
    if (!container || typeof LANDING_DATA === 'undefined') return;

    const data = LANDING_DATA.scans[scanId];
    if (!data) return;

    container.innerHTML = '';
    data.forEach(item => {
      const row = document.createElement('tr');
      const changeClass = item.change >= 0 ? 'positive' : 'negative';
      const changeSign = item.change >= 0 ? '+' : '';

      row.innerHTML = `
        <td class="mono font-bold">${item.ticker}</td>
        <td class="mono font-semibold">${item.ltp.toFixed(2)}</td>
        <td class="mono"><span class="change-badge ${changeClass}">${changeSign}${item.change.toFixed(2)}%</span></td>
        <td class="mono">${item.rsi.toFixed(1)}</td>
        <td class="mono">${item.volSurge}</td>
        <td><span class="scan-tag ${getScanTagClass(item.setup)}">${item.setup}</span></td>
        <td class="mono text-muted text-xs">${item.pat}</td>
      `;
      container.appendChild(row);
    });
  }

  if (tabContainer) {
    const tabButtons = tabContainer.querySelectorAll('.gallery-tab-btn');
    
    // Set initial position of the sliding capsule
    const activeTab = tabContainer.querySelector('.gallery-tab-btn.active');
    if (activeTab) {
      setTimeout(() => setTabCapsulePosition(activeTab), 100);
      renderGalleryTable(activeTab.dataset.scan);
    }

    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        tabButtons.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        setTabCapsulePosition(btn);

        const scanId = btn.dataset.scan;
        
        // Animated transition for table content
        const innerContent = document.getElementById('gallery-pane-content');
        if (innerContent) {
          innerContent.classList.add('switching');
          setTimeout(() => {
            renderGalleryTable(scanId);
            innerContent.classList.remove('switching');
          }, 250);
        } else {
          renderGalleryTable(scanId);
        }
      });
    });

    // Handle resizing window to correct sliding capsule position
    window.addEventListener('resize', () => {
      const activeBtn = tabContainer.querySelector('.gallery-tab-btn.active');
      if (activeBtn) {
        setTabCapsulePosition(activeBtn);
      }
    });
  }

  // -----------------------------------------------------------
  // 5. MARKET INTELLIGENCE WIDGETS
  // -----------------------------------------------------------
  const intelSection = document.getElementById('market-intel-bento');
  let intelAnimated = false;

  function renderRegimeDial(score) {
    const circle = document.getElementById('regime-value-circle');
    if (!circle) return;

    // Circumference of Nifty semi-gauge is approximately 220
    const circumference = 220;
    const fraction = score / 100;
    const offset = circumference - (fraction * circumference);
    
    if (isReducedMotion) {
      circle.style.strokeDashoffset = offset;
    } else {
      setTimeout(() => {
        circle.style.strokeDashoffset = offset;
      }, 300);
    }
  }

  function renderBreadthWidgets() {
    if (typeof LANDING_DATA === 'undefined') return;
    const data = LANDING_DATA.intelligence;
    
    // Stacked Bar sizes
    const total = data.breadth.total;
    const advPct = (data.breadth.advances / total) * 100;
    const decPct = (data.breadth.declines / total) * 100;
    const uncPct = (data.breadth.unchanged / total) * 100;

    const advBar = document.getElementById('breadth-seg-adv');
    const decBar = document.getElementById('breadth-seg-dec');
    const uncBar = document.getElementById('breadth-seg-unc');

    if (advBar) advBar.style.width = `${advPct}%`;
    if (decBar) decBar.style.width = `${decPct}%`;
    if (uncBar) uncBar.style.width = `${uncPct}%`;

    // 52W Highs and Lows Column Heights
    const highsBar = document.getElementById('highs-bar-fill');
    const lowsBar = document.getElementById('lows-bar-fill');
    
    // Scale column heights (maximum 80px)
    const maxVal = Math.max(data.highsLows.highs52w, data.highsLows.lows52w);
    const highsHeight = (data.highsLows.highs52w / maxVal) * 80;
    const lowsHeight = (data.highsLows.lows52w / maxVal) * 80;

    if (highsBar) highsBar.style.height = `${highsHeight}px`;
    if (lowsBar) lowsBar.style.height = `${lowsHeight}px`;

    // Sector leaderboard bar width fills
    const sectorFills = document.querySelectorAll('.sector-score-bar-fill');
    sectorFills.forEach((fill, idx) => {
      const sector = data.sectors[idx];
      if (sector) {
        fill.style.width = `${sector.score}%`;
      }
    });
  }

  if (intelSection && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && !intelAnimated) {
          intelAnimated = true;
          if (typeof LANDING_DATA !== 'undefined' && LANDING_DATA.intelligence) {
            renderRegimeDial(LANDING_DATA.intelligence.regime.score);
            renderBreadthWidgets();
          }
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1 });
    observer.observe(intelSection);
  }

  // -----------------------------------------------------------
  // 6. EARLY ACCESS WAITLIST FORM
  // -----------------------------------------------------------
  const waitlistForm = document.getElementById('early-access-form');
  const waitlistSuccess = document.getElementById('early-access-success');
  const waitlistSubmitBtn = document.getElementById('early-access-btn');

  if (waitlistForm) {
    waitlistForm.addEventListener('submit', (e) => {
      e.preventDefault();
      
      const emailInput = document.getElementById('early-access-email');
      const email = emailInput.value.trim();
      
      if (!email) return;

      // Simulate a premium API loading state
      if (waitlistSubmitBtn) {
        waitlistSubmitBtn.disabled = true;
        waitlistSubmitBtn.textContent = 'Submitting...';
      }

      setTimeout(() => {
        // Success state
        waitlistForm.style.display = 'none';
        if (waitlistSuccess) {
          waitlistSuccess.style.display = 'block';
          waitlistSuccess.querySelector('.waitlist-registered-email').textContent = email;
        }
      }, 1200);
    });
  }
});
