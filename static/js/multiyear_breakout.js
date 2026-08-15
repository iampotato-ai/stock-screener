/**
 * Multiyear Breakout Scanner — Frontend Controller
 *
 * Handles data fetching, client-side sorting, parameter changes,
 * manual re-scan triggers, and badge updates for the Multiyear Breakout tab.
 */

(function () {
    'use strict';

    class MultiyearBreakout {
        constructor() {
            this.data = [];
            this.sortColumn = 'years_below_ath';
            this.sortDirection = 'desc';
            this.isLoading = false;
            this.lastFetchTime = 0;
            this.ttlMs = 5 * 60 * 1000; // 5 minute debounce for automatic tab-switch fetches
        }

        init() {
            this.bindEvents();
            // If the tab is already active on load, fetch immediately
            const activeTab = document.querySelector('.workspace-tab.active');
            if (activeTab && activeTab.dataset.view === 'multiyear-breakout') {
                this.fetchData();
            }
        }

        bindEvents() {
            // Listen for tab click
            document.addEventListener('click', (e) => {
                const btn = e.target.closest('.workspace-tab[data-view="multiyear-breakout"]');
                if (!btn) return;
                if (!this.data.length || (Date.now() - this.lastFetchTime > this.ttlMs)) {
                    this.fetchData();
                }
            });

            // Run scanner button
            const runBtn = document.getElementById('btn-run-myb');
            if (runBtn) {
                runBtn.addEventListener('click', () => this.refreshData());
            }

            // Parameter change listeners (triggers local re-filter or fresh fetch)
            const minBaseSelect = document.getElementById('myb-min-base');
            if (minBaseSelect) {
                minBaseSelect.addEventListener('change', () => this.fetchData());
            }

            const windowDaysSelect = document.getElementById('myb-window-days');
            if (windowDaysSelect) {
                windowDaysSelect.addEventListener('change', () => this.fetchData());
            }
        }

        getParams() {
            const minBaseSelect = document.getElementById('myb-min-base');
            const windowDaysSelect = document.getElementById('myb-window-days');
            return {
                min_base_years: minBaseSelect ? parseInt(minBaseSelect.value, 10) : 5,
                breakout_window_days: windowDaysSelect ? parseInt(windowDaysSelect.value, 10) : 10,
            };
        }

        async fetchData(force = false) {
            if (this.isLoading) return;
            this.setLoading(true);

            const { min_base_years, breakout_window_days } = this.getParams();
            const url = `/api/v1/multiyear-breakout?min_base_years=${min_base_years}&breakout_window_days=${breakout_window_days}${force ? '&force=true' : ''}`;

            try {
                const response = await fetch(url);
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                const result = await response.json();
                this.data = result.data || [];
                this.totalScanned = result.total_scanned || 0;
                this.lastFetchTime = Date.now();
                this.updateLastRun(result.refreshed);
                this.updateBadge(this.data.length);
                this.render();
            } catch (err) {
                console.error('Failed to fetch Multiyear Breakout data:', err);
                this.renderError(err.message);
            } finally {
                this.setLoading(false);
            }
        }

        async refreshData() {
            if (this.isLoading) return;
            this.setLoading(true);

            const { min_base_years, breakout_window_days } = this.getParams();
            try {
                const response = await fetch('/api/v1/multiyear-breakout/refresh', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ min_base_years, breakout_window_days }),
                });
                if (!response.ok) {
                    throw new Error(`HTTP error ${response.status}`);
                }
                const result = await response.json();
                this.data = result.data || [];
                this.totalScanned = result.total_scanned || 0;
                this.lastFetchTime = Date.now();
                this.updateLastRun(result.refreshed);
                this.updateBadge(this.data.length);
                this.render();
            } catch (err) {
                console.error('Failed to refresh Multiyear Breakout scan:', err);
                this.renderError(err.message);
            } finally {
                this.setLoading(false);
            }
        }

        setLoading(loading) {
            this.isLoading = loading;
            const spinner = document.getElementById('myb-scan-spinner');
            const runBtn = document.getElementById('btn-run-myb');
            if (spinner) {
                spinner.classList.toggle('hidden', !loading);
            }
            if (runBtn) {
                runBtn.disabled = loading;
            }
            if (loading && (!this.data || !this.data.length)) {
                const tbody = document.getElementById('myb-tbody');
                if (tbody) {
                    tbody.innerHTML = `
                        <tr>
                            <td colspan="12" style="padding: 2.5rem; text-align: center; color: var(--color-text-muted);">
                                <div style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                                    <span class="btn-spinner" style="display: inline-block;"></span>
                                    <span>Scanning universe for multiyear all-time high breakouts...</span>
                                </div>
                            </td>
                        </tr>
                    `;
                }
            }
        }

        updateLastRun(refreshed) {
            const el = document.getElementById('myb-last-run-timestamp');
            if (!el) return;
            if (!refreshed) {
                el.textContent = '(Last Run: Never)';
                return;
            }
            try {
                const dt = new Date(refreshed);
                el.textContent = `(Last Run: ${dt.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })} ${dt.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })})`;
            } catch {
                el.textContent = `(Last Run: ${refreshed.slice(0, 16)})`;
            }
        }

        updateBadge(count) {
            const badge = document.getElementById('myb-count-badge');
            if (!badge) return;
            if (count > 0) {
                badge.textContent = count;
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }

        sortBy(column) {
            if (this.sortColumn === column) {
                this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortColumn = column;
                this.sortDirection = ['symbol', 'sector', 'prior_ath_date', 'breakout_date'].includes(column) ? 'asc' : 'desc';
            }
            this.render();
        }

        getSortedData() {
            const col = this.sortColumn;
            const dir = this.sortDirection === 'asc' ? 1 : -1;

            return [...this.data].sort((a, b) => {
                let va = a[col];
                let vb = b[col];

                if (va === null || va === undefined) return 1;
                if (vb === null || vb === undefined) return -1;

                if (typeof va === 'string') {
                    return va.localeCompare(vb) * dir;
                }
                return (va - vb) * dir;
            });
        }

        render() {
            const tbody = document.getElementById('myb-tbody');
            const countEl = document.getElementById('myb-results-count');
            if (!tbody) return;

            const sorted = this.getSortedData();

            if (countEl) {
                const scannedText = this.totalScanned ? ` <span style="font-size: 0.8rem; font-weight: 500; color: var(--color-text-muted);">(Scanned ${this.totalScanned.toLocaleString('en-IN')} NSE stocks with ≥₹1,000 Cr market cap)</span>` : '';
                countEl.innerHTML = `Found <span style="color: #10b981; font-weight: 700;">${sorted.length}</span> multiyear breakout setup${sorted.length === 1 ? '' : 's'}${scannedText}`;
            }

            if (!sorted.length) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="12" style="padding: 2.5rem; text-align: center; color: var(--color-text-muted); font-style: italic;">
                            No stocks currently breaking out after ${this.getParams().min_base_years}+ years. Click "Run Scanner" to scan again.
                        </td>
                    </tr>
                `;
                return;
            }

            const html = sorted.map((row) => {
                const symbol = row.symbol || '--';
                const currentPrice = row.current_price != null ? `₹${row.current_price.toLocaleString('en-IN')}` : '--';
                const priorAth = row.prior_ath_price != null ? `₹${row.prior_ath_price.toLocaleString('en-IN')}` : '--';
                const priorAthDate = row.prior_ath_date || '--';
                const breakoutDate = row.breakout_date || '--';
                const years = row.years_below_ath != null ? row.years_below_ath : '--';
                const pctAbove = row.pct_above_ath != null ? `${row.pct_above_ath > 0 ? '+' : ''}${row.pct_above_ath.toFixed(1)}%` : '--';
                const pctColor = (row.pct_above_ath || 0) >= 0 ? '#10b981' : '#ef4444';

                // Volume confirmation badge
                const volBadge = row.volume_confirmed
                    ? `<span class="myb-vol-badge confirmed" title="Breakout volume > 20-day average">✓ High Vol</span>`
                    : `<span class="myb-vol-badge unconfirmed" title="Breakout volume was average">Normal</span>`;

                // Base length badge
                const yearsNum = parseFloat(years) || 0;
                let baseBadgeClass = 'myb-base-normal';
                if (yearsNum >= 10) baseBadgeClass = 'myb-base-extreme';
                else if (yearsNum >= 7) baseBadgeClass = 'myb-base-high';

                const baseBadge = `<span class="myb-base-badge ${baseBadgeClass}">${years} yrs</span>`;

                // Consolidation range
                const baseRange = row.consolidation_range_pct != null ? `${row.consolidation_range_pct.toFixed(1)}%` : '--';

                // Market cap
                const mktCap = row.market_cap_cr != null ? `₹${Math.round(row.market_cap_cr).toLocaleString('en-IN')} Cr` : '--';

                // Sector
                const sector = row.sector && row.sector !== 'N/A' ? row.sector : 'General';

                // RS vs Nifty
                let rsText = '--';
                let rsColor = 'var(--color-text-secondary)';
                if (row.rs_vs_nifty != null) {
                    const rsVal = (row.rs_vs_nifty * 100).toFixed(1);
                    if (row.rs_vs_nifty > 0) {
                        rsText = `+${rsVal}%`;
                        rsColor = '#10b981';
                    } else {
                        rsText = `${rsVal}%`;
                        rsColor = '#ef4444';
                    }
                }

                return `
                    <tr class="myb-table-row">
                        <td style="font-weight: 700; color: var(--color-text-primary); font-family: var(--font-mono);">
                            <span class="myb-symbol-pill" onclick="window.openTradingView && window.openTradingView('${symbol}')" title="Click to view chart">${symbol}</span>
                        </td>
                        <td class="text-right" style="font-weight: 600; font-family: var(--font-mono);">${currentPrice}</td>
                        <td class="text-right" style="font-family: var(--font-mono); color: var(--color-text-secondary);">${priorAth}</td>
                        <td class="text-center" style="font-size: 0.8rem; color: var(--color-text-muted); font-family: var(--font-mono);">${priorAthDate}</td>
                        <td class="text-center" style="font-size: 0.8rem; color: #10b981; font-weight: 600; font-family: var(--font-mono);">${breakoutDate}</td>
                        <td class="text-right">${baseBadge}</td>
                        <td class="text-right" style="font-weight: 700; font-family: var(--font-mono); color: ${pctColor};">${pctAbove}</td>
                        <td class="text-center">${volBadge}</td>
                        <td class="text-right" style="font-family: var(--font-mono); color: var(--color-text-secondary);">${baseRange}</td>
                        <td class="text-right" style="font-size: 0.8rem; font-family: var(--font-mono); color: var(--color-text-muted);">${mktCap}</td>
                        <td style="font-size: 0.8rem; color: var(--color-text-secondary); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${sector}</td>
                        <td class="text-right" style="font-weight: 600; font-family: var(--font-mono); color: ${rsColor};">${rsText}</td>
                    </tr>
                `;
            }).join('');

            tbody.innerHTML = html;
        }

        renderError(msg) {
            const tbody = document.getElementById('myb-tbody');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="12" style="padding: 2rem; text-align: center; color: #ef4444;">
                            ⚠️ Error loading Multiyear Breakout data: ${msg}
                        </td>
                    </tr>
                `;
            }
        }
    }

    // Expose singleton on window
    window.multiyearBreakout = new MultiyearBreakout();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => window.multiyearBreakout.init());
    } else {
        window.multiyearBreakout.init();
    }
})();
