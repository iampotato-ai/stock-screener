/**
 * Daily Market Brief (Morning Summary Widget) JS Module
 * Fetches and renders pre-market brief synthesized by Gemini 2.5 Flash / Quantitative Fallback.
 */

class DailyMarketBrief {
  constructor() {
    this.container = document.getElementById('market-brief-widget');
    this.activeTab = 'macro';
    this.currentData = null;
  }

  init() {
    if (!this.container) return;
    this.fetchBrief();
    this.bindEvents();
  }

  async fetchBrief(forceRefresh = false) {
    try {
      this.renderLoading();
      const url = forceRefresh ? '/api/v1/market-brief/refresh' : '/api/v1/market-brief';
      const method = forceRefresh ? 'POST' : 'GET';
      
      const res = await fetch(url, { method });
      const json = await res.json();

      if (json.status === 'success' && json.data) {
        this.currentData = json.data;
        this.renderBrief();
      } else {
        this.renderError(json.message || 'Unable to load market brief');
      }
    } catch (err) {
      console.error('Failed to fetch daily market brief:', err);
      this.renderError('Network error loading market brief');
    }
  }

  bindEvents() {
    if (!this.container) return;

    this.container.addEventListener('click', (e) => {
      const refreshBtn = e.target.closest('#brief-refresh-btn');
      if (refreshBtn) {
        e.preventDefault();
        this.fetchBrief(true);
        return;
      }

      const tabBtn = e.target.closest('.brief-nav-tab');
      if (tabBtn) {
        e.preventDefault();
        const tab = tabBtn.dataset.tab;
        if (tab) {
          this.activeTab = tab;
          this.updateActiveTab();
        }
      }
    });
  }

