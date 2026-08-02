/**
 * India Fear & Greed Index Component (UI/UX Pro Max Edition)
 */
(function() {
  'use strict';

  function getBadgeClass(score) {
    if (score <= 24) return 'fg-label-extreme-fear';
    if (score <= 44) return 'fg-label-fear';
    if (score <= 55) return 'fg-label-neutral';
    if (score <= 75) return 'fg-label-greed';
    return 'fg-label-extreme-greed';
  }

  function getScoreColor(score) {
    if (score <= 24) return '#ef4444';
    if (score <= 44) return '#f97316';
    if (score <= 55) return '#eab308';
    if (score <= 75) return '#84cc16';
    return '#10b981';
  }

  function updateTileUI(data) {
    const score = (data && typeof data.score === 'number') ? data.score : 50;
    const label = (data && data.label) ? data.label : 'Neutral';

    const numEl = document.getElementById('fg-score-num');
    const badgeEl = document.getElementById('fg-label-badge');
    const progressFill = document.getElementById('fg-progress-fill');
    const subText = document.getElementById('fg-sub-text');

    if (numEl) {
      numEl.textContent = score;
      numEl.style.color = getScoreColor(score);
    }

    if (badgeEl) {
      badgeEl.textContent = label;
      badgeEl.className = 'fg-badge ' + getBadgeClass(score);
    }

    if (progressFill) {
      progressFill.style.width = score + '%';
      progressFill.style.backgroundColor = getScoreColor(score);
    }

    if (subText) {
      subText.textContent = `${label} sentiment`;
    }

    // Update sub-indicator details
    const subs = (data && (data.subIndicators || data.sub_indicators)) || {};
    const momentumVal = document.getElementById('fg-detail-momentum');
    const strengthVal = document.getElementById('fg-detail-strength');
    const breadthVal = document.getElementById('fg-detail-breadth');
    const vixVal = document.getElementById('fg-detail-vix');
    const adVal = document.getElementById('fg-detail-ad');

    if (momentumVal) momentumVal.textContent = (subs.momentum !== undefined ? subs.momentum : '--');
    if (strengthVal) strengthVal.textContent = (subs.strength !== undefined ? subs.strength : '--');
    if (breadthVal) breadthVal.textContent = (subs.breadth !== undefined ? subs.breadth : '--');
    if (vixVal) vixVal.textContent = (subs.volatility !== undefined ? subs.volatility : '--');
    if (adVal) adVal.textContent = (subs.adMomentum !== undefined ? subs.adMomentum : (subs.ad_momentum !== undefined ? subs.ad_momentum : '--'));
  }

  async function fetchFearGreedIndex() {
    try {
      const resp = await fetch('/api/v1/fear-greed-index');
      if (!resp.ok) {
        console.warn('Fear & Greed Index API status:', resp.status);
        return;
      }
      const result = await resp.json();
      if (result.success && result.data) {
        updateTileUI(result.data);
      }
    } catch (err) {
      console.warn('Failed to fetch Fear & Greed Index:', err);
    }
  }

  // Initialize component on DOMContentLoaded
  document.addEventListener('DOMContentLoaded', function() {
    fetchFearGreedIndex();
    // Refresh every 5 minutes
    setInterval(fetchFearGreedIndex, 5 * 60 * 1000);
  });

  // Export globally for manual refresh triggers
  window.refreshFearGreedTile = fetchFearGreedIndex;
})();