  renderLoading() {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="brief-card glass-panel loading-state" style="padding: 1.25rem; min-height: 140px; display: flex; align-items: center; justify-content: center; gap: 0.75rem;">
        <div class="brief-spinner" style="width: 20px; height: 20px; border: 2px solid rgba(255,255,255,0.1); border-top-color: var(--accent-blue); border-radius: 50%; animation: briefSpin 0.8s linear infinite;"></div>
        <span style="font-size: 0.85rem; color: var(--color-text-muted); font-weight: 500;">Synthesizing Daily Market Brief...</span>
      </div>
    `;
  }

  renderError(msg) {
    if (!this.container) return;
    this.container.innerHTML = `
      <div class="brief-card glass-panel" style="padding: 1rem 1.25rem;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <span style="font-size: 0.85rem; color: #ef4444; font-weight: 600;">Daily Brief Notice: ${msg}</span>
          <button id="brief-refresh-btn" class="btn-icon-soft" title="Try Refresh">Retry</button>
        </div>
      </div>
    `;
  }

  renderBrief() {
    if (!this.container || !this.currentData) return;

    const data = this.currentData;
    const isFallback = data.is_fallback;
    const band = (data.regime_band || 'Neutral').toUpperCase();
    const score = data.regime_score || 50;

    let biasClass = 'badge-neutral';
    if (score >= 65) biasClass = 'badge-success';
    else if (score <= 40) biasClass = 'badge-danger';

    this.container.innerHTML = `
      <div class="brief-card glass-panel">
        <div class="brief-header">
          <div class="brief-header-left">
            <span class="brief-pill-tag"><i data-lucide="sun" style="width: 14px; height: 14px; margin-right: 4px; color: #f59e0b;"></i> DAILY MARKET BRIEF</span>
            <span class="brief-date-badge">${data.brief_date || ''}</span>
            <span class="brief-bias-badge ${biasClass}">${band} REGIME (${score}/100)</span>
            ${isFallback ? '<span class="brief-fallback-badge" title="Generated using quantitative rules engine">QUANT FALLBACK</span>' : ''}
          </div>
          <div class="brief-header-right">
            <button id="brief-refresh-btn" class="brief-refresh-btn" title="Refresh Market Brief">
              <i data-lucide="rotate-cw" style="width: 14px; height: 14px;"></i> Refresh Brief
            </button>
          </div>
        </div>

        <h3 class="brief-headline">${data.headline || ''}</h3>

        <div class="brief-nav-bar">
          <button class="brief-nav-tab ${this.activeTab === 'macro' ? 'active' : ''}" data-tab="macro">
            <i data-lucide="globe" style="width: 14px; height: 14px;"></i> Macro Regime
          </button>
          <button class="brief-nav-tab ${this.activeTab === 'sectors' ? 'active' : ''}" data-tab="sectors">
            <i data-lucide="layers" style="width: 14px; height: 14px;"></i> Sector Drivers (${(data.sector_catalysts || []).length})
          </button>
          <button class="brief-nav-tab ${this.activeTab === 'picks' ? 'active' : ''}" data-tab="picks">
            <i data-lucide="zap" style="width: 14px; height: 14px;"></i> Actionable Movers (${(data.top_actionable_stocks || []).length})
          </button>
        </div>

        <div class="brief-tab-content">
          ${this.renderTabBody()}
        </div>
      </div>
    `;

    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  updateActiveTab() {
    const tabs = this.container.querySelectorAll('.brief-nav-tab');
    tabs.forEach(t => {
      if (t.dataset.tab === this.activeTab) t.classList.add('active');
      else t.classList.remove('active');
    });

    const body = this.container.querySelector('.brief-tab-content');
    if (body) {
      body.innerHTML = this.renderTabBody();
    }
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  }

  renderTabBody() {
    if (!this.currentData) return '';
    const d = this.currentData;

    if (this.activeTab === 'macro') {
      const risks = d.key_risks || [];
      return `
        <div class="brief-macro-pane">
          <p class="brief-macro-text">${d.macro_summary || ''}</p>
          ${risks.length > 0 ? `
            <div class="brief-risks-row">
              <span class="brief-risks-label">Key Risks / Watchouts:</span>
              ${risks.map(r => `<span class="brief-risk-chip"><i data-lucide="alert-triangle" style="width: 12px; height: 12px; color: #f59e0b;"></i> ${r}</span>`).join('')}
            </div>
          ` : ''}
        </div>
      `;
    }

    if (this.activeTab === 'sectors') {
      const sectors = d.sector_catalysts || [];
      if (sectors.length === 0) return '<p class="brief-empty">No major sector catalysts reported today.</p>';
      return `
        <div class="brief-sectors-grid">
          ${sectors.map(s => {
            const b = (s.bias || 'Neutral').toLowerCase();
            const badgeCls = b.includes('bull') ? 'val-up' : b.includes('bear') ? 'val-down' : 'val-neutral';
            return `
              <div class="brief-sector-card">
                <div class="brief-sector-header">
                  <span class="brief-sector-title">${s.sector}</span>
                  <span class="brief-sector-bias ${badgeCls}">${s.bias}</span>
                </div>
                <p class="brief-sector-driver">${s.driver}</p>
              </div>
            `;
          }).join('')}
        </div>
      `;
    }

    if (this.activeTab === 'picks') {
      const picks = d.top_actionable_stocks || [];
      if (picks.length === 0) return '<p class="brief-empty">No active stock setups identified in pre-market brief.</p>';
      return `
        <div class="brief-picks-grid">
          ${picks.map(p => `
            <div class="brief-pick-card" onclick="if(typeof switchWorkspace === 'function') switchWorkspace('screener');">
              <div class="brief-pick-header">
                <span class="brief-pick-symbol">${p.symbol}</span>
                <span class="brief-pick-tag">EP / Catalyst</span>
              </div>
              <p class="brief-pick-reason">${p.reason}</p>
            </div>
          `).join('')}
        </div>
      `;
    }

    return '';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.dailyMarketBrief = new DailyMarketBrief();
  window.dailyMarketBrief.init();
});
