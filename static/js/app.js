// App state variables
let previousScanMap = {};
let stocksData = [];
let universeData = [];
let filteredStocks = [];
let marketBreadth = {
  advances: 0, declines: 0, unchanged: 0, total: 0,
  adRatio: 0, adLine: 0,
  pctAboveSMA21: 0, pctAboveSMA50: 0, maBreadthScore: 0,
  pctNear52High: 0, avgRecommend: 0,
  regimeScore: 0, regimeBand: 'Neutral',
  regimeColor: '--accent-amber', regimeEmoji: '⚖️',
  scanStrength: 0, topBreadthSectors: [], weakBreadthSectors: [],
  new52Highs: 0, new52Lows: 0,
  allBreadthSectors: [],
};
const sparklineRegistry = new Map();
let sectors = new Set();
let currentSortField = 'market_cap_basic';
let currentSortOrder = 'desc';
let currentPage = 1;
const itemsPerPage = 50;
let activeIntradayFilter = null;
let activeStatFilter = null;
let activeDrawerChart = null;
let activeOverlayChart = null;
let activeKronosChart = null;
let activeKronosFullChart = null;
let activeKronosBacktestChart = null;
let activeEnsembleSeries = {};
let journalData = [];

// ── Stat card previous-value store ──
const statCardPrev = {
  total: 0,
  elite: 0,
  strong: 0,
  sectorLeader: 0,
  breakoutReady: 0,
};

/**
 * Animates a numeric value counting up/down to a target.
 * @param {HTMLElement} el     — the element whose textContent to update
 * @param {number} from        — starting value (pass previous value for delta animation)
 * @param {number} to          — target value
 * @param {number} duration    — ms, default 600
 * @param {Function} formatter — optional formatter fn, default integer
 */
function animateCount(el, from, to, duration = 600, formatter = Math.round) {
  if (!el) return;

  // Respect prefers-reduced-motion
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    el.textContent = formatter(to);
    return;
  }

  const start = performance.now();
  const delta = to - from;

  function step(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);

    // Ease out cubic — fast start, soft landing
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = formatter(from + delta * eased);

    if (progress < 1) requestAnimationFrame(step);
  }

  requestAnimationFrame(step);
}

/**
 * Call this after stocksData is updated from a scan or refresh.
 * @param {Object[]} stocks — the new stocksData array
 */
function updateStatCards(stocks) {
  if (!stocks) return;
  const counts = {
    total:        stocks.length,
    elite:        stocks.filter(s => (s.swingband || '').toLowerCase() === 'elite').length,
    strong:       stocks.filter(s => (s.swingband || '').toLowerCase() === 'strong').length,
    sectorLeader: stocks.filter(s => s.setupLabel === 'Sector Leader').length,
    breakoutReady: stocks.filter(s => s.setupLabel === 'Breakout Ready').length,
  };

  // Animate each card
  animateCount(document.getElementById('stat-total'),        statCardPrev.total,        counts.total,        700);
  animateCount(document.getElementById('stat-elite'),        statCardPrev.elite,        counts.elite,        600);
  animateCount(document.getElementById('stat-strong'),       statCardPrev.strong,       counts.strong,       650);
  animateCount(document.getElementById('stat-sector-leader'), statCardPrev.sectorLeader, counts.sectorLeader, 600);
  animateCount(document.getElementById('stat-breakout'),     statCardPrev.breakoutReady, counts.breakoutReady, 600);

  // Save for next animation cycle
  Object.assign(statCardPrev, counts);
}

// --- Shared UI factories ---
function makeBadge(text, classNames, title = '') {
    return `<span class="badge ${classNames}"${title ? ` title="${escapeHtml(title)}"` : ''}>${text}</span>`;
}

function makeSetupPill(label, confidence, tags = []) {
    let pillClass = 'setup-pill-early';
    let icon = '';
    if (label.includes('VCP')) { pillClass = 'setup-pill-vcp'; icon = '🌀 '; }
    else if (label.includes('Cup & Handle')) { pillClass = 'setup-pill-cup'; icon = '🍺 '; }
    else if (label.includes('High Tight Flag')) { pillClass = 'setup-pill-flag'; icon = '🚩 '; }
    else if (label.includes('Long Base')) { pillClass = 'setup-pill-base'; icon = '🧱 '; }
    else if (label.startsWith('Breakout Ready')) { pillClass = 'setup-pill-breakout'; icon = '🚀 '; }
    else if (label.startsWith('Pullback to MA')) { pillClass = 'setup-pill-pullback'; icon = '📉 '; }
    else if (label.startsWith('Inside Bar Coil')) { pillClass = 'setup-pill-coil'; icon = '🌀 '; }
    else if (label.startsWith('Stage 2 Camp')) { pillClass = 'setup-pill-camp'; icon = '⛺ '; }
    else if (label.startsWith('Sector Leader')) { pillClass = 'setup-pill-leader'; icon = '👑 '; }
    else if (label.startsWith('Momentum Continuation')) { pillClass = 'setup-pill-cont'; icon = '📈 '; }
    
    const titleStr = tags && tags.length
        ? `Tags: ${tags.join(', ')}\nConfidence: ${confidence}%`
        : `Confidence: ${confidence}%`;
    return `<span class="setup-pill ${pillClass}" title="${escapeHtml(titleStr)}">${icon}${label}</span>`;
}

function makeFilterChip(value, label, activeValue, extraClass = '') {
    const isActive = activeValue === value;
    return `<button class="filter-chip${isActive ? ' active' : ''}${extraClass ? ' ' + extraClass : ''}" data-value="${value}" role="button" tabindex="0">${label}</button>`;
}

// Expose factories to window
window.makeBadge = makeBadge;
window.makeSetupPill = makeSetupPill;
window.makeFilterChip = makeFilterChip;

// Auto Refresh state
let autoRefreshInterval = null;
let secondsRemaining = 0;
const REFRESH_INTERVAL_SEC = 120;

// Announcements state
let loadedAnnouncements = [];
let lastFetchedAnnouncementsSymbols = [];
let isAnnouncementsLoading = false;

// Events (NSE Event Calendar) state
let loadedEvents = [];
let lastFetchedEventsSymbols = [];
let isEventsLoading = false;
let expandedEventId = null;

// News state
let loadedNews = {};
let isNewsLoading = false;

// Deals (NSE Block/Bulk Deals) state
let loadedDeals = [];
let dealsTradeDate = '';
let dealsMarketStatus = '';
let isDealsLoading = false;
let lastFetchedDealsSymbols = [];
let expandedDealIdx = null;

// Elements
const btnScan = document.getElementById('btn-scan');
const scanSpinner = document.getElementById('scan-spinner');
const searchInput = document.getElementById('search-input');
const btnSectors = document.getElementById('btn-sectors');
const sectorsDropdown = document.getElementById('sectors-dropdown');
const selectedSectorLabel = document.getElementById('selected-sector-label');
const btnDots = document.getElementById('btn-dots');
const dotsDropdown = document.getElementById('dots-dropdown');
const selectedDotsLabel = document.getElementById('selected-dots-label');
const tableBody = document.getElementById('table-body');
const showingText = document.getElementById('showing-text');
const btnExport = document.getElementById('btn-export');
const btnSaveSnapshot = document.getElementById('btn-save-snapshot');
const btnColumns = document.getElementById('btn-columns');
const columnDropdown = document.getElementById('column-dropdown');

const btnIms = document.getElementById('btn-ims');
const imsDropdown = document.getElementById('ims-dropdown');
const selectedImsLabel = document.getElementById('selected-ims-label');
const btnSwing = document.getElementById('btn-swing');
const swingDropdown = document.getElementById('swing-dropdown');
const selectedSwingLabel = document.getElementById('selected-swing-label');
const btnCandle = document.getElementById('btn-candle');
const candleDropdown = document.getElementById('candle-dropdown');
const selectedCandleLabel = document.getElementById('selected-candle-label');
const btnQuickSwing = document.getElementById('btn-quick-swing');
const autoRefreshCheckbox = document.getElementById('auto-refresh-checkbox');
const autoRefreshCountdownEl = document.getElementById('auto-refresh-countdown');

let selectedSector = 'all';
let currentSetupFilter = 'all';
let currentMtfFilter = 'all';

// Active screener tab
let currentTab = 'overview';

// Master columns config per tab
const masterColumnsConfig = {
    overview: [
        { id: 'ticker', name: 'Ticker', sortField: 'clean_ticker', isVisible: true, align: 'left', canToggle: false },
        { id: 'setupLabel', name: 'Setup', sortField: 'setupLabel', isVisible: true, align: 'center', canToggle: true },
        { id: 'mtfScore', name: 'MTF', sortField: 'mtfScore', isVisible: true, align: 'center', canToggle: true, tooltip: 'Multi-Timeframe Confirmation: checks if weekly and monthly trends align with the setup.' },
        { id: 'description', name: 'Company Name', sortField: 'description', isVisible: true, align: 'left', canToggle: true },
        { id: 'close', name: 'Price (₹)', sortField: 'close', isVisible: true, align: 'right', canToggle: true },
        { id: 'change', name: 'Change (%)', sortField: 'change', isVisible: true, align: 'right', canToggle: true },
        { id: 'day_range', name: 'Day Range', sortField: 'day_range_pct', isVisible: true, align: 'center', canToggle: true },
        { id: 'volume', name: 'Volume', sortField: 'volume', isVisible: true, align: 'right', canToggle: true },
        { id: 'perf_w', name: '1W Perf (%)', sortField: 'perf_w', isVisible: true, align: 'right', canToggle: true },
        { id: 'perf_m', name: '1M Perf (%)', sortField: 'perf_m', isVisible: true, align: 'right', canToggle: true },
        { id: 'perf_3m', name: '3M Perf (%)', sortField: 'perf_3m', isVisible: true, align: 'right', canToggle: true },
        { id: 'mkt_cap_cr', name: 'Mkt Cap (Cr)', sortField: 'mkt_cap_cr', isVisible: true, align: 'right', canToggle: true },
        { id: 'atr_pct', name: 'ATR (%)', sortField: 'atr_pct', isVisible: true, align: 'right', canToggle: true },
        { id: 'relative_volume', name: 'RVOL (10d)', sortField: 'relative_volume', isVisible: true, align: 'right', canToggle: true },
        { id: 'intraday_score', name: 'IMS', sortField: 'intraday_score', isVisible: true, align: 'center', canToggle: true },
        { id: 'swingscore', name: 'Swing', sortField: 'swingscore', isVisible: true, align: 'center', canToggle: true },
        { id: 'gap', name: 'Gap (%)', sortField: 'gap', isVisible: true, align: 'right', canToggle: true },
        { id: 'change_from_open', name: 'Chg from Open (%)', sortField: 'change_from_open', isVisible: true, align: 'right', canToggle: true },
        { id: 'vwap', name: 'VWAP (₹)', sortField: 'VWAP', isVisible: true, align: 'right', canToggle: true },
        { id: 'rsi', name: 'RSI', sortField: 'RSI', isVisible: true, align: 'right', canToggle: true },
        { id: 'pct_above_low', name: 'Above 52W Low (%)', sortField: 'pct_above_low', isVisible: true, align: 'right', canToggle: true },
        { id: 'turnover_m', name: 'Avg Turnover (Cr)', sortField: 'turnover_m', isVisible: true, align: 'right', canToggle: true },
        { id: 'days_in_scan', name: 'Days in Scan', sortField: 'days_in_scan', isVisible: true, align: 'center', canToggle: true, tooltip: 'Consecutive trading days this stock has been in the scan.' },
        { id: 'first_seen', name: 'First Seen', sortField: 'first_seen', isVisible: true, align: 'center', canToggle: true, tooltip: 'First date this stock appeared in the scan.' },
        { id: 'times_seen_20d', name: 'Seen (20d)', sortField: 'times_seen_20d', isVisible: true, align: 'center', canToggle: true, tooltip: 'Number of times this stock appeared in the scan in the last 20 days.' },
        { id: 're_entry', name: 'Re-entry', sortField: 're_entry', isVisible: true, align: 'center', canToggle: true, tooltip: 'Indicates if the stock fell off the scan previously and has returned today.' },
        { id: 'upcoming_earnings', name: 'Earnings', sortField: 'upcoming_earnings', isVisible: true, align: 'center', canToggle: true, tooltip: 'Next upcoming earnings report date.' },
        { id: 'action', name: 'Action', sortField: null, isVisible: true, align: 'center', canToggle: true }
    ],
    valuation: [
        { id: 'ticker', name: 'Ticker', sortField: 'clean_ticker', isVisible: true, align: 'left', canToggle: false },
        { id: 'description', name: 'Company Name', sortField: 'description', isVisible: true, align: 'left', canToggle: true },
        { id: 'close', name: 'Price (₹)', sortField: 'close', isVisible: true, align: 'right', canToggle: true },
        { id: 'change', name: 'Change (%)', sortField: 'change', isVisible: true, align: 'right', canToggle: true },
        { id: 'mkt_cap_cr', name: 'Mkt Cap (Cr)', sortField: 'mkt_cap_cr', isVisible: true, align: 'right', canToggle: true },
        { id: 'pe_ratio', name: 'P/E', sortField: 'pe_ratio', isVisible: true, align: 'right', canToggle: true, tooltip: 'Price to Earnings Ratio. Lower means the stock is cheaper relative to its earnings.' },
        { id: 'ev_ebitda', name: 'EV/EBITDA', sortField: 'ev_ebitda', isVisible: true, align: 'right', canToggle: true, tooltip: 'Enterprise Value to EBITDA. A valuation metric often used as an alternative to P/E, considering debt.' },
        { id: 'pb_ratio', name: 'P/B', sortField: 'pb_ratio', isVisible: true, align: 'right', canToggle: true, tooltip: 'Price to Book Ratio. Compares a firm\'s market value to its book value.' },
        { id: 'ps_ratio', name: 'P/S', sortField: 'ps_ratio', isVisible: true, align: 'right', canToggle: true, tooltip: 'Price to Sales Ratio. Shows how much investors pay per rupee of sales.' },
        { id: 'div_yield', name: 'Div Yield (%)', sortField: 'div_yield', isVisible: true, align: 'right', canToggle: true, tooltip: 'Dividend Yield. The annual dividend payment relative to the stock price.' },
        { id: 'fcf_yield', name: 'FCF Yield (%)', sortField: 'fcf_yield', isVisible: true, align: 'right', canToggle: true, tooltip: 'Free Cash Flow Yield. Higher yield indicates the company is generating more cash relative to its market value.' },
        { id: 'ev_cr', name: 'EV (Cr)', sortField: 'ev_cr', isVisible: true, align: 'right', canToggle: true, tooltip: 'Enterprise Value in Crores. Total valuation of the company including debt, minus cash.' },
        { id: 'action', name: 'Action', sortField: null, isVisible: true, align: 'center', canToggle: true }
    ],
    quality: [
        { id: 'ticker', name: 'Ticker', sortField: 'clean_ticker', isVisible: true, align: 'left', canToggle: false },
        { id: 'description', name: 'Company Name', sortField: 'description', isVisible: true, align: 'left', canToggle: true },
        { id: 'close', name: 'Price (₹)', sortField: 'close', isVisible: true, align: 'right', canToggle: true },
        { id: 'change', name: 'Change (%)', sortField: 'change', isVisible: true, align: 'right', canToggle: true },
        { id: 'roe', name: 'ROE (%)', sortField: 'roe', isVisible: true, align: 'right', canToggle: true, tooltip: 'Return on Equity. Measures profitability generated from shareholders\' equity. >15% is good.' },
        { id: 'roce', name: 'ROCE (%)', sortField: 'roce', isVisible: true, align: 'right', canToggle: true, tooltip: 'Return on Capital Employed. Profitability metric including debt. >15% indicates strong capital efficiency.' },
        { id: 'roa', name: 'ROA (%)', sortField: 'roa', isVisible: true, align: 'right', canToggle: true, tooltip: 'Return on Assets. Shows how profitable a company is relative to its total assets.' },
        { id: 'gross_margin', name: 'Gross Margin (%)', sortField: 'gross_margin', isVisible: true, align: 'right', canToggle: true, tooltip: 'Percentage of revenue left after deducting the cost of goods sold.' },
        { id: 'ebitda_margin', name: 'EBITDA Margin (%)', sortField: 'ebitda_margin', isVisible: true, align: 'right', canToggle: true, tooltip: 'Operating profitability as a percentage of revenue. >20% is typically strong.' },
        { id: 'cfo_ebitda', name: 'CFO/EBITDA (%)', sortField: 'cfo_ebitda', isVisible: true, align: 'right', canToggle: true, tooltip: 'Cash Flow to EBITDA ratio. Measures how well operating profits convert to cash. >70% is healthy.' },
        { id: 'cfo_pat', name: 'CFO/PAT (%)', sortField: 'cfo_pat', isVisible: true, align: 'right', canToggle: true, tooltip: 'Cash Flow to Net Profit ratio. Indicates earnings quality. >80% means profits are backed by real cash.' },
        { id: 'debt_to_equity', name: 'D/E Ratio', sortField: 'debt_to_equity', isVisible: true, align: 'right', canToggle: true, tooltip: 'Debt to Equity ratio. <0.5 is generally safe, >1.5 may indicate high financial risk depending on the sector.' },
        { id: 'interest_coverage', name: 'Interest Cov.', sortField: 'interest_coverage', isVisible: true, align: 'right', canToggle: true, tooltip: 'Interest Coverage Ratio. How easily a company can pay interest on its debt. >3x is considered safe.' },
        { id: 'wc_intensity', name: 'WC Intensity (%)', sortField: 'wc_intensity', isVisible: true, align: 'right', canToggle: true, tooltip: 'Working Capital Intensity. Shows how much working capital is tied up per rupee of sales. Lower is better.' },
        { id: 'action', name: 'Action', sortField: null, isVisible: true, align: 'center', canToggle: true }
    ],
    growth: [
        { id: 'ticker', name: 'Ticker', sortField: 'clean_ticker', isVisible: true, align: 'left', canToggle: false },
        { id: 'description', name: 'Company Name', sortField: 'description', isVisible: true, align: 'left', canToggle: true },
        { id: 'close', name: 'Price (₹)', sortField: 'close', isVisible: true, align: 'right', canToggle: true },
        { id: 'change', name: 'Change (%)', sortField: 'change', isVisible: true, align: 'right', canToggle: true },
        { id: 'revenue_growth_qoq', name: 'Revenue Growth QoQ (%)', sortField: 'revenue_growth_qoq', isVisible: true, align: 'right', canToggle: true, tooltip: 'Quarter-over-Quarter revenue growth.' },
        { id: 'revenue_growth_yoy', name: 'Revenue Growth YoY (%)', sortField: 'revenue_growth_yoy', isVisible: true, align: 'right', canToggle: true, tooltip: 'Year-over-Year revenue growth.' },
        { id: 'revenue_growth_3y', name: 'Revenue Growth 3Y (CAGR %)', sortField: 'revenue_growth_3y', isVisible: true, align: 'right', canToggle: true, tooltip: '3-Year Compound Annual Growth Rate for revenue.' },
        { id: 'ebitda_cagr', name: 'EBITDA CAGR (3Y)', sortField: 'ebitda_cagr', isVisible: true, align: 'right', canToggle: true, tooltip: '3-Year Compound Annual Growth Rate for EBITDA.' },
        { id: 'eps_cagr', name: 'EPS CAGR (3Y)', sortField: 'eps_cagr', isVisible: true, align: 'right', canToggle: true, tooltip: '3-Year Compound Annual Growth Rate for Earnings Per Share.' },
        { id: 'bv_growth', name: 'Book Value Growth (%)', sortField: 'bv_growth', isVisible: true, align: 'right', canToggle: true, tooltip: 'Growth in Book Value per share. Important for financial and asset-heavy companies.' },
        { id: 'order_growth', name: 'Order-Book Growth (%)', sortField: 'order_growth', isVisible: true, align: 'right', canToggle: true, tooltip: 'Growth in the company\'s order book, indicating future revenue visibility.' },
        { id: 'segment_growth', name: 'Segment Growth', sortField: 'segment_growth', isVisible: true, align: 'left', canToggle: true },
        { id: 'action', name: 'Action', sortField: null, isVisible: true, align: 'center', canToggle: true }
    ]
};

// Column configuration state - points to the active tab's config
let columnsConfig = masterColumnsConfig.overview;


// Stat Elements
// Legacy stats (replaced by stat cards)
// const valScanned = document.getElementById('val-scanned');
// const valMatched = document.getElementById('val-matched');

const setupFilterChips = document.querySelectorAll('#setup-filter-chips .filter-chip');
// val-gainer elements replaced by dynamic top-gainers-list container



// Helper: format nullable fundamental values
function renderFundVal(val, decimals, suffix) {
    if (val == null || isNaN(val)) return '<span class="val-na">—</span>';
    const s = suffix || '';
    return val.toFixed(decimals) + s;
}

// Ensure the openUpgradeModal exists as an empty placeholder if not defined
window.openUpgradeModal = window.openUpgradeModal || function() {
    alert("Upgrade modal coming soon!");
};

// Initialize event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Fetch trading holidays dynamically
    fetch('/api/nse-holidays')
        .then(res => res.json())
        .then(data => {
            if (data && data.holidays) {
                window.nseHolidays = new Set(data.holidays);
                console.log(`[EnsembleCast] Loaded ${window.nseHolidays.size} trading holidays dynamically.`);
            }
        })
        .catch(err => console.error('[EnsembleCast] Failed to fetch trading holidays:', err));

    // Request Notification permission
    if ("Notification" in window && Notification.permission !== "granted" && Notification.permission !== "denied") {
        Notification.requestPermission();
    }

    // Setup Watchlist state
    initWatchlist();

    // Initialize Smart Alert Engine UI
    if (typeof AlertEngine !== 'undefined') {
        AlertEngine.initUI();
    }

    // Primary Workspace Navigation Tabs
    const workspaceTabs = document.querySelectorAll('.workspace-tab');
    const workspaceViews = document.querySelectorAll('.workspace-view');
    const slidingCap = document.querySelector('.workspace-sliding-cap');

    function updateSlidingCap(activeTab) {
        if (!slidingCap || !activeTab) return;
        slidingCap.style.left = `${activeTab.offsetLeft}px`;
        slidingCap.style.width = `${activeTab.offsetWidth}px`;
    }

    function switchWorkspace(viewName) {
        workspaceTabs.forEach(tab => {
            if (tab.dataset.view === viewName) {
                tab.classList.add('active');
                updateSlidingCap(tab);
            } else {
                tab.classList.remove('active');
            }
        });

        workspaceViews.forEach(view => {
            if (view.id === `view-${viewName}`) {
                view.classList.add('active');
            } else {
                view.classList.remove('active');
            }
        });

        // Trigger rendering or data updates on tab entry
        if (viewName === 'watchlist') {
            const jc = document.getElementById('journal-container');
            if (jc) jc.style.display = 'flex';
            if (typeof renderJournal === 'function') renderJournal();
        } else if (viewName === 'rrg') {
            const rc = document.getElementById('rrg-container');
            if (rc) rc.style.display = 'flex';
            if (typeof renderRRG === 'function') renderRRG();
        } else if (viewName === 'intraday') {
            const ic = document.getElementById('intraday-container');
            if (ic) ic.style.display = 'flex';
            if (typeof renderIntradayWorkspace === 'function') renderIntradayWorkspace();
        } else if (viewName === 'ai-forecast') {
            if (typeof renderAIForecastWorkspace === 'function') renderAIForecastWorkspace();
        } else if (viewName === 'screener') {
            // Redirect from sub-tabs promoted to top-level views
            if (currentTab === 'journal') {
                const watchlistTab = document.querySelector('.workspace-tab[data-view="watchlist"]');
                if (watchlistTab) {
                    watchlistTab.click();
                } else {
                    switchWorkspace('watchlist');
                }
                return;
            }
            if (currentTab === 'rrg') {
                const rrgTab = document.querySelector('.workspace-tab[data-view="rrg"]');
                if (rrgTab) {
                    rrgTab.click();
                } else {
                    switchWorkspace('rrg');
                }
                return;
            }
            if (currentTab === 'intraday') {
                const intradayTab = document.querySelector('.workspace-tab[data-view="intraday"]');
                if (intradayTab) {
                    intradayTab.click();
                } else {
                    switchWorkspace('intraday');
                }
                return;
            }
        }
        
        localStorage.setItem('momentum_active_workspace', viewName);
    }

    if (workspaceTabs.length > 0) {
        workspaceTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                switchWorkspace(tab.dataset.view);
            });
        });

        // Restore cached workspace selection or default to dashboard
        const cachedWorkspace = localStorage.getItem('momentum_active_workspace') || 'dashboard';
        switchWorkspace(cachedWorkspace);

        window.addEventListener('resize', () => {
            const activeTab = document.querySelector('.workspace-tab.active');
            updateSlidingCap(activeTab);
        });

        // Initial delay positioning to allow CSS animations and flex layouts to compute width
        setTimeout(() => {
            const activeTab = document.querySelector('.workspace-tab.active');
            updateSlidingCap(activeTab);
        }, 200);
    }

    // Theme toggle logic
    const themeBtn = document.getElementById('btn-theme-toggle');
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            const currentTheme = document.body.getAttribute('data-theme') || 'dark';
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.body.setAttribute('data-theme', newTheme);
            localStorage.setItem('app-theme', newTheme);
            
            // Sync active TradingView chart
            if (activeDrawerChart) {
                const themeOpts = getChartThemeOptions(newTheme);
                activeDrawerChart.applyOptions({
                    layout: themeOpts.layout,
                    grid: themeOpts.grid,
                    crosshair: themeOpts.crosshair,
                });
            }
            if (activeOverlayChart) {
                const themeOpts = getChartThemeOptions(newTheme);
                activeOverlayChart.applyOptions({
                    layout: themeOpts.layout,
                    grid: themeOpts.grid,
                    crosshair: themeOpts.crosshair,
                });
            }
        });
    }

    // Run an initial scan on load
    runScan();
    
    // Scan button listener
    if (btnScan) btnScan.addEventListener('click', runScan);
    
    // Export button listener
    if (btnExport) btnExport.addEventListener('click', exportToExcel);
    if (btnSaveSnapshot) btnSaveSnapshot.addEventListener('click', saveSnapshot);

    // Quick Sort Swing Setup
    if (btnQuickSwing) {
        btnQuickSwing.addEventListener('click', () => {
            currentSortField = 'swingscore';
            currentSortOrder = 'desc';
            currentPage = 1;
            sortStocks();
            renderTableHeader();
            renderTable();
        });
    }
    
    // Setup Filter Chips listeners
    if (setupFilterChips) {
        setupFilterChips.forEach(chip => {
            chip.addEventListener('click', () => {
                setupFilterChips.forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                currentSetupFilter = chip.dataset.value;
                filterAndRender();
            });
        });
    }
    
    // MTF Filter Chips listeners
    const mtfFilterChips = document.querySelectorAll('#mtf-filter-chips .filter-chip');
    if (mtfFilterChips.length > 0) {
        mtfFilterChips.forEach(chip => {
            chip.addEventListener('click', () => {
                mtfFilterChips.forEach(c => c.classList.remove('active'));
                chip.classList.add('active');
                currentMtfFilter = chip.dataset.value;
                filterAndRender();
            });
        });
    }
    
    // Filtering listeners
    searchInput.addEventListener('input', filterAndRender);
    
    // Range Filters event listeners
    const rangeFilterInputs = [
        'filter-rvol-min', 'filter-rvol-max',
        'filter-change-min', 'filter-change-max',
        'filter-pe-min', 'filter-pe-max',
        'filter-ims', 'filter-swing', 'filter-candle'
    ];
    rangeFilterInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
            el.addEventListener(eventName, filterAndRender);
        }
    });
    
    const btnClearRangeFilters = document.getElementById('btn-clear-range-filters');
    if (btnClearRangeFilters) {
        btnClearRangeFilters.addEventListener('click', () => {
            rangeFilterInputs.forEach(id => {
                const el = document.getElementById(id);
                if (el) {
                    if (id === 'filter-ims') {
                        el.value = 'all';
                        if (selectedImsLabel) selectedImsLabel.textContent = 'All Scores';
                        document.querySelectorAll('#ims-dropdown .select-dropdown-item').forEach(item => {
                            item.classList.toggle('active', item.dataset.value === 'all');
                        });
                    } else if (id === 'filter-swing') {
                        el.value = 'all';
                        if (selectedSwingLabel) selectedSwingLabel.textContent = 'All Scores';
                        document.querySelectorAll('#swing-dropdown .select-dropdown-item').forEach(item => {
                            item.classList.toggle('active', item.dataset.value === 'all');
                        });
                    } else if (id === 'filter-candle') {
                        el.value = 'all';
                        if (selectedCandleLabel) selectedCandleLabel.textContent = 'All Patterns';
                        document.querySelectorAll('#candle-dropdown .select-dropdown-item').forEach(item => {
                            item.classList.toggle('active', item.dataset.value === 'all');
                        });
                    } else if (el.tagName === 'SELECT') {
                        el.value = 'all';
                    } else {
                        el.value = '';
                    }
                }
            });
            
            // Reset setup filter chips
            const setupChips = document.querySelectorAll('#setup-filter-chips .filter-chip');
            if (setupChips.length > 0) {
                setupChips.forEach(c => c.classList.remove('active'));
                setupChips[0].classList.add('active');
                currentSetupFilter = 'all';
            }
            
            const mtfChips = document.querySelectorAll('#mtf-filter-chips .filter-chip');
            if (mtfChips.length > 0) {
                mtfChips.forEach(c => c.classList.remove('active'));
                mtfChips[0].classList.add('active');
                currentMtfFilter = 'all';
            }
            
            // Reset intraday preset filter
            activeIntradayFilter = null;
            
            filterAndRender();
        });
    }
    
    // Sector dropdown toggle button listener
    if (btnSectors && sectorsDropdown) {
        btnSectors.addEventListener('click', (e) => {
            e.stopPropagation();
            sectorsDropdown.classList.toggle('hidden');
            const isExpanded = !sectorsDropdown.classList.contains('hidden');
            btnSectors.setAttribute('aria-expanded', isExpanded);
        });
    }

    // Dot Indicators dropdown toggle button listener
    if (btnDots && dotsDropdown) {
        btnDots.addEventListener('click', (e) => {
            e.stopPropagation();
            dotsDropdown.classList.toggle('hidden');
            const isExpanded = !dotsDropdown.classList.contains('hidden');
            btnDots.setAttribute('aria-expanded', isExpanded);
        });
    }

    // IMS Score dropdown toggle button listener
    if (btnIms && imsDropdown) {
        btnIms.addEventListener('click', (e) => {
            e.stopPropagation();
            imsDropdown.classList.toggle('hidden');
            const isExpanded = !imsDropdown.classList.contains('hidden');
            btnIms.setAttribute('aria-expanded', isExpanded);
        });
    }

    // Swing Score dropdown toggle button listener
    if (btnSwing && swingDropdown) {
        btnSwing.addEventListener('click', (e) => {
            e.stopPropagation();
            swingDropdown.classList.toggle('hidden');
            const isExpanded = !swingDropdown.classList.contains('hidden');
            btnSwing.setAttribute('aria-expanded', isExpanded);
        });
    }

    // Candlestick Pattern dropdown toggle button listener
    if (btnCandle && candleDropdown) {
        btnCandle.addEventListener('click', (e) => {
            e.stopPropagation();
            candleDropdown.classList.toggle('hidden');
            const isExpanded = !candleDropdown.classList.contains('hidden');
            btnCandle.setAttribute('aria-expanded', isExpanded);
        });
    }

    // Hide dropdowns when clicking outside
    document.addEventListener('click', (e) => {
        // Sector dropdown
        if (sectorsDropdown && btnSectors && !sectorsDropdown.classList.contains('hidden') && !sectorsDropdown.contains(e.target) && e.target !== btnSectors) {
            sectorsDropdown.classList.add('hidden');
            btnSectors.setAttribute('aria-expanded', 'false');
        }
        
        // Dot Indicators dropdown
        if (dotsDropdown && !dotsDropdown.classList.contains('hidden') && !dotsDropdown.contains(e.target) && e.target !== btnDots) {
            dotsDropdown.classList.add('hidden');
            btnDots.setAttribute('aria-expanded', 'false');
        }

        // IMS Score dropdown
        if (imsDropdown && !imsDropdown.classList.contains('hidden') && !imsDropdown.contains(e.target) && e.target !== btnIms) {
            imsDropdown.classList.add('hidden');
            btnIms.setAttribute('aria-expanded', 'false');
        }

        // Swing Score dropdown
        if (swingDropdown && !swingDropdown.classList.contains('hidden') && !swingDropdown.contains(e.target) && e.target !== btnSwing) {
            swingDropdown.classList.add('hidden');
            btnSwing.setAttribute('aria-expanded', 'false');
        }

        // Candlestick Pattern dropdown
        if (candleDropdown && !candleDropdown.classList.contains('hidden') && !candleDropdown.contains(e.target) && e.target !== btnCandle) {
            candleDropdown.classList.add('hidden');
            btnCandle.setAttribute('aria-expanded', 'false');
        }
        
        // Columns dropdown
        if (!columnDropdown.classList.contains('hidden') && !columnDropdown.contains(e.target) && e.target !== btnColumns) {
            columnDropdown.classList.add('hidden');
        }
    });

    // Dot Indicators dropdown item click listener
    document.querySelectorAll('#dots-dropdown .select-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
            const val = item.dataset.value;
            const input = document.getElementById('filter-dots');
            if (input) input.value = val;
            
            if (selectedDotsLabel) {
                selectedDotsLabel.innerHTML = item.innerHTML;
            }
            
            document.querySelectorAll('#dots-dropdown .select-dropdown-item').forEach(opt => {
                opt.classList.toggle('active', opt === item);
            });
            
            if (dotsDropdown && btnDots) {
                dotsDropdown.classList.add('hidden');
                btnDots.setAttribute('aria-expanded', 'false');
            }
            
            filterAndRender();
        });
    });

    // IMS Score dropdown item click listener
    document.querySelectorAll('#ims-dropdown .select-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
            const val = item.dataset.value;
            const input = document.getElementById('filter-ims');
            if (input) input.value = val;
            
            if (selectedImsLabel) {
                selectedImsLabel.innerHTML = item.innerHTML;
            }
            
            document.querySelectorAll('#ims-dropdown .select-dropdown-item').forEach(opt => {
                opt.classList.toggle('active', opt === item);
            });
            
            if (imsDropdown && btnIms) {
                imsDropdown.classList.add('hidden');
                btnIms.setAttribute('aria-expanded', 'false');
            }
            
            filterAndRender();
        });
    });

    // Swing Score dropdown item click listener
    document.querySelectorAll('#swing-dropdown .select-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
            const val = item.dataset.value;
            const input = document.getElementById('filter-swing');
            if (input) input.value = val;
            
            if (selectedSwingLabel) {
                selectedSwingLabel.innerHTML = item.innerHTML;
            }
            
            document.querySelectorAll('#swing-dropdown .select-dropdown-item').forEach(opt => {
                opt.classList.toggle('active', opt === item);
            });
            
            if (swingDropdown && btnSwing) {
                swingDropdown.classList.add('hidden');
                btnSwing.setAttribute('aria-expanded', 'false');
            }
            
            filterAndRender();
        });
    });

    // Candlestick Pattern dropdown item click listener
    document.querySelectorAll('#candle-dropdown .select-dropdown-item').forEach(item => {
        item.addEventListener('click', () => {
            const val = item.dataset.value;
            const input = document.getElementById('filter-candle');
            if (input) input.value = val;
            
            if (selectedCandleLabel) {
                selectedCandleLabel.innerHTML = item.innerHTML;
            }
            
            document.querySelectorAll('#candle-dropdown .select-dropdown-item').forEach(opt => {
                opt.classList.toggle('active', opt === item);
            });
            
            if (candleDropdown && btnCandle) {
                candleDropdown.classList.add('hidden');
                btnCandle.setAttribute('aria-expanded', 'false');
            }
            
            filterAndRender();
        });
    });



    // Initialize Auto Refresh
    if (autoRefreshCheckbox) {
        const saved = localStorage.getItem('tv_auto_refresh') === 'true';
        autoRefreshCheckbox.checked = saved;
        autoRefreshCheckbox.addEventListener('change', (e) => {
            localStorage.setItem('tv_auto_refresh', e.target.checked);
            if (e.target.checked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });
        if (saved) startAutoRefresh();
    }

    // Column dropdown toggle button listener
    btnColumns.addEventListener('click', (e) => {
        e.stopPropagation();
        columnDropdown.classList.toggle('hidden');
    });
    
    // Watchlist Toggle Button Event Listener
    // Compact Mode Density Toggle Listener
    const densityBtn = document.getElementById('btn-toggle-density');
    const densityLabel = document.getElementById('density-label');
    
    function applyDensity(isCompact) {
        if (isCompact) {
            document.body.classList.add('compact-mode');
            if (densityLabel) densityLabel.textContent = 'Comfortable';
        } else {
            document.body.classList.remove('compact-mode');
            if (densityLabel) densityLabel.textContent = 'Compact';
        }
        localStorage.setItem('momentum_table_density', isCompact ? 'compact' : 'comfortable');
    }
    
    if (densityBtn) {
        densityBtn.addEventListener('click', () => {
            const isCurrentlyCompact = document.body.classList.contains('compact-mode');
            applyDensity(!isCurrentlyCompact);
        });
        
        // Restore cached density preference
        const cachedDensity = localStorage.getItem('momentum_table_density') === 'compact';
        applyDensity(cachedDensity);
    }
    
    // Column preferences and reordering setup
    initColumns();

    // News source modal close listeners
    const btnCloseSourceModal = document.getElementById('btn-close-source-modal');
    const newsSourceModal = document.getElementById('news-source-modal');
    if (btnCloseSourceModal && newsSourceModal) {
        btnCloseSourceModal.addEventListener('click', () => {
            newsSourceModal.classList.add('hidden');
        });
        newsSourceModal.addEventListener('click', (e) => {
            if (e.target === newsSourceModal) {
                newsSourceModal.classList.add('hidden');
            }
        });
    }

    // Sentiment explanation modal close listeners
    const btnCloseSentModal = document.getElementById('btn-close-sent-modal');
    const sentimentModal = document.getElementById('sentiment-explanation-modal');
    if (btnCloseSentModal && sentimentModal) {
        btnCloseSentModal.addEventListener('click', () => {
            sentimentModal.classList.add('hidden');
        });
        sentimentModal.addEventListener('click', (e) => {
            if (e.target === sentimentModal) {
                sentimentModal.classList.add('hidden');
            }
        });
    }

    // Regime history modal listeners
    const btnOpenHistory = document.getElementById('open-regime-history');
    const btnCloseHistory = document.getElementById('close-regime-history');
    const btnExportRegime = document.getElementById('btn-export-regime-csv');
    const historyModal = document.getElementById('regime-history-modal');
    if (btnOpenHistory) {
        btnOpenHistory.addEventListener('click', openRegimeHistoryModal);
    }
    if (btnExportRegime) {
        btnExportRegime.addEventListener('click', exportRegimeHistoryToCSV);
    }
    if (btnCloseHistory && historyModal) {
        btnCloseHistory.addEventListener('click', () => {
            historyModal.classList.add('hidden');
        });
        historyModal.addEventListener('click', (e) => {
            if (e.target === historyModal) {
                historyModal.classList.add('hidden');
            }
        });
    }

    // Chart overlay modal listeners
    const drawerChartContainer = document.getElementById('drawer-tv-chart-container');
    const closeChartModalBtn = document.getElementById('close-chart-modal');
    const chartOverlayModal = document.getElementById('chart-overlay-modal');
    
    if (drawerChartContainer) {
        drawerChartContainer.addEventListener('click', () => {
            if (window.currentDrawerChartData && window.currentTradeStock) {
                if (chartOverlayModal) {
                    chartOverlayModal.classList.remove('hidden');
                    document.getElementById('overlay-chart-title').innerHTML = `📈 ${window.currentTradeStock.clean_ticker} - Daily Chart`;
                    setTimeout(() => {
                        createOverlayChart('overlay-tv-chart', window.currentDrawerChartData, window.currentDrawerForecastData || [], window.currentDrawerCandlestickPatterns || {});
                    }, 50);
                }
            }
        });
    }

    if (closeChartModalBtn) {
        closeChartModalBtn.addEventListener('click', closeChartOverlay);
    }
    if (chartOverlayModal) {
        chartOverlayModal.addEventListener('click', (e) => {
            if (e.target === chartOverlayModal) {
                closeChartOverlay();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeChartOverlay();
        }
    });

    // Tab switching event listeners
    const screenerTabs = document.getElementById('screener-tabs');
    if (screenerTabs) {
        screenerTabs.addEventListener('click', (e) => {
            const btn = e.target.closest('.tab-btn');
            if (!btn || btn.classList.contains('active')) return;
            
            // Redirect from sub-tabs promoted to top-level workspaces
            const tabName = btn.dataset.tab;
            if (tabName === 'journal') {
                const watchlistTab = document.querySelector('.workspace-tab[data-view="watchlist"]');
                if (watchlistTab) {
                    watchlistTab.click();
                } else {
                    switchWorkspace('watchlist');
                }
                return;
            }
            if (tabName === 'rrg') {
                const rrgTab = document.querySelector('.workspace-tab[data-view="rrg"]');
                if (rrgTab) {
                    rrgTab.click();
                } else {
                    switchWorkspace('rrg');
                }
                return;
            }
            if (tabName === 'intraday') {
                const intradayTab = document.querySelector('.workspace-tab[data-view="intraday"]');
                if (intradayTab) {
                    intradayTab.click();
                } else {
                    switchWorkspace('intraday');
                }
                return;
            }

            // Update active tab button
            screenerTabs.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Switch tab
            currentTab = btn.dataset.tab;
            
            const growthDisclaimer = document.getElementById('growth-disclaimer');
            if (growthDisclaimer) {
                growthDisclaimer.style.display = currentTab === 'growth' ? 'flex' : 'none';
            }
            
            const mainContainer = document.getElementById('main-table-container');
            const rrgContainer = document.getElementById('rrg-container');
            const intradayContainer = document.getElementById('intraday-container');
            const journalContainer = document.getElementById('journal-container');
            const rrContainer = document.getElementById('rr-setups-container');
            const tableFooter = document.getElementById('table-footer');
            
            if (currentTab === 'rrg') {
                if (mainContainer) mainContainer.style.display = 'none';
                if (tableFooter) tableFooter.style.display = 'none';
                if (intradayContainer) intradayContainer.style.display = 'none';
                if (journalContainer) journalContainer.style.display = 'none';
                if (rrContainer) rrContainer.style.display = 'none';
                if (rrgContainer) rrgContainer.style.display = 'flex';
                if (typeof renderRRG === 'function') renderRRG();
            } else if (currentTab === 'intraday') {
                if (mainContainer) mainContainer.style.display = 'none';
                if (tableFooter) tableFooter.style.display = 'none';
                if (rrgContainer) rrgContainer.style.display = 'none';
                if (journalContainer) journalContainer.style.display = 'none';
                if (rrContainer) rrContainer.style.display = 'none';
                if (intradayContainer) intradayContainer.style.display = 'flex';
                if (typeof renderIntradayWorkspace === 'function') renderIntradayWorkspace();
            } else if (currentTab === 'journal') {
                if (mainContainer) mainContainer.style.display = 'none';
                if (tableFooter) tableFooter.style.display = 'none';
                if (rrgContainer) rrgContainer.style.display = 'none';
                if (intradayContainer) intradayContainer.style.display = 'none';
                if (rrContainer) rrContainer.style.display = 'none';
                if (journalContainer) journalContainer.style.display = 'flex';
                if (typeof renderJournal === 'function') renderJournal();
            } else if (currentTab === 'rr-setups') {
                if (mainContainer) mainContainer.style.display = 'none';
                if (tableFooter) tableFooter.style.display = 'none';
                if (rrgContainer) rrgContainer.style.display = 'none';
                if (intradayContainer) intradayContainer.style.display = 'none';
                if (journalContainer) journalContainer.style.display = 'none';
                if (rrContainer) rrContainer.style.display = 'flex';
                if (typeof runRRScreen === 'function') runRRScreen();
            } else {
                if (mainContainer) mainContainer.style.display = 'block';
                if (tableFooter) tableFooter.style.display = 'flex';
                if (rrgContainer) rrgContainer.style.display = 'none';
                if (intradayContainer) intradayContainer.style.display = 'none';
                if (journalContainer) journalContainer.style.display = 'none';
                if (rrContainer) rrContainer.style.display = 'none';
                
                // Clear intraday preset when returning to main tables so it doesn't silently filter
                if (activeIntradayFilter) {
                    activeIntradayFilter = null;
                    filterAndRender();
                }
                
                columnsConfig = masterColumnsConfig[currentTab];
                
                // Re-render headers and data
                renderTableHeader();
                renderTable();
                
                // Re-initialize column dropdown for the new tab
                initColumns();
            }
        });
    }

    // Restore R:R preferences
    if (typeof restoreRRPrefs === 'function') {
        restoreRRPrefs();
    }

    // Wire R:R inputs change listeners
    const rrInputs = ['rr-min-input', 'rr-atr-mult', 'rr-target-ext', 'rr-max-risk', 'rr-min-swing'];
    rrInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('input', () => {
                if (typeof runRRScreen === 'function') runRRScreen();
            });
        }
    });

    // --- Table Keyboard Navigation (Item 6) ---
    let selectedRowIndex = -1;

    document.addEventListener('keydown', (e) => {
        const activeWorkspace = document.querySelector('.workspace-tab.active')?.dataset.view;
        if (activeWorkspace !== 'screener') return;
        if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;

        if (!tableBody) return;
        const rows = tableBody.querySelectorAll('tr:not(.skeleton-row)');
        if (!rows.length) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedRowIndex = Math.min(selectedRowIndex + 1, rows.length - 1);
            highlightSelectedRow(rows);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedRowIndex = Math.max(selectedRowIndex - 1, 0);
            highlightSelectedRow(rows);
        } else if (e.key === 'Enter' && selectedRowIndex >= 0) {
            rows[selectedRowIndex]?.click();
        } else if ((e.key === 'w' || e.key === 'W') && selectedRowIndex >= 0) {
            const ticker = rows[selectedRowIndex]?.dataset.ticker;
            if (ticker) addToWatchlist(ticker, e);
        }
    });

    function highlightSelectedRow(rows) {
        rows.forEach(r => r.classList.remove('row-keyboard-selected'));
        const target = rows[selectedRowIndex];
        if (target) {
            target.classList.add('row-keyboard-selected');
            target.scrollIntoView({ block: 'nearest' });
        }
    }

    // --- ARIA + Keyboard Accessibility (Item 7) ---
    function makeKeyboardClickable(selector) {
        document.querySelectorAll(selector).forEach(el => {
            if (!el.getAttribute('role')) el.setAttribute('role', 'button');
            if (!el.getAttribute('tabindex')) el.setAttribute('tabindex', '0');
            
            // Remove existing keydown if any, then add
            el.removeEventListener('keydown', handleElementKeydown);
            el.addEventListener('keydown', handleElementKeydown);
        });
    }

    function handleElementKeydown(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            e.currentTarget.click();
        }
    }

    // Expose accessibility helper so it can be called after render cycles
    window.makeKeyboardClickable = makeKeyboardClickable;

    // Run accessibility pass on initial cards and elements
    setTimeout(() => {
        makeKeyboardClickable('.stat-card');
        makeKeyboardClickable('.bm-sector-row');
    }, 500);
});

// Compute changes between scans
function computeScanDelta(oldStock, newStock) {
    if (!oldStock) {
        return { isNew: true, imsUpgraded: false, swingUpgraded: false, setupChanged: false, crossedBreakoutZone: false, message: "New Entry" };
    }
    
    let isNew = false;
    let imsUpgraded = false;
    let swingUpgraded = false;
    let setupChanged = false;
    let crossedBreakoutZone = false;
    let message = "";
    
    // IMS Upgrade
    const oldIms = oldStock.ims_band || "weak";
    const newIms = newStock.ims_band || "weak";
    if (newIms === "strong" && oldIms !== "strong") {
        imsUpgraded = true;
        message = "IMS Upgraded to Strong";
    }
    
    // Swing Upgrade
    const oldSwing = oldStock.swingband || "weak";
    const newSwing = newStock.swingband || "weak";
    if ((newSwing === "strong" || newSwing === "elite") && (oldSwing !== "strong" && oldSwing !== "elite")) {
        swingUpgraded = true;
        if (!message) message = "Swing Upgraded";
    }
    
    // Setup Changed
    const oldSetup = oldStock.setupLabel || "Early Watch";
    const newSetup = newStock.setupLabel || "Early Watch";
    if (newSetup !== oldSetup && newSetup !== "Early Watch") {
        setupChanged = true;
        if (!message) message = "New Setup: " + newSetup;
    }
    
    // Breakout Zone
    const oldPrice = parseFloat(oldStock.close);
    const newPrice = parseFloat(newStock.close);
    const high52w = parseFloat(newStock.price_52_week_high);
    if (!isNaN(oldPrice) && !isNaN(newPrice) && !isNaN(high52w) && high52w > 0) {
        const threshold = 0.98 * high52w;
        if (newPrice >= threshold && oldPrice < threshold) {
            crossedBreakoutZone = true;
            if (!message) message = "Entered Breakout Zone";
        }
    }
    
    const hasChange = imsUpgraded || swingUpgraded || setupChanged || crossedBreakoutZone;
    
    // Trigger notification if it's in watchlist
    if (hasChange) {
        const watchlistData = JSON.parse(localStorage.getItem('tvScreenerWatchlist') || '[]');
        const isInWatchlist = watchlistData.some(item => item.ticker === newStock.clean_ticker);
        
        if (isInWatchlist && "Notification" in window && Notification.permission === "granted") {
            new Notification(`Alert: ${newStock.clean_ticker}`, {
                body: message,
                icon: "/static/favicon.ico"
            });
        }
    }
    
    if (hasChange) {
        return { isNew, imsUpgraded, swingUpgraded, setupChanged, crossedBreakoutZone, message };
    }
    return null;
}

// Run scan from Flask backend API
async function runScan() {
    // UI Loading state
    if (btnScan) btnScan.disabled = true;
    if (scanSpinner) scanSpinner.classList.remove('hidden');
    
    const visibleCount = columnsConfig.filter(c => c.isVisible).length;
    let skeletonHtml = '';
    for (let r = 0; r < 5; r++) {
        skeletonHtml += `
            <tr class="skeleton-row">
                ${columnsConfig.filter(c => c.isVisible).map(col => {
                    const widthPercent = (col.id === 'ticker' || col.id === 'change') 
                        ? '60%' 
                        : `${Math.floor(Math.random() * 40) + 40}%`;
                    return `
                        <td>
                            <div class="skeleton-bar" style="width: ${widthPercent};"></div>
                        </td>
                    `;
                }).join('')}
            </tr>
        `;
    }
    if (tableBody) tableBody.innerHTML = skeletonHtml;
    
    // Reset stats
    if (window.valScanned) valScanned.textContent = "-";
    if (window.valMatched) valMatched.textContent = "-";
    const gainerContainer = document.getElementById('top-gainers-list');
    if (gainerContainer) {
        gainerContainer.innerHTML = '<div class="top-gainer-placeholder" style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.5rem 0; text-align: center;">Scanning...</div>';
    }
    const sectorContainer = document.getElementById('top-sectors-list');
    if (sectorContainer) {
        sectorContainer.innerHTML = '<div class="top-sector-placeholder" style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.5rem 0; text-align: center;">Scanning...</div>';
    }
    const moversContainer = document.getElementById('intraday-movers-list');
    if (moversContainer) {
        moversContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.5rem 0; text-align: center;">Scanning...</div>';
    }
    
    try {
        const response = await fetch('/api/scan');
        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.error) {
            showErrorState(result.error);
            return;
        }
        
        if (stocksData && stocksData.length > 0) {
            previousScanMap = {};
            stocksData.forEach(s => { previousScanMap[s.clean_ticker] = s; });
        }
        
        stocksData = result.stocks || [];
        stocksData.forEach(s => {
            const h = parseFloat(s.high);
            const l = parseFloat(s.low);
            const c = parseFloat(s.close);
            s.day_range_pct = (!isNaN(h) && !isNaN(l) && h > l && !isNaN(c)) ? ((c - l) / (h - l)) * 100 : -1;
        });
        universeData = result.universe || [];
        filteredStocks = [...stocksData];
        
        // Update stats
        if (window.valScanned) valScanned.textContent = result.total_scanned.toLocaleString();
        if (window.valMatched) valMatched.textContent = result.total_matched.toLocaleString();
        
        // Update timestamp
        const timeStr = new Date().toLocaleTimeString('en-US', {hour: '2-digit', minute:'2-digit', second:'2-digit'});
        const timeEl = document.getElementById('last-updated-time');
        if (timeEl) {
            timeEl.textContent = `(Updated: ${timeStr})`;
        }
        
        // Calculate sector scores using the full market universe
        if (universeData.length > 0) {
            calculateSectorScores(universeData);
        } else {
            calculateSectorScores(stocksData);
        }
        
        calculateStats(stocksData, false);
        
        if (Object.keys(previousScanMap).length > 0) {
            stocksData.forEach(s => {
                s.scanDelta = computeScanDelta(previousScanMap[s.clean_ticker], s);
            });
        }
        
        if (universeData && universeData.length > 0) {
            populateSectors(universeData);
        } else {
            populateSectors(stocksData);
        }
        if (typeof renderIntradayWorkspace === 'function') renderIntradayWorkspace();
        filterAndRender();
        // Update new animated stat cards
        updateStatCards(stocksData);
        saveBreadthSnapshot();
        
        // Refresh watchlist stock prices/stats after scan
        updateWatchlistData();
        
        // Auto-run R:R screen or update count badge
        if (typeof runRRScreen === 'function') {
            runRRScreen();
        }
        
        // Trigger Smart Alert Engine for swing flips
        if (typeof AlertEngine !== 'undefined' && previousScanMap && Object.keys(previousScanMap).length > 0) {
            const wlRaw = (typeof watchlistStocks !== 'undefined' && Array.isArray(watchlistStocks)) ? watchlistStocks : [];
            const wlSymbols = new Set(wlRaw.map(s => s.split(':').pop().toUpperCase()));
            AlertEngine.checkSwingFlips(previousScanMap, stocksData, wlSymbols);
        }
        
    } catch (e) {
        console.error("Scan error:", e);
        showErrorState("Client Error: " + (e.stack || e.message || String(e)));
        if (scanSpinner) scanSpinner.classList.add('hidden');
        if (btnScan) btnScan.disabled = false;
    } finally {
        if (btnScan) btnScan.disabled = false;
        if (scanSpinner) scanSpinner.classList.add('hidden');
    }
}

// Auto Refresh Functions
function isMarketOpen() {
    const now = new Date();
    // Assuming IST based on client timezone
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const time = hours + minutes / 60;
    // Market is open 9:15 AM to 3:30 PM
    const isOpen = time >= 9.25 && time <= 15.5;
    const day = now.getDay();
    const isWeekday = day >= 1 && day <= 5;
    return isOpen && isWeekday;
}

function startAutoRefresh() {
    stopAutoRefresh();
    if (!isMarketOpen()) {
        if(autoRefreshCountdownEl) autoRefreshCountdownEl.textContent = "Closed";
        return;
    }
    secondsRemaining = REFRESH_INTERVAL_SEC;
    updateCountdownDisplay();
    
    autoRefreshInterval = setInterval(() => {
        secondsRemaining--;
        updateCountdownDisplay();
        if (secondsRemaining <= 0) {
            if (isMarketOpen()) {
                runScan();
                secondsRemaining = REFRESH_INTERVAL_SEC;
            } else {
                stopAutoRefresh();
                if(autoRefreshCountdownEl) autoRefreshCountdownEl.textContent = "Closed";
            }
        }
    }, 1000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) clearInterval(autoRefreshInterval);
    autoRefreshInterval = null;
    if(autoRefreshCountdownEl) autoRefreshCountdownEl.textContent = "";
}

function updateCountdownDisplay() {
    if (!autoRefreshCountdownEl) return;
    const m = Math.floor(secondsRemaining / 60);
    const s = secondsRemaining % 60;
    autoRefreshCountdownEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;
}

// Populate Sector filter dropdown
function populateSectors(stocks) {
    sectors.clear();
    stocks.forEach(stock => {
        if (stock.sector) {
            sectors.add(stock.sector);
        }
    });
    
    // Reset dropdown
    if (sectorsDropdown) sectorsDropdown.innerHTML = '';
    
    // Add "All Sectors" option
    const allOption = document.createElement('div');
    allOption.className = `select-dropdown-item${selectedSector === 'all' ? ' active' : ''}`;
    allOption.dataset.sector = 'all';
    allOption.textContent = 'All Sectors';
    allOption.addEventListener('click', () => selectSector('all'));
    if (sectorsDropdown) sectorsDropdown.appendChild(allOption);
    
    // Sort sectors by their score in descending order
    const sortedSectors = Array.from(sectors).sort((a, b) => {
        const scoreA = sectorScores[a] ? sectorScores[a].score : 0;
        const scoreB = sectorScores[b] ? sectorScores[b].score : 0;
        if (scoreA !== scoreB) {
            return scoreB - scoreA; // Descending order of score
        }
        return a.localeCompare(b); // Alphabetical fallback
    });
    
    sortedSectors.forEach(sector => {
        const option = document.createElement('div');
        option.className = `select-dropdown-item${selectedSector === sector ? ' active' : ''}`;
        option.dataset.sector = sector;
        
        const score = sectorScores[sector] ? sectorScores[sector].score : 0;
        const scoreBadge = score >= 70 ? `🟢 ${score}%` : `${score}%`;
        
        option.innerHTML = `
            <span style="display:flex; justify-content:space-between; width:100%; align-items:center; gap:1rem;">
                <span>${sector}</span>
                <span class="badge" style="font-size:0.65rem; padding:0.15rem 0.4rem; background:rgba(255,255,255,0.06); color:var(--color-text-secondary); border-radius:3px;">${scoreBadge}</span>
            </span>
        `;
        option.addEventListener('click', () => selectSector(sector));
        if (sectorsDropdown) sectorsDropdown.appendChild(option);
    });
}

function selectSector(sector) {
    selectedSector = sector;
    if (selectedSectorLabel) selectedSectorLabel.textContent = sector === 'all' ? 'All Sectors' : sector;
    
    document.querySelectorAll('#sectors-dropdown .select-dropdown-item').forEach(item => {
        item.classList.toggle('active', item.dataset.sector === sector);
    });
    
    if (sectorsDropdown) sectorsDropdown.classList.add('hidden');
    if (btnSectors) btnSectors.setAttribute('aria-expanded', 'false');
    filterAndRender();
}

function renderSparkline(canvas, points, isPositive) {
  if (!canvas || !points || points.length < 2) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.width;
  const height = canvas.height;
  
  ctx.clearRect(0, 0, width, height);
  
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = (max - min) || 1;
  
  ctx.beginPath();
  points.forEach((val, idx) => {
    const x = (idx / (points.length - 1)) * (width - 4) + 2;
    const y = height - ((val - min) / range) * (height - 4) - 2;
    if (idx === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  
  ctx.strokeStyle = isPositive ? '#10b981' : '#ef4444';
  ctx.lineWidth = 1.5;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.stroke();
  
  // Fill gradient
  ctx.lineTo((width - 4) + 2, height);
  ctx.lineTo(2, height);
  ctx.closePath();
  ctx.fillStyle = isPositive ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)';
  ctx.fill();
}

function computeMarketBreadth(universe, filtered) {
  if (!universe || universe.length === 0) return;

  let advances = 0, declines = 0, unchanged = 0;
  let aboveSMA21 = 0, aboveSMA50 = 0, near52High = 0;
  let new52Highs = 0, new52Lows = 0;
  let recSum = 0, recCount = 0;
  const total = universe.length;
  const sectorMap = {};

  universe.forEach(s => {
    const change = parseFloat(s.change ?? s.perfw ?? 0);
    const close  = parseFloat(s.close  ?? 0);
    const sma21  = parseFloat(s.SMA21  ?? 0);
    const sma50  = parseFloat(s.SMA50  ?? 0);
    const hi52   = parseFloat(s.price52weekhigh ?? s.price_52_week_high ?? 0);
    const lo52   = parseFloat(s.price52weeklow  ?? s.price_52_week_low  ?? 0);
    const rec    = parseFloat(s['Recommend.All'] ?? 0);
    const sector = s.sector || 'Unknown';

    if (change > 0) advances++; else if (change < 0) declines++; else unchanged++;
    if (close > 0 && sma21 > 0 && close > sma21) aboveSMA21++;
    if (close > 0 && sma50 > 0 && close > sma50) aboveSMA50++;
    if (hi52 > 0 && close > 0 && (hi52 - close) / hi52 < 0.05) near52High++;
    if (hi52 > 0 && close >= hi52) new52Highs++;
    if (lo52 > 0 && close <= lo52) new52Lows++;
    if (!isNaN(rec)) { recSum += rec; recCount++; }

    if (!sectorMap[sector]) sectorMap[sector] = { advances: 0, declines: 0, total: 0 };
    sectorMap[sector].total++;
    if (change > 0) sectorMap[sector].advances++;
    else if (change < 0) sectorMap[sector].declines++;
  });

  const adRatio      = total > 0 ? advances / total : 0;
  const pctSMA21     = total > 0 ? (aboveSMA21 / total) * 100 : 0;
  const pctSMA50     = total > 0 ? (aboveSMA50 / total) * 100 : 0;
  const maBreadth    = (pctSMA21 + pctSMA50) / 2;
  const pct52High    = total > 0 ? (near52High / total) * 100 : 0;
  const avgRec       = recCount > 0 ? ((recSum / recCount + 1) / 2) * 100 : 50;
  const scanStrength = total > 0 ? (filtered.length / total) * 100 : 0;

  const regimeScore = Math.round(
    (adRatio * 30) + ((maBreadth / 100) * 30) +
    ((pct52High / 100) * 20) + ((avgRec / 100) * 20)
  );

  let regimeBand, regimeColor, regimeEmoji;
  if      (regimeScore >= 75) { regimeBand='Bull Run';    regimeColor='--color-success';  regimeEmoji='🚀'; }
  else if (regimeScore >= 55) { regimeBand='Bullish';     regimeColor='--accent-teal';    regimeEmoji='📈'; }
  else if (regimeScore >= 40) { regimeBand='Neutral';     regimeColor='--accent-amber';   regimeEmoji='⚖️'; }
  else if (regimeScore >= 20) { regimeBand='Bearish';     regimeColor='--accent-orange';  regimeEmoji='📉'; }
  else                        { regimeBand='Bear Market'; regimeColor='--color-error';    regimeEmoji='🐻'; }

  const sectorArr = Object.entries(sectorMap)
    .filter(([, v]) => v.total >= 3)
    .map(([name, v]) => ({
      name,
      breadthPct: Math.round((v.advances / v.total) * 100),
      advances: v.advances, declines: v.declines, total: v.total,
    }))
    .sort((a, b) => b.breadthPct - a.breadthPct);

  Object.assign(marketBreadth, {
    advances, declines, unchanged, total,
    adRatio, adLine: advances - declines,
    pctAboveSMA21: Math.round(pctSMA21),
    pctAboveSMA50: Math.round(pctSMA50),
    maBreadthScore: Math.round(maBreadth),
    pctNear52High: Math.round(pct52High),
    avgRecommend: Math.round(avgRec),
    regimeScore, regimeBand, regimeColor, regimeEmoji,
    scanStrength: Math.round(scanStrength * 10) / 10,
    topBreadthSectors: sectorArr.slice(0, 3),
    new52Highs, new52Lows,
    weakBreadthSectors: sectorArr.slice(-3).reverse(),
    allBreadthSectors: sectorArr,
  });
}

function renderBreadthPanel() {
  const b = marketBreadth;
  if (!b.total) return;

  const setText  = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  const setWidth = (id, p) => { const el = document.getElementById(id); if (el) el.style.width = p + '%'; };

  // Regime arc gauge
  setText('regime-band',  b.regimeBand);
  setText('regime-emoji', b.regimeEmoji);
  const badge = document.getElementById('breadth-regime-badge');
  if (badge) badge.setAttribute('data-regime', b.regimeBand.toLowerCase().replace(' ', '-'));
  animateCount(document.getElementById('regime-score-num'),
    parseInt(document.getElementById('regime-score-num')?.textContent) || 0, b.regimeScore, 800);
  const arc = document.getElementById('regime-arc-fill');
  if (arc) { arc.style.strokeDashoffset = 78.5 - (b.regimeScore / 100) * 78.5; }
  const needle = document.getElementById('regime-needle');
  if (needle) {
    const angle = (b.regimeScore / 100) * 180 - 90;
    needle.style.transform = `rotate(${angle}deg)`;
  }

  // A/D
  animateCount(document.getElementById('bm-advances'),  0, b.advances,  600);
  animateCount(document.getElementById('bm-declines'),  0, b.declines,  600);
  animateCount(document.getElementById('bm-unchanged'), 0, b.unchanged, 600);
  setWidth('ad-bar-adv', (b.advances / b.total) * 100);
  setWidth('ad-bar-dec', (b.declines / b.total) * 100);

  // MA breadth
  setText('bm-sma21', b.pctAboveSMA21 + '%');
  setText('bm-sma50', b.pctAboveSMA50 + '%');
  setWidth('bm-ma-fill', b.maBreadthScore);
  const maFill = document.getElementById('bm-ma-fill');
  if (maFill) maFill.className = 'mini-progress-fill ' +
    (b.maBreadthScore > 60 ? 'bm-green' : b.maBreadthScore > 40 ? 'bm-amber' : 'bm-red');

  // 52W high
  setText('bm-52high-val', b.pctNear52High + '%');
  setWidth('bm-52high-fill', b.pctNear52High);

  // New 52W Highs/Lows
  animateCount(document.getElementById('bm-newhighs'), 0, b.new52Highs, 600);
  animateCount(document.getElementById('bm-newlows'),  0, b.new52Lows,  600);

  // TV sentiment
  const sentLabel = b.avgRecommend >= 70 ? 'Strong Buy' : b.avgRecommend >= 55 ? 'Buy' :
                    b.avgRecommend >= 45 ? 'Neutral'    : b.avgRecommend >= 30 ? 'Sell' : 'Strong Sell';
  setText('bm-sent-val', sentLabel);
  setWidth('bm-sent-fill', b.avgRecommend);

  // Scan hit rate
  setText('bm-scan-val', b.scanStrength + '%');
  setText('bm-scan-sub', `${filteredStocks?.length ?? '--'} of ${b.total} stocks qualify`);

  // Top breadth sectors
  const topEl = document.getElementById('bm-top-sectors');
  if (topEl && b.topBreadthSectors.length > 0) {
    topEl.innerHTML = b.topBreadthSectors.map(s => `
      <div class="bm-sector-row" onclick="selectSector('${s.name}')" title="Filter to ${s.name}">
        <span class="bm-sector-name">${s.name}</span>
        <span class="bm-sector-pct ${s.breadthPct >= 60 ? 'val-up' : s.breadthPct <= 40 ? 'val-down' : ''}">
          ${s.breadthPct}%
        </span>
      </div>`).join('');
  }

  // Sector Rotation Heatmap Pills
  const heatmap = document.getElementById('breadth-sector-heatmap');
  if (heatmap) {
    heatmap.innerHTML = (b.allBreadthSectors || []).map(sec => {
      const tone = sec.breadthPct >= 60 ? 'strong' : sec.breadthPct >= 40 ? 'mixed' : sec.breadthPct >= 25 ? 'weak' : 'danger';
      return `
        <button class="sector-pill sector-pill--${tone}" onclick="selectSector('${sec.name}')" title="Filter to ${sec.name}">
          <span class="sector-pill-name">${sec.name}</span>
          <span class="sector-pill-pct">${sec.breadthPct}%</span>
          <div class="sector-pill-progress-track">
            <div class="sector-pill-progress-bar" style="width: ${sec.breadthPct}%"></div>
          </div>
        </button>`;
    }).join('');
  }

  renderRegimeWarning();
  renderBreadthTrendSparkline();
  if (typeof makeKeyboardClickable === 'function') {
      makeKeyboardClickable('.bm-sector-row');
  }
}

const REGIME_MESSAGES = {
  'Bull Run':    { text: 'Market in full bull run — favour breakouts and momentum continuation setups.', type: 'bullish', preset: 'elite', presetLabel: 'Use Aggressive Preset →' },
  'Bullish':     { text: 'Broad market is bullish — good environment to enter swing setups with conviction.', type: 'bullish', preset: 'strong', presetLabel: 'Use Breakout Preset →' },
  'Neutral':     { text: 'Mixed breadth — prefer high-quality setups only. Tighten stops by 20%.', type: 'neutral', preset: null, presetLabel: null },
  'Bearish':     { text: 'Deteriorating breadth — avoid new long entries. Focus on managing open positions.', type: 'bearish', preset: 'watch', presetLabel: 'Use Defensive Preset →' },
  'Bear Market': { text: 'Bear market conditions — no new swing longs. Defensive stance only.', type: 'danger', preset: null, presetLabel: null },
};

function renderRegimeWarning() {
  const msg = REGIME_MESSAGES[marketBreadth.regimeBand];
  if (!msg) return;
  let el = document.getElementById('regime-warning-banner');
  if (!el) {
    el = document.createElement('div');
    el.id = 'regime-warning-banner';
    const bar = document.getElementById('breadth-bar');
    if (bar) bar.insertAdjacentElement('afterend', el); else return;
  }
  el.className = `regime-banner regime-banner--${msg.type}`;
  
  const presetBtnHtml = msg.preset
    ? `<button class="btn-regime-preset" onclick="applyRegimePreset('${msg.preset}')" style="margin-right: 0.5rem; background: var(--accent-blue); border: none; border-radius: 4px; padding: 0.35rem 0.75rem; color: #fff; font-size: 0.75rem; font-weight: 700; cursor: pointer; transition: var(--transition-smooth);">
         ${msg.presetLabel}
       </button>`
    : '';

  el.innerHTML = `
    <div class="regime-banner-left" style="display: flex; align-items: center; gap: 0.8rem; flex: 1;">
      <span class="regime-banner-icon" style="font-size: 1.5rem;">${marketBreadth.regimeEmoji}</span>
      <div class="regime-banner-content" style="display: flex; flex-direction: column;">
        <span class="regime-banner-title" style="font-weight: 700; font-size: 0.8rem; letter-spacing: 0.05em; color: var(--color-text-primary);">${marketBreadth.regimeBand.toUpperCase()} REGIME ACTIVE</span>
        <span class="regime-banner-text" style="font-size: 0.8rem; color: var(--color-text-secondary);">${msg.text}</span>
      </div>
    </div>
    <div class="regime-banner-right" style="display: flex; align-items: center; gap: 1rem;">
      ${presetBtnHtml}
      <div class="regime-banner-score-badge" style="display: flex; flex-direction: column; align-items: center; background: rgba(0,0,0,0.15); border: 1px solid rgba(255,255,255,0.05); border-radius: 6px; padding: 0.25rem 0.6rem;">
        <span class="score-label" style="font-size: 0.6rem; color: var(--color-text-muted); font-weight: 700;">SCORE</span>
        <div style="display: flex; align-items: baseline;">
          <span class="score-value" style="font-size: 1rem; font-weight: 800; color: var(--color-text-primary);">${marketBreadth.regimeScore}</span>
          <span class="score-max" style="font-size: 0.7rem; color: var(--color-text-muted);">/100</span>
        </div>
      </div>
    </div>
  `;
}

function applyRegimePreset(swingBand) {
  const swingFilterInput = document.getElementById('filter-swing');
  if (swingFilterInput) {
    swingFilterInput.value = swingBand;
    
    // Also update dropdown visual label if it exists
    const label = document.getElementById('selected-swing-label');
    if (label) {
      label.textContent = swingBand.charAt(0).toUpperCase() + swingBand.slice(1);
    }
    
    // Reset other filters to ensure preset runs cleanly
    const imsFilterInput = document.getElementById('filter-ims');
    if (imsFilterInput) imsFilterInput.value = 'all';
    const imsLabel = document.getElementById('selected-ims-label');
    if (imsLabel) imsLabel.textContent = 'All Scores';

    filterAndRender();
  }
  const screenerTab = document.querySelector('.workspace-tab[data-view="screener"]');
  if (screenerTab) screenerTab.click();
}

window.applyRegimePreset = applyRegimePreset;

async function saveBreadthSnapshot() {
  if (!marketBreadth.total) return;
  try {
    await fetch('/api/breadth-snapshot', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(marketBreadth),
    });
  } catch (_) {}
}

function getRegimeDelta(history) {
  if (!history || history.length < 2) return { value: 0, label: '• 0', cls: 'flat' };
  const current = history[0]?.regimeScore ?? 0;
  const prev    = history[1]?.regimeScore ?? current;
  const diff    = current - prev;
  if (diff > 0) return { value: diff, label: `▲ ${diff}`, cls: 'up' };
  if (diff < 0) return { value: diff, label: `▼ ${Math.abs(diff)}`, cls: 'down' };
  return { value: 0, label: '• 0', cls: 'flat' };
}

let latestRegimeHistory = [];

async function openRegimeHistoryModal() {
  try {
    const res = await fetch('/api/breadth-history?limit=90');
    const data = await res.json();
    latestRegimeHistory = data.history || [];
    const body = document.getElementById('regime-history-body');
    if (!body) return;

    const getBandClass = (band) => {
      const b = (band || '').toLowerCase().replace(' ', '-');
      if (b === 'bull-run' || b === 'bullish') return 'val-up';
      if (b === 'neutral') return 'bm-unch';
      if (b === 'bearish' || b === 'bear-market') return 'val-down';
      return '';
    };

    body.innerHTML = `
      <table class="regime-history-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Time</th>
            <th>Regime Band</th>
            <th style="text-align:right;">Score</th>
            <th style="text-align:right;">SMA21</th>
            <th style="text-align:right;">SMA50</th>
            <th style="text-align:right;">52W H</th>
          </tr>
        </thead>
        <tbody>
          ${(latestRegimeHistory).map(r => `
            <tr>
              <td>${r.date}</td>
              <td>${r.time}</td>
              <td class="${getBandClass(r.regimeBand)}" style="font-weight:600;">${r.regimeBand}</td>
              <td style="text-align:right; font-weight:700; color:var(--color-text-primary);">${r.regimeScore}</td>
              <td style="text-align:right;">${r.pctAboveSMA21}%</td>
              <td style="text-align:right;">${r.pctAboveSMA50}%</td>
              <td style="text-align:right;">${r.pctNear52High}%</td>
            </tr>`).join('')}
        </tbody>
      </table>`;
    document.getElementById('regime-history-modal')?.classList.remove('hidden');
  } catch (_) {}
}

function exportRegimeHistoryToCSV() {
  if (!latestRegimeHistory || latestRegimeHistory.length === 0) {
    alert("No data available to export.");
    return;
  }
  let csv = "Date,Time,Regime Band,Regime Score,Advances,Declines,% Above SMA21,% Above SMA50,% Near 52W High,Avg Analyst Rating\n";
  latestRegimeHistory.forEach(r => {
    csv += `"${r.date}","${r.time}","${r.regimeBand}",${r.regimeScore},${r.advances || 0},${r.declines || 0},${r.pctAboveSMA21},${r.pctAboveSMA50},${r.pctNear52High},${r.avgRecommend || 0}\n`;
  });
  
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement("a");
  const url = URL.createObjectURL(blob);
  link.setAttribute("href", url);
  link.setAttribute("download", `regime_breadth_history_${new Date().toISOString().split('T')[0]}.csv`);
  link.style.visibility = 'hidden';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

async function getBreadthHistory(limit = 20) {
  try {
    const res = await fetch(`/api/breadth-history?limit=${limit}`);
    const data = await res.json();
    return data.history || [];
  } catch (err) {
    console.error('Error fetching breadth history:', err);
    return [];
  }
}

async function renderBreadthTrendSparkline() {
  try {
    const history = await getBreadthHistory(20);
    if (!history || history.length < 2) return;

    // Trigger Smart Alert Engine for Regime Delta
    if (typeof AlertEngine !== 'undefined' && typeof marketBreadth !== 'undefined' && typeof marketBreadth.regimeScore !== 'undefined') {
        AlertEngine.checkRegimeDelta(marketBreadth.regimeScore, history);
    }

    const delta = getRegimeDelta(history);
    const deltaEl = document.getElementById('regime-score-delta');
    if (deltaEl) {
      deltaEl.textContent = delta.label;
      deltaEl.className = `regime-score-delta ${delta.cls}`;
    }

    const today    = new Date().toISOString().slice(0, 10);
    const todayPts = history.filter(h => h.date === today).reverse().map(h => h.regimeScore);
    const canvas = document.getElementById('breadth-trend-canvas');
    if (canvas && todayPts.length >= 2) {
      renderSparkline(canvas, todayPts, todayPts[todayPts.length - 1] >= todayPts[0]);
    }

    // Chronological points for sparkline trends (oldest to newest)
    const chronologicalHist = [...history].reverse();

    // 1. A/D Ratio Sparkline
    const adSeries = chronologicalHist.map(h => ((h.advances || 0) / Math.max((h.advances || 0) + (h.declines || 0), 1)) * 100);
    const adCanvas = document.getElementById('spark-ad');
    if (adCanvas && adSeries.length >= 2) {
      renderSparkline(adCanvas, adSeries, adSeries[adSeries.length - 1] >= adSeries[0]);
    }

    // 2. MA Breadth Sparkline
    const maSeries = chronologicalHist.map(h => (((h.pctAboveSMA21 || 0) + (h.pctAboveSMA50 || 0)) / 2));
    const maCanvas = document.getElementById('spark-ma');
    if (maCanvas && maSeries.length >= 2) {
      renderSparkline(maCanvas, maSeries, maSeries[maSeries.length - 1] >= maSeries[0]);
    }

    // 3. 52W High Breadth Sparkline
    const hiSeries = chronologicalHist.map(h => h.pctNear52High || 0);
    const hiCanvas = document.getElementById('spark-52w');
    if (hiCanvas && hiSeries.length >= 2) {
      renderSparkline(hiCanvas, hiSeries, hiSeries[hiSeries.length - 1] >= hiSeries[0]);
    }

    // 4. TV Sentiment Sparkline
    const seSeries = chronologicalHist.map(h => h.avgRecommend || 0);
    const seCanvas = document.getElementById('spark-sent');
    if (seCanvas && seSeries.length >= 2) {
      renderSparkline(seCanvas, seSeries, seSeries[seSeries.length - 1] >= seSeries[0]);
    }
  } catch (err) {
    console.error('Error rendering sparklines:', err);
  }
}

// Global sector strength scores cache
let sectorScores = {};

// Sector Strength Scorer
function calculateSectorScores(stocks) {
    if (!stocks || stocks.length === 0) {
        sectorScores = {};
        return;
    }
    
    // Group stocks by sector
    const sectorsMap = {};
    stocks.forEach(stock => {
        const sector = stock.sector;
        if (!sector) return;
        
        if (!sectorsMap[sector]) {
            sectorsMap[sector] = [];
        }
        sectorsMap[sector].push(stock);
    });
    
    const universeW = stocks.map(s => s.perf_w).filter(v => v != null && !isNaN(v));
    const universeM = stocks.map(s => s.perf_m).filter(v => v != null && !isNaN(v));
    const universe3M = stocks.map(s => s.perf_3m).filter(v => v != null && !isNaN(v));
    
    // Compute universe benchmarks (proxies for Nifty 50) using Median to align with RRG
    const avgUniverse1W = universeW.length > 0 ? getMedian(universeW) : 0;
    const avgUniverse1M = universeM.length > 0 ? getMedian(universeM) : 0;
    const avgUniverse3M = universe3M.length > 0 ? getMedian(universe3M) : 0;
    
    sectorScores = {};
    
    Object.keys(sectorsMap).forEach(sector => {
        const sectorStocks = sectorsMap[sector];
        const count = sectorStocks.length;
        
        // 1. Relative Strength vs Universe/Market (40 points)
        // 1. Relative Strength vs Universe/Market (40 points)
        const wValues = sectorStocks.map(s => s.perf_w).filter(v => v != null && !isNaN(v));
        const mValues = sectorStocks.map(s => s.perf_m).filter(v => v != null && !isNaN(v));
        const m3Values = sectorStocks.map(s => s.perf_3m).filter(v => v != null && !isNaN(v));
        
        const avgSector1W = wValues.length > 0 ? getMedian(wValues) : 0;
        const avgSector1M = mValues.length > 0 ? getMedian(mValues) : 0;
        const avgSector3M = m3Values.length > 0 ? getMedian(m3Values) : 0;
        
        const diff1W = avgSector1W - avgUniverse1W;
        const diff1M = avgSector1M - avgUniverse1M;
        const diff3M = avgSector3M - avgUniverse3M;
        
        const combinedRS = (diff1M * 1.5) + (diff3M * 1.0);
        const rsScore = Math.max(0, Math.min(40, 20 + (combinedRS * 2)));
        
        // 2. Breadth: Advances vs Declines (25 points)
        let advances = 0;
        sectorStocks.forEach(s => {
            if (s.change > 0) advances++;
        });
        const breadthPct = count > 0 ? (advances / count) : 0.5;
        const breadthScore = breadthPct * 25;
        
        // 3. Trend: close above SMA21 and SMA50 (20 points)
        let inTrend = 0;
        sectorStocks.forEach(s => {
            const close = parseFloat(s.close) || 0;
            const sma21 = parseFloat(s.SMA21) || 0;
            const sma50 = parseFloat(s.SMA50) || 0;
            if (close > sma21 && close > sma50) {
                inTrend++;
            }
        });
        const trendPct = count > 0 ? (inTrend / count) : 0.5;
        const trendScore = trendPct * 20;
        
        // 4. Leadership: stocks near 52W high (15 points)
        let leaders = 0;
        sectorStocks.forEach(s => {
            const close = parseFloat(s.close) || 0;
            const high52 = parseFloat(s.price_52_week_high || s.price52weekhigh) || 0;
            if (high52 > 0 && close >= (high52 * 0.96)) {
                leaders++;
            }
        });
        const leadershipPct = count > 0 ? (leaders / count) : 0.2;
        const leadershipScore = leadershipPct * 15;
        
        const totalScore = Math.round(rsScore + breadthScore + trendScore + leadershipScore);
        
        let quadrant = 'Lagging';
        if (diff1M > 0 && diff1W > 0) quadrant = 'Leading';
        else if (diff1M <= 0 && diff1W > 0) quadrant = 'Improving';
        else if (diff1M > 0 && diff1W <= 0) quadrant = 'Weakening';
        
        sectorScores[sector] = {
            score: totalScore,
            advances: advances,
            declines: count - advances,
            count: count,
            avg1W: avgSector1W,
            avg1M: avgSector1M,
            avg3M: avgSector3M,
            delta1W: diff1W,
            delta1M: diff1M,
            quadrant: quadrant,
            isTop3: false
        };
    });
    
    // Assign isTop3 flag to the top 3 valid sectors
    const validSectors = Object.keys(sectorScores).filter(s => sectorScores[s].count >= 2);
    validSectors.sort((a, b) => sectorScores[b].score - sectorScores[a].score);
    validSectors.slice(0, 3).forEach(s => {
        sectorScores[s].isTop3 = true;
    });
}

function applyImsSectorAdjustment(stock) {
    if (!stock.ims_breakdown || stock.intraday_score === undefined) return;
    
    const alignIdx = stock.ims_breakdown.findIndex(b => b.toLowerCase().includes("sector alignment"));
    if (alignIdx !== -1) {
        const line = stock.ims_breakdown[alignIdx];
        const alreadyHasPoint = line.includes('(+1)');
        
        const sect = stock.sector;
        const isStrongSector = !!(sect && sectorScores[sect] && sectorScores[sect].isTop3);
        
        if (isStrongSector && !alreadyHasPoint) {
            stock.intraday_score += 1;
        } else if (!isStrongSector && alreadyHasPoint) {
            stock.intraday_score -= 1;
        }
        
        if (isStrongSector) {
            stock.ims_breakdown[alignIdx] = `Strong sector alignment: ${sect} (${sectorScores[sect].score}/100) (+1)`;
        } else if (sect && sectorScores[sect]) {
            stock.ims_breakdown[alignIdx] = `Neutral/Weak sector alignment: ${sect} (${sectorScores[sect].score}/100) (+0)`;
        } else {
            stock.ims_breakdown[alignIdx] = `Sector alignment unknown (+0)`;
        }
        
        // Update IMS band
        if (stock.intraday_score >= 7) {
            stock.ims_band = "strong";
        } else if (stock.intraday_score >= 5) {
            stock.ims_band = "moderate";
        } else {
            stock.ims_band = "weak";
        }
    }
}

function applySwingSectorAdjustment(stock) {
    if (!stock.swingbreakdown || stock.swingscore === undefined) return;
    
    const alignIdx = stock.swingbreakdown.findIndex(b => b.toLowerCase().includes("sector alignment"));
    if (alignIdx !== -1) {
        const line = stock.swingbreakdown[alignIdx];
        const alreadyHasPoint = line.includes('(+1)');
        
        const sect = stock.sector;
        const isStrongSector = !!(sect && sectorScores[sect] && sectorScores[sect].isTop3);
        
        if (isStrongSector && !alreadyHasPoint) {
            stock.swingscore += 1;
        } else if (!isStrongSector && alreadyHasPoint) {
            stock.swingscore -= 1;
        }
        
        if (stock.swingscore > 10) stock.swingscore = 10;
        
        if (isStrongSector) {
            stock.swingbreakdown[alignIdx] = `Strong sector alignment: ${sect} (${sectorScores[sect].score}/100) (+1)`;
        } else if (sect && sectorScores[sect]) {
            stock.swingbreakdown[alignIdx] = `Neutral/Weak sector alignment: ${sect} (${sectorScores[sect].score}/100) (+0)`;
        } else {
            stock.swingbreakdown[alignIdx] = `Sector alignment unknown (+0)`;
        }
        
        if (stock.swingscore >= 8) stock.swingband = "elite";
        else if (stock.swingscore >= 6) stock.swingband = "strong";
        else if (stock.swingscore >= 4) stock.swingband = "watch";
        else stock.swingband = "weak";
    }
}

// Calculate summary stats
function calculateStats(stocks, calculateSectors = true) {
    if (stocks.length === 0) return;
    
    // Compute sector strength scores
    if (calculateSectors) {
        calculateSectorScores(stocks);
    }
    
    computeMarketBreadth(universeData.length > 0 ? universeData : stocks, filteredStocks ?? stocks);
    renderBreadthPanel();
    
    // Recalculate IMS and Swing Sector Alignment using real sector scores

    
    stocks.forEach(stock => {
        applyImsSectorAdjustment(stock);
        applySwingSectorAdjustment(stock);
        
        // Re-evaluate Sector Leader setup label based on valid sector scores
        if (stock.perf_w > 0 && stock.close > stock.SMA21) {
            const sect = stock.sector;
            if (sect && sectorScores[sect] && sectorScores[sect].isTop3) {
                if (stock.setupLabel !== "Breakout Ready" && stock.setupLabel !== "Pullback to MA" && stock.setupLabel !== "Inside Bar Coil") {
                    stock.setupLabel = "Sector Leader";
                }
                if (stock.setupTags && !stock.setupTags.includes("Sector Leader")) {
                    stock.setupTags.push("Sector Leader");
                }
            }
        }
        
    });
    
    // Determine the top 3 strongest sectors
    const validSectors = Object.keys(sectorScores).filter(s => sectorScores[s].count >= 2);
    const targetList = validSectors.length > 0 ? validSectors : Object.keys(sectorScores);
    
    const sortedSectors = targetList.map(s => ({
        name: s,
        score: sectorScores[s].score,
        count: sectorScores[s].count,
        advances: sectorScores[s].advances,
        declines: sectorScores[s].declines
    })).sort((a, b) => b.score - a.score);
    
    const top3Sectors = sortedSectors.slice(0, 3);
    
    // Update Top Sectors UI list
    const sectorListContainer = document.getElementById('top-sectors-list');
    if (sectorListContainer) {
        if (top3Sectors.length === 0) {
            sectorListContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.5rem 0; text-align: center;">No strong sectors found</div>';
        } else {
            sectorListContainer.innerHTML = top3Sectors.map((sec, idx) => {
                const isStrong = sec.score >= 70;
                const badgeHtml = isStrong ? '🟢 Strong' : '⚪ Stable';
                return `
                    <div class="top-sector-row" onclick="selectSector('${sec.name}')" title="Click to filter screener table by ${sec.name} sector">
                        <span class="top-sector-rank">#${idx + 1}</span>
                        <div class="top-sector-info">
                            <span class="top-sector-name">${sec.name}</span>
                            <span class="top-sector-meta">${sec.count} stocks &middot; ${sec.advances} Adv / ${sec.declines} Dec</span>
                        </div>
                        <div class="top-sector-score-wrap">
                            <span class="top-sector-score-badge">${badgeHtml}</span>
                            <span class="top-sector-score-val">${sec.score}<span style="font-size:0.65rem; color:var(--color-text-muted); font-weight:normal;">/100</span></span>
                        </div>
                    </div>
                `;
            }).join('');
        }
    }
    
    // Populate Intraday Movers stats card (Top 5 highest IMS scores)
    const moversListContainer = document.getElementById('intraday-movers-list');
    if (moversListContainer) {
        const sortedByIMS = [...stocks].filter(s => s.intraday_score != null).sort((a, b) => {
            if (b.intraday_score !== a.intraday_score) return b.intraday_score - a.intraday_score;
            return Math.abs(b.change) - Math.abs(a.change); // tie-break by absolute change
        });
        const top5Movers = sortedByIMS.slice(0, 5);
        
        if (top5Movers.length === 0) {
            moversListContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--color-text-muted); padding: 0.5rem 0; text-align: center;">No scores available</div>';
        } else {
            moversListContainer.innerHTML = top5Movers.map((stock, idx) => {
                const score = stock.intraday_score;
                const band = stock.ims_band || 'weak';
                const badgeClass = band === 'strong' ? 'ims-strong' : band === 'moderate' ? 'ims-moderate' : 'ims-weak';
                const changeClass = stock.change >= 0 ? 'val-up' : 'val-down';
                const changeSign = stock.change > 0 ? '+' : '';
                const breakdownText = (stock.ims_breakdown || []).join('\n');
                return `
                    <div class="intraday-mover-row" onclick="openTradingView('${stock.clean_ticker}')" title="${escapeHtml(breakdownText)}">
                        <span class="intraday-mover-rank">#${idx + 1}</span>
                        <span class="intraday-mover-symbol">${stock.clean_ticker}</span>
                        <span class="intraday-mover-score ims-badge ${badgeClass}">${score}/10</span>
                        <span class="intraday-mover-change ${changeClass}">${changeSign}${stock.change.toFixed(2)}%</span>
                    </div>
                `;
            }).join('');
        }
    }
}

// Show error message in table body
function showErrorState(message) {
    const visibleCount = columnsConfig.filter(c => c.isVisible).length;
    if (tableBody) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="${visibleCount}" class="table-empty-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="hsl(350, 80%, 55%)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:1rem;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                    <p style="color:var(--accent-red); font-weight:600;">Scan Failed</p>
                    <p style="font-size:0.85rem; max-width:500px; margin:0.5rem auto 0 auto;">${message}</p>
                </td>
            </tr>
        `;
    }
    if (showingText) showingText.textContent = "Scan failed";
}

// Helper to check if stock close is flirting with or between 10, 21, and 50 MA/EMA
function checkMaFlirtingOrBetween(stock) {
    const price = parseFloat(stock.close);
    // Prefer EMA, fall back to SMA
    const ma10 = parseFloat(stock.EMA10 !== undefined && stock.EMA10 !== null ? stock.EMA10 : stock.SMA10);
    const ma21 = parseFloat(stock.EMA21 !== undefined && stock.EMA21 !== null ? stock.EMA21 : stock.SMA21);
    const ma50 = parseFloat(stock.EMA50 !== undefined && stock.EMA50 !== null ? stock.EMA50 : stock.SMA50);
    const isEma = (stock.EMA10 !== undefined && stock.EMA10 !== null);
    const maType = isEma ? "EMA" : "SMA";
    
    if (isNaN(price) || isNaN(ma10) || isNaN(ma21) || isNaN(ma50)) {
        return { isMatch: false, tooltip: "" };
    }
    
    const limit = 0.015;
    const diff10 = Math.abs(price - ma10) / ma10;
    const diff21 = Math.abs(price - ma21) / ma21;
    const diff50 = Math.abs(price - ma50) / ma50;
    
    const isFlirting10 = diff10 <= limit;
    const isFlirting21 = diff21 <= limit;
    const isFlirting50 = diff50 <= limit;
    
    const minMa = Math.min(ma10, ma21, ma50);
    const maxMa = Math.max(ma10, ma21, ma50);
    const isBetween = price >= minMa && price <= maxMa;
    
    const isMatch = isFlirting10 || isFlirting21 || isFlirting50 || isBetween;
    
    let tooltip = "";
    if (isMatch) {
        const details = [];
        details.push(`Price: ₹${price.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        details.push(`10 ${maType}: ₹${ma10.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        details.push(`21 ${maType}: ₹${ma21.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        details.push(`50 ${maType}: ₹${ma50.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`);
        
        let reasonStr = "";
        if (isBetween) {
            reasonStr = `Price is between the ${maType}s`;
        } else {
            const flirtTypes = [];
            if (isFlirting10) flirtTypes.push(`10 ${maType} (within ${(diff10 * 100).toFixed(2)}%)`);
            if (isFlirting21) flirtTypes.push(`21 ${maType} (within ${(diff21 * 100).toFixed(2)}%)`);
            if (isFlirting50) flirtTypes.push(`50 ${maType} (within ${(diff50 * 100).toFixed(2)}%)`);
            reasonStr = `Price is flirting with: ${flirtTypes.join(", ")}`;
        }
        tooltip = `MA Compression Alert (${maType})\n${reasonStr}\n\n${details.join("\n")}`;
    }
    
    return { isMatch, tooltip };
}

// Filter stocks by search, sector dropdown, and numeric ranges
function filterAndRender() {

    const searchVal = searchInput.value.toLowerCase().trim();
    const sectorVal = selectedSector;
    
    // Get Range Filter values
    const rvolMin = parseFloat(document.getElementById('filter-rvol-min')?.value);
    const rvolMax = parseFloat(document.getElementById('filter-rvol-max')?.value);
    const changeMin = parseFloat(document.getElementById('filter-change-min')?.value);
    const changeMax = parseFloat(document.getElementById('filter-change-max')?.value);
    const peMin = parseFloat(document.getElementById('filter-pe-min')?.value);
    const peMax = parseFloat(document.getElementById('filter-pe-max')?.value);
    
    filteredStocks = stocksData.filter(stock => {
        const matchesSearch = stock.clean_ticker.toLowerCase().includes(searchVal) || 
                              stock.description.toLowerCase().includes(searchVal) ||
                              (stock.setupLabel && stock.setupLabel.toLowerCase().includes(searchVal));
        const matchesSector = sectorVal === 'all' || stock.sector === sectorVal;
        
        // RVOL Range
        let matchesRvol = true;
        if (!isNaN(rvolMin) && (stock.relative_volume === null || stock.relative_volume === undefined || stock.relative_volume < rvolMin)) {
            matchesRvol = false;
        }
        if (!isNaN(rvolMax) && (stock.relative_volume === null || stock.relative_volume === undefined || stock.relative_volume > rvolMax)) {
            matchesRvol = false;
        }
        
        // Change % Range
        let matchesChange = true;
        if (!isNaN(changeMin) && (stock.change === null || stock.change === undefined || stock.change < changeMin)) {
            matchesChange = false;
        }
        if (!isNaN(changeMax) && (stock.change === null || stock.change === undefined || stock.change > changeMax)) {
            matchesChange = false;
        }
        
        // P/E Ratio Range
        let matchesPe = true;
        if (!isNaN(peMin) && (stock.pe_ratio === null || stock.pe_ratio === undefined || stock.pe_ratio < peMin)) {
            matchesPe = false;
        }
        if (!isNaN(peMax) && (stock.pe_ratio === null || stock.pe_ratio === undefined || stock.pe_ratio > peMax)) {
            matchesPe = false;
        }

        // IMS Score Filter
        const imsFilter = document.getElementById('filter-ims')?.value || 'all';
        let matchesIms = true;
        const imsBand = stock.ims_band || 'weak';
        
        if (imsFilter === 'strong') {
            matchesIms = imsBand === 'strong';
        } else if (imsFilter === 'moderate') {
            matchesIms = imsBand === 'moderate' || imsBand === 'strong'; // Allow strong to pass moderate filter
        } else if (imsFilter === 'weak') {
            matchesIms = imsBand === 'weak';
        }

        // Swing Score Filter
        const swingFilter = document.getElementById('filter-swing')?.value || 'all';
        let matchesSwing = true;
        const swingBand = stock.swingband || 'weak';
        
        if (swingFilter === 'elite') {
            matchesSwing = swingBand === 'elite';
        } else if (swingFilter === 'strong') {
            matchesSwing = swingBand === 'elite' || swingBand === 'strong';
        } else if (swingFilter === 'watch') {
            matchesSwing = swingBand === 'elite' || swingBand === 'strong' || swingBand === 'watch';
        }

        // Candlestick Pattern Filter
        const candleFilter = document.getElementById('filter-candle')?.value || 'all';
        let matchesCandle = true;
        if (candleFilter !== 'all') {
            const patterns = stock.candlestick_patterns || {};
            if (candleFilter === 'Bullish Engulfing') {
                matchesCandle = patterns['Engulfing'] === 100;
            } else if (candleFilter === 'Bearish Engulfing') {
                matchesCandle = patterns['Engulfing'] === -100;
            } else {
                matchesCandle = patterns[candleFilter] !== undefined && patterns[candleFilter] !== 0;
            }
        }
        
        // Setup Filter
        let matchesSetup = true;
        if (currentSetupFilter !== 'all') {
            if (currentSetupFilter === 'Earnings-Safe') {
                const eDate = stock.upcoming_earnings;
                if (eDate) {
                    const [ey, em, ed] = eDate.split('-').map(Number);
                    const diffDays = Math.round((new Date(ey, em - 1, ed) - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24));
                    if (diffDays >= 0 && diffDays <= 5) {
                        matchesSetup = false;
                    }
                }
            } else if (currentSetupFilter === 'Bullish Div') {
                const imsStrong = (stock.ims_band || '').toLowerCase() === 'strong';
                const swingStrong = ['strong', 'elite'].includes((stock.swingband || '').toLowerCase());
                matchesSetup = swingStrong && !imsStrong;
            } else if (currentSetupFilter === 'vol_coil') {
                matchesSetup = stock.volDryUp === true;
            } else if (currentSetupFilter === 'stage2_camp') {
                matchesSetup = stock.setupLabel && stock.setupLabel.startsWith('Stage 2 Camp');
            } else if (currentSetupFilter === 'intel-high-grade') {
                const label = (stock.setupLabel || '').toUpperCase();
                matchesSetup = label.includes('[A]') || label.includes('[A+]');
            } else {
                matchesSetup = stock.setupLabel === currentSetupFilter || (stock.setupTags && stock.setupTags.includes(currentSetupFilter));
            }
        }

        // Stat Card Filter
        let matchesStatCard = true;
        if (activeStatFilter && activeStatFilter !== 'total') {
            const sb = (stock.swingband || '').toLowerCase();
            if (activeStatFilter === 'elite') {
                matchesStatCard = sb === 'elite';
            } else if (activeStatFilter === 'strong') {
                matchesStatCard = sb === 'strong';
            } else if (activeStatFilter === 'leader') {
                matchesStatCard = stock.setupLabel === 'Sector Leader';
            } else if (activeStatFilter === 'breakout') {
                matchesStatCard = stock.setupLabel === 'Breakout Ready';
            }
        }
        
        // Intraday Pro Preset Filters
        let matchesIntraday = true;
        if (activeIntradayFilter) {
            const gap = parseFloat(stock.gap) || 0;
            const changeFromOpen = parseFloat(stock.change_from_open) || 0;
            const vwap = parseFloat(stock.VWAP) || 0;
            const close = parseFloat(stock.close) || 0;
            const rvol = parseFloat(stock.relative_volume) || 0;
            const ims = (stock.ims_band || '').toLowerCase();
            const swing = (stock.swingband || '').toLowerCase();
            const intradayScore = parseFloat(stock.intraday_score) || 0;
            
            if (activeIntradayFilter === 'gap_go') {
                matchesIntraday = gap >= 1.0 && changeFromOpen > 0 && close > vwap;
            } else if (activeIntradayFilter === 'vwap_leaders') {
                matchesIntraday = close > vwap && close < vwap * 1.015 && intradayScore > 0;
            } else if (activeIntradayFilter === 'high_rvol') {
                matchesIntraday = rvol >= 1.5;
            } else if (activeIntradayFilter === 'strong_ims') {
                matchesIntraday = ims === 'strong';
            } else if (activeIntradayFilter === 'confluence') {
                matchesIntraday = ims === 'strong' && (swing === 'strong' || swing === 'elite');
            }
        }
        
        // MTF Filter
        let matchesMtf = true;
        if (currentMtfFilter !== 'all') {
            matchesMtf = (stock.mtfScore || 0).toString() === currentMtfFilter;
        }
        
        return matchesSearch && matchesSector && matchesRvol && matchesChange && matchesPe && matchesIms && matchesSwing && matchesCandle && matchesSetup && matchesStatCard && matchesIntraday && matchesMtf;
    });
    
    // Clear the active intraday filter after applying so it doesn't stick permanently if the user changes other filters manually
    // Actually, maybe we keep it until they click "Clear Filters" or change tabs? Let's clear it on tab change or Clear Filters button.
    // For now, let's just leave it active.
    
    currentPage = 1;
    sortStocks();
    
    const activeWorkspace = document.querySelector('.workspace-tab.active')?.dataset.view;
    if (activeWorkspace === 'rrg') {
        if (typeof renderRRG === 'function') renderRRG();
    } else if (currentTab === 'rr-setups') {
        if (typeof runRRScreen === 'function') runRRScreen();
    } else if (currentTab === 'intraday') {
        if (typeof renderIntradayWorkspace === 'function') renderIntradayWorkspace();
    } else if (currentTab === 'journal') {
        if (typeof renderJournal === 'function') renderJournal();
    } else {
        renderTable();
    }
}

// Handle sorting column triggers
function handleSort(field, clickedHeader) {
    if (isDraggingHeader) return; // Prevent sorting when dragging headers
    
    if (currentSortField === field) {
        // Toggle direction
        currentSortOrder = currentSortOrder === 'desc' ? 'asc' : 'desc';
    } else {
        currentSortField = field;
        currentSortOrder = 'desc'; // Default to high-to-low on change
    }
    
    currentPage = 1;
    sortStocks();
    renderTableHeader(); // Re-render headers to update indicators
    renderTable();       // Re-render table body with sorted items
}

// Sort filtered stocks list
function sortStocks() {
    filteredStocks.sort((a, b) => {
        let valA = a[currentSortField];
        let valB = b[currentSortField];
        
        if (currentSortField === 'day_range_pct') {
            if (valA === undefined || valA === null) {
                const h = parseFloat(a.high);
                const l = parseFloat(a.low);
                const c = parseFloat(a.close);
                valA = (!isNaN(h) && !isNaN(l) && h > l && !isNaN(c)) ? ((c - l) / (h - l)) * 100 : -1;
            }
            if (valB === undefined || valB === null) {
                const h = parseFloat(b.high);
                const l = parseFloat(b.low);
                const c = parseFloat(b.close);
                valB = (!isNaN(h) && !isNaN(l) && h > l && !isNaN(c)) ? ((c - l) / (h - l)) * 100 : -1;
            }
        }
        
        // Handle undefined or null values
        if (valA === undefined || valA === null) return 1;
        if (valB === undefined || valB === null) return -1;
        
        // String sort
        if (typeof valA === 'string') {
            return currentSortOrder === 'asc' 
                ? valA.localeCompare(valB) 
                : valB.localeCompare(valA);
        }
        
        // Numeric sort with secondary tiebreaker
        let res = currentSortOrder === 'asc' ? valA - valB : valB - valA;
        if (res === 0 && currentSortField === 'swingscore') {
             // secondary sort by 1W Perf if tied on swingscore
             let perfA = a['perf_w'] || 0;
             let perfB = b['perf_w'] || 0;
             res = currentSortOrder === 'asc' ? perfA - perfB : perfB - perfA;
        }
        return res;
    });
}

function destroyAllSparklines() {
  sparklineRegistry.forEach(chart => chart.destroy());
  sparklineRegistry.clear();
}

// ── Stat Card Filter click handler ──
window.applyStatFilter = function(filter) {
    if (activeStatFilter === filter) {
        // Toggle off if clicking the same active filter
        activeStatFilter = null;
    } else {
        activeStatFilter = filter;
    }
    
    // Update UI highlights
    document.querySelectorAll('.stat-card').forEach(card => card.classList.remove('active'));
    if (activeStatFilter) {
        const activeCard = document.getElementById(`card-${activeStatFilter}`);
        if (activeCard) activeCard.classList.add('active');
    }

    // Since this acts as a global top-level filter, we might want to clear other strict drop-downs, 
    // or let them compound. Let's let them compound for maximum flexibility.
    filterAndRender();
};

// Render data inside table
function renderTable() {
    const visibleCount = columnsConfig.filter(c => c.isVisible).length;
    
    if (filteredStocks.length === 0) {
        if (tableBody) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="${visibleCount}" class="table-empty-state">
                        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-muted)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-bottom:1rem;"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        <p>No matching stocks found</p>
                        <p style="font-size:0.8rem;">Try adjusting your search criteria or choosing a different sector.</p>
                    </td>
                </tr>
            `;
        }
        showingText.textContent = "Showing 0 stocks";
        const pagControls = document.getElementById('pagination-controls');
        if (pagControls) pagControls.innerHTML = '';
        return;
    }
    
    // Pagination slicing
    const totalPages = Math.ceil(filteredStocks.length / itemsPerPage);
    if (currentPage > totalPages) {
        currentPage = totalPages;
    }
    const startIndex = (currentPage - 1) * itemsPerPage;
    const endIndex = Math.min(startIndex + itemsPerPage, filteredStocks.length);
    const pageItems = filteredStocks.slice(startIndex, endIndex);

    let html = '';
    pageItems.forEach(stock => {
        const isStrongIms = (stock.intraday_score >= 7 || stock.ims_band === 'strong');
        let rowClass = isStrongIms ? 'ims-strong-row' : '';
        if (stock.scanDelta) {
            rowClass += ' row-highlight-change';
        }
        html += `<tr data-ticker="${stock.clean_ticker}" class="${rowClass.trim()}" onclick="openTradeDrawer('${stock.clean_ticker}')">`;
        
        columnsConfig.forEach(col => {
            if (!col.isVisible) return;
            
            if (col.id === 'ticker') {
                let sectorDotHtml = '';
                const sect = stock.sector;
                if (sect && sectorScores[sect] && sectorScores[sect].isTop3) {
                    sectorDotHtml = `<span class="strong-sector-dot" title="Top 3 Market Sector: ${sect} (Strength Score: ${sectorScores[sect].score}/100)"></span>`;
                }
                
                let insideBarDotHtml = '';
                if (stock.is_inside_bar) {
                    const h = stock.high !== null && stock.high !== undefined ? Number(stock.high).toFixed(2) : '-';
                    const l = stock.low !== null && stock.low !== undefined ? Number(stock.low).toFixed(2) : '-';
                    const h1 = stock['high[1]'] !== null && stock['high[1]'] !== undefined ? Number(stock['high[1]']).toFixed(2) : '-';
                    const l1 = stock['low[1]'] !== null && stock['low[1]'] !== undefined ? Number(stock['low[1]']).toFixed(2) : '-';
                    insideBarDotHtml = `<span class="inside-bar-dot" title="Formed Inside Bar (Today's Range is inside Yesterday's Range)\nToday's High: ₹${h} < Prev High: ₹${h1}\nToday's Low: ₹${l} > Prev Low: ₹${l1}"></span>`;
                }
                
                let volDryUpDotHtml = '';
                if (stock.volDryUp) {
                    volDryUpDotHtml = `<span class="vol-dryup-dot" title="Volume Compression: RVOL < 0.8 with tight range — potential energy building">🔵</span>`;
                }
                
                let maFlirtingDotHtml = '';
                const maFlirtingInfo = checkMaFlirtingOrBetween(stock);
                if (maFlirtingInfo.isMatch) {
                    maFlirtingDotHtml = `<span class="ma-flirting-dot" title="${escapeHtml(maFlirtingInfo.tooltip)}"></span>`;
                }

                const imsStrong = (stock.ims_band || '').toLowerCase() === 'strong';
                const swingStrong = ['strong', 'elite'].includes((stock.swingband || '').toLowerCase());
                
                let divergenceDotHtml = '';
                if (swingStrong && !imsStrong) {
                    divergenceDotHtml = `<span class="divergence-dot bullish" title="Bullish Divergence: Strong swing setup with quiet intraday — potential accumulation">🔍</span>`;
                } else if (imsStrong && !swingStrong) {
                    divergenceDotHtml = `<span class="divergence-dot bearish" title="Caution: Strong intraday but weak swing — may be a one-day pop only">⚡</span>`;
                }
                
                let high52wDotHtml = '';
                const high52w = parseFloat(stock.price_52_week_high);
                const closePrice = parseFloat(stock.close);
                if (!isNaN(high52w) && !isNaN(closePrice) && high52w > 0) {
                    if (closePrice >= 0.98 * high52w) {
                        high52wDotHtml = `<span class="high-52w-alert" title="Near 52-Week High (Potential Breakout)&#10;Current: ₹${closePrice.toFixed(2)} | 52W High: ₹${high52w.toFixed(2)}">🔥</span>`;
                    }
                }
                
                let changeRibbonHtml = '';
                if (stock.scanDelta && stock.scanDelta.message) {
                    changeRibbonHtml = `<div class="change-ribbon" title="Recently updated">${stock.scanDelta.message}</div>`;
                }

                // Group minor signals in popover
                const inPopover = [insideBarDotHtml, volDryUpDotHtml, maFlirtingDotHtml, divergenceDotHtml].filter(Boolean);
                const popoverHtml = inPopover.length
                    ? `<span class="signal-strip" tabindex="0" title="${inPopover.length} minor signals — hover or focus to view">
                         ···
                         <span class="signal-popover">${inPopover.join('')}</span>
                       </span>`
                    : '';
                
                html += `
                    <td data-column="ticker" class="ticker-col" style="position:relative;">
                        ${changeRibbonHtml}
                        <div class="symbol-cell">
                            <span class="ticker-box">${stock.clean_ticker}${sectorDotHtml}${high52wDotHtml}${popoverHtml}</span>
                            <div style="display: flex; gap: 0.25rem;">
                                <button class="btn-add-watchlist-table" onclick="event.stopPropagation(); openTradingView('${stock.clean_ticker}')" title="Open Chart">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"></path><line x1="16" y1="5" x2="22" y2="5"></line><line x1="19" y1="2" x2="19" y2="8"></line><polyline points="9 22 9 12 15 12 15 22"></polyline></svg>
                                </button>
                                <button class="btn-add-watchlist-table" onclick="event.stopPropagation(); addToWatchlist('${stock.clean_ticker}', event)" title="Add to Watchlist">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                                </button>
                            </div>
                        </div>
                    </td>
                `;
            } else if (col.id === 'setupLabel') {
                const label = stock.setupLabel || 'Early Watch';
                const conf = stock.setupConfidence || 0;
                const setupPillHtml = makeSetupPill(label, conf, stock.setupTags);
                
                html += `
                    <td data-column="setupLabel" class="text-center">
                        ${setupPillHtml}
                    </td>
                `;
            } else if (col.id === 'mtfScore') {
                let mtfScore = stock.mtfScore !== undefined ? stock.mtfScore : 0;
                let badgeClass = 'mtf-none';
                let label = '0TF';
                if (mtfScore === 2) { badgeClass = 'mtf-both'; label = '2TF'; }
                else if (mtfScore === 1) { badgeClass = 'mtf-partial'; label = '1TF'; }
                
                html += `
                    <td data-column="mtfScore" class="text-center">
                        <span class="badge ${badgeClass}" title="${stock.mtfLabel || 'None'}">${label}</span>
                    </td>
                `;

            } else if (col.id === 'description') {
                html += `
                    <td data-column="description" style="font-weight: 600; color: var(--color-text-primary); text-overflow: ellipsis; white-space: nowrap; overflow: hidden; max-width: 200px;" title="${escapeHtml(stock.description)}">
                        ${stock.description}
                    </td>
                `;
            } else if (col.id === 'close') {
                html += `
                    <td data-column="close" class="text-right" style="font-weight:700; color:var(--color-text-primary);">₹${stock.close.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</td>
                `;
            } else if (col.id === 'change') {
                const changeClass = stock.change >= 0 ? 'val-up' : 'val-down';
                const changeSign = stock.change > 0 ? '+' : '';
                const arrow = stock.change >= 0 ? '▲' : '▼';
                html += `
                    <td data-column="change" class="text-right ${changeClass}" aria-label="${changeSign}${stock.change.toFixed(2)} percent change">
                        <span class="colorblind-arrow">${arrow}</span>${changeSign}${stock.change.toFixed(2)}%
                    </td>
                `;
            } else if (col.id === 'day_range') {
                const high = parseFloat(stock.high);
                const low = parseFloat(stock.low);
                const closePrice = parseFloat(stock.close);
                let rangeHtml = '-';
                
                if (!isNaN(high) && !isNaN(low) && !isNaN(closePrice) && high > low) {
                    const range = high - low;
                    const pos = closePrice - low;
                    const pct = Math.max(0, Math.min(100, (pos / range) * 100));
                    
                    rangeHtml = `
                        <div class="day-range-container" title="Low: ₹${low.toFixed(2)} | High: ₹${high.toFixed(2)} | Close: ₹${closePrice.toFixed(2)}">
                            <div class="day-range-bar">
                                <div class="day-range-fill" style="width: ${pct}%;"></div>
                                <div class="day-range-marker" style="left: ${pct}%;"></div>
                            </div>
                        </div>
                    `;
                }
                
                html += `
                    <td data-column="day_range" class="text-center">${rangeHtml}</td>
                `;
            } else if (col.id === 'volume') {
                html += `
                    <td data-column="volume" class="text-right" style="color:var(--color-text-secondary); font-family: 'Outfit', sans-serif;">${formatVolume(stock.volume)}</td>
                `;
            } else if (col.id === 'perf_w') {
                const perfWClass = stock.perf_w >= 0 ? 'val-up' : 'val-down';
                const perfWSign = stock.perf_w > 0 ? '+' : '';
                html += `
                    <td data-column="perf_w" class="text-right ${perfWClass}">${perfWSign}${stock.perf_w.toFixed(2)}%</td>
                `;
            } else if (col.id === 'perf_m') {
                const perfMClass = stock.perf_m >= 0 ? 'val-up' : 'val-down';
                const perfMSign = stock.perf_m > 0 ? '+' : '';
                html += `
                    <td data-column="perf_m" class="text-right ${perfMClass}">${perfMSign}${stock.perf_m.toFixed(2)}%</td>
                `;
            } else if (col.id === 'perf_3m') {
                const perf3mClass = stock.perf_3m >= 0 ? 'val-up' : 'val-down';
                const perf3mSign = stock.perf_3m > 0 ? '+' : '';
                html += `
                    <td data-column="perf_3m" class="text-right ${perf3mClass}">${perf3mSign}${stock.perf_3m.toFixed(2)}%</td>
                `;
            } else if (col.id === 'mkt_cap_cr') {
                html += `
                    <td data-column="mkt_cap_cr" class="text-right">₹${stock.mkt_cap_cr.toLocaleString('en-IN', {maximumFractionDigits: 0})} Cr</td>
                `;
            } else if (col.id === 'atr_pct') {
                html += `
                    <td data-column="atr_pct" class="text-right" style="font-weight:600; color:var(--color-text-primary);">${stock.atr_pct}%</td>
                `;
            } else if (col.id === 'relative_volume') {
                html += `
                    <td data-column="relative_volume" class="text-right" style="font-weight:600; color:var(--color-text-primary);">${stock.relative_volume}</td>
                `;
            } else if (col.id === 'gap') {
                const gapClass = stock.gap != null ? (stock.gap >= 0 ? 'val-up' : 'val-down') : '';
                const gapSign = stock.gap > 0 ? '+' : '';
                html += `<td data-column="gap" class="text-right ${gapClass}">${stock.gap != null ? gapSign + stock.gap.toFixed(2) + '%' : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'change_from_open') {
                const cfoClass = stock.change_from_open != null ? (stock.change_from_open >= 0 ? 'val-up' : 'val-down') : '';
                const cfoSign = stock.change_from_open > 0 ? '+' : '';
                html += `<td data-column="change_from_open" class="text-right ${cfoClass}">${stock.change_from_open != null ? cfoSign + stock.change_from_open.toFixed(2) + '%' : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'vwap') {
                html += `<td data-column="vwap" class="text-right">${stock.VWAP != null ? '₹' + stock.VWAP.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'rsi') {
                const rsiClass = stock.RSI != null ? (stock.RSI >= 70 ? 'val-up' : stock.RSI <= 30 ? 'val-down' : '') : '';
                html += `<td data-column="rsi" class="text-right ${rsiClass}" style="font-weight:600;">${renderFundVal(stock.RSI, 1)}</td>`;
            } else if (col.id === 'pct_above_low') {
                html += `
                    <td data-column="pct_above_low" class="text-right" style="color:var(--accent-green); font-weight:600;">+${stock.pct_above_low}%</td>
                `;
            } else if (col.id === 'turnover_m') {
                html += `
                    <td data-column="turnover_m" class="text-right">₹${stock.turnover_m.toFixed(1)} Cr</td>
                `;
            } else if (col.id === 'pe_ratio') {
                html += `<td data-column="pe_ratio" class="text-right">${renderFundVal(stock.pe_ratio, 1)}</td>`;
            } else if (col.id === 'ev_ebitda') {
                html += `<td data-column="ev_ebitda" class="text-right">${renderFundVal(stock.ev_ebitda, 1)}</td>`;
            } else if (col.id === 'pb_ratio') {
                html += `<td data-column="pb_ratio" class="text-right">${renderFundVal(stock.pb_ratio, 2)}</td>`;
            } else if (col.id === 'ps_ratio') {
                html += `<td data-column="ps_ratio" class="text-right">${renderFundVal(stock.ps_ratio, 2)}</td>`;
            } else if (col.id === 'div_yield') {
                html += `<td data-column="div_yield" class="text-right">${renderFundVal(stock.div_yield, 2, '%')}</td>`;
            } else if (col.id === 'fcf_yield') {
                const fcfClass = stock.fcf_yield != null ? (stock.fcf_yield >= 0 ? 'val-up' : 'val-down') : '';
                html += `<td data-column="fcf_yield" class="text-right ${fcfClass}">${renderFundVal(stock.fcf_yield, 2, '%')}</td>`;
            } else if (col.id === 'ev_cr') {
                html += `<td data-column="ev_cr" class="text-right">${stock.ev_cr != null ? '₹' + stock.ev_cr.toLocaleString('en-IN', {maximumFractionDigits: 0}) + ' Cr' : '<span class=\"val-na\">—</span>'}</td>`;
            } else if (col.id === 'roe') {
                const roeClass = stock.roe != null ? (stock.roe >= 15 ? 'val-up' : stock.roe < 8 ? 'val-down' : '') : '';
                html += `<td data-column="roe" class="text-right ${roeClass}" style="font-weight:600;">${renderFundVal(stock.roe, 1, '%')}</td>`;
            } else if (col.id === 'roce') {
                const roceClass = stock.roce != null ? (stock.roce >= 15 ? 'val-up' : stock.roce < 8 ? 'val-down' : '') : '';
                html += `<td data-column="roce" class="text-right ${roceClass}" style="font-weight:600;">${renderFundVal(stock.roce, 1, '%')}</td>`;
            } else if (col.id === 'roa') {
                html += `<td data-column="roa" class="text-right">${renderFundVal(stock.roa, 1, '%')}</td>`;
            } else if (col.id === 'gross_margin') {
                html += `<td data-column="gross_margin" class="text-right">${renderFundVal(stock.gross_margin, 1, '%')}</td>`;
            } else if (col.id === 'ebitda_margin') {
                const emClass = stock.ebitda_margin != null ? (stock.ebitda_margin >= 20 ? 'val-up' : stock.ebitda_margin < 10 ? 'val-down' : '') : '';
                html += `<td data-column="ebitda_margin" class="text-right ${emClass}">${renderFundVal(stock.ebitda_margin, 1, '%')}</td>`;
            } else if (col.id === 'debt_to_equity') {
                const deClass = stock.debt_to_equity != null ? (stock.debt_to_equity <= 0.5 ? 'val-up' : stock.debt_to_equity > 1.5 ? 'val-down' : '') : '';
                html += `<td data-column="debt_to_equity" class="text-right ${deClass}" style="font-weight:600;">${renderFundVal(stock.debt_to_equity, 2)}</td>`;
            } else if (col.id === 'interest_coverage') {
                const icClass = stock.interest_coverage != null ? (stock.interest_coverage >= 3 ? 'val-up' : stock.interest_coverage < 1.5 ? 'val-down' : '') : '';
                html += `<td data-column="interest_coverage" class="text-right ${icClass}">${renderFundVal(stock.interest_coverage, 1, 'x')}</td>`;
            } else if (col.id === 'cfo_pat') {
                const cfoClass = stock.cfo_pat != null ? (stock.cfo_pat >= 80 ? 'val-up' : stock.cfo_pat < 50 ? 'val-down' : '') : '';
                html += `<td data-column="cfo_pat" class="text-right ${cfoClass}">${renderFundVal(stock.cfo_pat, 1, '%')}</td>`;
            } else if (col.id === 'net_income_cr') {
                const niClass = stock.net_income_cr != null ? (stock.net_income_cr >= 0 ? 'val-up' : 'val-down') : '';
                html += `<td data-column="net_income_cr" class="text-right ${niClass}">₹${stock.net_income_cr != null ? stock.net_income_cr.toLocaleString('en-IN', {maximumFractionDigits: 0}) + ' Cr' : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'fcf_cr') {
                const fcfCrClass = stock.fcf_cr != null ? (stock.fcf_cr >= 0 ? 'val-up' : 'val-down') : '';
                html += `<td data-column="fcf_cr" class="text-right ${fcfCrClass}">₹${stock.fcf_cr != null ? stock.fcf_cr.toLocaleString('en-IN', {maximumFractionDigits: 0}) + ' Cr' : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'cfo_ebitda') {
                const cfoEbClass = stock.cfo_ebitda != null ? (stock.cfo_ebitda >= 70 ? 'val-up' : stock.cfo_ebitda < 40 ? 'val-down' : '') : '';
                html += `<td data-column="cfo_ebitda" class="text-right ${cfoEbClass}">${renderFundVal(stock.cfo_ebitda, 1, '%')}</td>`;
            } else if (col.id === 'wc_intensity') {
                const wcClass = stock.wc_intensity != null ? (stock.wc_intensity <= 15 ? 'val-up' : stock.wc_intensity > 30 ? 'val-down' : '') : '';
                const simBadge = stock.growth_data_source === "simulated" ? '<span class="sim-disclaimer" title="Simulated value" style="color: var(--color-warning, #f59e0b); font-size: 0.85em; margin-right: 2px; cursor: help;">~</span>' : '';
                html += `<td data-column="wc_intensity" class="text-right ${wcClass}">${simBadge}${renderFundVal(stock.wc_intensity, 1, '%')}</td>`;
            } else if (col.id === 'revenue_growth_qoq') {
                const qoqClass = stock.revenue_growth_qoq != null ? (stock.revenue_growth_qoq >= 4 ? 'val-up' : stock.revenue_growth_qoq < 1.5 ? 'val-down' : '') : '';
                html += `<td data-column="revenue_growth_qoq" class="text-right ${qoqClass}" style="font-weight:600;">${renderFundVal(stock.revenue_growth_qoq, 1, '%')}</td>`;
            } else if (col.id === 'revenue_growth_yoy') {
                const yoyClass = stock.revenue_growth_yoy != null ? (stock.revenue_growth_yoy >= 15 ? 'val-up' : stock.revenue_growth_yoy < 8 ? 'val-down' : '') : '';
                html += `<td data-column="revenue_growth_yoy" class="text-right ${yoyClass}" style="font-weight:600;">${renderFundVal(stock.revenue_growth_yoy, 1, '%')}</td>`;
            } else if (col.id === 'revenue_growth_3y') {
                const y3Class = stock.revenue_growth_3y != null ? (stock.revenue_growth_3y >= 15 ? 'val-up' : stock.revenue_growth_3y < 8 ? 'val-down' : '') : '';
                const simBadge = stock.growth_data_source === "simulated" ? '<span class="sim-disclaimer" title="Simulated value" style="color: var(--color-warning, #f59e0b); font-size: 0.85em; margin-right: 2px; cursor: help;">~</span>' : '';
                html += `<td data-column="revenue_growth_3y" class="text-right ${y3Class}" style="font-weight:600;">${simBadge}${renderFundVal(stock.revenue_growth_3y, 1, '%')}</td>`;
            } else if (col.id === 'ebitda_cagr') {
                const ecClass = stock.ebitda_cagr != null ? (stock.ebitda_cagr >= 15 ? 'val-up' : stock.ebitda_cagr < 8 ? 'val-down' : '') : '';
                const simBadge = stock.growth_data_source === "simulated" ? '<span class="sim-disclaimer" title="Simulated value" style="color: var(--color-warning, #f59e0b); font-size: 0.85em; margin-right: 2px; cursor: help;">~</span>' : '';
                html += `<td data-column="ebitda_cagr" class="text-right ${ecClass}">${simBadge}${renderFundVal(stock.ebitda_cagr, 1, '%')}</td>`;
            } else if (col.id === 'eps_cagr') {
                const epClass = stock.eps_cagr != null ? (stock.eps_cagr >= 15 ? 'val-up' : stock.eps_cagr < 8 ? 'val-down' : '') : '';
                const simBadge = stock.growth_data_source === "simulated" ? '<span class="sim-disclaimer" title="Simulated value" style="color: var(--color-warning, #f59e0b); font-size: 0.85em; margin-right: 2px; cursor: help;">~</span>' : '';
                html += `<td data-column="eps_cagr" class="text-right ${epClass}" style="font-weight:600;">${simBadge}${renderFundVal(stock.eps_cagr, 1, '%')}</td>`;
            } else if (col.id === 'bv_growth') {
                const bvClass = stock.bv_growth != null ? (stock.bv_growth >= 12 ? 'val-up' : stock.bv_growth < 6 ? 'val-down' : '') : '';
                html += `<td data-column="bv_growth" class="text-right ${bvClass}">${renderFundVal(stock.bv_growth, 1, '%')}</td>`;
            } else if (col.id === 'order_growth') {
                const ogClass = stock.order_growth != null ? (stock.order_growth >= 15 ? 'val-up' : '') : '';
                html += `<td data-column="order_growth" class="text-right ${ogClass}">${stock.order_growth != null ? stock.order_growth.toFixed(1) + '%' : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'segment_growth') {
                html += `<td data-column="segment_growth" class="text-left" style="font-size:0.75rem; color:var(--color-text-secondary); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:180px;" title="${stock.segment_growth || ''}">${stock.segment_growth != null ? stock.segment_growth : '<span class="val-na">—</span>'}</td>`;
            } else if (col.id === 'intraday_score') {
                const imsScore = stock.intraday_score != null ? stock.intraday_score : 0;
                const imsBand = stock.ims_band || 'weak';
                const imsBadgeClass = imsBand === 'strong' ? 'ims-strong' : imsBand === 'moderate' ? 'ims-moderate' : 'ims-weak';
                const imsBreakdown = (stock.ims_breakdown || []).join('\n');
                html += `
                    <td data-column="intraday_score" class="text-center">
                        <span class="ims-badge ${imsBadgeClass}" title="${escapeHtml(imsBreakdown)}">${imsScore}/10</span>
                    </td>
                `;
            } else if (col.id === 'swingscore') {
                const swingScore = stock.swingscore != null ? stock.swingscore : 0;
                const swingBand = stock.swingband || 'weak';
                const swingBadgeClass = 'badge-swing-' + swingBand;
                const swingBreakdown = (stock.swingbreakdown || []).join('\n');
                html += `
                    <td data-column="swingscore" class="text-center">
                        <span class="badge ${swingBadgeClass}" title="${escapeHtml(swingBreakdown)}" style="padding: 0.3rem 0.6rem; font-size: 0.75rem;">${swingScore}/10</span>
                    </td>
                `;
            } else if (col.id === 'days_in_scan') {
                const days = stock.days_in_scan || 0;
                let badgeClass = 'badge-neutral';
                if (days >= 3) badgeClass = 'badge-persistent';
                else if (days > 0) badgeClass = 'badge-fresh';
                
                html += `<td data-column="${col.id}" class="text-center"><span class="badge ${badgeClass}">${days}</span></td>`;
            } else if (col.id === 'first_seen') {
                const seen = stock.first_seen || 'New';
                html += `<td data-column="${col.id}" class="text-center" style="color:var(--color-text-secondary); font-size: 0.85rem;">${seen}</td>`;
            } else if (col.id === 'times_seen_20d') {
                const count = stock.times_seen_20d || 0;
                html += `<td data-column="${col.id}" class="text-center" style="font-weight: 600; color:var(--color-text-primary);">${count}</td>`;
            } else if (col.id === 're_entry') {
                const isReEntry = stock.re_entry;
                const entryHtml = isReEntry ? `<span title="Re-entry setup" style="font-size: 1.1rem;">🔄</span>` : '-';
                html += `<td data-column="${col.id}" class="text-center">${entryHtml}</td>`;
            } else if (col.id === 'upcoming_earnings') {
                const eDate = stock.upcoming_earnings;
                if (!eDate) {
                    html += `<td data-column="${col.id}" class="text-center" style="color:var(--color-text-secondary); font-size: 0.85rem;">-</td>`;
                } else {
                    const today = new Date();
                    const target = new Date(eDate);
                    const diffTime = target - today;
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                    
                    const formatted = target.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
                    
                    if (diffDays >= 0 && diffDays <= 5) {
                        // High risk - 5 days or less
                        html += `<td data-column="${col.id}" class="text-center"><span class="badge" style="background-color: rgba(232, 175, 52, 0.2); color: #e8af34; border: 1px solid rgba(232, 175, 52, 0.4);" title="Earnings in ${diffDays} days — consider waiting for post-earnings setup">⚠️ ${formatted}</span></td>`;
                    } else if (diffDays > 5 && diffDays <= 10) {
                        // Upcoming - 10 days or less
                        html += `<td data-column="${col.id}" class="text-center"><span class="badge badge-earnings-soon" title="Earnings in ${diffDays} day(s)">${formatted}</span></td>`;
                    } else {
                        html += `<td data-column="${col.id}" class="text-center" style="color:var(--color-text-primary); font-size: 0.9rem;">${formatted}</td>`;
                    }
                }
            } else if (col.id === 'action') {
                html += `
                    <td data-column="action" class="text-center" onclick="event.stopPropagation();">
                        <button class="btn-table-chart" onclick="openTradingView('${stock.clean_ticker}')">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
                            TradingView
                        </button>
                    </td>
                `;
            }
        });
        
        html += `</tr>`;
    });
    
    if (tableBody) tableBody.innerHTML = html;
    if (showingText) showingText.textContent = `Showing ${startIndex + 1}-${endIndex} of ${filteredStocks.length} matching stocks`;
    renderPagination(totalPages);
}

function renderPagination(totalPages) {
    const container = document.getElementById('pagination-controls');
    if (!container) return;
    
    if (totalPages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    container.innerHTML = `
        <button class="pagination-btn" id="btn-page-prev" ${currentPage === 1 ? 'disabled' : ''} title="Previous Page">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"></polyline></svg>
        </button>
        <span class="pagination-info">Page ${currentPage} / ${totalPages}</span>
        <button class="pagination-btn" id="btn-page-next" ${currentPage === totalPages ? 'disabled' : ''} title="Next Page">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
        </button>
    `;
    
    document.getElementById('btn-page-prev').addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            renderTable();
        }
    });
    
    document.getElementById('btn-page-next').addEventListener('click', () => {
        if (currentPage < totalPages) {
            currentPage++;
            renderTable();
        }
    });
}

function openTradingView(ticker) {
    window.open(`https://www.tradingview.com/chart/?symbol=NSE:${ticker}`, '_blank');
}

// Helper to escape HTML tags
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// Export filtered data as CSV (Only active columns in their current order)
function exportToExcel() {
    if (filteredStocks.length === 0) {
        alert("No stock data to export. Please run a scan first.");
        return;
    }
    
    if (typeof XLSX === 'undefined') {
        alert("Excel export library is loading, please try again in a moment.");
        return;
    }
    
    // Create a new workbook
    const wb = XLSX.utils.book_new();
    
    const tabs = ['overview', 'valuation', 'quality', 'growth'];
    const tabNames = {
        'overview': 'Overview',
        'valuation': 'Valuation',
        'quality': 'Quality',
        'growth': 'Growth'
    };
    
    tabs.forEach(tabId => {
        const colList = masterColumnsConfig[tabId];
        const headers = [];
        const fields = [];
        
        colList.forEach(col => {
            if (col.id !== 'action' && col.id !== 'day_range') {
                headers.push(col.name);
                fields.push(col.sortField || col.id);
            }
        });
        
        const sheetData = [];
        // Add headers row
        sheetData.push(headers);
        
        // Add stock data rows
        filteredStocks.forEach(stock => {
            const row = fields.map(f => {
                let val = stock[f];
                if (val === undefined || val === null) {
                    return '';
                }
                return val;
            });
            sheetData.push(row);
        });
        
        // Convert array of arrays to sheet
        const ws = XLSX.utils.aoa_to_sheet(sheetData);
        
        // Add sheet to workbook
        XLSX.utils.book_append_sheet(wb, ws, tabNames[tabId]);
    });
    
    // Add Trade Journal Sheet
    const journalData = getJournalData();
    if (journalData && journalData.length > 0) {
        const jHeaders = ['Date', 'Ticker', 'Setup', 'Swing Band', 'Entry', 'Stop', 'T1', 'T2', 'T3', 'Qty', 'Risk (₹)', 'Status', 'Exit Price', 'Exit Date', 'PnL (₹)', 'R-Achieved', 'Notes'];
        const jSheetData = [jHeaders];
        
        journalData.forEach(t => {
            jSheetData.push([
                t.date, t.ticker, t.setupLabel, t.swingband,
                t.entry, t.stop, t.target1, t.target2, t.target3,
                t.qty, t.riskAmount, t.status, t.exitPrice || '',
                t.exitDate || '', t.pnl || '', t.rAchieved || '',
                t.notes || ''
            ]);
        });
        
        const jws = XLSX.utils.aoa_to_sheet(jSheetData);
        XLSX.utils.book_append_sheet(wb, jws, 'Trade Journal');
    }
    
    // Generate buffer and trigger download
    const dateStr = new Date().toISOString().slice(0, 10);
    XLSX.writeFile(wb, `NSE_Momentum_Screener_Export_${dateStr}.xlsx`);
}

// Dynamic Column Management System
function initColumns() {
    const storageKey = `tv_columns_config_${currentTab}`;
    const savedConfig = localStorage.getItem(storageKey);
    if (savedConfig) {
        try {
            const parsed = JSON.parse(savedConfig);
            if (parsed && Array.isArray(parsed) && parsed.length > 0) {
                // Ensure all items in default columnsConfig are in parsed config
                const defaultIds = masterColumnsConfig[currentTab].map(c => c.id);
                const validParsed = parsed.filter(item => defaultIds.includes(item.id));
                
                // Sync sortField and other default settings from master configuration to prevent stale values in localStorage
                validParsed.forEach(col => {
                    const defaultCol = masterColumnsConfig[currentTab].find(c => c.id === col.id);
                    if (defaultCol) {
                        col.sortField = defaultCol.sortField;
                        col.tooltip = defaultCol.tooltip;
                        col.name = defaultCol.name;
                        col.align = defaultCol.align;
                    }
                });
                
                const parsedIds = validParsed.map(c => c.id);
                
                // Add any missing default columns to the end
                masterColumnsConfig[currentTab].forEach(defaultCol => {
                    if (!parsedIds.includes(defaultCol.id)) {
                        validParsed.push(defaultCol);
                    }
                });
                columnsConfig = validParsed;
                masterColumnsConfig[currentTab] = columnsConfig;
            }
        } catch (e) {
            console.error("Error reading columns config from localStorage:", e);
        }
    }
    
    applyColumnVisibilityAndOrder();
}

function saveColumnsConfig() {
    const storageKey = `tv_columns_config_${currentTab}`;
    localStorage.setItem(storageKey, JSON.stringify(columnsConfig));
}

function applyColumnVisibilityAndOrder() {
    renderColumnDropdown();
    renderTableHeader();
    renderTable();
}

// Render dynamic column selector checkboxes in dropdown
function renderColumnDropdown() {
    const container = document.getElementById('column-checkboxes');
    if (!container) return;
    
    container.innerHTML = '';
    
    columnsConfig.forEach(col => {
        if (!col.canToggle) return;
        
        const dragItem = document.createElement('div');
        dragItem.className = 'column-drag-item';
        dragItem.dataset.columnId = col.id;
        dragItem.draggable = true;
        
        dragItem.innerHTML = `
            <span class="drag-handle" title="Drag to reorder column">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="12" r="1.5"></circle><circle cx="9" cy="5" r="1.5"></circle><circle cx="9" cy="19" r="1.5"></circle><circle cx="15" cy="12" r="1.5"></circle><circle cx="15" cy="5" r="1.5"></circle><circle cx="15" cy="19" r="1.5"></circle></svg>
            </span>
            <label style="display:flex; align-items:center; gap:0.6rem; font-size:0.85rem; font-weight:500; cursor:pointer; width:100%;">
                <input type="checkbox" data-column-toggle="${col.id}" ${col.isVisible ? 'checked' : ''} style="margin:0;">
                <span>${col.name}</span>
            </label>
        `;
        
        const checkbox = dragItem.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('change', () => {
            col.isVisible = checkbox.checked;
            saveColumnsConfig();
            applyColumnVisibilityAndOrder();
        });
        
        checkbox.addEventListener('click', (e) => {
            e.stopPropagation();
        });
        
        // Dropdown drag listeners
        dragItem.addEventListener('dragstart', handleColDropdownDragStart);
        dragItem.addEventListener('dragover', handleColDropdownDragOver);
        dragItem.addEventListener('dragleave', handleColDropdownDragLeave);
        dragItem.addEventListener('drop', handleColDropdownDrop);
        dragItem.addEventListener('dragend', handleColDropdownDragEnd);
        
        container.appendChild(dragItem);
    });
}

// Dropdown Drag Event Handlers
let dropdownDragSrcEl = null;

function handleColDropdownDragStart(e) {
    dropdownDragSrcEl = this;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.columnId);
    this.classList.add('dragging');
}

function handleColDropdownDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    this.classList.add('drag-over');
    return false;
}

function handleColDropdownDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleColDropdownDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    const srcId = e.dataTransfer.getData('text/plain') || (dropdownDragSrcEl ? dropdownDragSrcEl.dataset.columnId : null);
    const targetId = this.dataset.columnId;
    
    if (srcId && targetId && srcId !== targetId) {
        const srcIndex = columnsConfig.findIndex(c => c.id === srcId);
        const targetIndex = columnsConfig.findIndex(c => c.id === targetId);
        
        if (srcIndex !== -1 && targetIndex !== -1) {
            const [movedCol] = columnsConfig.splice(srcIndex, 1);
            columnsConfig.splice(targetIndex, 0, movedCol);
            
            saveColumnsConfig();
            applyColumnVisibilityAndOrder();
        }
    }
    return false;
}

function handleColDropdownDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('.column-drag-item').forEach(item => {
        item.classList.remove('drag-over');
    });
}

// Render dynamic table headers
function renderTableHeader() {
    const headerRow = document.getElementById('table-header-row');
    if (!headerRow) return;
    
    headerRow.innerHTML = '';
    
    let visibleIndex = 0;
    columnsConfig.forEach(col => {
        if (!col.isVisible) return;
        
        const th = document.createElement('th');
        th.dataset.column = col.id;
        
        if (col.sortField) {
            th.dataset.sort = col.sortField;
            th.addEventListener('click', () => handleSort(col.sortField, th));
        }
        
        if (col.align === 'right') {
            th.className = 'text-right';
        } else if (col.align === 'center') {
            th.className = 'text-center';
        }
        
        if (col.sortField === currentSortField) {
            th.classList.add(currentSortOrder === 'desc' ? 'sort-desc' : 'sort-asc');
        }
        
        th.textContent = col.name;
        
        if (col.tooltip) {
            th.setAttribute('title', col.tooltip);
            th.style.textDecoration = 'underline dotted rgba(255, 255, 255, 0.4)';
            th.style.textUnderlineOffset = '4px';
        }
        
        th.setAttribute('draggable', 'true');
        
        // Header drag listeners
        th.addEventListener('dragstart', handleHeaderDragStart);
        th.addEventListener('dragover', handleHeaderDragOver);
        th.addEventListener('dragleave', handleHeaderDragLeave);
        th.addEventListener('drop', handleHeaderDrop);
        th.addEventListener('dragend', handleHeaderDragEnd);
        
        if (visibleIndex === 0 || visibleIndex === 1) {
            const resizer = document.createElement('div');
            resizer.classList.add('col-resizer');
            resizer.addEventListener('mousedown', initColumnResize);
            resizer.dataset.colIdx = visibleIndex;
            th.appendChild(resizer);
        }
        
        visibleIndex++;
        headerRow.appendChild(th);
    });
}

// Header Drag Event Handlers
let isDraggingHeader = false;
let headerDragSrcId = null;

function handleHeaderDragStart(e) {
    isDraggingHeader = true;
    headerDragSrcId = this.dataset.column;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', this.dataset.column);
    this.classList.add('dragging');
}

function handleHeaderDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    if (this.dataset.column !== headerDragSrcId) {
        this.classList.add('drag-over');
    }
    return false;
}

// Recalculate colspan for full-width states (loading, empty, error)
function handleHeaderDragLeave(e) {
    this.classList.remove('drag-over');
}

function handleHeaderDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    const srcId = e.dataTransfer.getData('text/plain') || headerDragSrcId;
    const targetId = this.dataset.column;
    
    if (srcId && targetId && srcId !== targetId) {
        const srcIndex = columnsConfig.findIndex(c => c.id === srcId);
        const targetIndex = columnsConfig.findIndex(c => c.id === targetId);
        
        if (srcIndex !== -1 && targetIndex !== -1) {
            const [movedCol] = columnsConfig.splice(srcIndex, 1);
            columnsConfig.splice(targetIndex, 0, movedCol);
            
            saveColumnsConfig();
            applyColumnVisibilityAndOrder();
        }
    }
    return false;
}

function handleHeaderDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('.screener-table th').forEach(th => {
        th.classList.remove('drag-over');
    });
    
    setTimeout(() => {
        isDraggingHeader = false;
    }, 100);
}

// Watchlist Management
let watchlistStocks = [];
let watchlistSections = [];
let watchlistDataMap = {};
let watchlistCurrentPage = 1;
const watchlistItemsPerPage = 10;
let activeNewsFilter = 'all'; // 'all' or ticker symbol
let showWatchlistKronosColumns = false;
let watchlistKronosRankings = {};
let isKronosBatchSorting = false;
let isWatchlistLoaded = false;
let lastKronosSortTime = 0;
const KRONOS_SORT_COOLDOWN_MS = 5 * 60 * 1000; // 5-minute cooldown

// ── Kronos Forecast Config ──
const KRONOS_FORECAST_HORIZON = 5;  // Forecast horizon: 3, 5, or 10 sessions

// Toast system for styled notification messages
function showToast(message, type = 'info') {
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.style.cssText = 'position: fixed; bottom: 20px; right: 20px; display: flex; flex-direction: column; gap: 10px; z-index: 10000;';
        document.body.appendChild(toastContainer);
    }
    
    const toast = document.createElement('div');
    toast.className = 'glass-panel';
    const borderCol = type === 'error' ? 'rgba(239, 68, 68, 0.4)' : type === 'success' ? 'rgba(16, 185, 129, 0.4)' : 'rgba(255, 255, 255, 0.1)';
    const textCol = type === 'error' ? '#f87171' : type === 'success' ? '#34d399' : 'var(--color-text-primary)';
    const icon = type === 'error' ? '⚠️' : type === 'success' ? '✅' : 'ℹ️';
    
    toast.style.cssText = `
        padding: 0.8rem 1.2rem;
        background: rgba(15, 23, 42, 0.85);
        border: 1px solid ${borderCol};
        border-radius: var(--radius-md, 8px);
        color: ${textCol};
        font-size: 0.85rem;
        font-weight: 500;
        display: flex;
        align-items: center;
        gap: 0.6rem;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
        backdrop-filter: blur(12px);
        animation: fadeSlideIn 0.3s ease-out forwards;
        min-width: 250px;
        max-width: 380px;
    `;
    
    toast.innerHTML = `<span>${icon}</span><span style="flex-grow:1;">${message}</span>`;
    toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.5s ease-out forwards';
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}

function fetchWatchlistFromBackend() {
    fetch('/api/watchlist')
        .then(res => res.json())
        .then(data => {
            if (Array.isArray(data)) {
                const savedOrder = localStorage.getItem('tv_watchlist_sections_order');
                if (savedOrder) {
                    try {
                        const orderArray = JSON.parse(savedOrder);
                        data.sort((a, b) => {
                            const idxA = orderArray.indexOf(a.id);
                            const idxB = orderArray.indexOf(b.id);
                            if (idxA === -1 && idxB === -1) return 0;
                            if (idxA === -1) return 1;
                            if (idxB === -1) return -1;
                            return idxA - idxB;
                        });
                    } catch (e) {}
                }
                watchlistSections = data;
                
                if (watchlistSections.length === 0) {
                    const defaultId = 'sec-main';
                    watchlistSections = [{
                        id: defaultId,
                        name: 'Main Watchlist',
                        stocks: [],
                        collapsed: false
                    }];
                    fetch('/api/watchlist/sections', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: defaultId, name: 'Main Watchlist' })
                    });
                }
                syncWatchlistStocksFlat();
                renderWatchlist();
                renderAnnouncements();
                
                isWatchlistLoaded = true;
                const btnKronosBatchSort = document.getElementById('btn-kronos-batch-sort');
                if (btnKronosBatchSort) {
                    btnKronosBatchSort.disabled = false;
                }
            }
        })
        .catch(err => {
            console.error("Error loading watchlist from backend:", err);
        });
}

function fetchJournalFromBackend() {
    fetch('/api/journal')
        .then(res => res.json())
        .then(data => {
            if (Array.isArray(data)) {
                journalData = data;
                renderJournal();
            }
        })
        .catch(err => console.error("Error loading journal from backend:", err));
}

function initWatchlist() {
    // Check if migration to SQLite backend is complete
    const migrationComplete = localStorage.getItem('tv_migration_complete');
    if (!migrationComplete) {
        const legacySections = localStorage.getItem('tv_watchlist_sections');
        const legacyJournal = localStorage.getItem('tvTradeJournal');
        
        if (legacySections || legacyJournal) {
            const payload = {
                watchlist_sections: legacySections ? JSON.parse(legacySections) : [],
                journal: legacyJournal ? JSON.parse(legacyJournal) : []
            };
            
            fetch('/api/migrate-local-data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(resData => {
                if (resData.success) {
                    localStorage.setItem('tv_migration_complete', 'true');
                    localStorage.removeItem('tv_watchlist_sections');
                    localStorage.removeItem('tv_watchlist_stocks');
                    localStorage.removeItem('tvTradeJournal');
                    console.log("Migration of watchlists and journals to SQLite database complete.");
                }
                fetchWatchlistFromBackend();
                fetchJournalFromBackend();
            })
            .catch(err => {
                console.error("Migration error:", err);
                fetchWatchlistFromBackend();
                fetchJournalFromBackend();
            });
        } else {
            localStorage.setItem('tv_migration_complete', 'true');
            fetchWatchlistFromBackend();
            fetchJournalFromBackend();
        }
    } else {
        fetchWatchlistFromBackend();
        fetchJournalFromBackend();
    }
    
    // Setup manual add button toggles
    const btnAddWatchlistManual = document.getElementById('btn-add-watchlist-manual');
    const watchlistAddBox = document.getElementById('watchlist-add-box');
    const btnSubmitWatchlistManual = document.getElementById('btn-submit-watchlist-manual');
    const watchlistManualInput = document.getElementById('watchlist-manual-input');
    
    if (btnAddWatchlistManual && watchlistAddBox) {
        btnAddWatchlistManual.addEventListener('click', (e) => {
            e.stopPropagation();
            watchlistAddBox.classList.toggle('hidden');
            if (!watchlistAddBox.classList.contains('hidden')) {
                watchlistManualInput.focus();
            }
        });
    }

    // Toggle AI columns button
    const btnKronosColumnToggle = document.getElementById('btn-kronos-column-toggle');
    if (btnKronosColumnToggle) {
        btnKronosColumnToggle.addEventListener('click', (e) => {
            e.stopPropagation();
            showWatchlistKronosColumns = !showWatchlistKronosColumns;
            btnKronosColumnToggle.style.color = showWatchlistKronosColumns ? '#f59e0b' : 'var(--color-text-secondary)';
            renderWatchlist();
        });
    }

    // Kronos batch sort button
    const btnKronosBatchSort = document.getElementById('btn-kronos-batch-sort');
    if (btnKronosBatchSort) {
        if (!isWatchlistLoaded) {
            btnKronosBatchSort.disabled = true;
        }
        btnKronosBatchSort.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (isKronosBatchSorting) return;

            const now = Date.now();
            if (now - lastKronosSortTime < KRONOS_SORT_COOLDOWN_MS) {
                const remainingSecs = Math.ceil((KRONOS_SORT_COOLDOWN_MS - (now - lastKronosSortTime)) / 1000);
                const mins = Math.floor(remainingSecs / 60);
                const secs = remainingSecs % 60;
                if (typeof showToast === 'function') {
                    showToast(`Sort is on cooldown. Please wait ${mins}m ${secs}s before running again.`, "info");
                }
                return;
            }

            // 1. Immediately disable and set loading state to prevent double clicks
            btnKronosBatchSort.disabled = true;
            isKronosBatchSorting = true;
            showWatchlistKronosColumns = true;
            
            if (btnKronosColumnToggle) btnKronosColumnToggle.style.color = '#f59e0b';
            
            const originalSortBtnHtml = btnKronosBatchSort.innerHTML;
            btnKronosBatchSort.innerHTML = `<span class="btn-spinner"></span>`;
            
            renderWatchlist();

            try {
                const response = await fetch(`/api/watchlist/kronos-ranking?pred_len=${KRONOS_FORECAST_HORIZON}`);
                if (!response.ok) {
                    throw new Error(`Failed to fetch rankings: ${response.statusText}`);
                }
                const data = await response.json();
                
                if (data && data.sections) {
                    lastKronosSortTime = Date.now();
                    if (data.partial && typeof showToast === 'function') {
                        showToast(`Sort completed: ${data.missing_count} tickers timed out and moved to the bottom.`, "warning");
                    }
                    
                    // Reset stale rankings ONLY now, upon successful response
                    watchlistKronosRankings = {};
                    
                    data.sections.forEach(sec => {
                        sec.rankings.forEach(r => {
                            watchlistKronosRankings[r.ticker] = {
                                rank: r.rank,
                                predicted_return_pct: r.predicted_return_pct,
                                ai_forecast_bias: r.ai_forecast_bias,
                                ai_confidence_score: r.ai_confidence_score,
                                cache_hit: r.cache_hit
                            };
                        });

                        const section = watchlistSections.find(s => s.id === sec.id);
                        if (section && sec.rankings.length > 0) {
                            const apiOrder = sec.rankings.map(r => r.ticker);
                            const remaining = section.stocks.filter(s => !apiOrder.includes(s));
                            section.stocks = [...apiOrder, ...remaining];
                        }
                    });

                    // Trigger Smart Alert Engine for Kronos forecast spikes
                    if (typeof AlertEngine !== 'undefined') {
                        const wlSymbols = new Set((watchlistStocks || []).map(s => s.split(':').pop().toUpperCase()));
                        AlertEngine.checkKronosSpikes(watchlistKronosRankings, wlSymbols);
                    }

                    const saveFunc = window.saveWatchlistSections || (typeof saveWatchlistSections === 'function' ? saveWatchlistSections : null);
                    if (saveFunc) {
                        saveFunc(true);
                    } else {
                        throw new Error('[Kronos Sort] saveWatchlistSections is not defined');
                    }
                    
                    // Show last sorted timestamp suggestion
                    const lastSortedEl = document.getElementById('kronos-last-sorted');
                    if (lastSortedEl) {
                        const now = new Date();
                        const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                        lastSortedEl.textContent = `Last sorted: ${timeStr}`;
                        lastSortedEl.style.display = 'block';
                    }
                }
            } catch (err) {
                console.error("Kronos batch sorting error:", err);
                // Reset visual state so user knows the sort failed
                showWatchlistKronosColumns = false;
                if (btnKronosColumnToggle) {
                    btnKronosColumnToggle.style.color = 'var(--color-text-secondary)';
                }
                // Use inline toast/error badge instead of blocking alert()
                const errBadge = document.getElementById('kronos-sort-error-badge');
                if (errBadge) {
                    errBadge.textContent = '⚠ Sort failed — retry';
                    errBadge.style.display = 'inline';
                    setTimeout(() => { errBadge.style.display = 'none'; }, 4000);
                } else {
                    alert("Kronos sort failed: " + err.message);  // fallback only
                }
            } finally {
                isKronosBatchSorting = false;
                btnKronosBatchSort.disabled = false;
                btnKronosBatchSort.innerHTML = originalSortBtnHtml;
                renderWatchlist();
            }
        });
    }
    
    if (btnSubmitWatchlistManual) {
        btnSubmitWatchlistManual.addEventListener('click', () => {
            submitManualWatchlist();
        });
    }
    
    if (watchlistManualInput) {
        watchlistManualInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                submitManualWatchlist();
            }
        });
    }
    
    // Setup global Add Section controls
    const btnAddSectionGlobal = document.getElementById('btn-add-section-global');
    const globalAddSectionBox = document.getElementById('global-add-section-box');
    const btnSubmitGlobalSection = document.getElementById('btn-submit-global-section');
    const globalAddSectionInput = document.getElementById('global-add-section-input');
    
    if (btnAddSectionGlobal && globalAddSectionBox) {
        btnAddSectionGlobal.addEventListener('click', (e) => {
            e.stopPropagation();
            globalAddSectionBox.classList.toggle('hidden');
            if (!globalAddSectionBox.classList.contains('hidden')) {
                globalAddSectionInput.focus();
            }
        });
    }
    
    if (btnSubmitGlobalSection) {
        btnSubmitGlobalSection.addEventListener('click', () => {
            submitGlobalSection();
        });
    }
    
    if (globalAddSectionInput) {
        globalAddSectionInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                submitGlobalSection();
            }
        });
    }
    
    // News filter select listener
    const newsFilterSelect = document.getElementById('news-filter-select');
    if (newsFilterSelect) {
        newsFilterSelect.addEventListener('change', (e) => {
            activeNewsFilter = e.target.value;
            renderAnnouncements();
        });
    }

    // Close any floating popup menu on body click
    document.addEventListener('click', () => {
        const menu = document.getElementById('screener-add-to-section-menu');
        if (menu) {
            menu.remove();
        }
    });
} // Closing initWatchlist

function normalizeBias(rawBias) {
    if (!rawBias) return 'Sideways Consolidation';
    const lower = rawBias.toLowerCase();
    if (lower.includes('breakout')) return 'Strong Breakout';
    if (lower.includes('bullish') || lower.includes('continuation')) return 'Bullish Continuation';
    if (lower.includes('downtrend') || lower.includes('strong downtrend') || lower.includes('strong down')) return 'Strong Downtrend';
    if (lower.includes('bearish') || lower.includes('pressure')) return 'Bearish Pressure';
    return 'Sideways Consolidation';
}

async function saveWatchlistSections(force = false) {
    if (!isWatchlistLoaded) {
        console.warn('[Watchlist Save] Save skipped: Watchlist not loaded.');
        return;
    }
    if (isKronosBatchSorting && !force) {
        console.warn('[Watchlist Save] Save skipped: Kronos sort in progress.');
        return;
    }
    const order = watchlistSections.map(s => s.id);
    localStorage.setItem('tv_watchlist_sections_order', JSON.stringify(order));
    syncWatchlistStocksFlat();
    
    try {
        await fetch('/api/watchlist/sections/reorder', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ order })
        });
    } catch (err) {
        console.error('[Watchlist Sync] Failed to save section order to backend database:', err);
    }

    // Persist stock order per section to backend
    watchlistSections.forEach(sec => {
        if (sec.stocks && Array.isArray(sec.stocks)) {
            fetch(`/api/watchlist/sections/${sec.id}/reorder`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stocks: sec.stocks })
            }).catch(err => console.error(`[WL] Failed to persist order for section ${sec.id}:`, err));
        }
    });
}
window.saveWatchlistSections = saveWatchlistSections;

function syncWatchlistStocksFlat() {
    const allSyms = new Set();
    watchlistSections.forEach(sec => {
        if (sec.stocks && Array.isArray(sec.stocks)) {
            sec.stocks.forEach(sym => allSyms.add(sym.toUpperCase()));
        }
    });
    watchlistStocks = Array.from(allSyms);
    localStorage.setItem('tv_watchlist_stocks', JSON.stringify(watchlistStocks));
}

function submitGlobalSection() {
    const input = document.getElementById('global-add-section-input');
    if (!input) return;
    const name = input.value.trim();
    if (!name) return;
    
    const newSecId = 'sec-' + Date.now();
    const newSec = {
        id: newSecId,
        name: name,
        stocks: [],
        collapsed: false
    };
    
    fetch('/api/watchlist/sections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: newSecId, name: name })
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            watchlistSections.push(newSec);
            saveWatchlistSections();
            renderWatchlist();
        } else {
            alert("Failed to create section: " + resData.error);
        }
    })
    .catch(err => console.error("Error creating section:", err));
    
    input.value = '';
    const box = document.getElementById('global-add-section-box');
    if (box) box.classList.add('hidden');
}

function deleteSection(sectionId) {
    const sec = watchlistSections.find(s => s.id === sectionId);
    if (!sec) return;
    
    if (confirm(`Are you sure you want to delete the section "${sec.name}"? All stocks in it will be removed from this section.`)) {
        fetch(`/api/watchlist/sections/${sectionId}`, {
            method: 'DELETE'
        })
        .then(res => res.json())
        .then(resData => {
            if (resData.success) {
                watchlistSections = watchlistSections.filter(s => s.id !== sectionId);
                // If empty, auto create default
                if (watchlistSections.length === 0) {
                    const defaultId = 'sec-main';
                    const defaultSec = {
                        id: defaultId,
                        name: 'Main Watchlist',
                        stocks: [],
                        collapsed: false
                    };
                    fetch('/api/watchlist/sections', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ id: defaultId, name: 'Main Watchlist' })
                    })
                    .then(r => r.json())
                    .then(d => {
                        if (d.success) {
                            watchlistSections.push(defaultSec);
                            saveWatchlistSections();
                            renderWatchlist();
                            renderAnnouncements();
                        }
                    });
                } else {
                    saveWatchlistSections();
                    renderWatchlist();
                    renderAnnouncements();
                }
            } else {
                alert("Failed to delete section: " + resData.error);
            }
        })
        .catch(err => console.error("Error deleting section:", err));
    }
}

function moveSection(sectionId, direction) {
    if (!isWatchlistLoaded || isKronosBatchSorting) return;
    const index = watchlistSections.findIndex(s => s.id === sectionId);
    if (index === -1) return;
    
    if (direction === 'up' && index > 0) {
        const temp = watchlistSections[index];
        watchlistSections[index] = watchlistSections[index - 1];
        watchlistSections[index - 1] = temp;
    } else if (direction === 'down' && index < watchlistSections.length - 1) {
        const temp = watchlistSections[index];
        watchlistSections[index] = watchlistSections[index + 1];
        watchlistSections[index + 1] = temp;
    } else {
        return;
    }
    
    saveWatchlistSections();
    renderWatchlist();
}

function toggleSectionCollapse(sectionId, event) {
    if (event.target.closest('.section-actions') || event.target.closest('.section-add-box') || event.target.closest('input')) {
        return;
    }
    
    const sec = watchlistSections.find(s => s.id === sectionId);
    if (sec) {
        sec.collapsed = !sec.collapsed;
        saveWatchlistSections();
        renderWatchlist();
    }
}

function startRenameSection(sectionId, element) {
    const sec = watchlistSections.find(s => s.id === sectionId);
    if (!sec) return;
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'section-name-input';
    input.value = sec.name;
    
    element.replaceWith(input);
    input.focus();
    input.select();
    
    let finished = false;
    const saveRename = () => {
        if (finished) return;
        finished = true;
        const newName = input.value.trim();
        if (newName && newName !== sec.name) {
            fetch(`/api/watchlist/sections/${sectionId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            })
            .then(res => res.json())
            .then(resData => {
                if (resData.success) {
                    sec.name = newName;
                    saveWatchlistSections();
                    renderWatchlist();
                } else {
                    alert("Failed to rename section: " + resData.error);
                    renderWatchlist();
                }
            })
            .catch(err => {
                console.error("Error renaming section:", err);
                renderWatchlist();
            });
        } else {
            renderWatchlist();
        }
    };
    
    input.addEventListener('blur', saveRename);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            saveRename();
        } else if (e.key === 'Escape') {
            finished = true;
            renderWatchlist();
        }
    });
}

function submitManualWatchlist() {
    const input = document.getElementById('watchlist-manual-input');
    if (!input) return;
    const ticker = input.value.trim().toUpperCase();
    if (!ticker) return;
    
    // Add to first section by default
    if (watchlistSections.length > 0) {
        addStockToSection(watchlistSections[0].id, ticker);
    }
    input.value = '';
    document.getElementById('watchlist-add-box').classList.add('hidden');
}

function addToWatchlist(ticker, event) {
    if (watchlistSections.length === 1) {
        addStockToSection(watchlistSections[0].id, ticker);
        return;
    }
    showAddToSectionMenu(ticker, event);
}

function showAddToSectionMenu(ticker, event) {
    const existingMenu = document.getElementById('screener-add-to-section-menu');
    if (existingMenu) existingMenu.remove();
    
    const menu = document.createElement('div');
    menu.id = 'screener-add-to-section-menu';
    menu.className = 'floating-add-menu glass-panel';
    
    const posX = event.clientX + window.scrollX;
    const posY = event.clientY + window.scrollY;
    menu.style.left = `${posX}px`;
    menu.style.top = `${posY}px`;
    
    let html = `<div class="floating-menu-header">Add ${ticker} to:</div>`;
    watchlistSections.forEach(sec => {
        html += `
            <div class="floating-menu-item" onclick="event.stopPropagation(); addStockToSection('${sec.id}', '${ticker}'); document.getElementById('screener-add-to-section-menu').remove();">
                <span>${escapeHtml(sec.name)}</span>
                <span class="floating-menu-item-count">${sec.stocks.length}</span>
            </div>
        `;
    });
    menu.innerHTML = html;
    
    document.body.appendChild(menu);
    event.stopPropagation();
}

function addStockToSection(sectionId, ticker) {
    ticker = ticker.toUpperCase().trim();
    const sec = watchlistSections.find(s => s.id === sectionId);
    if (!sec) return;
    
    if (sec.stocks.includes(ticker)) {
        alert(`${ticker} is already in this section.`);
        return;
    }
    
    const currentFlat = Array.from(new Set(watchlistSections.flatMap(s => s.stocks)));
    if (currentFlat.length >= 50 && !currentFlat.includes(ticker)) {
        alert("Watchlist limit reached. You can add up to 50 unique stocks across all sections.");
        return;
    }
    
    fetch('/api/watchlist/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section_id: sectionId, ticker: ticker })
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            sec.stocks.push(ticker);
            sec.collapsed = false;
            saveWatchlistSections();
            renderWatchlist();
            selectWatchlistStock(ticker);
            fetchWatchlistSingle(ticker);
            renderAnnouncements();
        } else {
            alert("Failed to add stock: " + resData.error);
        }
    })
    .catch(err => console.error("Error adding stock to watchlist:", err));
}

function removeStockFromSection(sectionId, ticker) {
    const e = window.event;
    if (e && e.stopPropagation) {
        e.stopPropagation();
    }
    
    const sec = watchlistSections.find(s => s.id === sectionId);
    if (!sec) return;
    
    fetch('/api/watchlist/items', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ section_id: sectionId, ticker: ticker })
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            const originalLength = sec.stocks.length;
            sec.stocks = sec.stocks.filter(s => s.toUpperCase() !== ticker.toUpperCase());
            
            if (sec.stocks.length !== originalLength) {
                saveWatchlistSections();
                
                const row = document.querySelector(`.watchlist-row[data-symbol="${ticker}"][data-section-id="${sectionId}"]`);
                if (row) {
                    row.style.transition = 'all 0.3s ease';
                    row.style.opacity = '0';
                    row.style.transform = 'translateX(20px)';
                    setTimeout(() => {
                        renderWatchlist();
                    }, 250);
                } else {
                    renderWatchlist();
                }
                
                if (activeNewsFilter === ticker) {
                    resetWatchlistDetails();
                } else {
                    renderAnnouncements();
                }
            }
        } else {
            alert("Failed to remove stock: " + resData.error);
        }
    })
    .catch(err => console.error("Error removing stock from watchlist:", err));
}

async function updateWatchlistData() {
    if (watchlistStocks.length === 0) {
        renderWatchlist();
        renderAnnouncements();
        return;
    }
    
    try {
        const response = await fetch('/api/fetch_symbols', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ symbols: watchlistStocks })
        });
        
        if (response.ok) {
            const result = await response.json();
            const fetchedStocks = result.stocks || [];
            
            watchlistDataMap = {};
            fetchedStocks.forEach(stock => {
                applyImsSectorAdjustment(stock);
                watchlistDataMap[stock.clean_ticker] = stock;
            });
        }
    } catch (e) {
        console.error("Error fetching watchlist data:", e);
    }
    
    renderWatchlist();
    renderAnnouncements();
}

function formatVolume(vol) {
    if (vol === undefined || vol === null) return '-';
    vol = parseFloat(vol);
    if (vol >= 1000000) {
        return (vol / 1000000).toFixed(2) + 'M';
    }
    if (vol >= 1000) {
        return (vol / 1000).toFixed(2) + 'K';
    }
    return vol.toString();
}

function renderWatchlist() {
    const sectionsContainer = document.getElementById('watchlist-sections');
    const watchlistCount = document.getElementById('watchlist-count');
    
    if (!sectionsContainer) return;
    sectionsContainer.innerHTML = '';
    
    watchlistCount.textContent = `${watchlistStocks.length} / 50`;
    
    watchlistSections.forEach((section, secIdx) => {
        const secCard = document.createElement('div');
        secCard.className = `watchlist-section-card`;
        secCard.dataset.sectionId = section.id;
        
        const header = document.createElement('div');
        header.className = 'section-header';
        header.addEventListener('click', (e) => toggleSectionCollapse(section.id, e));
        
        const titleWrap = document.createElement('div');
        titleWrap.className = 'section-title-wrap';
        
        const toggleBtn = document.createElement('span');
        toggleBtn.className = `section-toggle-btn ${section.collapsed ? 'collapsed' : ''}`;
        toggleBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
        
        const titleSpan = document.createElement('span');
        titleSpan.className = 'section-name';
        titleSpan.textContent = section.name;
        titleSpan.title = "Double-click to rename";
        titleSpan.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            startRenameSection(section.id, titleSpan);
        });
        
        const countSpan = document.createElement('span');
        countSpan.className = 'section-count';
        countSpan.textContent = section.stocks.length;
        
        titleWrap.appendChild(toggleBtn);
        titleWrap.appendChild(titleSpan);
        titleWrap.appendChild(countSpan);
        
        const actions = document.createElement('div');
        actions.className = 'section-actions';
        
        const btnAdd = document.createElement('button');
        btnAdd.className = 'section-act-btn btn-add-to-section';
        btnAdd.title = "Add Stock";
        btnAdd.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>`;
        btnAdd.addEventListener('click', (e) => {
            e.stopPropagation();
            const addBox = secCard.querySelector('.section-add-box');
            if (addBox) {
                addBox.classList.toggle('hidden');
                if (!addBox.classList.contains('hidden')) {
                    addBox.querySelector('.section-add-input').focus();
                }
            }
        });
        
        const btnRename = document.createElement('button');
        btnRename.className = 'section-act-btn btn-rename-section';
        btnRename.title = "Rename Section";
        btnRename.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>`;
        btnRename.addEventListener('click', (e) => {
            e.stopPropagation();
            startRenameSection(section.id, titleSpan);
        });
        
        const btnUp = document.createElement('button');
        btnUp.className = 'section-act-btn btn-move-sec-up';
        btnUp.title = "Move Up";
        btnUp.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"></polyline></svg>`;
        if (secIdx === 0) btnUp.style.opacity = '0.35';
        btnUp.addEventListener('click', (e) => {
            e.stopPropagation();
            moveSection(section.id, 'up');
        });
        
        const btnDown = document.createElement('button');
        btnDown.className = 'section-act-btn btn-move-sec-down';
        btnDown.title = "Move Down";
        btnDown.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"></polyline></svg>`;
        if (secIdx === watchlistSections.length - 1) btnDown.style.opacity = '0.35';
        btnDown.addEventListener('click', (e) => {
            e.stopPropagation();
            moveSection(section.id, 'down');
        });
        
        const btnDel = document.createElement('button');
        btnDel.className = 'section-act-btn btn-del-section';
        btnDel.title = "Delete Section";
        btnDel.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
        btnDel.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSection(section.id);
        });
        
        actions.appendChild(btnAdd);
        actions.appendChild(btnRename);
        actions.appendChild(btnUp);
        actions.appendChild(btnDown);
        actions.appendChild(btnDel);
        
        header.appendChild(titleWrap);
        header.appendChild(actions);
        secCard.appendChild(header);
        
        const sAddBox = document.createElement('div');
        sAddBox.className = 'section-add-box hidden';
        
        const sAddInput = document.createElement('input');
        sAddInput.type = 'text';
        sAddInput.className = 'section-add-input';
        sAddInput.placeholder = 'Type NSE Ticker (e.g. INFY)...';
        sAddInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                const val = sAddInput.value.trim().toUpperCase();
                if (val) {
                    addStockToSection(section.id, val);
                    sAddInput.value = '';
                    sAddBox.classList.add('hidden');
                }
            }
        });
        
        const btnAddSubmit = document.createElement('button');
        btnAddSubmit.className = 'btn btn-primary btn-section-add-submit';
        btnAddSubmit.textContent = 'Add';
        btnAddSubmit.addEventListener('click', () => {
            const val = sAddInput.value.trim().toUpperCase();
            if (val) {
                addStockToSection(section.id, val);
                sAddInput.value = '';
                sAddBox.classList.add('hidden');
            }
        });
        
        sAddBox.appendChild(sAddInput);
        sAddBox.appendChild(btnAddSubmit);
        secCard.appendChild(sAddBox);
        
        const stocksListDiv = document.createElement('div');
        stocksListDiv.className = `section-stocks-list ${section.collapsed ? 'hidden' : ''}`;
        
        if (section.stocks.length === 0) {
            const emptyPlaceholder = document.createElement('div');
            emptyPlaceholder.className = 'section-empty-placeholder';
            emptyPlaceholder.innerHTML = '<p>Section is empty.</p><p style="font-size: 0.65rem; color: var(--color-text-muted); margin-top: 0.2rem;">Click + to add stocks.</p>';
            stocksListDiv.appendChild(emptyPlaceholder);
        } else {
            const table = document.createElement('table');
            table.className = 'watchlist-table';
            
            // Add missing table headers
            const thead = document.createElement('thead');
            if (showWatchlistKronosColumns) {
                thead.innerHTML = `
                    <tr>
                        <th style="text-align: left; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem; min-width: 60px;">Symbol</th>
                        <th style="text-align: center; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;"># Rank</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;">AI Return</th>
                        <th style="text-align: center; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;">Bias</th>
                        <th style="text-align: center; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;">Conf.</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;">CMP</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.7rem;">Change%</th>
                        <th style="width: 24px;"></th>
                    </tr>
                `;
            } else {
                thead.innerHTML = `
                    <tr>
                        <th style="text-align: left; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.75rem;">Symbol</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.75rem;">CMP</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.75rem;">Change%</th>
                        <th style="text-align: right; padding-bottom: 0.5rem; color: var(--color-text-muted); font-weight: 500; font-size: 0.75rem;">Vol</th>
                        <th style="width: 24px;"></th>
                    </tr>
                `;
            }
            table.appendChild(thead);
            
            const tbody = document.createElement('tbody');
            
            section.stocks.forEach(symbol => {
                let stock = watchlistDataMap[symbol];
                if (!stock) {
                    stock = stocksData.find(s => s.clean_ticker === symbol);
                }
                
                const tr = document.createElement('tr');
                tr.className = 'watchlist-row';
                tr.dataset.symbol = symbol;
                tr.dataset.sectionId = section.id;
                tr.draggable = true;
                
                if (activeNewsFilter === symbol) {
                    tr.classList.add('active-row');
                }
                
                tr.addEventListener('click', () => {
                    selectWatchlistStock(symbol);
                    if (window.openTradeDrawer) window.openTradeDrawer(symbol);
                });
                
                if (stock) {
                    const changeClass = stock.change >= 0 ? 'val-up' : 'val-down';
                    const changeSign = stock.change > 0 ? '+' : '';
                    const priceFormatted = `₹${stock.close.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                    const volumeFormatted = formatVolume(stock.volume);
                    
                    let sectorDotHtml = '';
                    const sect = stock.sector;
                    if (sect && sectorScores[sect] && sectorScores[sect].isTop3) {
                        sectorDotHtml = `<span class="strong-sector-dot" title="Top 3 Market Sector: ${sect} (Strength Score: ${sectorScores[sect].score}/100)"></span>`;
                    }
                    
                    let insideBarDotHtml = '';
                    if (stock.is_inside_bar) {
                        const h = stock.high !== null && stock.high !== undefined ? Number(stock.high).toFixed(2) : '-';
                        const l = stock.low !== null && stock.low !== undefined ? Number(stock.low).toFixed(2) : '-';
                        const h1 = stock['high[1]'] !== null && stock['high[1]'] !== undefined ? Number(stock['high[1]']).toFixed(2) : '-';
                        const l1 = stock['low[1]'] !== null && stock['low[1]'] !== undefined ? Number(stock['low[1]']).toFixed(2) : '-';
                        insideBarDotHtml = `<span class="inside-bar-dot" title="Formed Inside Bar (Today's Range is inside Yesterday's Range)\nToday's High: ₹${h} < Prev High: ₹${h1}\nToday's Low: ₹${l} > Prev Low: ₹${l1}"></span>`;
                    }
                    
                    let volDryUpDotHtml = '';
                    if (stock.volDryUp) {
                        volDryUpDotHtml = `<span class="vol-dryup-dot" title="Volume Compression: RVOL < 0.8 with tight range — potential energy building">🔵</span>`;
                    }
                    
                    let maFlirtingDotHtml = '';
                    const maFlirtingInfo = checkMaFlirtingOrBetween(stock);
                    if (maFlirtingInfo.isMatch) {
                        maFlirtingDotHtml = `<span class="ma-flirting-dot" title="${escapeHtml(maFlirtingInfo.tooltip)}"></span>`;
                    }
                    
                    const imsStrongQS = (stock.ims_band || '').toLowerCase() === 'strong';
                    const swingStrongQS = ['strong', 'elite'].includes((stock.swingband || '').toLowerCase());
                    
                    let divergenceDotHtml = '';
                    if (swingStrongQS && !imsStrongQS) {
                        divergenceDotHtml = `<span class="divergence-dot bullish" title="Bullish Divergence: Strong swing setup with quiet intraday — potential accumulation">🔍</span>`;
                    } else if (imsStrongQS && !swingStrongQS) {
                        divergenceDotHtml = `<span class="divergence-dot bearish" title="Caution: Strong intraday but weak swing — may be a one-day pop only">⚡</span>`;
                    }
                    
                    // IMS badge for watchlist
                    let imsBadgeHtml = '';
                    if (stock.intraday_score != null) {
                        const wlBand = stock.ims_band || 'weak';
                        const wlBadgeClass = wlBand === 'strong' ? 'ims-strong' : wlBand === 'moderate' ? 'ims-moderate' : 'ims-weak';
                        const wlBreakdown = (stock.ims_breakdown || []).join('\n');
                        imsBadgeHtml = `<span class="ims-badge-sm ${wlBadgeClass}" title="IMS: ${stock.intraday_score}/10\n${escapeHtml(wlBreakdown)}">${stock.intraday_score}</span>`;
                    }
                    
                    // Check for bulk/block deals today
                    let dealsBadgeHtml = '';
                    if (typeof loadedDeals !== 'undefined' && loadedDeals.length > 0) {
                        const stockDeals = loadedDeals.filter(d => d.symbol === symbol);
                        if (stockDeals.length > 0) {
                            const totalCr = stockDeals.reduce((sum, d) => sum + parseFloat(d.valueCr || 0), 0);
                            dealsBadgeHtml = `<div style="font-size: 0.65rem; color: var(--accent-blue); margin-top: 0.25rem; font-weight: normal; text-decoration: none; letter-spacing: 0.02em;">₹${totalCr.toFixed(1)}Cr Deal Today</div>`;
                        }
                    }
                    
                    let rankHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let aiReturnHtml = '<td class="watchlist-cell-right" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let biasHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let confidenceHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';

                    const rankData = watchlistKronosRankings[symbol];
                    if (rankData) {
                        const rankVal = rankData.rank != null ? `#${rankData.rank}` : '—';
                        const originBadge = rankData.cache_hit ? 
                            `<span style="font-size:0.55rem; padding:0 2px; border-radius:2px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:var(--color-text-muted); margin-left:2px;" title="Cached Forecast">C</span>` : 
                            `<span style="font-size:0.55rem; padding:0 2px; border-radius:2px; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.2); color:#f59e0b; margin-left:2px;" title="Live Forecast">L</span>`;

                        rankHtml = `<td class="watchlist-cell-center" style="font-weight:600; color:var(--color-text-primary); font-size:0.7rem;">
                            <span style="background:rgba(255,255,255,0.04); padding:1px 4px; border-radius:2px;">${rankVal}</span>
                        </td>`;
                        
                        if (rankData.predicted_return_pct != null) {
                            const retSign = rankData.predicted_return_pct >= 0 ? '+' : '';
                            const retColor = rankData.predicted_return_pct >= 0 ? '#4ade80' : '#f87171';
                            aiReturnHtml = `<td class="watchlist-cell-right" style="font-weight:700; color:${retColor}; font-size:0.7rem;">${retSign}${rankData.predicted_return_pct.toFixed(2)}%${originBadge}</td>`;
                        }
                        
                        if (rankData.ai_forecast_bias) {
                            const bias = normalizeBias(rankData.ai_forecast_bias);
                            const biasStyles = {
                                'Strong Breakout':        { bg: 'rgba(16,185,129,0.1)',    color: '#10b981', border: 'rgba(16,185,129,0.2)' },
                                'Bullish Continuation':   { bg: 'rgba(52,211,153,0.08)',   color: '#34d399', border: 'rgba(52,211,153,0.15)' },
                                'Sideways Consolidation': { bg: 'rgba(148,163,184,0.08)',  color: '#94a3b8', border: 'rgba(148,163,184,0.15)' },
                                'Bearish Pressure':       { bg: 'rgba(248,113,113,0.08)',  color: '#f87171', border: 'rgba(248,113,113,0.15)' },
                                'Strong Downtrend':       { bg: 'rgba(239,68,68,0.1)',     color: '#ef4444', border: 'rgba(239,68,68,0.2)' }
                            };
                            const style = biasStyles[bias] || biasStyles['Sideways Consolidation'];
                            const shortBias = bias === 'Strong Breakout' ? 'Str Break' : 
                                              bias === 'Bullish Continuation' ? 'Bullish' : 
                                              bias === 'Sideways Consolidation' ? 'Sideways' : 
                                              bias === 'Bearish Pressure' ? 'Bearish' : 'Str Down';
                            
                            biasHtml = `<td class="watchlist-cell-center" style="font-size:0.6rem;">
                                <span style="background:${style.bg}; color:${style.color}; border:1px solid ${style.border}; padding:1px 3px; border-radius:2px; font-weight:500; white-space:nowrap;">
                                    ${shortBias}
                                </span>
                            </td>`;
                        }
                        
                        if (rankData.ai_confidence_score) {
                            const conf = rankData.ai_confidence_score;
                            const confClass = conf >= 70 ? 'val-up' : conf >= 50 ? 'val-warn' : 'val-down';
                            confidenceHtml = `<td class="watchlist-cell-center" style="font-size:0.65rem; font-weight:600;">
                                <div style="display:flex; flex-direction:column; align-items:center; gap:2px; min-width:30px; margin:0 auto;">
                                    <span class="${confClass}">${conf}%</span>
                                    <div style="width:100%; height:3px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden;">
                                        <div style="width:${conf}%; height:100%; background:linear-gradient(90deg, #3b82f6, #10b981);"></div>
                                    </div>
                                </div>
                            </td>`;
                        }
                    } else if (isKronosBatchSorting) {
                        rankHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                        aiReturnHtml = `<td class="watchlist-cell-right"><span class="small-spinner"></span></td>`;
                        biasHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                        confidenceHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                    }

                    if (showWatchlistKronosColumns) {
                        tr.innerHTML = `
                            <td class="watchlist-symbol" onclick="event.stopPropagation(); openTradingView('${symbol}')" title="Open in TradingView (New Tab)" style="cursor: pointer;">
                                <div style="display: flex; align-items: center;"><span style="text-decoration: underline;">${symbol}</span>${sectorDotHtml}${insideBarDotHtml}${volDryUpDotHtml}${maFlirtingDotHtml}${divergenceDotHtml}${imsBadgeHtml}</div>
                                ${dealsBadgeHtml}
                            </td>
                            ${rankHtml}
                            ${aiReturnHtml}
                            ${biasHtml}
                            ${confidenceHtml}
                            <td class="watchlist-cell-right" style="font-weight:700; color:var(--color-text-primary);">${priceFormatted}</td>
                            <td class="watchlist-cell-right ${changeClass}">${changeSign}${stock.change.toFixed(2)}%</td>
                            <td class="text-center" onclick="if(window.event) window.event.stopPropagation();">
                                <button class="watchlist-remove-btn" onclick="removeStockFromSection('${section.id}', '${symbol}')" title="Remove from Section">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                </button>
                            </td>
                        `;
                    } else {
                        tr.innerHTML = `
                            <td class="watchlist-symbol" onclick="event.stopPropagation(); openTradingView('${symbol}')" title="Open in TradingView (New Tab)" style="cursor: pointer;">
                                <div style="display: flex; align-items: center;"><span style="text-decoration: underline;">${symbol}</span>${sectorDotHtml}${insideBarDotHtml}${volDryUpDotHtml}${maFlirtingDotHtml}${divergenceDotHtml}${imsBadgeHtml}</div>
                                ${dealsBadgeHtml}
                            </td>
                            <td class="watchlist-cell-right" style="font-weight:700; color:var(--color-text-primary);">${priceFormatted}</td>
                            <td class="watchlist-cell-right ${changeClass}">${changeSign}${stock.change.toFixed(2)}%</td>
                            <td class="watchlist-cell-right" style="color:var(--color-text-secondary);">${volumeFormatted}</td>
                            <td class="text-center" onclick="if(window.event) window.event.stopPropagation();">
                                <button class="watchlist-remove-btn" onclick="removeStockFromSection('${section.id}', '${symbol}')" title="Remove from Section">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                </button>
                            </td>
                        `;
                    }
                } else {
                    let rankHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let aiReturnHtml = '<td class="watchlist-cell-right" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let biasHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';
                    let confidenceHtml = '<td class="watchlist-cell-center" style="color:var(--color-text-muted); font-size:0.7rem;">—</td>';

                    const rankData = watchlistKronosRankings[symbol];
                    if (rankData) {
                        const rankVal = rankData.rank != null ? `#${rankData.rank}` : '—';
                        const originBadge = rankData.cache_hit ? 
                            `<span style="font-size:0.55rem; padding:0 2px; border-radius:2px; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.1); color:var(--color-text-muted); margin-left:2px;" title="Cached Forecast">C</span>` : 
                            `<span style="font-size:0.55rem; padding:0 2px; border-radius:2px; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.2); color:#f59e0b; margin-left:2px;" title="Live Forecast">L</span>`;

                        rankHtml = `<td class="watchlist-cell-center" style="font-weight:600; color:var(--color-text-primary); font-size:0.7rem;">
                            <span style="background:rgba(255,255,255,0.04); padding:1px 4px; border-radius:2px;">${rankVal}</span>
                        </td>`;
                        
                        if (rankData.predicted_return_pct != null) {
                            const retSign = rankData.predicted_return_pct >= 0 ? '+' : '';
                            const retColor = rankData.predicted_return_pct >= 0 ? '#4ade80' : '#f87171';
                            aiReturnHtml = `<td class="watchlist-cell-right" style="font-weight:700; color:${retColor}; font-size:0.7rem;">${retSign}${rankData.predicted_return_pct.toFixed(2)}%${originBadge}</td>`;
                        }
                        
                        if (rankData.ai_forecast_bias) {
                            const bias = normalizeBias(rankData.ai_forecast_bias);
                            const biasStyles = {
                                'Strong Breakout':        { bg: 'rgba(16,185,129,0.1)',    color: '#10b981', border: 'rgba(16,185,129,0.2)' },
                                'Bullish Continuation':   { bg: 'rgba(52,211,153,0.08)',   color: '#34d399', border: 'rgba(52,211,153,0.15)' },
                                'Sideways Consolidation': { bg: 'rgba(148,163,184,0.08)',  color: '#94a3b8', border: 'rgba(148,163,184,0.15)' },
                                'Bearish Pressure':       { bg: 'rgba(248,113,113,0.08)',  color: '#f87171', border: 'rgba(248,113,113,0.15)' },
                                'Strong Downtrend':       { bg: 'rgba(239,68,68,0.1)',     color: '#ef4444', border: 'rgba(239,68,68,0.2)' }
                            };
                            const style = biasStyles[bias] || biasStyles['Sideways Consolidation'];
                            const shortBias = bias === 'Strong Breakout' ? 'Str Break' : 
                                              bias === 'Bullish Continuation' ? 'Bullish' : 
                                              bias === 'Sideways Consolidation' ? 'Sideways' : 
                                              bias === 'Bearish Pressure' ? 'Bearish' : 'Str Down';
                            
                            biasHtml = `<td class="watchlist-cell-center" style="font-size:0.6rem;">
                                <span style="background:${style.bg}; color:${style.color}; border:1px solid ${style.border}; padding:1px 3px; border-radius:2px; font-weight:500; white-space:nowrap;">
                                    ${shortBias}
                                </span>
                            </td>`;
                        }
                        
                        if (rankData.ai_confidence_score) {
                            const conf = rankData.ai_confidence_score;
                            const confClass = conf >= 70 ? 'val-up' : conf >= 50 ? 'val-warn' : 'val-down';
                            confidenceHtml = `<td class="watchlist-cell-center" style="font-size:0.65rem; font-weight:600;">
                                <div style="display:flex; flex-direction:column; align-items:center; gap:2px; min-width:30px; margin:0 auto;">
                                    <span class="${confClass}">${conf}%</span>
                                    <div style="width:100%; height:3px; background:rgba(255,255,255,0.08); border-radius:2px; overflow:hidden;">
                                        <div style="width:${conf}%; height:100%; background:linear-gradient(90deg, #3b82f6, #10b981);"></div>
                                    </div>
                                </div>
                            </td>`;
                        }
                    } else if (isKronosBatchSorting) {
                        rankHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                        aiReturnHtml = `<td class="watchlist-cell-right"><span class="small-spinner"></span></td>`;
                        biasHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                        confidenceHtml = `<td class="watchlist-cell-center"><span class="small-spinner"></span></td>`;
                    }

                    if (showWatchlistKronosColumns) {
                        tr.innerHTML = `
                            <td class="watchlist-symbol" onclick="event.stopPropagation(); openTradingView('${symbol}')" title="Open in TradingView (New Tab)" style="text-decoration: underline; cursor: pointer;">${symbol}</td>
                            ${rankHtml}
                            ${aiReturnHtml}
                            ${biasHtml}
                            ${confidenceHtml}
                            <td class="watchlist-cell-right" style="color:var(--color-text-muted);">-</td>
                            <td class="watchlist-cell-right" style="color:var(--color-text-muted);">-</td>
                            <td class="text-center" onclick="if(window.event) window.event.stopPropagation();">
                                <button class="watchlist-remove-btn" onclick="removeStockFromSection('${section.id}', '${symbol}')" title="Remove from Section">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                </button>
                            </td>
                        `;
                    } else {
                        tr.innerHTML = `
                            <td class="watchlist-symbol" onclick="event.stopPropagation(); openTradingView('${symbol}')" title="Open in TradingView (New Tab)" style="text-decoration: underline; cursor: pointer;">${symbol}</td>
                            <td class="watchlist-cell-right" style="color:var(--color-text-muted);">-</td>
                            <td class="watchlist-cell-right" style="color:var(--color-text-muted);">-</td>
                            <td class="watchlist-cell-right" style="color:var(--color-text-muted);">-</td>
                            <td class="text-center" onclick="if(window.event) window.event.stopPropagation();">
                                <button class="watchlist-remove-btn" onclick="removeStockFromSection('${section.id}', '${symbol}')" title="Remove from Section">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                                </button>
                            </td>
                        `;
                    }
                }
                
                tbody.appendChild(tr);
            });
            table.appendChild(tbody);
            stocksListDiv.appendChild(table);
        }
        
        secCard.appendChild(stocksListDiv);
        sectionsContainer.appendChild(secCard);
    });
    
    // Wire drag & drop
    addDragAndDropListeners();
}

function selectWatchlistStock(ticker) {
    document.querySelectorAll('.watchlist-row').forEach(row => {
        row.classList.remove('active-row');
    });
    const rows = document.querySelectorAll(`.watchlist-row[data-symbol="${ticker}"]`);
    rows.forEach(row => {
        row.classList.add('active-row');
    });
    
    // Automatically filter announcements to this stock
    const select = document.getElementById('news-filter-select');
    if (select) {
        select.value = ticker;
        activeNewsFilter = ticker;
        renderAnnouncements();
    }
}

function resetWatchlistDetails() {
    activeNewsFilter = 'all';
    const select = document.getElementById('news-filter-select');
    if (select) select.value = 'all';
    renderAnnouncements();
}

async function fetchWatchlistSingle(ticker) {
    try {
        const response = await fetch('/api/fetch_symbols', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ symbols: [ticker] })
        });
        
        if (response.ok) {
            const result = await response.json();
            const fetchedStocks = result.stocks || [];
            if (fetchedStocks.length > 0) {
                const stock = fetchedStocks[0];
                watchlistDataMap[stock.clean_ticker] = stock;
                
                if (activeNewsFilter === ticker) {
                    selectWatchlistStock(ticker);
                }
                
                renderWatchlist();
            }
        }
    } catch (e) {
        console.error("Error fetching single watchlist stock:", e);
    }
}

// Corporate Announcements are fetched from real NSE API via /api/announcements endpoint
// Events are fetched from real NSE Event Calendar via /api/events endpoint
// Deals are fetched from real NSE Bulk/Block Deals via /api/deals endpoint

function updateNewsFilterOptions() {
    const select = document.getElementById('news-filter-select');
    if (!select) return;
    
    const currentValue = select.value;
    select.innerHTML = '<option value="all">All Watchlist Stocks</option>';
    
    [...watchlistStocks].sort().forEach(ticker => {
        const opt = document.createElement('option');
        opt.value = ticker;
        opt.textContent = ticker;
        select.appendChild(opt);
    });
    
    if (watchlistStocks.includes(currentValue)) {
        select.value = currentValue;
        activeNewsFilter = currentValue;
    } else {
        select.value = 'all';
        activeNewsFilter = 'all';
    }
}

async function fetchEvents(forceFetch = false) {
    if (watchlistStocks.length === 0) { loadedEvents = []; return; }
    const sortedWatchlist = [...watchlistStocks].sort();
    const sortedLast = [...lastFetchedEventsSymbols].sort();
    const match = JSON.stringify(sortedWatchlist) === JSON.stringify(sortedLast);
    if (!forceFetch && match && loadedEvents.length >= 0 && lastFetchedEventsSymbols.length > 0) return;
    if (isEventsLoading) return;
    isEventsLoading = true;
    try {
        const res = await fetch('/api/events', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: watchlistStocks })
        });
        if (res.ok) {
            const data = await res.json();
            loadedEvents = data.events || [];
            lastFetchedEventsSymbols = [...watchlistStocks];
        }
    } catch (e) {
        console.error('Error fetching events:', e);
    } finally {
        isEventsLoading = false;
    }
}

async function fetchDeals(forceFetch = false) {
    // Always fetch ALL block deals (not filtered to watchlist)
    // We'll highlight watchlist stocks on the client side
    if (isDealsLoading) return;
    // Skip if already loaded and watchlist hasn't changed
    const sortedWatchlist = [...watchlistStocks].sort();
    const sortedLast = [...lastFetchedDealsSymbols].sort();
    const match = JSON.stringify(sortedWatchlist) === JSON.stringify(sortedLast);
    if (!forceFetch && match && dealsTradeDate !== '') return;
    isDealsLoading = true;
    try {
        // Call without symbols so backend returns ALL block deals
        const res = await fetch('/api/deals', { method: 'GET' });
        if (res.ok) {
            const data = await res.json();
            loadedDeals = data.deals || [];
            dealsTradeDate = data.tradeDate || '';
            dealsMarketStatus = data.marketStatus || '';
            lastFetchedDealsSymbols = [...watchlistStocks];
            
            // Trigger Smart Alert Engine for Large Deals
            if (typeof AlertEngine !== 'undefined') {
                const wlSymbols = new Set((watchlistStocks || []).map(s => s.split(':').pop().toUpperCase()));
                AlertEngine.checkLargeDeals(loadedDeals, wlSymbols);
            }
        }
    } catch (e) {
        console.error('Error fetching deals:', e);
    } finally {
        isDealsLoading = false;
    }
}

function toggleDealExpand(idx) {
    expandedDealIdx = (expandedDealIdx === idx) ? null : idx;
    renderAnnouncementsHtml();
}

function fmtVolume(v) {
    if (v >= 10000000) return (v / 10000000).toFixed(2) + 'Cr';
    if (v >= 100000) return (v / 100000).toFixed(2) + 'L';
    if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
    return v.toString();
}

function renderDealsSection() {
    // Always show ALL bulk and block deals; never filter by ticker
    // Watchlist stocks get a special badge highlight
    const dealsToShow = loadedDeals;
    if (dealsToShow.length === 0) return '';

    const watchlistSet = new Set(watchlistStocks.map(s => s.split(':').pop().toUpperCase()));
    const dateLabel = dealsTradeDate ? `as of ${dealsTradeDate.split(' ')[0]}` : '';

    let rows = dealsToShow.map((deal, idx) => {
        const isExpanded = (expandedDealIdx === idx);
        const isInWatchlist = watchlistSet.has(deal.symbol.toUpperCase());
        const isBuy = deal.buySell && deal.buySell.toUpperCase() === 'BUY';
        const actionColor = isBuy ? 'var(--color-positive)' : 'var(--color-negative)';
        const actionBg = isBuy ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';
        const actionText = deal.buySell || '';
        const watchlistBadge = isInWatchlist
            ? `<span class="deal-watchlist-badge">&#128278; Watchlist</span>`
            : '';
        const labelText = deal.clientName ? `${deal.dealType} &middot; ${deal.clientName}` : deal.dealType;
        
        return `
        <div class="deal-item ${isExpanded ? 'deal-item-expanded' : ''} ${isInWatchlist ? 'deal-item-watchlist' : ''}" onclick="toggleDealExpand(${idx})">
            <div class="deal-item-header">
                <div class="deal-left">
                    <span class="deal-type-icon">⚡</span>
                    <div class="deal-info">
                        <div class="deal-ticker-row">
                            <span class="deal-ticker" onclick="event.stopPropagation(); openTradingView('${deal.symbol}')" title="Open in TradingView">${deal.symbol}</span>
                            ${watchlistBadge}
                        </div>
                        <span class="deal-type-label" style="text-overflow: ellipsis; white-space: nowrap; overflow: hidden; max-width: 140px;" title="${deal.clientName || ''}">${labelText}</span>
                    </div>
                </div>
                <div class="deal-right">
                    <span class="deal-value-badge ${deal.sizeClass}">₹${deal.valueCr}Cr</span>
                    <span class="deal-action-badge" style="color:${actionColor}; background:${actionBg}; font-weight: 700; font-size: 0.65rem; padding: 0.15rem 0.4rem; border-radius: 4px; min-width: 45px; text-align: center;">${actionText}</span>
                    <span class="event-expand-icon">${isExpanded ? '▲' : '▼'}</span>
                </div>
            </div>
            ${isExpanded ? `
            <div class="deal-details-panel">
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Client</span>
                    <span class="deal-detail-value" style="font-weight: 600;">${deal.clientName || '-'}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Action</span>
                    <span class="deal-detail-value" style="color:${actionColor}; font-weight: 700;">${deal.buySell || '-'}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Price</span>
                    <span class="deal-detail-value">₹${deal.price}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Volume</span>
                    <span class="deal-detail-value">${fmtVolume(deal.volume)}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Value</span>
                    <span class="deal-detail-value">₹${deal.valueCr} Cr</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Exchange</span>
                    <span class="deal-detail-value">${deal.exchange}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Trade Date</span>
                    <span class="deal-detail-value">${deal.tradeDate || '-'}</span>
                </div>
                <div class="deal-detail-row">
                    <span class="deal-detail-label">Source</span>
                    <span class="deal-detail-value" style="color:var(--color-text-muted);font-size:0.62rem">${deal.source}</span>
                </div>
            </div>` : ''}
        </div>`;
    }).join('');

    return `
    <div class="deals-section">
        <div class="deals-section-header">
            <span class="deals-section-icon">⚡</span>
            <span>Bulk & Block Deals Today</span>
            <span class="deals-count-badge">${dealsToShow.length}</span>
            ${dateLabel ? `<span class="deals-date-label">${dateLabel}</span>` : ''}
        </div>
        <div class="deals-list">${rows}</div>
    </div>`;
}

function toggleEventExpand(id) {
    expandedEventId = (expandedEventId === id) ? null : id;
    renderAnnouncementsHtml();
}

function renderEventsSection(filter) {
    let eventsToShow = loadedEvents;
    if (filter && filter !== 'all') {
        eventsToShow = loadedEvents.filter(e => e.symbol === filter);
    }
    if (eventsToShow.length === 0) return '';

    let rows = eventsToShow.map((ev, idx) => {
        const id = `evt-${idx}`;
        const isExpanded = (expandedEventId === id);
        const descHtml = ev.description
            ? `<div class="event-desc ${isExpanded ? 'event-desc-expanded' : ''}">${ev.description}</div>`
            : '';
        return `
        <div class="event-item" id="${id}">
            <div class="event-item-row" onclick="toggleEventExpand('${id}')">
                <div class="event-left">
                    <span class="event-icon">${ev.icon}</span>
                    <div class="event-info">
                        <span class="event-ticker" onclick="event.stopPropagation(); openTradingView('${ev.symbol}')" title="Open in TradingView">${ev.symbol}</span>
                        <span class="event-purpose">${ev.purpose}</span>
                    </div>
                </div>
                <div class="event-right">
                    <span class="event-badge ${ev.badgeClass}">${ev.eventType}</span>
                    <span class="event-date">${ev.date}</span>
                    <span class="event-expand-icon">${isExpanded ? '▲' : '▼'}</span>
                </div>
            </div>
            ${isExpanded && descHtml ? `<div class="event-desc-panel">${ev.description}</div>` : ''}
        </div>`;
    }).join('');

    return `
    <div class="events-section">
        <div class="events-section-header">
            <span class="events-section-icon">🗓️</span>
            <span>Upcoming Events</span>
            <span class="events-count-badge">${eventsToShow.length}</span>
        </div>
        <div class="events-list">${rows}</div>
    </div>
    <div class="announcements-divider">
        <span>Recent Announcements</span>
    </div>`;
}

async function fetchGoogleNews(ticker) {
    if (loadedNews[ticker]) return; // Already cached
    if (isNewsLoading) return;
    isNewsLoading = true;
    try {
        const res = await fetch(`/api/news?symbol=${ticker}`);
        if (res.ok) {
            const data = await res.json();
            loadedNews[ticker] = data.news || [];
        }
    } catch (e) {
        console.error('Error fetching Google News:', e);
        loadedNews[ticker] = [];
    } finally {
        isNewsLoading = false;
    }
}

function renderNewsSectionHtml() {
    if (activeNewsFilter === 'all') return ''; 
    const articles = loadedNews[activeNewsFilter];
    if (!articles || articles.length === 0) return '';

    let html = `<div class="announcements-divider"><span>Latest News & Insights</span></div>`;
    articles.forEach(news => {
        let dateStr = news.pub_date;
        try {
            const d = new Date(news.pub_date);
            if (!isNaN(d)) {
                dateStr = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            }
        } catch(e) {}
        
        html += `
            <div class="announcement-item" onclick="window.open('${news.link}', '_blank')" style="cursor: pointer; transition: background 0.2s;">
                <div class="announcement-meta">
                    <span class="announcement-source" style="font-weight: 600; color: var(--accent-orange); border: 1px solid rgba(255,165,0,0.3); padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.65rem;">${news.source}</span>
                    <span style="font-size: 0.65rem; color: var(--color-text-muted);">${dateStr}</span>
                </div>
                <div class="announcement-headline" style="color: var(--color-text-primary); margin-top: 0.4rem; font-size: 0.85rem; line-height: 1.3;">${news.title}</div>
            </div>`;
    });
    return html;
}

function renderAnnouncementsHtml() {
    const feed = document.getElementById('announcements-feed');
    if (!feed) return;

    let filteredNews = loadedAnnouncements;
    if (activeNewsFilter !== 'all') {
        filteredNews = loadedAnnouncements.filter(n => n.ticker === activeNewsFilter);
    }
    // Only show announcements with positive or negative sentiment (skip neutral/routine)
    filteredNews = filteredNews.filter(n => n.sentiment !== 'sent-neutral');

    const eventsHtml = renderEventsSection(activeNewsFilter);
    const dealsHtml = renderDealsSection(); // Always shows all deals

    if (!eventsHtml && !dealsHtml && filteredNews.length === 0) {
        feed.innerHTML = `
            <div class="news-placeholder">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                <p>No announcements found${activeNewsFilter !== 'all' ? ` for ${activeNewsFilter}` : ''}.</p>
            </div>`;
        return;
    }

    // Build layout: Events → Deals → News → (divider) → Announcements
    const newsHtml = renderNewsSectionHtml();
    let html = eventsHtml + dealsHtml + newsHtml;
    if ((eventsHtml || dealsHtml || newsHtml) && filteredNews.length > 0) {
        html += `<div class="announcements-divider"><span>Recent Corporate Filings</span></div>`;
    }
    filteredNews.forEach(news => {
        html += `
            <div class="announcement-item">
                <div class="announcement-meta">
                    <span class="announcement-ticker" onclick="openTradingView('${news.ticker}')" title="Open ${news.ticker} in TradingView">${news.ticker}</span>
                    <span>${news.date}</span>
                </div>
                <div class="announcement-headline">${news.headline}</div>
                <div class="announcement-badges">
                    <span class="announcement-badge ${news.category}">${news.categoryName}</span>
                    <span class="announcement-badge ${news.impact}">${news.impactName}</span>
                    <span class="sentiment-badge ${news.sentiment}" onclick="showSentimentExplanation('${news.id}')" title="Click to view sentiment analysis details">${news.sentimentName}</span>
                    <span class="announcement-source-link" onclick="showAnnouncementSource('${news.id}')" title="View Corporate Filings for ${news.ticker}">Filings ↗</span>
                </div>
            </div>`;
    });
    feed.innerHTML = html;
}

async function renderAnnouncements(forceFetch = false) {
    const feed = document.getElementById('announcements-feed');
    if (!feed) return;
    
    updateNewsFilterOptions();
    
    // If watchlist is empty, we don't fetch announcements or events, but we still fetch/show block deals!
    if (watchlistStocks.length === 0) {
        loadedAnnouncements = [];
        loadedEvents = [];
        if (forceFetch || dealsTradeDate === '') {
            if (!isDealsLoading) {
                feed.innerHTML = `
                    <div class="news-placeholder">
                        <div style="border: 2px solid rgba(255,255,255,0.1); border-top: 2px solid var(--accent-blue); border-radius: 50%; width: 18px; height: 18px; animation: sector-pulse 1s linear infinite; margin-bottom: 0.5rem; display: inline-block;"></div>
                        <p style="font-size: 0.75rem; color: var(--color-text-muted);">Fetching live bulk & block deals...</p>
                    </div>
                `;
                fetchDeals(forceFetch).then(() => {
                    renderAnnouncementsHtml();
                    if (loadedDeals.length > 0) {
                        const emptyTip = document.createElement('div');
                        emptyTip.style.padding = '1rem';
                        emptyTip.style.fontSize = '0.75rem';
                        emptyTip.style.color = 'var(--color-text-muted)';
                        emptyTip.style.textAlign = 'center';
                        emptyTip.style.borderTop = '1px solid var(--panel-border)';
                        emptyTip.style.marginTop = '1rem';
                        emptyTip.innerHTML = '💡 Add stocks to your watchlist to view corporate announcements and upcoming events.';
                        feed.appendChild(emptyTip);
                    } else {
                        feed.innerHTML = `
                            <div class="news-placeholder">
                                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path><path d="M12 6v6l4 2"></path></svg>
                                <p>Your watchlist is empty.</p>
                                <p style="font-size:0.75rem; color:var(--color-text-muted); margin-top:0.2rem;">Add stocks to your watchlist to view dynamic announcements.</p>
                            </div>
                        `;
                    }
                });
            }
        } else {
            renderAnnouncementsHtml();
            if (loadedDeals.length > 0) {
                const emptyTip = document.createElement('div');
                emptyTip.style.padding = '1rem';
                emptyTip.style.fontSize = '0.75rem';
                emptyTip.style.color = 'var(--color-text-muted)';
                emptyTip.style.textAlign = 'center';
                emptyTip.style.borderTop = '1px solid var(--panel-border)';
                emptyTip.style.marginTop = '1rem';
                emptyTip.innerHTML = '💡 Add stocks to your watchlist to view corporate announcements and upcoming events.';
                feed.appendChild(emptyTip);
            }
        }
        return;
    }
    
    // Check if watchlist symbol list matches last fetched list
    const sortedWatchlist = [...watchlistStocks].sort();
    const sortedLastFetched = [...lastFetchedAnnouncementsSymbols].sort();
    const symbolsMatch = JSON.stringify(sortedWatchlist) === JSON.stringify(sortedLastFetched);
    
    if (forceFetch || !symbolsMatch || loadedAnnouncements.length === 0) {
        if (isAnnouncementsLoading) return; // Prevent concurrent requests
        isAnnouncementsLoading = true;
        
        feed.innerHTML = `
            <div class="news-placeholder">
                <div style="border: 2px solid rgba(255,255,255,0.1); border-top: 2px solid var(--accent-blue); border-radius: 50%; width: 18px; height: 18px; animation: sector-pulse 1s linear infinite; margin-bottom: 0.5rem; display: inline-block;"></div>
                <p style="font-size: 0.75rem; color: var(--color-text-muted);">Fetching live NSE data...</p>
            </div>
        `;
        
        // Fetch announcements, events, and deals concurrently
        try {
            const [annRes] = await Promise.all([
                fetch('/api/announcements', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ symbols: watchlistStocks })
                }),
                fetchEvents(forceFetch),
                fetchDeals(forceFetch)
            ]);
            if (annRes.ok) {
                const data = await annRes.json();
                loadedAnnouncements = data.announcements || [];
                lastFetchedAnnouncementsSymbols = [...watchlistStocks];
            } else {
                console.error("Failed to fetch live announcements from backend.");
            }
        } catch (e) {
            console.error("Error fetching announcements: ", e);
        } finally {
            isAnnouncementsLoading = false;
        }
    } else {
        // Announcements are cached — still try to fetch events and deals if needed
        fetchEvents(forceFetch);
        fetchDeals(forceFetch).then(() => renderAnnouncementsHtml());
    }
    
    // Fetch Google news for the active stock
    if (activeNewsFilter !== 'all') {
        fetchGoogleNews(activeNewsFilter).then(() => renderAnnouncementsHtml());
    }
    
    renderAnnouncementsHtml();
}

function showAnnouncementSource(id) {
    const announcement = loadedAnnouncements.find(n => n.id === id);
    if (!announcement) return;
    
    let url;
    if (announcement.attchmntFile) {
        // Redirect directly to the official NSE filing PDF doc!
        url = announcement.attchmntFile;
    } else {
        // Fallback to Trendlyne corporate actions page
        url = `https://trendlyne.com/corporate-actions/announcements/NSE/${announcement.ticker}/`;
    }
    
    window.open(url, '_blank', 'noopener,noreferrer');
}

function showSentimentExplanation(id) {
    const announcement = loadedAnnouncements.find(n => n.id === id);
    if (!announcement) return;
    
    // Set text contents of the modal
    document.getElementById('sent-modal-ticker').textContent = announcement.ticker;
    document.getElementById('sent-modal-date').textContent = announcement.date;
    document.getElementById('sent-modal-headline').textContent = announcement.headline;
    
    // Set badges
    const catBadge = document.getElementById('sent-modal-category');
    catBadge.textContent = announcement.categoryName;
    catBadge.className = `announcement-badge ${announcement.category}`;
    
    const impBadge = document.getElementById('sent-modal-impact');
    impBadge.textContent = announcement.impactName;
    impBadge.className = `announcement-badge ${announcement.impact}`;
    
    const sentBadge = document.getElementById('sent-modal-badge');
    sentBadge.textContent = announcement.sentimentName;
    sentBadge.className = `sentiment-badge ${announcement.sentiment}`;
    
    // Set explanation reason text
    document.getElementById('sent-modal-reason').textContent = announcement.sentimentReason || "No explanation reason provided for this announcement.";
    
    // Show the modal
    const sentModal = document.getElementById('sentiment-explanation-modal');
    if (sentModal) {
        sentModal.classList.remove('hidden');
    }
}

// Watchlist Drag & Drop Reordering Logic
let dragSrcSymbol = null;
let dragSrcSectionId = null;

function handleDragStart(e) {
    if (!isWatchlistLoaded || isKronosBatchSorting) {
        e.preventDefault();
        return;
    }
    dragSrcSymbol = this.dataset.symbol;
    dragSrcSectionId = this.dataset.sectionId;
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragSrcSymbol);
    this.classList.add('dragging');
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    
    const targetRow = e.target.closest('.watchlist-row');
    if (targetRow && targetRow.dataset.symbol !== dragSrcSymbol) {
        targetRow.classList.add('drag-over');
    }
    
    const targetCard = e.target.closest('.watchlist-section-card');
    if (targetCard) {
        targetCard.classList.add('drag-over');
    }
    
    return false;
}

function handleDragLeave(e) {
    const targetRow = e.target.closest('.watchlist-row');
    if (targetRow) {
        targetRow.classList.remove('drag-over');
    }
    
    const targetCard = e.target.closest('.watchlist-section-card');
    if (targetCard) {
        const rect = targetCard.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX >= rect.right || e.clientY < rect.top || e.clientY >= rect.bottom) {
            targetCard.classList.remove('drag-over');
        }
    }
}

function handleDrop(e) {
    if (e.stopPropagation) {
        e.stopPropagation();
    }
    
    if (!isWatchlistLoaded || isKronosBatchSorting) {
        return false;
    }
    
    const targetRow = e.target.closest('.watchlist-row');
    const targetCard = e.target.closest('.watchlist-section-card');
    
    if (!targetCard) return false;
    
    const targetSectionId = targetCard.dataset.sectionId;
    const targetSymbol = targetRow ? targetRow.dataset.symbol : null;
    
    if (dragSrcSymbol && dragSrcSectionId) {
        const srcSec = watchlistSections.find(s => s.id === dragSrcSectionId);
        const targetSec = watchlistSections.find(s => s.id === targetSectionId);
        
        if (srcSec && targetSec) {
            const srcIdx = srcSec.stocks.indexOf(dragSrcSymbol);
            if (srcIdx !== -1) {
                srcSec.stocks.splice(srcIdx, 1);
            }
            
            if (targetSymbol) {
                const targetIdx = targetSec.stocks.indexOf(targetSymbol);
                if (targetIdx !== -1) {
                    targetSec.stocks.splice(targetIdx, 0, dragSrcSymbol);
                } else {
                    targetSec.stocks.push(dragSrcSymbol);
                }
            } else {
                targetSec.stocks.push(dragSrcSymbol);
            }
            
            targetSec.collapsed = false;
            
            saveWatchlistSections();
            renderWatchlist();
            renderAnnouncements();
        }
    }
    
    return false;
}

function handleDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('.watchlist-row').forEach(row => {
        row.classList.remove('drag-over');
    });
    document.querySelectorAll('.watchlist-section-card').forEach(card => {
        card.classList.remove('drag-over');
    });
}

function addDragAndDropListeners() {
    const rows = document.querySelectorAll('.watchlist-row');
    rows.forEach(row => {
        row.addEventListener('dragstart', handleDragStart, false);
        row.addEventListener('dragover', handleDragOver, false);
        row.addEventListener('dragleave', handleDragLeave, false);
        row.addEventListener('drop', handleDrop, false);
        row.addEventListener('dragend', handleDragEnd, false);
    });
    
    const cards = document.querySelectorAll('.watchlist-section-card');
    cards.forEach(card => {
        card.addEventListener('dragover', handleDragOver, false);
        card.addEventListener('dragleave', handleDragLeave, false);
        card.addEventListener('drop', handleDrop, false);
    });
}

// --- Column Resizing ---
let resizeStartX, resizeStartWidth, resizeColIdx = -1;

function initColumnResize(e) {
    e.stopPropagation();
    e.preventDefault();
    
    resizeColIdx = parseInt(e.target.dataset.colIdx);
    resizeStartX = e.clientX;
    
    const rootStyles = getComputedStyle(document.documentElement);
    if (resizeColIdx === 0) {
        resizeStartWidth = parseInt(rootStyles.getPropertyValue('--col-ticker-width')) || 150;
    } else if (resizeColIdx === 1) {
        resizeStartWidth = parseInt(rootStyles.getPropertyValue('--col-desc-width')) || 250;
    }
    
    document.addEventListener('mousemove', handleColumnResize);
    document.addEventListener('mouseup', stopColumnResize);
    e.target.classList.add('resizing');
}

function handleColumnResize(e) {
    if (resizeColIdx === -1) return;
    const diff = e.clientX - resizeStartX;
    const newWidth = Math.max(50, resizeStartWidth + diff);
    
    if (resizeColIdx === 0) {
        document.documentElement.style.setProperty('--col-ticker-width', `${newWidth}px`);
    } else if (resizeColIdx === 1) {
        document.documentElement.style.setProperty('--col-desc-width', `${newWidth}px`);
    }
}

function stopColumnResize(e) {
    document.removeEventListener('mousemove', handleColumnResize);
    document.removeEventListener('mouseup', stopColumnResize);
    document.querySelectorAll('.col-resizer').forEach(r => r.classList.remove('resizing'));
    resizeColIdx = -1;
}

// --- Snapshot Logic ---
async function saveSnapshot() {
    const btn = document.getElementById('btn-save-snapshot');
    if (!btn) return;
    
    const originalText = btn.innerHTML;
    
    if (!confirm("Are you sure you want to save the current Momentum Matches scan (currently " + filteredStocks.length + " stocks) to history?\n\nThis will be used to calculate 'Days in Scan' and 'Seen (20d)' metrics.")) {
        return;
    }
    
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><path d="M12 6v6l4 2"></path></svg> <span>Saving...</span>`;
    btn.disabled = true;
    
    const items = filteredStocks.map(s => ({
        ticker: s.clean_ticker,
        close: parseFloat(s.close) || 0,
        setupLabel: s.setupLabel || 'Early Watch',
        swingband: s.swingband || 'weak'
    }));
    
    try {
        const response = await fetch('/api/save_snapshot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ items: items, tickers: items.map(i => i.ticker) })
        });
        const data = await response.json();
        
        if (response.ok) {
            alert(`Snapshot saved successfully!\nDate: ${data.date}\nTotal Stocks Found: ${data.total_found}\nNew Stocks Saved Today: ${data.saved_count}`);
            // Force a re-scan to update the history columns in the UI
            runScan();
        } else {
            alert(`Error saving snapshot: ${data.error}`);
        }
    } catch (err) {
        alert('Failed to save snapshot. Check console for details.');
        console.error(err);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

// --- RRG Logic ---
let rrgChartInstance = null;
let rrgViewMode = 'sectors'; // 'sectors' or 'stocks'

function getMedian(values) {
    if (values.length === 0) return 0;
    values.sort((a, b) => a - b);
    const half = Math.floor(values.length / 2);
    if (values.length % 2) return values[half];
    return (values[half - 1] + values[half]) / 2.0;
}

const RRG_SECTOR_COLORS = {
  'Capital Goods':     '#6366f1',
  'Metals':            '#f59e0b',
  'Industrial':        '#10b981',
  'Financial Services':'#3b82f6',
  'IT':                '#8b5cf6',
  'Healthcare':        '#ec4899',
  'Consumer':          '#f97316',
  'Energy':            '#14b8a6',
  'Infrastructure':    '#84cc16',
  'Auto':              '#ef4444',
  'Finance':           '#3b82f6',
  'Technology Services':'#8b5cf6',
  'Health Technology': '#ec4899',
  'Health Services':   '#ec4899',
  'Electronic Technology':'#8b5cf6',
  'Retail Trade':      '#f97316',
  'Producer Manufacturing':'#6366f1',
  'Process Industries': '#f59e0b',
  'Consumer Services': '#f97316',
  'Non-Energy Minerals':'#f59e0b',
  'Utilities':         '#14b8a6',
  'Transportation':    '#84cc16',
  'Commercial Services':'#84cc16'
};
const RRG_DEFAULT_COLOR = '#94a3b8';

let rrgHistoryFrames = [];     // All frames from /api/rrg/history
let rrgCurrentFrame  = 0;      // Currently displayed frame index
let rrgAnimTimer     = null;   // setInterval handle
const RRG_ANIM_INTERVAL_MS = 600; // ms per frame during auto-play

let rrgScale = { rsMin: 88, rsMax: 112, moMin: -6, moMax: 6 };
let rrgHoveredSector = null;
let rrgMouseX = null;
let rrgMouseY = null;

function updateRRGScaleLimits(frames) {
    if (!frames || !frames.length) {
        rrgScale = { rsMin: 88, rsMax: 112, moMin: -6, moMax: 6 };
        return;
    }
    let maxDevX = 2.0; // minimum default deviation
    let maxDevY = 0.5; // minimum default deviation
    
    frames.forEach(f => {
        if (!f.sectors) return;
        f.sectors.forEach(s => {
            const devX = Math.abs(s.jdk_rs - 100.0);
            const devY = Math.abs(s.jdk_rs_momentum);
            if (devX > maxDevX) maxDevX = devX;
            if (devY > maxDevY) maxDevY = devY;
        });
    });
    
    // Add 20% padding
    const deltaX = maxDevX * 1.20;
    const deltaY = maxDevY * 1.20;
    
    rrgScale = {
        rsMin: 100.0 - deltaX,
        rsMax: 100.0 + deltaX,
        moMin: -deltaY,
        moMax: deltaY
    };
}

function renderRRG() {
    const timelineBar = document.getElementById('rrg-timeline-bar');
    const rrgCanvas = document.getElementById('rrg-canvas');
    const rrgChart = document.getElementById('rrgChart');
    
    if (rrgViewMode === 'sectors') {
        if (timelineBar) timelineBar.style.display = 'flex';
        if (rrgCanvas) rrgCanvas.style.display = 'block';
        if (rrgChart) rrgChart.style.display = 'none';
        // Hide the stocks filter label bar in sectors/timeline mode
        const labelBar = document.getElementById('rrg-sector-label-bar');
        if (labelBar) labelBar.style.display = 'none';
        
        const weeksSelect = document.getElementById('rrg-weeks-select');
        const weeks = weeksSelect ? parseInt(weeksSelect.value) : 12;
        loadRRGHistory(weeks);
    } else {
        if (timelineBar) timelineBar.style.display = 'none';
        if (rrgCanvas) rrgCanvas.style.display = 'none';
        if (rrgChart) rrgChart.style.display = 'block';
        
        stopRRGAnimation();
        renderStaticStocksRRG();
    }
    
    // Render sector heatmap
    if (typeof renderSectorHeatmap === 'function') {
        renderSectorHeatmap();
    }
}

function renderStaticStocksRRG() {
    if (!universeData || universeData.length === 0) return;
    
    // Calculate Benchmark (Median of all universe stocks)
    const validW = universeData.map(s => s.perf_w).filter(v => v !== null && !isNaN(v));
    const validM = universeData.map(s => s.perf_m).filter(v => v !== null && !isNaN(v));
    
    const benchW = getMedian(validW);
    const benchM = getMedian(validM);
    
    // Use universeData filtered by selected sector for the RRG stocks view.
    const sourceStocks = (selectedSector && selectedSector !== 'all')
        ? universeData.filter(s => s.sector === selectedSector)
        : universeData;
    
    // Show/hide sector label bar
    const rrgLabelBar = document.getElementById('rrg-sector-label-bar');
    const rrgSectorLabel = document.getElementById('rrg-sector-label');
    if (rrgLabelBar && rrgSectorLabel) {
        if (selectedSector && selectedSector !== 'all') {
            rrgSectorLabel.textContent = `Showing: ${selectedSector}  (${sourceStocks.length} stocks)`;
            rrgLabelBar.style.display = 'flex';
        } else {
            rrgSectorLabel.textContent = `All Universe Stocks (${sourceStocks.length})`;
            rrgLabelBar.style.display = 'flex';
        }
    }
    
    // Build a fast lookup Set of tickers in filteredStocks (screener-quality stocks)
    const screenerTickerSet = new Set(filteredStocks.map(s => s.clean_ticker || s.ticker));
    
    // Split sourceStocks into screener-quality (orange) vs universe-only (grey)
    const screenerPoints = [];
    const universeOnlyPoints = [];
    
    sourceStocks.forEach(s => {
        const ticker = s.ticker || s.clean_ticker || '';
        const point = {
            x: ((s.perf_m || 0) - benchM),
            y: ((s.perf_w || 0) - benchW),
            label: ticker,
            sector: s.sector || '',
            isScreener: screenerTickerSet.has(ticker)
        };
        if (screenerTickerSet.has(ticker)) {
            screenerPoints.push(point);
        } else {
            universeOnlyPoints.push(point);
        }
    });

    // Dataset 0: Universe-only stocks (dim grey — background context)
    const universeDataset = {
        label: 'Universe',
        data: universeOnlyPoints,
        backgroundColor: 'rgba(148, 163, 184, 0.25)',
        borderColor: 'rgba(148, 163, 184, 0.5)',
        borderWidth: 1,
        pointRadius: 3.5,
        pointHoverRadius: 5,
        pointStyle: 'circle',
        order: 2
    };
    
    // Dataset 1: Screener-quality stocks (orange glow — your filtered picks)
    const screenerDataset = {
        label: 'Screener Picks',
        data: screenerPoints,
        backgroundColor: 'rgba(251, 146, 60, 0.90)',   // orange-400
        borderColor: 'rgba(253, 186, 116, 1)',           // orange-300 border
        borderWidth: 1.5,
        pointRadius: 5,
        pointHoverRadius: 7.5,
        pointStyle: 'circle',
        order: 1   // rendered on top
    };
    
    const canvas = document.getElementById('rrgChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (rrgChartInstance) rrgChartInstance.destroy();
    
    // --- Quadrant background plugin ---
    const quadrantPlugin = {
        id: 'quadrants',
        beforeDraw: (chart) => {
            const { ctx, chartArea: { top, bottom, left, right }, scales: { x, y } } = chart;
            ctx.save();
            const xZero = x.getPixelForValue(0);
            const yZero = y.getPixelForValue(0);
            ctx.fillStyle = 'rgba(16, 185, 129, 0.08)';
            ctx.fillRect(xZero, top, right - xZero, yZero - top);
            ctx.fillStyle = 'rgba(234, 179, 8, 0.08)';
            ctx.fillRect(xZero, yZero, right - xZero, bottom - yZero);
            ctx.fillStyle = 'rgba(239, 68, 68, 0.08)';
            ctx.fillRect(left, yZero, xZero - left, bottom - yZero);
            ctx.fillStyle = 'rgba(59, 130, 246, 0.08)';
            ctx.fillRect(left, top, xZero - left, yZero - top);
            ctx.restore();
        }
    };
    
    // --- Labels plugin: draw ticker labels for all visible datasets ---
    const labelsPlugin = {
        id: 'labels',
        afterDatasetsDraw: (chart) => {
            const { ctx, data } = chart;
            const totalPoints = data.datasets.reduce((sum, ds) => sum + ds.data.length, 0);
            if (totalPoints > 60) return; // skip labels if too crowded
            
            ctx.save();
            ctx.textAlign = 'left';
            ctx.textBaseline = 'middle';
            
            data.datasets.forEach((dataset, dsIdx) => {
                const isScreenerDs = dsIdx === 1; // dataset 1 = screener picks
                const meta = chart.getDatasetMeta(dsIdx);
                ctx.font = isScreenerDs ? 'bold 9px Inter, sans-serif' : '8px Inter, sans-serif';
                ctx.fillStyle = isScreenerDs ? 'rgba(251, 146, 60, 0.95)' : 'rgba(148, 163, 184, 0.6)';
                
                dataset.data.forEach((point, index) => {
                    const element = meta.data[index];
                    if (element && !element.hidden) {
                        ctx.fillText(point.label.substring(0, 6), element.x + 6, element.y - 4);
                    }
                });
            });
            ctx.restore();
        }
    };

    // --- Legend plugin: draw custom mini-legend in top-right corner ---
    const legendPlugin = {
        id: 'rrgLegend',
        afterDraw: (chart) => {
            const { ctx, chartArea: { top, right } } = chart;
            ctx.save();
            const lx = right - 160;
            const ly = top + 8;
            
            // Orange dot = screener picks
            ctx.beginPath();
            ctx.arc(lx, ly + 5, 5, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(251, 146, 60, 0.9)';
            ctx.fill();
            ctx.font = '9px Inter, sans-serif';
            ctx.fillStyle = 'rgba(251, 146, 60, 1)';
            ctx.textAlign = 'left';
            ctx.fillText(`Screener Picks (${screenerPoints.length})`, lx + 10, ly + 6);
            
            // Grey dot = universe
            ctx.beginPath();
            ctx.arc(lx, ly + 20, 4, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(148, 163, 184, 0.5)';
            ctx.fill();
            ctx.fillStyle = 'rgba(148, 163, 184, 0.8)';
            ctx.fillText(`Universe Only (${universeOnlyPoints.length})`, lx + 10, ly + 21);
            
            ctx.restore();
        }
    };
    
    rrgChartInstance = new Chart(ctx, {
        type: 'scatter',
        data: { datasets: [universeDataset, screenerDataset] },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            color: '#9ca3af',
            onClick: (event, elements) => {
                if (!elements || elements.length === 0) return;
                const el = elements[0];
                const dsData = rrgChartInstance.data.datasets[el.datasetIndex].data;
                const point = dsData[el.index];
                if (point && point.label) {
                    openTradeDrawerFromRRG(point.label);
                }
            },
            onHover: (event, elements) => {
                canvas.style.cursor = elements.length > 0 ? 'pointer' : 'default';
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (ctx) => ctx[0].raw.label,
                        label: (ctx) => {
                            const pt = ctx.raw;
                            const tag = pt.isScreener ? ' 🟠 Screener Pick' : ' · Universe';
                            return [
                                `RS (1M): ${pt.x > 0 ? '+' : ''}${pt.x.toFixed(1)}% vs Market`,
                                `Mom (1W): ${pt.y > 0 ? '+' : ''}${pt.y.toFixed(1)}% vs Market`,
                                tag
                            ];
                        },
                        labelColor: (ctx) => {
                            const isScr = ctx.datasetIndex === 1;
                            return {
                                borderColor: isScr ? 'rgb(251,146,60)' : 'rgba(148,163,184,0.5)',
                                backgroundColor: isScr ? 'rgb(251,146,60)' : 'rgba(148,163,184,0.3)'
                            };
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    title: { display: true, text: 'Relative Strength (1M vs Market)', color: '#9ca3af' }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.1)' },
                    title: { display: true, text: 'Relative Momentum (1W vs Market)', color: '#9ca3af' }
                }
            }
        },
        plugins: [quadrantPlugin, labelsPlugin, legendPlugin]
    });
}

// Open trade drawer from RRG — tries stocksData first, falls back to universeData
function openTradeDrawerFromRRG(ticker) {
    // Try to find in screener stocksData first (full data)
    const screenerStock = stocksData.find(s => s.clean_ticker === ticker || s.ticker === ticker);
    if (screenerStock) {
        openTradeDrawer(screenerStock.clean_ticker);
        return;
    }
    
    // Fallback: stock is in universeData only — build a minimal stub and open drawer
    const uStock = universeData.find(s => s.ticker === ticker || s.clean_ticker === ticker);
    if (!uStock) return;
    
    // Build a minimal stub compatible with drawer fields
    const stub = {
        clean_ticker: uStock.ticker || uStock.clean_ticker || ticker,
        ticker: uStock.ticker || ticker,
        description: uStock.ticker || ticker,
        sector: uStock.sector || '',
        close: uStock.close || 0,
        perf_w: uStock.perf_w || 0,
        perf_m: uStock.perf_m || 0,
        setupLabel: '— Universe Stock',
        setupTags: [],
        swingband: null,
        ims_band: null,
        volDryUp: false,
        mtfScore: null,
        upcoming_earnings: null,
        SMA21: uStock.SMA21 || 0,
        SMA50: uStock.SMA50 || 0,
        _isUniverseOnly: true   // flag for drawer to show a notice
    };
    
    window.currentTradeStock = stub;
    const overlay = document.getElementById('trade-drawer-overlay');
    const drawer = document.getElementById('trade-drawer');
    if (!overlay || !drawer) return;
    
    document.getElementById('drawer-ticker').textContent = stub.clean_ticker;
    document.getElementById('drawer-name').textContent = `${stub.sector || 'Unknown Sector'} · Universe Stock`;
    
    // Setup pill
    const pillEl = document.getElementById('drawer-setup-pill');
    if (pillEl) {
        pillEl.className = 'setup-pill setup-pill-early';
        pillEl.textContent = 'Universe Stock';
    }
    
    // Price
    const closePrice = parseFloat(stub.close) || 0;
    const priceEl = document.getElementById('drawer-current-price');
    if (priceEl) priceEl.textContent = closePrice > 0 ? `₹${closePrice.toFixed(2)}` : '—';
    
    // Hide earnings / MTF / vol warnings
    ['drawer-earnings-warning', 'drawer-mtf-warning', 'drawer-vol-warning'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });
    
    // Show a notice that screener data is unavailable
    const intelSection = document.getElementById('drawer-intelligence-section');
    if (intelSection) {
        intelSection.style.display = 'block';
        const aiResult = document.getElementById('drawer-ai-result');
        if (aiResult) {
            aiResult.innerHTML = `
                <div style="padding: 1rem; background: rgba(251,146,60,0.08); border: 1px solid rgba(251,146,60,0.2); border-radius: 8px; text-align:center;">
                    <div style="font-size:1.5rem; margin-bottom:0.5rem;">📊</div>
                    <div style="font-size:0.85rem; font-weight:600; color:rgba(251,146,60,0.9); margin-bottom:0.4rem;">Not in Screener</div>
                    <div style="font-size:0.75rem; color:var(--color-text-secondary);">
                        ${stub.clean_ticker} appears in the universe but doesn't pass the<br>
                        momentum filter criteria (SMA10 > 21 > 50, ATR > 3%, etc.).<br>
                        Full trade analysis is only available for screener picks.
                    </div>
                    <div style="margin-top:0.75rem; font-size:0.75rem; color:var(--color-text-muted);">
                        1M: <strong style="color:${(stub.perf_m||0)>=0?'#10b981':'#ef4444'}">${(stub.perf_m||0)>0?'+':''}${(stub.perf_m||0).toFixed(1)}%</strong>
                        &nbsp;|&nbsp;
                        1W: <strong style="color:${(stub.perf_w||0)>=0?'#10b981':'#ef4444'}">${(stub.perf_w||0)>0?'+':''}${(stub.perf_w||0).toFixed(1)}%</strong>
                    </div>
                </div>`;
        }
    }
    
    // History
    const historyContainer = document.getElementById('drawer-history-content');
    if (historyContainer) historyContainer.innerHTML = '<div style="font-size:0.8rem;color:var(--color-text-muted);">No screener history for universe-only stocks.</div>';
    
    // Chart action button
    const btnChart = document.getElementById('btn-drawer-chart');
    if (btnChart) btnChart.onclick = () => openTradingView(stub.clean_ticker);
    const btnWatchlist = document.getElementById('btn-drawer-watchlist');
    if (btnWatchlist) btnWatchlist.onclick = (e) => addToWatchlist(stub.clean_ticker, e);
    
    // Regime hint
    const rb = marketBreadth.regimeBand ?? 'Neutral';
    const rs = marketBreadth.regimeScore ?? 50;
    const sizingMap = {
      'Bull Run':    { hint: 'Full size — bull conditions support aggressive positioning.', cls: 'regime-hint--bullish' },
      'Bullish':     { hint: 'Normal size — bullish market supports standard risk.',        cls: 'regime-hint--bullish' },
      'Neutral':     { hint: 'Half size — mixed market. Reduce risk per trade by 50%.',    cls: 'regime-hint--neutral' },
      'Bearish':     { hint: 'Quarter size only — high stop-out risk in bearish conditions.', cls: 'regime-hint--bearish' },
      'Bear Market': { hint: 'Avoid new longs — bear market conditions active.',            cls: 'regime-hint--danger' },
    };
    const sz = sizingMap[rb] ?? sizingMap['Neutral'];
    const hint = document.getElementById('drawer-regime-hint');
    if (hint) {
        hint.className = `drawer-regime-hint ${sz.cls}`;
        hint.innerHTML = `<span class="regime-hint-label">Market Regime</span><span class="regime-hint-band">${rb} (${rs}/100)</span><span class="regime-hint-guidance">${sz.hint}</span>`;
    }
    
    overlay.classList.add('open');
    drawer.classList.add('open');
}



function renderRRGTimeline(frames, frameIdx) {
    const canvas = document.getElementById('rrg-canvas');
    if (!canvas || !frames.length) return;
    
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    
    const W = rect.width;
    const H = rect.height;
    const pad = 48;
    const cx = W / 2;
    const cy = H / 2;
    
    // Dynamic coordinate mappers based on computed limits
    const RS_MIN = rrgScale.rsMin;
    const RS_MAX = rrgScale.rsMax;
    const MO_MIN = rrgScale.moMin;
    const MO_MAX = rrgScale.moMax;
    
    const clamp = (val, min, max) => Math.max(min, Math.min(max, val));
    const toX = rs  => pad + ((clamp(rs, RS_MIN, RS_MAX) - RS_MIN)  / (RS_MAX - RS_MIN))  * (W - pad * 2);
    const toY = mom => (H - pad) - ((clamp(mom, MO_MIN, MO_MAX) - MO_MIN) / (MO_MAX - MO_MIN)) * (H - pad * 2);
    
    ctx.clearRect(0, 0, W, H);
    
    // --- Background quadrant fills ---
    const quadrantFills = [
        { x: cx, y: pad,  w: W - pad - cx, h: cy - pad,      color: 'rgba(16, 185, 129, 0.04)', label: 'Leading',   pos: [W - pad - 12, pad + 20] },
        { x: cx, y: cy,   w: W - pad - cx, h: H - pad - cy,  color: 'rgba(239, 68, 68, 0.04)',  label: 'Weakening', pos: [W - pad - 12, H - pad - 16] },
        { x: pad, y: cy,  w: cx - pad,     h: H - pad - cy,  color: 'rgba(234, 179, 8, 0.04)',  label: 'Lagging',   pos: [pad + 12, H - pad - 16] },
        { x: pad, y: pad, w: cx - pad,     h: cy - pad,      color: 'rgba(59, 130, 246, 0.04)',  label: 'Improving', pos: [pad + 12, pad + 20] },
    ];
    quadrantFills.forEach(q => {
        ctx.fillStyle = q.color;
        ctx.fillRect(q.x, q.y, q.w, q.h);
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.font = 'bold 11px Outfit, sans-serif';
        ctx.textAlign = q.pos[0] > cx ? 'right' : 'left';
        ctx.fillText(q.label, q.pos[0], q.pos[1]);
    });
    
    // --- Axis lines ---
    ctx.strokeStyle = 'rgba(255,255,255,0.08)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, cy); ctx.lineTo(W - pad, cy); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, pad); ctx.lineTo(cx, H - pad); ctx.stroke();
    
    // --- Collect all unique sector names across frames ---
    const allSectors = [...new Set(frames.flatMap(f => f.sectors.map(s => s.sector)))];
    
    const hasActiveHover = (rrgHoveredSector !== null);
    
    allSectors.forEach(sectorName => {
        const color = RRG_SECTOR_COLORS[sectorName] || RRG_DEFAULT_COLOR;
        const isHovered = (rrgHoveredSector === sectorName);
        
        // Build the position trail for this sector up to frameIdx
        const trail = [];
        for (let i = Math.max(0, frameIdx - 11); i <= frameIdx; i++) {
            const frame = frames[i];
            const entry = frame?.sectors.find(s => s.sector === sectorName);
            if (entry) {
                trail.push({ x: toX(entry.jdk_rs), y: toY(entry.jdk_rs_momentum), score: entry.score, week: frame.week });
            }
        }
        if (!trail.length) return;
        
        // Apply alpha multiplier based on hover state
        const opacityMult = hasActiveHover ? (isHovered ? 1.0 : 0.15) : 1.0;
        
        // Draw trail lines (fading opacity older -> newer)
        for (let i = 1; i < trail.length; i++) {
            const alpha = (0.1 + (i / trail.length) * 0.5) * opacityMult;
            ctx.beginPath();
            ctx.strokeStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
            ctx.lineWidth = isHovered ? 3.0 : 1.5;
            ctx.moveTo(trail[i - 1].x, trail[i - 1].y);
            ctx.lineTo(trail[i].x, trail[i].y);
            ctx.stroke();
        }
        
        // Draw ghost dots (historical)
        for (let i = 0; i < trail.length - 1; i++) {
            const alpha = (0.12 + (i / trail.length) * 0.3) * opacityMult;
            const r = (4 + (trail[i].score / 100) * 3) * (isHovered ? 1.25 : 1.0);
            ctx.beginPath();
            ctx.arc(trail[i].x, trail[i].y, r, 0, Math.PI * 2);
            ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
            ctx.fill();
        }
        
        // Draw current dot (full opacity, larger)
        const cur = trail[trail.length - 1];
        const curR = (6 + (cur.score / 100) * 5) * (isHovered ? 1.3 : 1.0);
        ctx.beginPath();
        ctx.arc(cur.x, cur.y, curR, 0, Math.PI * 2);
        
        if (isHovered) {
            ctx.save();
            ctx.shadowBlur = 10;
            ctx.shadowColor = color;
        }
        
        ctx.fillStyle = hasActiveHover && !isHovered ? color + "40" : color;
        ctx.fill();
        
        if (isHovered) {
            ctx.restore();
        }
        
        ctx.strokeStyle = hasActiveHover && !isHovered ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.6)';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        
        // Draw label with a pill container
        // If there's an active hover, only render label for the hovered sector
        if (!hasActiveHover || isHovered) {
            ctx.save();
            ctx.font = isHovered ? 'bold 11px Inter, sans-serif' : '9px Inter, sans-serif';
            ctx.textAlign = 'left';
            
            const textWidth = ctx.measureText(sectorName).width;
            const bgW = textWidth + 8;
            const bgH = isHovered ? 16 : 12;
            const bgX = cur.x + curR + 3;
            const bgY = cur.y - (bgH / 2);
            
            ctx.fillStyle = isHovered ? 'rgba(15, 23, 42, 0.85)' : 'rgba(15, 23, 42, 0.55)';
            ctx.strokeStyle = isHovered ? color : 'rgba(255, 255, 255, 0.05)';
            ctx.lineWidth = isHovered ? 1.0 : 0.5;
            
            ctx.beginPath();
            if (ctx.roundRect) {
                ctx.roundRect(bgX, bgY, bgW, bgH, 3);
            } else {
                ctx.rect(bgX, bgY, bgW, bgH);
            }
            ctx.fill();
            ctx.stroke();
            
            ctx.fillStyle = isHovered ? '#ffffff' : 'rgba(255, 255, 255, 0.8)';
            ctx.fillText(sectorName, bgX + 4, cur.y + (isHovered ? 4 : 3));
            ctx.restore();
        }
    });
    
    // --- Draw Floating Tooltip ---
    if (rrgHoveredSector && rrgMouseX !== null && rrgMouseY !== null) {
        const frame = frames[frameIdx];
        const entry = frame?.sectors.find(s => s.sector === rrgHoveredSector);
        if (entry) {
            ctx.save();
            const sectorColor = RRG_SECTOR_COLORS[rrgHoveredSector] || RRG_DEFAULT_COLOR;
            const text1 = `${rrgHoveredSector}`;
            const text2 = `Relative Strength (X): ${entry.jdk_rs.toFixed(2)}`;
            const text3 = `Momentum (Y): ${entry.jdk_rs_momentum.toFixed(2)}`;
            const text4 = `Score: ${entry.score} | ${entry.quadrant}`;
            
            ctx.font = '11px Inter, sans-serif';
            const w1 = ctx.measureText(text1).width;
            const w2 = ctx.measureText(text2).width;
            const w3 = ctx.measureText(text3).width;
            const w4 = ctx.measureText(text4).width;
            const tooltipW = Math.max(w1, w2, w3, w4) + 16;
            const tooltipH = 68;
            
            let tx = rrgMouseX + 12;
            let ty = rrgMouseY + 12;
            if (tx + tooltipW > W) tx = rrgMouseX - tooltipW - 12;
            if (ty + tooltipH > H) ty = rrgMouseY - tooltipH - 12;
            
            // Tooltip drop shadow
            ctx.shadowBlur = 12;
            ctx.shadowColor = 'rgba(0, 0, 0, 0.4)';
            
            // Draw background
            ctx.fillStyle = 'rgba(15, 23, 42, 0.95)';
            ctx.strokeStyle = sectorColor;
            ctx.lineWidth = 1.0;
            ctx.beginPath();
            ctx.roundRect ? ctx.roundRect(tx, ty, tooltipW, tooltipH, 6) : ctx.rect(tx, ty, tooltipW, tooltipH);
            ctx.fill();
            ctx.stroke();
            
            ctx.shadowBlur = 0; // reset shadow
            
            // Draw details text
            ctx.fillStyle = '#ffffff';
            ctx.font = 'bold 11px Inter, sans-serif';
            ctx.fillText(text1, tx + 8, ty + 16);
            
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.font = '10px Inter, sans-serif';
            ctx.fillText(text2, tx + 8, ty + 30);
            ctx.fillText(text3, tx + 8, ty + 42);
            
            let quadColor = '#94a3b8';
            if (entry.quadrant === 'Leading') quadColor = '#10b981';
            else if (entry.quadrant === 'Weakening') quadColor = '#ef4444';
            else if (entry.quadrant === 'Lagging') quadColor = '#6366f1';
            else if (entry.quadrant === 'Improving') quadColor = '#f59e0b';
            
            ctx.fillStyle = quadColor;
            ctx.font = 'bold 10px Inter, sans-serif';
            ctx.fillText(text4, tx + 8, ty + 56);
            
            ctx.restore();
        }
    }
    
    // --- Week label update ---
    const weekLabel = document.getElementById('rrg-week-label');
    if (weekLabel && frames[frameIdx]) weekLabel.textContent = `Week: ${frames[frameIdx].week}`;
    
    // --- Scrubber sync ---
    const scrubber = document.getElementById('rrg-timeline-scrubber');
    if (scrubber) scrubber.value = frameIdx;
}

function startRRGAnimation() {
    if (rrgAnimTimer) return;
    document.getElementById('btn-rrg-play')?.classList.add('hidden');
    document.getElementById('btn-rrg-pause')?.classList.remove('hidden');
    
    rrgAnimTimer = setInterval(() => {
        rrgCurrentFrame++;
        if (rrgCurrentFrame >= rrgHistoryFrames.length) {
            stopRRGAnimation();
            rrgCurrentFrame = rrgHistoryFrames.length - 1;
        }
        renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
    }, RRG_ANIM_INTERVAL_MS);
}

function stopRRGAnimation() {
    clearInterval(rrgAnimTimer);
    rrgAnimTimer = null;
    document.getElementById('btn-rrg-play')?.classList.remove('hidden');
    document.getElementById('btn-rrg-pause')?.classList.add('hidden');
}

function resetRRGAnimation() {
    stopRRGAnimation();
    rrgCurrentFrame = 0;
    renderRRGTimeline(rrgHistoryFrames, 0);
}

async function loadRRGHistory(weeks = 12) {
    try {
        const res = await fetch(`/api/rrg/history?weeks=${weeks}`);
        const data = await res.json();
        rrgHistoryFrames = data.frames || [];
        
        // Fallback if history is empty
        if (rrgHistoryFrames.length === 0) {
            const weekLabel = document.getElementById('rrg-week-label');
            if (weekLabel) weekLabel.textContent = "Building history...";
            return;
        }
        
        // Calculate dynamic limits based on the loaded frames
        updateRRGScaleLimits(rrgHistoryFrames);
        
        rrgCurrentFrame  = Math.max(0, rrgHistoryFrames.length - 1);
        
        const scrubber = document.getElementById('rrg-timeline-scrubber');
        if (scrubber) {
            scrubber.max = Math.max(0, rrgHistoryFrames.length - 1);
            scrubber.value = rrgCurrentFrame;
        }
        
        renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
    } catch (err) {
        console.error('RRG history load failed:', err);
    }
}

// Add RRG Toggle Listeners
document.getElementById('btn-rrg-sectors')?.addEventListener('click', (e) => {
    rrgViewMode = 'sectors';
    document.getElementById('btn-rrg-sectors')?.classList.add('btn-primary');
    document.getElementById('btn-rrg-sectors')?.classList.remove('btn-secondary');
    document.getElementById('btn-rrg-stocks')?.classList.remove('btn-primary');
    document.getElementById('btn-rrg-stocks')?.classList.add('btn-secondary');
    renderRRG();
});
document.getElementById('btn-rrg-stocks')?.addEventListener('click', (e) => {
    rrgViewMode = 'stocks';
    document.getElementById('btn-rrg-stocks')?.classList.add('btn-primary');
    document.getElementById('btn-rrg-stocks')?.classList.remove('btn-secondary');
    document.getElementById('btn-rrg-sectors')?.classList.remove('btn-primary');
    document.getElementById('btn-rrg-sectors')?.classList.add('btn-secondary');
    renderRRG();
});

// Playback Controls
document.getElementById('btn-rrg-play')?.addEventListener('click', startRRGAnimation);
document.getElementById('btn-rrg-pause')?.addEventListener('click', stopRRGAnimation);
document.getElementById('btn-rrg-reset')?.addEventListener('click', resetRRGAnimation);

let rrgScrubberPending = false;
document.getElementById('rrg-timeline-scrubber')?.addEventListener('input', e => {
    stopRRGAnimation();
    rrgCurrentFrame = parseInt(e.target.value);
    if (!rrgScrubberPending) {
        rrgScrubberPending = true;
        requestAnimationFrame(() => {
            renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
            rrgScrubberPending = false;
        });
    }
});

document.getElementById('rrg-weeks-select')?.addEventListener('change', e => {
    stopRRGAnimation();
    loadRRGHistory(parseInt(e.target.value));
});

document.getElementById('btn-rrg-snapshot-now')?.addEventListener('click', () => {
    const snapBtn = document.getElementById('btn-rrg-snapshot-now');
    if (!snapBtn) return;
    const originalHtml = snapBtn.innerHTML;
    snapBtn.disabled = true;
    snapBtn.innerHTML = '<span class="btn-spinner"></span>';
    
    fetch('/api/rrg/snapshot', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                showToast("Snapshot saved successfully", "success");
                const weeksSelect = document.getElementById('rrg-weeks-select');
                const weeks = weeksSelect ? parseInt(weeksSelect.value) : 12;
                loadRRGHistory(weeks);
            } else {
                showToast("Snapshot error: " + data.error, "error");
            }
        })
        .catch(err => {
            showToast("Failed to run RRG snapshot: " + err.message, "error");
        })
        .finally(() => {
            snapBtn.disabled = false;
            snapBtn.innerHTML = originalHtml;
        });
});

document.getElementById('rrg-canvas')?.addEventListener('click', e => {
    if (rrgHistoryFrames.length === 0) return;
    const canvas  = e.currentTarget;
    const rect    = canvas.getBoundingClientRect();
    const mouseX  = e.clientX - rect.left;
    const mouseY  = e.clientY - rect.top;
    const frame   = rrgHistoryFrames[rrgCurrentFrame];
    if (!frame) return;
    
    const W = rect.width;
    const H = rect.height;
    const pad = 48;
    
    const clamp = (val, min, max) => Math.max(min, Math.min(max, val));
    const RS_MIN = rrgScale.rsMin, RS_MAX = rrgScale.rsMax, MO_MIN = rrgScale.moMin, MO_MAX = rrgScale.moMax;
    const toX = rs  => pad + ((clamp(rs, RS_MIN, RS_MAX) - RS_MIN)  / (RS_MAX - RS_MIN))  * (W - pad * 2);
    const toY = mom => (H - pad) - ((clamp(mom, MO_MIN, MO_MAX) - MO_MIN) / (MO_MAX - MO_MIN)) * (H - pad * 2);
    
    let clickedSector = null;
    frame.sectors.forEach(s => {
        const x = toX(s.jdk_rs);
        const y = toY(s.jdk_rs_momentum);
        const dx = mouseX - x;
        const dy = mouseY - y;
        const hitR = 6 + (s.score / 100) * 5 + 8; // generous hit area
        if (Math.sqrt(dx * dx + dy * dy) <= hitR) {
            clickedSector = s.sector;
        }
    });
    
    if (clickedSector) {
        const screenerTabs = document.querySelector('.screener-tabs');
        if (screenerTabs) {
            const momentumBtn = screenerTabs.querySelector('[data-tab="momentum"]');
            if (momentumBtn) momentumBtn.click();
        }
        
        if (typeof selectSector === 'function') {
            selectSector(clickedSector);
            switchWorkspace('screener');
            showToast(`Screener filtered to ${clickedSector} — check the table below`, 'info');
        }
    }
});

document.getElementById('rrg-canvas')?.addEventListener('mousemove', e => {
    if (rrgHistoryFrames.length === 0) return;
    const canvas  = e.currentTarget;
    const rect    = canvas.getBoundingClientRect();
    const mouseX  = e.clientX - rect.left;
    const mouseY  = e.clientY - rect.top;
    const frame   = rrgHistoryFrames[rrgCurrentFrame];
    if (!frame) return;
    
    const W = rect.width;
    const H = rect.height;
    const pad = 48;
    
    const clamp = (val, min, max) => Math.max(min, Math.min(max, val));
    const RS_MIN = rrgScale.rsMin, RS_MAX = rrgScale.rsMax, MO_MIN = rrgScale.moMin, MO_MAX = rrgScale.moMax;
    const toX = rs  => pad + ((clamp(rs, RS_MIN, RS_MAX) - RS_MIN)  / (RS_MAX - RS_MIN))  * (W - pad * 2);
    const toY = mom => (H - pad) - ((clamp(mom, MO_MIN, MO_MAX) - MO_MIN) / (MO_MAX - MO_MIN)) * (H - pad * 2);
    
    let hovered = null;
    frame.sectors.forEach(s => {
        const x = toX(s.jdk_rs);
        const y = toY(s.jdk_rs_momentum);
        const dx = mouseX - x;
        const dy = mouseY - y;
        const hitR = 6 + (s.score / 100) * 5 + 8; // generous hit area
        if (Math.sqrt(dx * dx + dy * dy) <= hitR) {
            hovered = s.sector;
        }
    });
    
    const changed = (rrgHoveredSector !== hovered || rrgMouseX !== mouseX || rrgMouseY !== mouseY);
    rrgHoveredSector = hovered;
    rrgMouseX = mouseX;
    rrgMouseY = mouseY;
    
    canvas.style.cursor = hovered ? 'pointer' : 'default';
    
    if (changed) {
        renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
    }
});

document.getElementById('rrg-canvas')?.addEventListener('mouseleave', e => {
    if (rrgHoveredSector !== null) {
        rrgHoveredSector = null;
        rrgMouseX = null;
        rrgMouseY = null;
        e.currentTarget.style.cursor = 'default';
        renderRRGTimeline(rrgHistoryFrames, rrgCurrentFrame);
    }
});


// --- Sector Heatmap ---
function renderSectorHeatmap() {
    const container = document.getElementById('sector-heatmap');
    if (!container) return;
    
    // Convert sectorScores to array and filter out empty sectors
    const sectorsArray = Object.keys(sectorScores)
        .filter(s => sectorScores[s].count > 0)
        .map(s => ({
            name: s,
            ...sectorScores[s]
        }));
        
    // Sort by quadrant priority, then by score
    const quadPriority = { 'Leading': 1, 'Improving': 2, 'Weakening': 3, 'Lagging': 4 };
    sectorsArray.sort((a, b) => {
        if (quadPriority[a.quadrant] !== quadPriority[b.quadrant]) {
            return quadPriority[a.quadrant] - quadPriority[b.quadrant];
        }
        return b.score - a.score;
    });
    
    let html = '';
    sectorsArray.forEach(sector => {
        let quadClass = '';
        let arrow = '';
        if (sector.quadrant === 'Leading') { quadClass = 'quad-leading'; arrow = '↗'; }
        else if (sector.quadrant === 'Improving') { quadClass = 'quad-improving'; arrow = '↖'; }
        else if (sector.quadrant === 'Weakening') { quadClass = 'quad-weakening'; arrow = '↘'; }
        else { quadClass = 'quad-lagging'; arrow = '↙'; }
        
        html += `
            <div class="sector-tile ${quadClass}" onclick="filterBySectorHeatmap('${sector.name}')">
                <div class="sector-tile-header">
                    <span class="sector-tile-name" title="${sector.name}">${sector.name}</span>
                    <span class="sector-tile-arrow">${arrow}</span>
                </div>
                <div class="sector-tile-quad">${sector.quadrant}</div>
                <div class="sector-tile-stats">
                    <span>Score: ${sector.score}</span>
                    <span>A/D: <span style="color:var(--accent-green)">${sector.advances}</span> / <span style="color:var(--accent-red)">${sector.declines}</span></span>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

window.clearRRGSectorFilter = function() {
    selectSector('all');
    rrgViewMode = 'stocks';
    const btnSectors = document.getElementById('btn-rrg-sectors');
    const btnStocks = document.getElementById('btn-rrg-stocks');
    if (btnSectors && btnStocks) {
        btnStocks.classList.add('active', 'btn-primary');
        btnStocks.classList.remove('btn-secondary');
        btnSectors.classList.remove('active', 'btn-primary');
        btnSectors.classList.add('btn-secondary');
    }
    renderRRG();
};

window.filterBySectorHeatmap = function(sectorName) {
    // Switch RRG View Mode to stocks
    rrgViewMode = 'stocks';
    
    // Update the toggles UI state
    const btnSectors = document.getElementById('btn-rrg-sectors');
    const btnStocks = document.getElementById('btn-rrg-stocks');
    if (btnSectors && btnStocks) {
        btnSectors.classList.remove('active', 'btn-primary');
        btnSectors.classList.add('btn-secondary');
        btnStocks.classList.add('active', 'btn-primary');
        btnStocks.classList.remove('btn-secondary');
    }
    
    // Set the filter (this also calls filterAndRender, which will trigger renderRRG)
    if (typeof selectSector === 'function') {
        selectSector(sectorName);
    }
};


// Add RRG Toggle Listeners
document.getElementById('btn-rrg-sectors')?.addEventListener('click', (e) => {
    rrgViewMode = 'sectors';
    e.target.classList.add('active', 'btn-primary');
    e.target.classList.remove('btn-secondary');
    const stBtn = document.getElementById('btn-rrg-stocks');
    stBtn.classList.remove('active', 'btn-primary');
    stBtn.classList.add('btn-secondary');
    renderRRG();
});
document.getElementById('btn-rrg-stocks')?.addEventListener('click', (e) => {
    rrgViewMode = 'stocks';
    e.target.classList.add('active', 'btn-primary');
    e.target.classList.remove('btn-secondary');
    const secBtn = document.getElementById('btn-rrg-sectors');
    secBtn.classList.remove('active', 'btn-primary');
    secBtn.classList.add('btn-secondary');
    renderRRG();
});

// -----------------------------------------------------------------------------
// Phase 3: Trade Setup Drawer Logic
// -----------------------------------------------------------------------------

window.currentTradeStock = null;

function openTradeDrawer(ticker) {
    const stock = stocksData.find(s => s.clean_ticker === ticker);
    if (!stock) return;
    
    window.currentTradeStock = stock;
    
    // Elements
    const overlay = document.getElementById('trade-drawer-overlay');
    const drawer = document.getElementById('trade-drawer');
    
    // Header
    document.getElementById('drawer-ticker').textContent = stock.clean_ticker;
    document.getElementById('drawer-name').textContent = stock.description;
    
    // Setup Pill
    const pillEl = document.getElementById('drawer-setup-pill');
    const label = stock.setupLabel || 'Early Watch';
    let pillClass = 'setup-pill-early';
    let icon = '';
    if (label.includes('VCP')) { pillClass = 'setup-pill-vcp'; icon = '🌀 '; }
    else if (label.includes('Cup & Handle')) { pillClass = 'setup-pill-cup'; icon = '🍺 '; }
    else if (label.includes('High Tight Flag')) { pillClass = 'setup-pill-flag'; icon = '🚩 '; }
    else if (label.includes('Long Base')) { pillClass = 'setup-pill-base'; icon = '🧱 '; }
    else if (label === 'Breakout Ready') { pillClass = 'setup-pill-breakout'; icon = '🚀 '; }
    else if (label === 'Pullback to MA') { pillClass = 'setup-pill-pullback'; icon = '📉 '; }
    else if (label === 'Inside Bar Coil') { pillClass = 'setup-pill-coil'; icon = '🌀 '; }
    else if (label === 'Sector Leader') { pillClass = 'setup-pill-leader'; icon = '👑 '; }
    else if (label === 'Momentum Continuation') { pillClass = 'setup-pill-cont'; icon = '📈 '; }
    
    pillEl.className = `setup-pill ${pillClass}`;
    pillEl.textContent = `${icon}${label}`;
    
    // Price
    const closePrice = parseFloat(stock.close) || 0;
    document.getElementById('drawer-current-price').textContent = `₹${closePrice.toFixed(2)}`;
    
    // Earnings Warning
    const warningEl = document.getElementById('drawer-earnings-warning');
    if (warningEl) {
        warningEl.style.display = 'none';
        const eDate = stock.upcoming_earnings;
        if (eDate) {
            const [ey, em, ed] = eDate.split('-').map(Number);
            const diffDays = Math.round((new Date(ey, em - 1, ed) - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24));
            const formatted = new Date(ey, em - 1, ed).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
            
            if (diffDays >= 0 && diffDays <= 5) {
                warningEl.style.display = 'block';
                warningEl.style.backgroundColor = 'rgba(232, 175, 52, 0.15)';
                warningEl.style.color = '#e8af34';
                warningEl.style.borderLeftColor = '#e8af34';
                warningEl.innerHTML = `⚠️ Earnings on ${formatted} — ${diffDays} day(s) away. Consider sizing down or waiting.`;
            } else if (diffDays > 5 && diffDays <= 10) {
                warningEl.style.display = 'block';
                warningEl.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                warningEl.style.color = 'var(--color-text-primary)';
                warningEl.style.borderLeftColor = 'rgba(255, 255, 255, 0.2)';
                warningEl.innerHTML = `📅 Earnings in ${diffDays} day(s) — plan exit before.`;
            }
        }
    }
    
    // MTF Warning
    const mtfWarningEl = document.getElementById('drawer-mtf-warning');
    if (mtfWarningEl) {
        if (stock.mtfScore === 0 && label === 'Breakout Ready') {
            mtfWarningEl.style.display = 'flex';
        } else {
            mtfWarningEl.style.display = 'none';
        }
    }
    
    // Volume Compression Warning
    const volWarningEl = document.getElementById('drawer-vol-warning');
    if (volWarningEl) {
        if (stock.volDryUp) {
            volWarningEl.style.display = 'flex';
        } else {
            volWarningEl.style.display = 'none';
        }
    }
    
    initializeTradeParams();
    
    // Fetch Scan History
    const historyContainer = document.getElementById('drawer-history-content');
    if (historyContainer) {
        historyContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--color-text-muted);">Loading history...</div>';
        
        fetch(`/api/backtest-summary?ticker=${encodeURIComponent(stock.clean_ticker)}`)
            .then(res => res.json())
            .then(data => {
                if (data.error || data.appearance_count === 0) {
                    historyContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--color-text-muted);">No history available.</div>';
                    return;
                }
                
                const retClass = data.return_since_first >= 0 ? 'history-stat-positive' : 'history-stat-negative';
                const retSign = data.return_since_first > 0 ? '+' : '';
                
                const maxGainClass = data.max_gain >= 0 ? 'history-stat-positive' : '';
                const maxGainSign = data.max_gain > 0 ? '+' : '';
                
                historyContainer.innerHTML = `
                    <div class="history-stat-row">
                        <span class="history-stat-label">First Seen</span>
                        <span class="history-stat-value">${data.first_seen}</span>
                    </div>
                    <div class="history-stat-row">
                        <span class="history-stat-label">Appearances</span>
                        <span class="history-stat-value">${data.appearance_count} days</span>
                    </div>
                    <div class="history-stat-row">
                        <span class="history-stat-label">First Price</span>
                        <span class="history-stat-value">₹${(data.first_close || 0).toFixed(2)}</span>
                    </div>
                    <div class="history-stat-row">
                        <span class="history-stat-label">Return Since First</span>
                        <span class="history-stat-value ${retClass}">${retSign}${data.return_since_first}%</span>
                    </div>
                    <div class="history-stat-row">
                        <span class="history-stat-label">Max Excursion</span>
                        <span class="history-stat-value ${maxGainClass}">${maxGainSign}${data.max_gain}%</span>
                    </div>
                `;
            })
            .catch(err => {
                console.error("History fetch error:", err);
                historyContainer.innerHTML = '<div style="font-size: 0.8rem; color: var(--accent-red);">Failed to load history.</div>';
            });
    }

    // Show drawer
    overlay.classList.add('open');
    drawer.classList.add('open');
    
    const rb = marketBreadth.regimeBand  ?? 'Neutral';
    const rs = marketBreadth.regimeScore ?? 50;
    const sizingMap = {
      'Bull Run':    { hint: 'Full size — bull conditions support aggressive positioning.', cls: 'regime-hint--bullish' },
      'Bullish':     { hint: 'Normal size — bullish market supports standard risk.',        cls: 'regime-hint--bullish' },
      'Neutral':     { hint: 'Half size — mixed market. Reduce risk per trade by 50%.',    cls: 'regime-hint--neutral' },
      'Bearish':     { hint: 'Quarter size only — high stop-out risk in bearish conditions.', cls: 'regime-hint--bearish' },
      'Bear Market': { hint: 'Avoid new longs — bear market conditions active.',            cls: 'regime-hint--danger' },
    };
    const sz = sizingMap[rb] ?? sizingMap['Neutral'];
    const hint = document.getElementById('drawer-regime-hint');
    if (hint) {
      hint.className = `drawer-regime-hint ${sz.cls}`;
      hint.innerHTML = `
        <span class="regime-hint-label">Market Regime</span>
        <span class="regime-hint-band">${rb} (${rs}/100)</span>
        <span class="regime-hint-guidance">${sz.hint}</span>
      `;
    }
    
    // Watchlist & Chart Action Buttons
    const btnChart = document.getElementById('btn-drawer-chart');
    if (btnChart) {
        btnChart.onclick = () => openTradingView(stock.clean_ticker);
    }
    const btnWatchlist = document.getElementById('btn-drawer-watchlist');
    if (btnWatchlist) {
        btnWatchlist.onclick = (e) => {
            addToWatchlist(stock.clean_ticker, e);
            // Optionally close drawer or just let them know
        };
    }

    // Screener Intelligence AI Setup Analysis fetch
    const intelSection = document.getElementById('drawer-intelligence-section');
    if (intelSection) {
        intelSection.style.display = 'block';
        document.getElementById('drawer-intel-pattern').textContent = 'Analyzing Pattern...';
        document.getElementById('drawer-intel-grade').textContent = '-';
        document.getElementById('drawer-intel-desc').textContent = 'Running pattern recognition scans on daily chart history...';
        document.getElementById('drawer-intel-checklist').innerHTML = '';
        
        // Reset Kronos elements
        const kronosForecastRow = document.getElementById('drawer-kronos-forecast-row');
        if (kronosForecastRow) {
            kronosForecastRow.style.display = 'none';
            document.getElementById('drawer-kronos-bias').textContent = '-';
            document.getElementById('drawer-kronos-score').textContent = '0%';
            document.getElementById('drawer-kronos-score-bar').style.width = '0%';
            const metricsEl = document.getElementById('drawer-kronos-metrics');
            if (metricsEl) { metricsEl.style.display = 'none'; metricsEl.innerHTML = ''; }
        }
        
        if (activeDrawerChart) {
            try {
                activeDrawerChart.remove();
            } catch (e) {
                console.error("Error removing chart:", e);
            }
            activeDrawerChart = null;
        }
        
        fetch(`/api/setup-analysis?ticker=${encodeURIComponent(stock.clean_ticker)}`)
            .then(res => res.json())
            .then(data => {
                if (data.error) {
                    document.getElementById('drawer-intel-pattern').textContent = 'Analysis Unavailable';
                    document.getElementById('drawer-intel-desc').textContent = `Could not analyze: ${data.error}`;
                    return;
                }
                
                document.getElementById('drawer-intel-pattern').textContent = data.pattern;
                document.getElementById('drawer-intel-grade').textContent = data.grade;
                document.getElementById('drawer-intel-desc').textContent = data.description;
                
                const gradeBadge = document.getElementById('drawer-intel-grade');
                if (gradeBadge) {
                    if (data.grade.includes('A')) {
                        gradeBadge.style.backgroundColor = 'rgba(16, 185, 129, 0.15)';
                        gradeBadge.style.color = '#4ade80';
                        gradeBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
                    } else if (data.grade.includes('B')) {
                        gradeBadge.style.backgroundColor = 'rgba(168, 85, 247, 0.15)';
                        gradeBadge.style.color = '#c084fc';
                        gradeBadge.style.borderColor = 'rgba(168, 85, 247, 0.3)';
                    } else {
                        gradeBadge.style.backgroundColor = 'rgba(255, 255, 255, 0.05)';
                        gradeBadge.style.color = 'var(--color-text-muted)';
                        gradeBadge.style.borderColor = 'rgba(255, 255, 255, 0.1)';
                    }
                }
                
                // Populate Kronos AI Forecast elements
                if (kronosForecastRow) {
                    kronosForecastRow.style.display = 'block';
                    const biasBadge = document.getElementById('drawer-kronos-bias');
                    const bias = data.ai_forecast_bias ? normalizeBias(data.ai_forecast_bias) : null;

                    if (!bias) {
                        // Model did not run or threw an error — show neutral grey Unavailable badge
                        biasBadge.textContent = 'Unavailable';
                        biasBadge.style.backgroundColor = 'rgba(148, 163, 184, 0.12)';
                        biasBadge.style.color = '#94a3b8';
                        biasBadge.style.border = '1px solid rgba(148, 163, 184, 0.25)';
                        document.getElementById('drawer-kronos-score').textContent = '—';
                        document.getElementById('drawer-kronos-score-bar').style.width = '0%';
                    } else {
                        biasBadge.textContent = bias;

                        // 5-label badge colour mapping
                        const biasStyles = {
                            'Strong Breakout':      { bg: 'rgba(16, 185, 129, 0.25)',  color: '#34d399', border: 'rgba(16, 185, 129, 0.5)' },
                            'Bullish Continuation': { bg: 'rgba(16, 185, 129, 0.12)',  color: '#4ade80', border: 'rgba(16, 185, 129, 0.3)' },
                            'Sideways Consolidation':{ bg: 'rgba(245, 158, 11, 0.12)', color: '#fbbf24', border: 'rgba(245, 158, 11, 0.3)' },
                            'Bearish Pressure':     { bg: 'rgba(249, 115, 22, 0.15)',  color: '#fb923c', border: 'rgba(249, 115, 22, 0.35)' },
                            'Strong Downtrend':     { bg: 'rgba(239, 68, 68, 0.20)',   color: '#f87171', border: 'rgba(239, 68, 68, 0.45)' },
                        };
                        const style = biasStyles[bias] || biasStyles['Sideways Consolidation'];
                        biasBadge.style.backgroundColor = style.bg;
                        biasBadge.style.color = style.color;
                        biasBadge.style.border = `1px solid ${style.border}`;

                        document.getElementById('drawer-kronos-score').textContent = data.ai_confidence_score + '%';

                        // Smoothly animate progress bar
                        setTimeout(() => {
                            document.getElementById('drawer-kronos-score-bar').style.width = data.ai_confidence_score + '%';
                        }, 50);

                        // Render forecast metrics pills (return%, consistency%, drawdown%, breakout)
                        const metricsEl = document.getElementById('drawer-kronos-metrics');
                        const m = data.forecast_metrics;
                        if (metricsEl && m && Object.keys(m).length > 0) {
                            const retSign  = m.return_pct  >= 0 ? '+' : '';
                            const ddSign   = m.max_drawdown_pct >= 0 ? '+' : '';
                            const splSign  = m.momentum_split >= 0 ? '+' : '';
                            const retColor = m.return_pct  >= 0 ? '#4ade80' : '#f87171';
                            const ddColor  = m.max_drawdown_pct >= 0 ? '#4ade80' : '#f87171';
                            const splColor = m.momentum_split >= 0 ? '#4ade80' : '#f87171';
                            const brkColor = m.breakout_signal ? '#34d399' : '#94a3b8';
                            const brkText  = m.breakout_signal ? '🚀 New High' : '⬛ No Breakout';
                            metricsEl.innerHTML = `
                                <span style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:1px 6px;font-size:0.68rem;color:${retColor}">
                                    Return ${retSign}${m.return_pct}%
                                </span>
                                <span style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:1px 6px;font-size:0.68rem;color:var(--color-text-secondary)">
                                    Consist ${m.consistency_pct}%
                                </span>
                                <span style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:1px 6px;font-size:0.68rem;color:${ddColor}">
                                    DD ${ddSign}${m.max_drawdown_pct}%
                                </span>
                                <span style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:1px 6px;font-size:0.68rem;color:${splColor}">
                                    Split ${splSign}${m.momentum_split}%
                                </span>
                                <span style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:4px;padding:1px 6px;font-size:0.68rem;color:${brkColor}">
                                    ${brkText}
                                </span>
                            `;
                            metricsEl.style.display = 'flex';
                        }
                    }
                }
                
                const checklistEl = document.getElementById('drawer-intel-checklist');
                if (checklistEl && data.indicators) {
                    const checkItems = [
                        { label: 'Price > 21 SMA', val: data.indicators.price_above_21_sma },
                        { label: 'Price > 50 SMA', val: data.indicators.price_above_50_sma },
                        { label: 'Volume Dryup', val: data.indicators.vol_dryup_last_10d },
                        { label: 'Breakout Vol', val: data.indicators.volume_expansion_today },
                        { label: 'Tight Consol (<10%)', val: data.indicators.tightness_last_15d }
                    ];
                    
                    checklistEl.innerHTML = checkItems.map(item => `
                        <div style="display: flex; align-items: center; gap: 0.3rem;">
                            <span>${item.val ? '🟢' : '❌'}</span>
                            <span style="color: ${item.val ? 'var(--color-text-primary)' : 'var(--color-text-muted)'}">${item.label}</span>
                        </div>
                    `).join('');
                }
                
                if (data.chart_data && data.chart_data.length > 0) {
                    window.currentDrawerChartData = data.chart_data;
                    window.currentDrawerForecastData = data.forecast_data || [];
                    createTradeDrawerChart('drawer-tv-chart', data.chart_data, data.forecast_data || []);
                }

                // Reset interactive Kronos section
                const kronosSection = document.getElementById('drawer-kronos-section');
                if (kronosSection) {
                    kronosSection.style.display = 'none';
                    const tbody = document.getElementById('drawer-kronos-tbody');
                    if (tbody) tbody.innerHTML = '';
                    destroyKronosChart();
                }

                // Fetch interactive Kronos details (sample_count = 10 for envelope calculation)
                fetch(`/api/kronos-forecast?ticker=${encodeURIComponent(stock.clean_ticker)}&pred_len=${KRONOS_FORECAST_HORIZON}&sample_count=10`)
                    .then(res => res.json())
                    .then(kdata => {
                        if (kdata.error) {
                            console.error("Kronos forecast API error:", kdata.error);
                            return;
                        }
                        if (window.currentTradeStock && window.currentTradeStock.clean_ticker === kdata.ticker) {
                            renderKronosForecastPanel(kdata);
                        }
                    })
                    .catch(err => {
                        console.error("Kronos forecast fetch error:", err);
                    });
            })
            .catch(err => {
                document.getElementById('drawer-intel-pattern').textContent = 'Error';
                document.getElementById('drawer-intel-desc').textContent = `Pattern scan failed: ${err}`;
            });
    }
}

function initializeTradeParams() {
    if (!window.currentTradeStock) return;
    const stock = window.currentTradeStock;
    
    const entryEl = document.getElementById('drawer-entry-input');
    const stopEl = document.getElementById('drawer-stop-input');
    const riskEl = document.getElementById('drawer-risk-amount');
    
    const savedStr = localStorage.getItem('tradeDrawerParams_' + stock.clean_ticker);
    let savedParams = null;
    if (savedStr) {
        try { savedParams = JSON.parse(savedStr); } catch(e){}
    }
    
    const label = stock.setupLabel || '';
    const closePrice = parseFloat(stock.close) || 0;
    const atr = parseFloat(stock.atr_pct) ? (closePrice * parseFloat(stock.atr_pct) / 100) : (closePrice * 0.03); // fallback 3%
    const sma21 = parseFloat(stock.SMA21) || closePrice;
    const sma50 = parseFloat(stock.SMA50) || closePrice;
    const high52 = parseFloat(stock.price_52_week_high) || closePrice;
    const highPrice = parseFloat(stock.high) || closePrice;
    const lowPrice = parseFloat(stock.low) || closePrice;
    
    let defaultEntry = closePrice;
    let entryType = 'Market Close';
    let defaultStop = closePrice - (1.5 * atr);
    let stopType = 'ATR (1.5)';
    
    // Entry Logic
    if (label === 'Breakout Ready') {
        defaultEntry = high52 * 1.002;
        entryType = '52W High Breakout';
    } else if (label === 'Pullback to MA') {
        entryType = 'Market / Retest Zone';
        const structStop = Math.min(sma21, sma50) * 0.995;
        if (structStop < defaultStop) {
            defaultStop = structStop;
            stopType = 'Below MA Structure';
        }
    } else if (label === 'Inside Bar Coil') {
        defaultEntry = highPrice * 1.002;
        entryType = 'IB High Breakout';
        const structStop = lowPrice * 0.998;
        if (structStop < defaultStop) {
            defaultStop = structStop;
            stopType = 'IB Low Structure';
        }
    } else if (label === 'Momentum Continuation') {
        entryType = 'Market Close';
    }
    
    if (defaultStop >= defaultEntry) defaultStop = defaultEntry * 0.95;
    
    entryEl.value = savedParams && savedParams.entry ? savedParams.entry : Number(defaultEntry).toFixed(2);
    stopEl.value = savedParams && savedParams.stop ? savedParams.stop : Number(defaultStop).toFixed(2);
    
    if (savedParams && savedParams.risk) {
        riskEl.value = savedParams.risk;
    } else if (!riskEl.value) {
        riskEl.value = 5000;
    }
    
    const notesEl = document.getElementById('drawer-notes');
    if (notesEl && savedParams && savedParams.notes) {
        notesEl.value = savedParams.notes;
    } else if (notesEl) {
        notesEl.value = '';
    }
    
    document.getElementById('drawer-entry-type').textContent = entryType;
    document.getElementById('drawer-stop-type').textContent = stopType;
    
    updateTradeParams();
}

function updateTradeParams() {
    if (!window.currentTradeStock) return;
    
    const entryEl = document.getElementById('drawer-entry-input');
    const stopEl = document.getElementById('drawer-stop-input');
    const riskEl = document.getElementById('drawer-risk-amount');
    
    const riskAmount = parseFloat(riskEl.value) || 1000;
    const entry = parseFloat(entryEl.value) || 0;
    const stop = parseFloat(stopEl.value) || 0;
    
    let riskPct = 0;
    if (entry <= 0 || stop >= entry) {
        document.getElementById('drawer-risk-per-share').textContent = '₹0.00';
        document.getElementById('drawer-risk-pct').textContent = '0.00%';
        document.getElementById('drawer-qty').textContent = '0';
        document.getElementById('drawer-capital-req').textContent = 'Capital Required: ₹0';
        document.getElementById('drawer-t1').textContent = '₹0.00';
        document.getElementById('drawer-t2').textContent = '₹0.00';
        document.getElementById('drawer-t3').textContent = '₹0.00';
    } else {
        const riskPerShare = entry - stop;
        riskPct = (riskPerShare / entry) * 100;
        let qty = Math.floor(riskAmount / riskPerShare);
        if (qty < 1) qty = 0;
        const capitalReq = qty * entry;
        const t1 = entry + (riskPerShare * 1.5);
        const t2 = entry + (riskPerShare * 2.0);
        const t3 = entry + (riskPerShare * 3.0);
        
        document.getElementById('drawer-risk-per-share').textContent = `₹${riskPerShare.toFixed(2)}`;
        document.getElementById('drawer-risk-pct').textContent = `${riskPct.toFixed(2)}%`;
        document.getElementById('drawer-qty').textContent = qty;
        document.getElementById('drawer-capital-req').textContent = `Capital Required: ₹${capitalReq.toLocaleString('en-IN', {maximumFractionDigits: 0})}`;
        document.getElementById('drawer-t1').textContent = `₹${t1.toFixed(2)}`;
        document.getElementById('drawer-t2').textContent = `₹${t2.toFixed(2)}`;
        document.getElementById('drawer-t3').textContent = `₹${t3.toFixed(2)}`;
    }
    
    // Risk Warning Banner logic
    const bannerEl = document.getElementById('drawer-risk-banner');
    if (bannerEl) {
        bannerEl.innerHTML = '';
        bannerEl.style.display = 'none';
        
        const warnings = [];
        
        // 1. Stop loss risk > 15%
        if (riskPct > 15) {
            warnings.push(`⚠️ Stop loss risk is extremely high (${riskPct.toFixed(2)}% > 15% safety floor). Tighten stop or reduce sizing!`);
        }
        
        // 2. Upcoming earnings within 3 days
        if (window.currentTradeStock && window.currentTradeStock.upcoming_earnings) {
            const eDate = window.currentTradeStock.upcoming_earnings;
            const [ey, em, ed] = eDate.split('-').map(Number);
            const diffDays = Math.round((new Date(ey, em - 1, ed) - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24));
            if (diffDays >= 0 && diffDays <= 3) {
                const formatted = new Date(ey, em - 1, ed).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
                warnings.push(`⚠️ Upcoming Earnings in ${diffDays} day(s) (${formatted}). High gap risk!`);
            }
        }
        
        if (warnings.length > 0) {
            bannerEl.innerHTML = warnings.map(w => `<div class="risk-warning-item">${w}</div>`).join('');
            bannerEl.style.display = 'flex';
        }
    }
    
    const notesEl = document.getElementById('drawer-notes');
    const userParams = {
        entry: entryEl.value,
        stop: stopEl.value,
        risk: riskEl.value,
        notes: notesEl ? notesEl.value : ''
    };
    localStorage.setItem('tradeDrawerParams_' + window.currentTradeStock.clean_ticker, JSON.stringify(userParams));
}

function closeTradeDrawer() {
    const overlay = document.getElementById('trade-drawer-overlay');
    const drawer = document.getElementById('trade-drawer');
    if (overlay) overlay.classList.remove('open');
    if (drawer) drawer.classList.remove('open');
    window.currentTradeStock = null;
    if (activeDrawerChart) {
        try {
            activeDrawerChart.remove();
        } catch (e) {
            console.error("Error removing chart:", e);
        }
        activeDrawerChart = null;
    }
    destroyKronosChart();
    const kronosSection = document.getElementById('drawer-kronos-section');
    if (kronosSection) kronosSection.style.display = 'none';
    const drawerBadge = document.getElementById('drawer-ensemble-conviction');
    if (drawerBadge) drawerBadge.remove();
}

window.openTradeDrawer = openTradeDrawer;
window.closeTradeDrawer = closeTradeDrawer;
window.initializeTradeParams = initializeTradeParams;
window.updateTradeParams = updateTradeParams;

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    const overlay = document.getElementById('trade-drawer-overlay');
    const btnClose = document.getElementById('btn-close-drawer');
    const riskInput = document.getElementById('drawer-risk-amount');
    const entryInput = document.getElementById('drawer-entry-input');
    const stopInput = document.getElementById('drawer-stop-input');
    
    if (overlay) overlay.addEventListener('click', closeTradeDrawer);
    if (btnClose) btnClose.addEventListener('click', closeTradeDrawer);
    if (riskInput) riskInput.addEventListener('input', updateTradeParams);
    
    if (entryInput) {
        entryInput.addEventListener('input', () => {
            document.getElementById('drawer-entry-type').textContent = 'Custom';
            updateTradeParams();
        });
    }
    
    if (stopInput) {
        stopInput.addEventListener('input', () => {
            document.getElementById('drawer-stop-type').textContent = 'Custom';
            updateTradeParams();
        });
    }

    // Kronos Workspace tab setup
    const btnRunKronos = document.getElementById('btn-run-kronos');
    if (btnRunKronos) {
        btnRunKronos.addEventListener('click', () => {
            renderAIForecastWorkspace();
        });
    }

    const kronosTickerInput = document.getElementById('kronos-ticker-input');
    if (kronosTickerInput) {
        kronosTickerInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                renderAIForecastWorkspace();
            }
        });
    }

    // Toggle button clicks for pred len in AI Forecast Workspace
    document.querySelectorAll('.workspace-view#view-ai-forecast .kronos-len-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.workspace-view#view-ai-forecast .kronos-len-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderAIForecastWorkspace();
        });
    });

    // Toggle button clicks for pred len in Trade Drawer
    document.querySelectorAll('#drawer-kronos-section .kronos-len-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#drawer-kronos-section .kronos-len-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const len = parseInt(btn.dataset.len);
            if (window.currentTradeStock) {
                fetch(`/api/kronos-forecast?ticker=${encodeURIComponent(window.currentTradeStock.clean_ticker)}&pred_len=${len}&sample_count=10`)
                    .then(res => res.json())
                    .then(kdata => {
                        if (!kdata.error) {
                            renderKronosForecastPanel(kdata);
                        }
                    });
            }
        });
    });

    // Hook toggle buttons for backtester mode in AI Forecast Workspace
    document.querySelectorAll('.bt-mode-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.bt-mode-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            const searchInput = document.getElementById('kronos-ticker-input');
            const symbol = (searchInput ? searchInput.value.trim().toUpperCase() : '') || 'RELIANCE';
            
            loadBacktestingMetrics(symbol);
        });
    });

    // Individual models toggle change event listener
    document.getElementById('showIndividualModels')?.addEventListener('change', () => {
        const searchInput = document.getElementById('kronos-ticker-input');
        const symbol = (searchInput ? searchInput.value.trim().toUpperCase() : '') || 'RELIANCE';
        
        // Re-render main chart if in ensemble mode
        const activeBtn = document.querySelector('.workspace-view#view-ai-forecast .kronos-len-btn.active');
        const isEnsemble = activeBtn && activeBtn.dataset.mode === 'ensemble';
        if (isEnsemble && window.lastEnsembleData) {
            renderEnsembleChart(window.lastEnsembleData);
        }

        // Re-render backtest chart if in ensemble mode
        const btModeActive = document.querySelector('.bt-mode-btn.active');
        const isEnsembleBt = btModeActive && btModeActive.dataset.mode === 'ensemble';
        if (isEnsembleBt && window.lastEnsembleBacktestData) {
            renderEnsembleBacktestChart(window.lastEnsembleBacktestData);
        }
    });
});

// -----------------------------------------------------------------------------
// Phase 4: Saved Filter Presets Logic
// -----------------------------------------------------------------------------

const systemPresets = [
    {
        id: "sys-breakout",
        name: "🚀 Breakout Hunter",
        isSystem: true,
        filters: {
            setup: "Breakout Ready",
            rvolMin: 1.2,
            changeMin: 0,
            peMin: null,
            peMax: null,
            ims: "strong",
            swing: "strong"
        }
    },
    {
        id: "sys-pullback",
        name: "📉 Pullback Buy Zone",
        isSystem: true,
        filters: {
            setup: "Pullback to MA",
            rvolMin: null,
            changeMin: null,
            peMin: null,
            peMax: null,
            ims: "all",
            swing: "all"
        }
    },
    {
        id: "sys-leader",
        name: "👑 Sector Leaders",
        isSystem: true,
        filters: {
            setup: "Sector Leader",
            rvolMin: null,
            changeMin: null,
            peMin: null,
            peMax: null,
            ims: "all",
            swing: "all"
        }
    },
    {
        id: "sys-momentum",
        name: "📈 High RVOL Momentum",
        isSystem: true,
        filters: {
            setup: "Momentum Continuation",
            rvolMin: 2.0,
            changeMin: null,
            peMin: null,
            peMax: null,
            ims: "strong",
            swing: "all"
        }
    }
];

function getUserPresets() {
    try {
        const data = localStorage.getItem('tvFilterPresets_user');
        return data ? JSON.parse(data) : [];
    } catch (e) {
        return [];
    }
}

function saveUserPresets(presets) {
    localStorage.setItem('tvFilterPresets_user', JSON.stringify(presets));
}

function getAllPresets() {
    return [...systemPresets, ...getUserPresets()];
}

function getCurrentFilters() {
    return {
        setup: currentSetupFilter,
        mtf: currentMtfFilter,
        rvolMin: parseFloat(document.getElementById('filter-rvol-min')?.value) || null,
        rvolMax: parseFloat(document.getElementById('filter-rvol-max')?.value) || null,
        changeMin: parseFloat(document.getElementById('filter-change-min')?.value) || null,
        changeMax: parseFloat(document.getElementById('filter-change-max')?.value) || null,
        peMin: parseFloat(document.getElementById('filter-pe-min')?.value) || null,
        peMax: parseFloat(document.getElementById('filter-pe-max')?.value) || null,
        ims: document.getElementById('filter-ims')?.value || 'all',
        swing: document.getElementById('filter-swing')?.value || 'all'
    };
}

function applyPreset(presetId) {
    const preset = getAllPresets().find(p => p.id === presetId);
    if (!preset) return;
    
    const f = preset.filters;
    
    // Setup chips
    currentSetupFilter = f.setup || 'all';
    document.querySelectorAll('.filter-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.value === currentSetupFilter);
    });
    
    // Range inputs
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val !== null && val !== undefined && !isNaN(val) ? val : '';
    };
    
    setVal('filter-rvol-min', f.rvolMin);
    setVal('filter-rvol-max', f.rvolMax);
    setVal('filter-change-min', f.changeMin);
    setVal('filter-change-max', f.changeMax);
    setVal('filter-pe-min', f.peMin);
    setVal('filter-pe-max', f.peMax);
    
    // Selects
    const setSelect = (id, labelId, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val || 'all';
        
        // Update custom dropdown UI
        const dropdownPrefix = id.replace('filter-', ''); // e.g. ims
        document.querySelectorAll(`#${dropdownPrefix}-dropdown .select-dropdown-item`).forEach(item => {
            item.classList.toggle('active', item.dataset.value === (val || 'all'));
            if (item.dataset.value === (val || 'all')) {
                const label = document.getElementById(labelId);
                if (label) label.textContent = item.textContent;
            }
        });
    };
    
    setSelect('filter-ims', 'selected-ims-label', f.ims);
    setSelect('filter-swing', 'selected-swing-label', f.swing);
    
    // Update main preset button label
    const presetLabel = document.getElementById('selected-preset-label');
    if (presetLabel) presetLabel.textContent = preset.name;
    
    // Trigger filter update
    filterAndRender();
}

function renderPresetsDropdown() {
    const dropdown = document.getElementById('preset-dropdown');
    if (!dropdown) return;
    
    const allPresets = getAllPresets();
    let html = `<div class="select-dropdown-item" data-value="reset">Reset to Default</div>`;
    
    if (systemPresets.length > 0) {
        html += `<div style="font-size: 0.65rem; text-transform: uppercase; color: var(--color-text-muted); padding: 0.5rem 1rem 0.2rem; font-weight: 700;">System Presets</div>`;
        systemPresets.forEach(p => {
            html += `<div class="select-dropdown-item" data-value="${p.id}">${p.name}</div>`;
        });
    }
    
    const userPresets = getUserPresets();
    if (userPresets.length > 0) {
        html += `<div style="font-size: 0.65rem; text-transform: uppercase; color: var(--color-text-muted); padding: 0.5rem 1rem 0.2rem; font-weight: 700;">Your Presets</div>`;
        userPresets.forEach(p => {
            html += `
                <div class="select-dropdown-item preset-item-row" data-value="${p.id}" style="display: flex; justify-content: space-between; align-items: center;">
                    <span>${p.name}</span>
                    <button class="btn-delete-preset" data-id="${p.id}" style="background: none; border: none; color: var(--color-text-muted); cursor: pointer; padding: 2px;" title="Delete Preset">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"></path><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                </div>
            `;
        });
    }
    
    dropdown.innerHTML = html;
    
    // Re-attach event listeners for dropdown items
    dropdown.querySelectorAll('.select-dropdown-item').forEach(item => {
        item.addEventListener('click', (e) => {
            // Ignore if clicking the delete button
            if (e.target.closest('.btn-delete-preset')) return;
            
            const val = item.dataset.value;
            if (val === 'reset') {
                const clearBtn = document.getElementById('btn-clear-range-filters');
                if (clearBtn) clearBtn.click();
                
                // Clear Setup Chips as well
                currentSetupFilter = 'all';
                document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
                const chipAll = document.querySelector('.filter-chip[data-value="all"]');
                if (chipAll) chipAll.classList.add('active');
                
                document.getElementById('selected-preset-label').textContent = 'Load Preset...';
                filterAndRender();
            } else {
                applyPreset(val);
            }
            dropdown.classList.add('hidden');
        });
    });
    
    // Attach event listeners for delete buttons
    dropdown.querySelectorAll('.btn-delete-preset').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const id = btn.dataset.id;
            deletePreset(id);
        });
    });
}

function savePreset() {
    const nameInput = document.getElementById('preset-name-input');
    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) return;
    
    const newPreset = {
        id: 'user-preset-' + Date.now(),
        name: name,
        isSystem: false,
        filters: getCurrentFilters()
    };
    
    const userPresets = getUserPresets();
    userPresets.push(newPreset);
    saveUserPresets(userPresets);
    
    renderPresetsDropdown();
    applyPreset(newPreset.id); // select it
    closePresetModal();
}

function deletePreset(id) {
    if (!confirm('Are you sure you want to delete this preset?')) return;
    const userPresets = getUserPresets();
    const updated = userPresets.filter(p => p.id !== id);
    saveUserPresets(updated);
    renderPresetsDropdown();
    document.getElementById('selected-preset-label').textContent = 'Load Preset...';
}

let intradayWidgetSort = {
    'gap-go': { field: 'change', asc: false },
    'vwap': { field: 'change', asc: false },
    'rvol': { field: 'change', asc: false },
    'confluence': { field: 'change', asc: false },
    'focus': { field: 'metric', asc: false }
};

window.sortIntradayWidget = function(widgetId, field) {
    if (intradayWidgetSort[widgetId].field === field) {
        intradayWidgetSort[widgetId].asc = !intradayWidgetSort[widgetId].asc;
    } else {
        intradayWidgetSort[widgetId].field = field;
        intradayWidgetSort[widgetId].asc = false;
    }
    renderIntradayWorkspace();
};

// --- Intraday Workspace ---
function renderIntradayWorkspace() {
    const presetDescriptions = {
        'gap-go': 'Gap & Go — Stocks gapping >1% above VWAP with positive momentum.',
        'vwap': 'VWAP Reclaim — Trading close to and above VWAP with active intraday score.',
        'rvol': 'High RVOL — Relative Volume ≥ 1.5x (unusual volume activity).',
        'confluence': 'Confluence — Strong IMS + Elite/Strong Swing score.',
        'focus': 'Watchlist Focus — Watchlist stocks meeting at least 1 intraday signal.'
    };

    if (!filteredStocks || filteredStocks.length === 0) {
        // Fallback or empty state
        const updateWidget = (id) => {
            const contentEl = document.getElementById(`widget-${id}`);
            const countEl = document.getElementById(`count-${id}`);
            if (contentEl) {
                contentEl.innerHTML = `
                    <div class="intraday-empty-state" style="padding:1.5rem 1rem; text-align:center; color:var(--color-text-muted); font-size:0.8rem; display:flex; flex-direction:column; gap:0.5rem; justify-content:center; align-items:center;">
                        <p style="margin:0; font-weight: 500; font-style: italic;">${presetDescriptions[id]}</p>
                        <p style="margin:0; opacity: 0.8; font-size: 0.75rem;">No candidates match right now. Check back during active trading hours.</p>
                    </div>
                `;
            }
            if (countEl) countEl.textContent = '0';
        };
        updateWidget('gap-go'); updateWidget('vwap'); updateWidget('rvol'); updateWidget('confluence'); updateWidget('focus');
        return;
    }
    
    // 1. Group stocks
    let widgetsData = {
        'gap-go': [],
        'vwap': [],
        'rvol': [],
        'confluence': [],
        'focus': []
    };
    
    // Sort all stocks by relative volume descending for the RVOL widget base dataset
    const sortedByRvol = [...filteredStocks].sort((a, b) => (parseFloat(b.relative_volume) || 0) - (parseFloat(a.relative_volume) || 0));
    widgetsData['rvol'] = sortedByRvol.filter(s => parseFloat(s.relative_volume) >= 1.5).slice(0, 30).map(s => {
        const rvol = parseFloat(s.relative_volume) || 0;
        return { ...s, _metricValue: `${rvol.toFixed(1)}x`, _metricRaw: rvol };
    });
    
    filteredStocks.forEach(s => {
        const gap = parseFloat(s.gap) || 0;
        const changeFromOpen = parseFloat(s.change_from_open) || 0;
        const vwap = parseFloat(s.VWAP) || 0;
        const close = parseFloat(s.close) || 0;
        const rvol = parseFloat(s.relative_volume) || 0;
        const ims = (s.ims_band || '').toLowerCase();
        const swing = (s.swingband || '').toLowerCase();
        const intradayScore = parseFloat(s.intraday_score) || 0;
        const isInWatchlist = watchlistStocks.includes(s.ticker) || watchlistStocks.includes(s.clean_ticker);
        
        // Gap and Go
        if (gap >= 1.0 && changeFromOpen > 0 && close > vwap) {
            widgetsData['gap-go'].push({ ...s, _metricValue: `+${gap.toFixed(1)}%`, _metricRaw: gap });
        }
        
        // VWAP Reclaim
        if (close > vwap && close < vwap * 1.015 && intradayScore > 0) {
            const dist = ((close - vwap) / vwap * 100);
            widgetsData['vwap'].push({ ...s, _metricValue: `+${dist.toFixed(2)}%`, _metricRaw: dist });
        }
        
        // Confluence
        if (ims === 'strong' && (swing === 'strong' || swing === 'elite')) {
            widgetsData['confluence'].push({ ...s, _metricValue: `${intradayScore.toFixed(0)}`, _metricRaw: intradayScore });
        }
        
        // Watchlist Focus
        if (isInWatchlist) {
            let metCount = 0;
            let activeParams = [];
            
            const isGapGo = gap >= 1.0 && changeFromOpen > 0 && close > vwap;
            if (isGapGo) { metCount++; activeParams.push('G'); }
            
            const isVwapReclaim = close > vwap && close < vwap * 1.015 && intradayScore > 0;
            if (isVwapReclaim) { metCount++; activeParams.push('V'); }
            
            const isHighRvol = rvol >= 1.5;
            if (isHighRvol) { metCount++; activeParams.push('R'); }
            
            const isOverlap = ims === 'strong' && (swing === 'strong' || swing === 'elite');
            if (isOverlap) { metCount++; activeParams.push('C'); }
            
            if (metCount >= 1) {
                widgetsData['focus'].push({ 
                    ...s, 
                    _metricValue: `${metCount}/4`, 
                    _metricRaw: metCount,
                    _activeParams: activeParams,
                    _intradayScore: intradayScore
                });
            }
        }
    });

    // 2. Sort and Render
    const widgetConfigs = {
        'gap-go': { metricLabel: 'Gap', color: '--accent-green' },
        'vwap': { metricLabel: 'Dist', color: '--accent-blue' },
        'rvol': { metricLabel: 'RVOL', color: '--accent-orange' },
        'confluence': { metricLabel: 'Score', color: '--accent-purple' },
        'focus': { metricLabel: 'Confl', color: '--accent-purple' }
    };

    Object.keys(widgetsData).forEach(widgetId => {
        const sortState = intradayWidgetSort[widgetId];
        let items = widgetsData[widgetId];
        
        // Sort
        items.sort((a, b) => {
            let valA, valB;
            if (sortState.field === 'ticker') {
                valA = a.clean_ticker || a.ticker;
                valB = b.clean_ticker || b.ticker;
                return sortState.asc ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else if (sortState.field === 'change') {
                valA = parseFloat(a.change) || 0;
                valB = parseFloat(b.change) || 0;
            } else if (sortState.field === 'metric') {
                valA = a._metricRaw || 0;
                valB = b._metricRaw || 0;
                if (widgetId === 'focus' && valA === valB) {
                    const scoreA = a._intradayScore || 0;
                    const scoreB = b._intradayScore || 0;
                    return sortState.asc ? scoreA - scoreB : scoreB - scoreA;
                }
            }
            return sortState.asc ? valA - valB : valB - valA;
        });
        
        const metricLabel = widgetConfigs[widgetId].metricLabel;
        const getSortIcon = (field) => sortState.field === field ? (sortState.asc ? ' ↑' : ' ↓') : '';
        
        const metricWidth = widgetId === 'focus' ? '85px' : '60px';
        let html = `
            <div style="display: flex; align-items: center; padding: 0.5rem 0.25rem; border-bottom: 1px solid var(--color-border); font-size: 0.75rem; color: var(--color-text-muted); margin-bottom: 0.5rem; user-select: none; gap: 0.5rem;">
                <span style="width: 20px; flex-shrink: 0;"></span>
                <span style="cursor:pointer; flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" onclick="sortIntradayWidget('${widgetId}', 'ticker')">Ticker${getSortIcon('ticker')}</span>
                <span style="cursor:pointer; width: 65px; flex-shrink: 0; text-align: right;" onclick="sortIntradayWidget('${widgetId}', 'change')">Change%${getSortIcon('change')}</span>
                <span style="cursor:pointer; text-align:right; width: ${metricWidth}; flex-shrink: 0;" onclick="sortIntradayWidget('${widgetId}', 'metric')">${metricLabel}${getSortIcon('metric')}</span>
            </div>
        `;

        items.forEach(s => {
            const change = parseFloat(s.change) || 0;
            const changeColor = change > 0 ? 'var(--accent-green)' : 'var(--accent-red)';
            const changeSign = change > 0 ? '+' : '';
            let colorClass = widgetConfigs[widgetId].color;
            
            let metricHtml = `<span style="color:var(${colorClass}); font-weight:600;">${s._metricValue}</span>`;
            if (widgetId === 'focus' && s._activeParams) {
                metricHtml = `
                    <span style="display: flex; align-items: center; justify-content: flex-end; gap: 4px;">
                        <span style="color:var(${colorClass}); font-weight:600;">${s._metricValue}</span>
                        <span style="display: flex; gap: 2px;">
                            ${s._activeParams.map(p => {
                                let badgeBg = 'rgba(255, 255, 255, 0.1)';
                                let badgeFg = 'var(--color-text-muted)';
                                if (p === 'G') { badgeBg = 'rgba(16, 185, 129, 0.15)'; badgeFg = '#10b981'; }
                                else if (p === 'V') { badgeBg = 'rgba(59, 130, 246, 0.15)'; badgeFg = '#3b82f6'; }
                                else if (p === 'R') { badgeBg = 'rgba(249, 115, 22, 0.15)'; badgeFg = '#f97316'; }
                                else if (p === 'C') { badgeBg = 'rgba(139, 92, 246, 0.15)'; badgeFg = '#8b5cf6'; }
                                return `<span style="font-size: 0.65rem; font-weight: bold; color: ${badgeFg}; background: ${badgeBg}; border: 1px solid ${badgeFg}30; padding: 1px 3px; border-radius: 3px; line-height: 1;" title="${p === 'G' ? 'Gap & Go' : p === 'V' ? 'VWAP Reclaim' : p === 'R' ? 'High RVOL' : 'Confluence Overlap'}">${p}</span>`;
                            }).join('')}
                        </span>
                    </span>
                `;
            }
            
            html += `
                <div class="intraday-item" onclick="openTradeDrawer('${s.clean_ticker || s.ticker}')" style="display: flex; align-items: center; cursor: pointer; padding: 0.5rem 0.25rem; border-radius: 4px; transition: var(--transition-smooth); gap: 0.5rem;">
                    <button onclick="event.stopPropagation(); openTradingView('${s.clean_ticker || s.ticker}')" title="Open in TradingView" style="background: none; border: none; padding: 0; cursor: pointer; color: var(--accent-blue); font-size: 0.8rem; display: flex; align-items: center; justify-content: center; width: 20px; flex-shrink: 0;">📈</button>
                    <span class="intraday-item-ticker" style="flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; color: var(--color-text-primary);">${s.clean_ticker || s.ticker}</span>
                    <span style="font-size: 0.75rem; color: ${changeColor}; width: 65px; flex-shrink: 0; text-align: right;">${changeSign}${change.toFixed(2)}%</span>
                    <span class="intraday-item-metric" style="justify-content: flex-end; width: ${metricWidth}; flex-shrink: 0;">
                        ${metricHtml}
                    </span>
                </div>
            `;
        });
        
        const contentEl = document.getElementById(`widget-${widgetId}`);
        const countEl = document.getElementById(`count-${widgetId}`);
        if (contentEl) {
            contentEl.innerHTML = items.length > 0 ? html : `
                <div class="intraday-empty-state" style="padding:1.5rem 1rem; text-align:center; color:var(--color-text-muted); font-size:0.8rem; display:flex; flex-direction:column; gap:0.5rem; justify-content:center; align-items:center;">
                    <p style="margin:0; font-weight: 500; font-style: italic;">${presetDescriptions[widgetId]}</p>
                    <p style="margin:0; opacity: 0.8; font-size: 0.75rem;">No candidates match right now.</p>
                </div>
            `;
        }
        if (countEl) countEl.textContent = items.length;
    });
}

window.applyIntradayFilter = function(filterName) {
    // Clear numeric ranges
    document.querySelectorAll('.range-group input').forEach(input => input.value = '');
    
    // Reset global filter variables
    currentSetupFilter = 'all';
    currentMtfFilter = 'all';
    
    // Reset dropdown values
    const filterIms = document.getElementById('filter-ims');
    if (filterIms) filterIms.value = 'all';
    const filterSwing = document.getElementById('filter-swing');
    if (filterSwing) filterSwing.value = 'all';
    
    // Reset dropdown labels
    if (typeof setSelect === 'function') {
        setSelect('filter-ims', 'selected-ims-label', 'All Scores');
        setSelect('filter-swing', 'selected-swing-label', 'All Scores');
    }
    
    // Reset setup & MTF chips visually
    document.querySelectorAll('#setup-filter-chips .filter-chip').forEach(c => c.classList.remove('active'));
    document.querySelector('#setup-filter-chips .filter-chip[data-value="all"]')?.classList.add('active');
    
    document.querySelectorAll('.mtf-filter-chip').forEach(c => c.classList.remove('active'));
    document.querySelector('.mtf-filter-chip[data-value="all"]')?.classList.add('active');
    
    // Clear search
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.value = '';
    
    // Inject custom function into filter pipeline
    activeIntradayFilter = filterName;
    
    // Apply filters and re-render current tab
    filterAndRender();
};

function openPresetModal() {
    const overlay = document.getElementById('preset-modal-overlay');
    if (overlay) overlay.classList.remove('hidden');
    const nameInput = document.getElementById('preset-name-input');
    if (nameInput) {
        nameInput.value = '';
        nameInput.focus();
    }
}

function closePresetModal() {
    const overlay = document.getElementById('preset-modal-overlay');
    if (overlay) overlay.classList.add('hidden');
}

// Preset Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Save Preset button in range filters
    const btnSavePreset = document.getElementById('btn-save-preset');
    if (btnSavePreset) btnSavePreset.addEventListener('click', openPresetModal);
    
    // Modal buttons
    const btnCancel = document.getElementById('btn-cancel-preset');
    const btnCloseModal = document.getElementById('btn-close-preset-modal');
    const btnConfirmSave = document.getElementById('btn-confirm-save-preset');
    
    if (btnCancel) btnCancel.addEventListener('click', closePresetModal);
    if (btnCloseModal) btnCloseModal.addEventListener('click', closePresetModal);
    if (btnConfirmSave) btnConfirmSave.addEventListener('click', savePreset);
    
    // Preset dropdown trigger
    const btnPresets = document.getElementById('btn-presets');
    const presetDropdown = document.getElementById('preset-dropdown');
    if (btnPresets && presetDropdown) {
        btnPresets.addEventListener('click', (e) => {
            e.stopPropagation();
            presetDropdown.classList.toggle('hidden');
        });
    }
    
    // Close dropdowns on outside click
    document.addEventListener('click', (e) => {
        if (presetDropdown && !e.target.closest('#preset-select-wrapper')) {
            presetDropdown.classList.add('hidden');
        }
    });
    
    // Initialize presets UI
    // Initialize presets UI
    renderPresetsDropdown();
});

// ==========================================
// TRADE JOURNAL LOGIC
// ==========================================

function getJournalData() {
    return journalData || [];
}

function setJournalData(data) {
    journalData = data || [];
}

window.saveTradeToJournal = function() {
    if (!window.currentTradeStock) {
        alert("No stock loaded in the drawer.");
        return;
    }
    
    const entryEl = document.getElementById('drawer-entry-input');
    const stopEl = document.getElementById('drawer-stop-input');
    const riskEl = document.getElementById('drawer-risk-amount');
    const qtyEl = document.getElementById('drawer-qty');
    const t1El = document.getElementById('drawer-t1');
    const t2El = document.getElementById('drawer-t2');
    const t3El = document.getElementById('drawer-t3');
    const notesEl = document.getElementById('drawer-notes');
    
    const dateStr = new Date().toISOString().split('T')[0];
    const tradeId = `trade-${Date.now()}-${window.currentTradeStock.clean_ticker}`;
    
    const trade = {
        id: tradeId,
        ticker: window.currentTradeStock.clean_ticker,
        name: window.currentTradeStock.description,
        date: dateStr,
        setupLabel: window.currentTradeStock.setupLabel || 'Early Watch',
        swingband: window.currentTradeStock.swingband || 'weak',
        entry: parseFloat(entryEl.value) || window.currentTradeStock.close,
        stop: parseFloat(stopEl.value) || 0,
        target1: parseFloat(t1El.textContent.replace('₹', '').replace(/,/g, '')) || 0,
        target2: parseFloat(t2El.textContent.replace('₹', '').replace(/,/g, '')) || 0,
        target3: parseFloat(t3El.textContent.replace('₹', '').replace(/,/g, '')) || 0,
        riskAmount: parseFloat(riskEl.value) || 0,
        qty: parseInt(qtyEl.textContent.replace(/,/g, '')) || 0,
        status: 'open',
        exitPrice: null,
        exitDate: null,
        pnl: null,
        rAchieved: null,
        notes: notesEl ? notesEl.value : ''
    };
    
    fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(trade)
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            journalData.unshift(trade);
            renderJournal();
            alert(`Trade for ${trade.ticker} saved to Journal!`);
        } else {
            alert("Failed to save trade: " + resData.error);
        }
    })
    .catch(err => console.error("Error saving trade to journal:", err));
}

function renderJournal() {
    const journal = getJournalData();
    const tbody = document.getElementById('journal-table-body');
    
    if (!journal || journal.length === 0) {
        tbody.innerHTML = `<tr><td colspan="13" style="text-align:center; padding: 2rem; color: var(--color-text-secondary);">No trades logged yet.</td></tr>`;
        updateJournalStats([]);
        return;
    }
    
    let html = '';
    journal.forEach(trade => {
        let statusBadge = '';
        if (trade.status === 'open') statusBadge = `<span class="badge badge-swing-watch">Open</span>`;
        else if (trade.status === 'stopped') statusBadge = `<span class="badge badge-swing-weak">Stopped</span>`;
        else statusBadge = `<span class="badge badge-swing-elite">${trade.status.toUpperCase()}</span>`;
        
        let currentPrice = null;
        const currentStock = stocksData.find(s => s.clean_ticker === trade.ticker);
        if (currentStock && currentStock.close) {
            currentPrice = parseFloat(currentStock.close);
        }
        
        let displayPnl = trade.pnl;
        let displayR = trade.rAchieved;
        let pnlSuffix = '';
        
        if (trade.status === 'open' && currentPrice !== null) {
            displayPnl = (currentPrice - trade.entry) * trade.qty;
            const riskPerShare = trade.entry - trade.stop;
            if (riskPerShare > 0) {
                displayR = (currentPrice - trade.entry) / riskPerShare;
            }
            pnlSuffix = ' <span style="font-size: 0.7rem; color: var(--color-text-muted);">(Open)</span>';
        }
        
        const pnlText = displayPnl !== null ? `₹${displayPnl.toFixed(2)}${pnlSuffix}` : '-';
        const pnlColor = displayPnl > 0 ? 'var(--accent-green)' : (displayPnl < 0 ? 'var(--accent-red)' : 'var(--color-text-primary)');
        const rText = displayR !== null ? `${displayR.toFixed(2)}R` : '-';
        const currentPriceText = currentPrice !== null ? `₹${currentPrice.toFixed(2)}` : (trade.exitPrice ? `₹${trade.exitPrice.toFixed(2)}` : '-');
        
        html += `<tr>
            <td>${trade.date}</td>
            <td style="font-weight: 700; text-decoration: underline;" onclick="event.stopPropagation(); openTradingView('${trade.ticker}')">${trade.ticker}</td>
            <td style="font-weight: 600;">${currentPriceText}</td>
            <td>${trade.setupLabel}</td>
            <td>₹${trade.entry.toFixed(2)}</td>
            <td>₹${trade.stop.toFixed(2)}</td>
            <td style="font-size: 0.8rem; color: var(--color-text-secondary);">
                T1: ₹${(trade.target1 || 0).toFixed(2)}<br>
                T2: ₹${(trade.target2 || 0).toFixed(2)}<br>
                T3: ₹${(trade.target3 || 0).toFixed(2)}
            </td>
            <td>${trade.qty}</td>
            <td>₹${trade.riskAmount.toFixed(2)}</td>
            <td>${statusBadge}</td>
            <td style="font-weight: 600; color: ${pnlColor};">${pnlText}</td>
            <td style="font-weight: 600;">${rText}</td>
            <td style="font-size: 0.85rem; max-width: 200px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(trade.notes || '')}">${escapeHtml(trade.notes || '')}</td>
            <td style="display: flex; gap: 0.5rem; align-items: center; justify-content: center; min-width: 60px;">
                <button onclick="window.openEditTradeModal('${trade.id}')" style="background: none; border: none; color: var(--color-text-muted); cursor: pointer; padding: 4px; font-size: 1.1rem;" title="Edit Entry">✏️</button>
                <button onclick="window.removeTradeFromJournal('${trade.id}')" style="background: none; border: none; color: var(--color-text-muted); cursor: pointer; padding: 4px; font-size: 1.1rem;" title="Remove Entry">🗑️</button>
            </td>
        </tr>`;
    });
    
    tbody.innerHTML = html;
    updateJournalStats(journal);
}

function updateJournalStats(journal) {
    const totalTrades = journal.length;
    let wins = 0;
    let losses = 0;
    let totalR = 0;
    let closedCount = 0;
    let totalRealizedPnL = 0;
    let totalUnrealizedPnL = 0;
    
    journal.forEach(t => {
        if (t.status !== 'open' && t.pnl !== null) {
            closedCount++;
            totalRealizedPnL += t.pnl;
            if (t.pnl > 0) wins++;
            else losses++;
            
            if (t.rAchieved !== null) {
                totalR += t.rAchieved;
            }
        } else if (t.status === 'open') {
            const currentStock = stocksData.find(s => s.clean_ticker === t.ticker);
            if (currentStock && currentStock.close) {
                const currentPrice = parseFloat(currentStock.close);
                totalUnrealizedPnL += (currentPrice - t.entry) * t.qty;
            }
        }
    });
    
    const winRate = closedCount > 0 ? ((wins / closedCount) * 100).toFixed(1) : 0;
    const avgR = closedCount > 0 ? (totalR / closedCount).toFixed(2) : 0;
    
    const netPnL = totalRealizedPnL + totalUnrealizedPnL;
    const pnlColor = netPnL > 0 ? 'var(--accent-green)' : (netPnL < 0 ? 'var(--accent-red)' : 'inherit');
    
    document.getElementById('journal-total-trades').textContent = totalTrades;
    document.getElementById('journal-win-rate').textContent = `${winRate}%`;
    document.getElementById('journal-avg-r').textContent = `${avgR}R`;
    
    const pnlEl = document.getElementById('journal-total-pnl');
    pnlEl.innerHTML = `₹${netPnL.toFixed(2)} <span style="font-size: 0.75rem; color: var(--color-text-muted); font-weight: normal;">(₹${totalUnrealizedPnL.toFixed(2)} Open)</span>`;
    pnlEl.style.color = pnlColor;
}

function promptUpdateTrade(tradeId) {
    const journal = getJournalData();
    const tradeIndex = journal.findIndex(t => t.id === tradeId);
    if (tradeIndex === -1) return;
    
    const trade = journal[tradeIndex];
    
    const newStatus = prompt(`Update status for ${trade.ticker} (open, hit-t1, hit-t2, hit-t3, stopped, manual-exit):`, trade.status);
    if (!newStatus) return;
    
    let exitPriceStr = prompt(`Enter exit price for ${trade.ticker} (Leave blank if keeping open):`, trade.exitPrice || trade.close || '');
    let exitPrice = parseFloat(exitPriceStr);
    
    let updatedFields = {
        status: newStatus.toLowerCase()
    };
    
    if (!isNaN(exitPrice)) {
        updatedFields.exitPrice = exitPrice;
        updatedFields.exitDate = new Date().toISOString().split('T')[0];
        updatedFields.pnl = (exitPrice - trade.entry) * trade.qty;
        
        const riskPerShare = trade.entry - trade.stop;
        if (riskPerShare > 0) {
            updatedFields.rAchieved = (exitPrice - trade.entry) / riskPerShare;
        } else {
            updatedFields.rAchieved = 0;
        }
    } else if (newStatus.toLowerCase() === 'open') {
        updatedFields.exitPrice = null;
        updatedFields.exitDate = null;
        updatedFields.pnl = null;
        updatedFields.rAchieved = null;
    }
    
    fetch(`/api/journal/${tradeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedFields)
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            Object.assign(trade, updatedFields);
            renderJournal();
        } else {
            alert("Failed to update trade: " + resData.error);
        }
    })
    .catch(err => console.error("Error updating trade:", err));
}

window.renderJournal = renderJournal;

window.exportJournalToExcel = function() {
    const journal = getJournalData();
    if (!journal || journal.length === 0) {
        alert("No trades to export.");
        return;
    }
    
    const exportData = journal.map(trade => {
        let currentPrice = null;
        const currentStock = stocksData.find(s => s.clean_ticker === trade.ticker);
        if (currentStock && currentStock.close) currentPrice = parseFloat(currentStock.close);
        
        let pnl = trade.pnl;
        let rAch = trade.rAchieved;
        if (trade.status === 'open' && currentPrice !== null) {
            pnl = (currentPrice - trade.entry) * trade.qty;
            const riskPerShare = trade.entry - trade.stop;
            if (riskPerShare > 0) rAch = (currentPrice - trade.entry) / riskPerShare;
        }
        
        return {
            "Date": trade.date,
            "Ticker": trade.ticker,
            "Setup": trade.setupLabel,
            "Entry Price": trade.entry,
            "Stop Loss": trade.stop,
            "Current/Exit Price": trade.exitPrice || currentPrice || '',
            "Target 1": trade.target1,
            "Target 2": trade.target2,
            "Target 3": trade.target3,
            "Quantity": trade.qty,
            "Risk Amount": trade.riskAmount,
            "Status": trade.status,
            "PnL": pnl !== null ? pnl.toFixed(2) : '',
            "R-Achieved": rAch !== null ? rAch.toFixed(2) : '',
            "Notes": trade.notes
        };
    });
    
    const ws = XLSX.utils.json_to_sheet(exportData);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Trade Journal");
    
    const today = new Date().toISOString().split('T')[0];
    XLSX.writeFile(wb, `Trade_Journal_${today}.xlsx`);
};

window.removeTradeFromJournal = function(tradeId) {
    if (!confirm("Are you sure you want to remove this trade entry from the Journal?")) {
        return;
    }
    fetch(`/api/journal/${tradeId}`, {
        method: 'DELETE'
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            journalData = journalData.filter(t => t.id !== tradeId);
            renderJournal();
        } else {
            alert("Failed to delete trade: " + resData.error);
        }
    })
    .catch(err => console.error("Error deleting trade:", err));
};

window.openManualTradeModal = function() {
    const overlay = document.getElementById('manual-trade-modal-overlay');
    if (!overlay) return;
    
    document.getElementById('manual-trade-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('manual-trade-ticker').value = '';
    document.getElementById('manual-trade-setup').value = '';
    document.getElementById('manual-trade-entry').value = '';
    document.getElementById('manual-trade-stop').value = '';
    document.getElementById('manual-trade-notes').value = '';
    
    overlay.classList.remove('hidden');
};

window.closeManualTradeModal = function() {
    const overlay = document.getElementById('manual-trade-modal-overlay');
    if (overlay) overlay.classList.add('hidden');
};

window.saveManualTrade = function() {
    const ticker = document.getElementById('manual-trade-ticker').value.trim().toUpperCase();
    const date = document.getElementById('manual-trade-date').value;
    const setup = document.getElementById('manual-trade-setup').value.trim();
    const entry = parseFloat(document.getElementById('manual-trade-entry').value);
    const stop = parseFloat(document.getElementById('manual-trade-stop').value);
    const riskAmount = parseFloat(document.getElementById('manual-trade-risk').value) || 5000;
    const notes = document.getElementById('manual-trade-notes').value.trim();
    
    if (!ticker || !entry || !stop || isNaN(entry) || isNaN(stop)) {
        alert("Please provide a valid Ticker, Entry Price, and Stop Loss.");
        return;
    }
    
    if (stop >= entry) {
        alert("Stop Loss must be below Entry Price.");
        return;
    }
    
    const riskPerShare = entry - stop;
    const qty = Math.floor(riskAmount / riskPerShare);
    
    const newTrade = {
        id: 'manual-' + Date.now() + '-' + ticker,
        ticker: ticker,
        name: ticker,
        date: date || new Date().toISOString().split('T')[0],
        setupLabel: setup || 'Manual Entry',
        swingband: 'manual',
        entry: entry,
        entryType: 'Manual',
        stop: stop,
        target1: entry + (riskPerShare * 1.5),
        target2: entry + (riskPerShare * 2.0),
        target3: entry + (riskPerShare * 3.0),
        riskAmount: riskAmount,
        qty: Math.max(qty, 1),
        status: 'open',
        exitPrice: null,
        exitDate: null,
        pnl: null,
        rAchieved: null,
        notes: notes
    };
    
    fetch('/api/journal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newTrade)
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            journalData.unshift(newTrade);
            renderJournal();
            closeManualTradeModal();
        } else {
            alert("Failed to save manual trade: " + resData.error);
        }
    })
    .catch(err => console.error("Error saving manual trade:", err));
};

window.openEditTradeModal = function(tradeId) {
    const journal = getJournalData();
    const trade = journal.find(t => t.id === tradeId);
    if (!trade) return;
    
    document.getElementById('edit-trade-id').value = trade.id;
    document.getElementById('edit-trade-ticker').value = trade.ticker;
    document.getElementById('edit-trade-date').value = trade.date;
    document.getElementById('edit-trade-setup').value = trade.setupLabel || '';
    document.getElementById('edit-trade-entry').value = trade.entry;
    document.getElementById('edit-trade-stop').value = trade.stop;
    document.getElementById('edit-trade-qty').value = trade.qty;
    document.getElementById('edit-trade-status').value = trade.status || 'open';
    document.getElementById('edit-trade-exit').value = trade.exitPrice || '';
    document.getElementById('edit-trade-notes').value = trade.notes || '';
    
    const overlay = document.getElementById('edit-trade-modal-overlay');
    if (overlay) overlay.classList.remove('hidden');
};

window.closeEditTradeModal = function() {
    const overlay = document.getElementById('edit-trade-modal-overlay');
    if (overlay) overlay.classList.add('hidden');
};

window.saveEditedTrade = function() {
    const tradeId = document.getElementById('edit-trade-id').value;
    const ticker = document.getElementById('edit-trade-ticker').value.trim().toUpperCase();
    const date = document.getElementById('edit-trade-date').value;
    const setup = document.getElementById('edit-trade-setup').value.trim();
    const entry = parseFloat(document.getElementById('edit-trade-entry').value);
    const stop = parseFloat(document.getElementById('edit-trade-stop').value);
    const qty = parseInt(document.getElementById('edit-trade-qty').value, 10);
    const status = document.getElementById('edit-trade-status').value;
    const exitPriceStr = document.getElementById('edit-trade-exit').value;
    const notes = document.getElementById('edit-trade-notes').value.trim();
    
    if (!ticker || !entry || !stop || isNaN(entry) || isNaN(stop) || isNaN(qty) || qty <= 0) {
        alert("Please provide valid Ticker, Entry, Stop, and Qty.");
        return;
    }
    
    const index = journalData.findIndex(t => t.id === tradeId);
    if (index === -1) return;
    
    const trade = journalData[index];
    
    const riskPerShare = entry - stop;
    let target1 = trade.target1;
    let target2 = trade.target2;
    let target3 = trade.target3;
    if (riskPerShare > 0) {
        target1 = entry + (riskPerShare * 1.5);
        target2 = entry + (riskPerShare * 2.0);
        target3 = entry + (riskPerShare * 3.0);
    }
    const riskAmount = riskPerShare * qty;
    
    const exitPrice = parseFloat(exitPriceStr);
    let exitPriceVal = null;
    let exitDateVal = null;
    let pnlVal = null;
    let rAchievedVal = null;
    
    if (status !== 'open' && !isNaN(exitPrice)) {
        exitPriceVal = exitPrice;
        exitDateVal = trade.exitDate || new Date().toISOString().split('T')[0];
        pnlVal = (exitPrice - entry) * qty;
        if (riskPerShare > 0) {
            rAchievedVal = (exitPrice - entry) / riskPerShare;
        } else {
            rAchievedVal = 0;
        }
    }
    
    const updatedFields = {
        ticker: ticker,
        name: ticker,
        date: date,
        setupLabel: setup,
        entry: entry,
        stop: stop,
        qty: qty,
        status: status,
        notes: notes,
        target1: target1,
        target2: target2,
        target3: target3,
        riskAmount: riskAmount,
        exitPrice: exitPriceVal,
        exitDate: exitDateVal,
        pnl: pnlVal,
        rAchieved: rAchievedVal
    };
    
    fetch(`/api/journal/${tradeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updatedFields)
    })
    .then(res => res.json())
    .then(resData => {
        if (resData.success) {
            Object.assign(trade, updatedFields);
            renderJournal();
            closeEditTradeModal();
        } else {
            alert("Failed to save edited trade: " + resData.error);
        }
    })
    .catch(err => console.error("Error saving edited trade:", err));
};

window.updateJournalLivePrices = async function(event) {
    const journal = getJournalData();
    const openTickers = [...new Set(journal.filter(t => t.status === 'open').map(t => t.ticker))];
    
    if (openTickers.length === 0) {
        alert("No open trades in the journal to refresh.");
        return;
    }
    
    // We can use the global event if available, else don't animate the button
    const btn = event ? event.currentTarget : null;
    let originalText = '';
    if (btn) {
        originalText = btn.innerHTML;
        btn.innerHTML = `<span style="margin-right: 6px;">⏳</span> Fetching...`;
        btn.disabled = true;
    }
    
    try {
        const response = await fetch('/api/fetch_symbols', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: openTickers })
        });
        
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }
        
        const data = await response.json();
        if (data.stocks && data.stocks.length > 0) {
            data.stocks.forEach(fetchedStock => {
                const idx = stocksData.findIndex(s => s.clean_ticker === fetchedStock.clean_ticker);
                if (idx !== -1) {
                    // Update existing
                    stocksData[idx] = Object.assign(stocksData[idx], fetchedStock);
                } else {
                    // Inject new
                    stocksData.push(fetchedStock);
                }
            });
            renderJournal();
            alert("Live prices updated successfully!");
        } else {
            alert("No data returned for open tickers.");
        }
    } catch (err) {
        console.error("Error refreshing live prices:", err);
        alert("Failed to refresh live prices.");
    } finally {
        if (btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
    }
};

/**
 * Calculates Simple Moving Average (SMA) client-side.
 * @param {Object[]} data - Array of OHLCV daily bars.
 * @param {number} period - SMA period.
 * @returns {Object[]} Array of { time, value } pairs.
 */
function calculateSMA(data, period) {
    const sma = [];
    for (let i = 0; i < data.length; i++) {
        if (i < period - 1) continue;
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j].close;
        }
        sma.push({
            time: data[i].date,
            value: sum / period
        });
    }
    return sma;
}

/**
 * Returns configuration options for TradingView Lightweight Charts based on the theme.
 * @param {string} theme - 'dark' or 'light'
 * @returns {Object} Chart options.
 */
function getChartThemeOptions(theme) {
    const isDark = theme !== 'light';
    return {
        layout: {
            background: {
                type: 'solid',
                color: isDark ? '#0b0e14' : '#ffffff'
            },
            textColor: isDark ? '#94a3b8' : '#475569',
        },
        grid: {
            vertLines: {
                color: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)'
            },
            horzLines: {
                color: isDark ? 'rgba(255, 255, 255, 0.04)' : 'rgba(0, 0, 0, 0.04)'
            }
        },
        crosshair: {
            vertLine: {
                color: isDark ? '#334155' : '#cbd5e1',
                width: 1,
                style: 3, // dashed
            },
            horzLine: {
                color: isDark ? '#334155' : '#cbd5e1',
                width: 1,
                style: 3, // dashed
            }
        }
    };
}

/**
 * Initializes and renders TradingView Lightweight Charts inside the specified container.
 * @param {string} containerId - ID of target div element.
 * @param {Object[]} rawData - Array of daily bars with open, high, low, close, volume, date.
 * @param {Object[]} [forecastData=[]] - Optional forecasted price bars.
 */
function createTradeDrawerChart(containerId, rawData, forecastData = [], candlestickPatterns = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (activeDrawerChart) {
        try {
            activeDrawerChart.remove();
        } catch (e) {
            console.error("Error removing chart:", e);
        }
        activeDrawerChart = null;
    }

    const theme = document.body.getAttribute('data-theme') || 'dark';
    const themeOpts = getChartThemeOptions(theme);

    // Initialize Chart
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 360,
        height: 200,
        layout: themeOpts.layout,
        grid: themeOpts.grid,
        crosshair: themeOpts.crosshair,
        timeScale: {
            borderVisible: false,
            timeVisible: false,
            secondsVisible: false,
        },
        rightPriceScale: {
            borderVisible: false,
            scaleMargins: {
                top: 0.1,
                bottom: 0.25, // room for volume at bottom
            },
        },
    });

    activeDrawerChart = chart;

    // 1. Candlestick Series
    const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
    });

    const formattedCandles = rawData.map(d => ({
        time: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
    }));
    candleSeries.setData(formattedCandles);

    // 1b. Forecast Candlestick Series & Path
    if (forecastData && forecastData.length > 0) {
        const forecastSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: 'rgba(168, 85, 247, 0.45)', // soft transparent purple
            downColor: 'rgba(236, 72, 153, 0.45)', // soft transparent pink/crimson
            borderUpColor: 'rgba(168, 85, 247, 0.7)',
            borderDownColor: 'rgba(236, 72, 153, 0.7)',
            wickUpColor: 'rgba(168, 85, 247, 0.7)',
            wickDownColor: 'rgba(236, 72, 153, 0.7)',
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const formattedForecast = forecastData.map(d => ({
            time: d.date,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
        }));
        forecastSeries.setData(formattedForecast);

        // Path Series (Connecting line)
        const pathSeries = chart.addSeries(LightweightCharts.LineSeries, {
            color: '#a855f7',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const pathData = [
            { time: rawData[rawData.length - 1].date, value: rawData[rawData.length - 1].close }
        ].concat(forecastData.map(d => ({
            time: d.date,
            value: d.close,
        })));
        pathSeries.setData(pathData);
    }

    // 2. Volume Series Overlay
    const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
        color: '#26a69a',
        priceFormat: {
            type: 'volume',
        },
        priceScaleId: '', // overlay
        scaleMargins: {
            top: 0.8, // lower 20%
            bottom: 0,
        },
    });

    const formattedVolume = rawData.map(d => {
        const isUp = d.close >= d.open;
        return {
            time: d.date,
            value: d.volume,
            color: isUp ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
        };
    });
    volumeSeries.setData(formattedVolume);

    // 3. Line Series for SMAs
    const sma10Data = calculateSMA(rawData, 10);
    const sma21Data = calculateSMA(rawData, 21);
    const sma50Data = calculateSMA(rawData, 50);

    const sma10Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#fbbf24', // Amber/Yellow
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma10Series.setData(sma10Data);

    const sma21Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#06b6d4', // Cyan
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma21Series.setData(sma21Data);

    const sma50Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#a855f7', // Purple
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma50Series.setData(sma50Data);

    // 4. Markers for Inside Bars and Breakouts
    const markers = [];
    for (let i = 0; i < rawData.length; i++) {
        const bar = rawData[i];
        if (i > 0) {
            const prevBar = rawData[i - 1];
            
            // Inside Bar: High <= PrevHigh and Low >= PrevLow
            if (bar.high <= prevBar.high && bar.low >= prevBar.low) {
                markers.push({
                    time: bar.date,
                    position: 'aboveBar',
                    color: '#f59e0b',
                    shape: 'circle',
                });
            }

            // Breakout: Close > Highest High of past 10 bars AND Volume expansion (Vol >= 1.4 * 50-day average Volume)
            const prevHighs = [];
            for (let k = Math.max(0, i - 10); k < i; k++) {
                prevHighs.push(rawData[k].high);
            }
            const highestHighOfPreceding = Math.max(...prevHighs);

            const volValues = [];
            for (let k = Math.max(0, i - 50); k < i; k++) {
                volValues.push(rawData[k].volume);
            }
            const avgVol = volValues.reduce((sumVal, v) => sumVal + v, 0) / volValues.length;

            if (bar.close > highestHighOfPreceding && bar.volume >= avgVol * 1.4) {
                markers.push({
                    time: bar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                });
            }
        }
    }

    // Add custom candlestick patterns on the last bar
    if (rawData.length > 0) {
        const lastBar = rawData[rawData.length - 1];
        Object.entries(candlestickPatterns).forEach(([patternName, value]) => {
            if (patternName === "Hammer" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                    text: 'Hammer 🔨',
                });
            }
            if (patternName === "Shooting Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#ef4444',
                    shape: 'arrowDown',
                    text: 'Shooting Star 🌠',
                });
            }
            if (patternName === "Morning Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                    text: 'Morning Star 🌅',
                });
            }
            if (patternName === "Evening Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#ef4444',
                    shape: 'arrowDown',
                    text: 'Evening Star 🌌',
                });
            }
            if (patternName === "Engulfing") {
                if (value > 0) {
                    markers.push({
                        time: lastBar.date,
                        position: 'belowBar',
                        color: '#10b981',
                        shape: 'arrowUp',
                        text: 'Bullish Engulfing 🟢',
                    });
                } else if (value < 0) {
                    markers.push({
                        time: lastBar.date,
                        position: 'aboveBar',
                        color: '#ef4444',
                        shape: 'arrowDown',
                        text: 'Bearish Engulfing 🔴',
                    });
                }
            }
            if (patternName === "Doji" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#cbd5e1',
                    shape: 'circle',
                    text: 'Doji ⚖️',
                });
            }
        });

        // Add primary setup name if not Continuation
        if (window.currentTradeStock && window.currentTradeStock.pattern_name && window.currentTradeStock.pattern_name !== "Trend Continuation") {
            markers.push({
                time: lastBar.date,
                position: 'belowBar',
                color: '#fbbf24',
                shape: 'arrowUp',
                text: window.currentTradeStock.pattern_name,
            });
        }
    }

    LightweightCharts.createSeriesMarkers(candleSeries, markers);

    // Zoom view by default to focus on the last 120 bars + forecast bars
    if (rawData && rawData.length > 0) {
        const totalBars = rawData.length;
        const startIdx = Math.max(0, totalBars - 120);
        const startBarDate = rawData[startIdx].date;
        const endBarDate = (forecastData && forecastData.length > 0) ? forecastData[forecastData.length - 1].date : rawData[totalBars - 1].date;
        
        chart.timeScale().setVisibleRange({
            from: startBarDate,
            to: endBarDate
        });
    }

    // Auto Resize Support
    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const { width, height } = entries[0].contentRect;
        chart.resize(width, height);
    });
    resizeObserver.observe(container);
    container.resizeObserver = resizeObserver;
}

/**
 * Closes the full screen chart overlay modal and destroys the activeOverlayChart instance.
 */
function closeChartOverlay() {
    const modal = document.getElementById('chart-overlay-modal');
    if (modal) modal.classList.add('hidden');
    if (activeOverlayChart) {
        try {
            activeOverlayChart.remove();
        } catch (e) {
            console.error("Error removing overlay chart:", e);
        }
        activeOverlayChart = null;
    }
}

/**
 * Renders an expanded TradingView chart inside the modal overlay.
 * @param {string} containerId - Target container ID.
 * @param {Object[]} rawData - Historical chart data bars.
 * @param {Object[]} [forecastData=[]] - Optional forecasted price bars.
 */
function createOverlayChart(containerId, rawData, forecastData = [], candlestickPatterns = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (activeOverlayChart) {
        try {
            activeOverlayChart.remove();
        } catch (e) {
            console.error("Error removing overlay chart:", e);
        }
        activeOverlayChart = null;
    }

    const theme = document.body.getAttribute('data-theme') || 'dark';
    const themeOpts = getChartThemeOptions(theme);

    // Initialize Chart
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth || 800,
        height: 400,
        layout: themeOpts.layout,
        grid: themeOpts.grid,
        crosshair: themeOpts.crosshair,
        timeScale: {
            borderVisible: true,
            timeVisible: true,
            secondsVisible: false,
        },
        rightPriceScale: {
            borderVisible: true,
            scaleMargins: {
                top: 0.1,
                bottom: 0.25, // room for volume at bottom
            },
        },
    });

    activeOverlayChart = chart;

    // 1. Candlestick Series
    const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
    });

    const formattedCandles = rawData.map(d => ({
        time: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
    }));
    candleSeries.setData(formattedCandles);

    // 1b. Forecast Candlestick Series & Path
    if (forecastData && forecastData.length > 0) {
        const forecastSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: 'rgba(168, 85, 247, 0.45)', // soft transparent purple
            downColor: 'rgba(236, 72, 153, 0.45)', // soft transparent pink/crimson
            borderUpColor: 'rgba(168, 85, 247, 0.7)',
            borderDownColor: 'rgba(236, 72, 153, 0.7)',
            wickUpColor: 'rgba(168, 85, 247, 0.7)',
            wickDownColor: 'rgba(236, 72, 153, 0.7)',
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const formattedForecast = forecastData.map(d => ({
            time: d.date,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
        }));
        forecastSeries.setData(formattedForecast);

        // Path Series (Connecting line)
        const pathSeries = chart.addSeries(LightweightCharts.LineSeries, {
            color: '#a855f7',
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            priceLineVisible: false,
            lastValueVisible: false,
        });

        const pathData = [
            { time: rawData[rawData.length - 1].date, value: rawData[rawData.length - 1].close }
        ].concat(forecastData.map(d => ({
            time: d.date,
            value: d.close,
        })));
        pathSeries.setData(pathData);
    }

    // 2. Volume Series Overlay
    const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
        color: '#26a69a',
        priceFormat: {
            type: 'volume',
        },
        priceScaleId: '', // overlay
        scaleMargins: {
            top: 0.8, // lower 20%
            bottom: 0,
        },
    });

    const formattedVolume = rawData.map(d => {
        const isUp = d.close >= d.open;
        return {
            time: d.date,
            value: d.volume,
            color: isUp ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
        };
    });
    volumeSeries.setData(formattedVolume);

    // 3. Line Series for SMAs
    const sma10Data = calculateSMA(rawData, 10);
    const sma21Data = calculateSMA(rawData, 21);
    const sma50Data = calculateSMA(rawData, 50);

    const sma10Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#fbbf24', // Amber/Yellow
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma10Series.setData(sma10Data);

    const sma21Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#06b6d4', // Cyan
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma21Series.setData(sma21Data);

    const sma50Series = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#a855f7', // Purple
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
    });
    sma50Series.setData(sma50Data);

    // 4. Markers for Inside Bars and Breakouts
    const markers = [];
    for (let i = 0; i < rawData.length; i++) {
        const bar = rawData[i];
        if (i > 0) {
            const prevBar = rawData[i - 1];
            
            // Inside Bar
            if (bar.high <= prevBar.high && bar.low >= prevBar.low) {
                markers.push({
                    time: bar.date,
                    position: 'aboveBar',
                    color: '#f59e0b',
                    shape: 'circle',
                });
            }

            // Breakout
            const prevHighs = [];
            for (let k = Math.max(0, i - 10); k < i; k++) {
                prevHighs.push(rawData[k].high);
            }
            const highestHighOfPreceding = Math.max(...prevHighs);

            const volValues = [];
            for (let k = Math.max(0, i - 50); k < i; k++) {
                volValues.push(rawData[k].volume);
            }
            const avgVol = volValues.reduce((sumVal, v) => sumVal + v, 0) / volValues.length;

            if (bar.close > highestHighOfPreceding && bar.volume >= avgVol * 1.4) {
                markers.push({
                    time: bar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                });
            }
        }
    }

    // Add custom candlestick patterns on the last bar
    if (rawData.length > 0) {
        const lastBar = rawData[rawData.length - 1];
        Object.entries(candlestickPatterns).forEach(([patternName, value]) => {
            if (patternName === "Hammer" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                    text: 'Hammer 🔨',
                });
            }
            if (patternName === "Shooting Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#ef4444',
                    shape: 'arrowDown',
                    text: 'Shooting Star 🌠',
                });
            }
            if (patternName === "Morning Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'belowBar',
                    color: '#10b981',
                    shape: 'arrowUp',
                    text: 'Morning Star 🌅',
                });
            }
            if (patternName === "Evening Star" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#ef4444',
                    shape: 'arrowDown',
                    text: 'Evening Star 🌌',
                });
            }
            if (patternName === "Engulfing") {
                if (value > 0) {
                    markers.push({
                        time: lastBar.date,
                        position: 'belowBar',
                        color: '#10b981',
                        shape: 'arrowUp',
                        text: 'Bullish Engulfing 🟢',
                    });
                } else if (value < 0) {
                    markers.push({
                        time: lastBar.date,
                        position: 'aboveBar',
                        color: '#ef4444',
                        shape: 'arrowDown',
                        text: 'Bearish Engulfing 🔴',
                    });
                }
            }
            if (patternName === "Doji" && value > 0) {
                markers.push({
                    time: lastBar.date,
                    position: 'aboveBar',
                    color: '#cbd5e1',
                    shape: 'circle',
                    text: 'Doji ⚖️',
                });
            }
        });

        // Add primary setup name if not Continuation
        if (window.currentTradeStock && window.currentTradeStock.pattern_name && window.currentTradeStock.pattern_name !== "Trend Continuation") {
            markers.push({
                time: lastBar.date,
                position: 'belowBar',
                color: '#fbbf24',
                shape: 'arrowUp',
                text: window.currentTradeStock.pattern_name,
            });
        }
    }

    LightweightCharts.createSeriesMarkers(candleSeries, markers);

    // Zoom view by default to focus on the last 120 bars + forecast bars
    if (rawData && rawData.length > 0) {
        const totalBars = rawData.length;
        const startIdx = Math.max(0, totalBars - 120);
        const startBarDate = rawData[startIdx].date;
        const endBarDate = (forecastData && forecastData.length > 0) ? forecastData[forecastData.length - 1].date : rawData[totalBars - 1].date;
        
        chart.timeScale().setVisibleRange({
            from: startBarDate,
            to: endBarDate
        });
    }

    // Auto Resize Support
    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const { width, height } = entries[0].contentRect;
        chart.resize(width, height);
    });
    resizeObserver.observe(container);
    container.resizeObserver = resizeObserver;
}

// -----------------------------------------------------------------------------
// Kronos AI Panel Helper Functions
// -----------------------------------------------------------------------------

function destroyKronosChart() {
    if (activeKronosChart) {
        try {
            activeKronosChart.remove();
        } catch(e) {
            console.error("Error removing activeKronosChart:", e);
        }
        activeKronosChart = null;
    }
}

function destroyKronosFullChart() {
    if (activeKronosFullChart) {
        try {
            activeKronosFullChart.remove();
        } catch(e) {
            console.error("Error removing activeKronosFullChart:", e);
        }
        activeKronosFullChart = null;
    }
}

function destroyKronosBacktestChart() {
    if (activeKronosBacktestChart) {
        try {
            activeKronosBacktestChart.remove();
        } catch(e) {
            console.error("Error removing activeKronosBacktestChart:", e);
        }
        activeKronosBacktestChart = null;
    }
}

function renderKronosForecastPanel(data) {
    const section = document.getElementById('drawer-kronos-section');
    if (!section || !data || !data.forecast) return;
    section.style.display = 'block';

    const lastClose = data.last_close;
    const finalClose = data.forecast[data.forecast.length - 1].close;
    const movePct = ((finalClose - lastClose) / lastClose * 100).toFixed(2);
    const badge = document.getElementById('kronos-confidence-badge');
    if (badge) {
        badge.textContent = `${movePct >= 0 ? '▲' : '▼'} ${Math.abs(movePct)}% (${data.pred_len}D)`;
        badge.style.backgroundColor = movePct >= 0
            ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)';
        badge.style.color = movePct >= 0 ? '#10b981' : '#ef4444';
        badge.style.border = movePct >= 0
            ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(239,68,68,0.3)';
    }

    const tbody = document.getElementById('drawer-kronos-tbody');
    if (tbody) {
        tbody.innerHTML = data.forecast.map(row => {
            const closeClass = row.close >= lastClose ? 'val-up' : 'val-down';
            const band = `₹${row.p10_close.toFixed(2)} – ₹${row.p90_close.toFixed(2)}`;
            return `
              <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                <td style="text-align: left; padding: 4px;">${row.date}</td>
                <td style="text-align: right; padding: 4px;">₹${row.open.toFixed(2)}</td>
                <td style="text-align: right; padding: 4px;">₹${row.high.toFixed(2)}</td>
                <td style="text-align: right; padding: 4px;">₹${row.low.toFixed(2)}</td>
                <td class="${closeClass}" style="text-align: right; padding: 4px; font-weight:700;">₹${row.close.toFixed(2)}</td>
                <td style="text-align: right; padding: 4px;">${formatVolume(row.volume)}</td>
                <td style="text-align: right; padding: 4px; font-size:0.7rem; color:var(--color-text-secondary);">${band}</td>
              </tr>`;
        }).join('');
    }

    destroyKronosChart();
    const container = document.getElementById('drawer-kronos-chart');
    if (!container || typeof LightweightCharts === 'undefined') return;

    const currentTheme = document.body.getAttribute('data-theme') || 'dark';
    const isDark = currentTheme === 'dark';
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 160,
        layout: {
            background: { color: 'transparent' },
            textColor: isDark ? '#94a3b8' : '#475569'
        },
        grid: {
            vertLines: { visible: false },
            horzLines: { color: isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)' }
        },
        timeScale: { borderVisible: false },
        rightPriceScale: { borderVisible: false },
    });
    activeKronosChart = chart;

    const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
        upColor: '#6366f1', downColor: '#a78bfa',
        borderUpColor: '#6366f1', borderDownColor: '#a78bfa',
        wickUpColor: '#6366f1', wickDownColor: '#a78bfa',
    });
    candleSeries.setData(data.forecast.map(r => ({
        time: r.date,
        open: r.open, high: r.high, low: r.low, close: r.close,
    })));

    const bandLow = chart.addSeries(LightweightCharts.AreaSeries, {
        lineColor: 'rgba(99,102,241,0.2)', topColor: 'rgba(99,102,241,0.05)',
        bottomColor: 'transparent', lineWidth: 1,
    });
    bandLow.setData(data.forecast.map(r => ({ time: r.date, value: r.p10_close })));

    const bandHigh = chart.addSeries(LightweightCharts.AreaSeries, {
        lineColor: 'rgba(99,102,241,0.2)', topColor: 'transparent',
        bottomColor: 'rgba(99,102,241,0.05)', lineWidth: 1,
    });
    bandHigh.setData(data.forecast.map(r => ({ time: r.date, value: r.p90_close })));

    chart.timeScale().fitContent();

    // Augment with EnsembleCast consensus line and conviction
    const ticker = data.ticker;
    const horizon = data.pred_len;

    // Reset conviction badge placeholder in the drawer to avoid stale state while fetching
    let drawerBadge = document.getElementById('drawer-ensemble-conviction');
    if (!drawerBadge) {
        drawerBadge = document.createElement('div');
        drawerBadge.id = 'drawer-ensemble-conviction';
        drawerBadge.style.marginTop = '0.5rem';
        const chartContainer = document.getElementById('drawer-kronos-chart');
        if (chartContainer) {
            const parent = chartContainer.parentNode;
            parent.insertBefore(drawerBadge, chartContainer.nextSibling);
        }
    }
    if (drawerBadge) {
        drawerBadge.className = 'conviction-badge conviction-loading';
        drawerBadge.innerHTML = '<span style="margin-right: 4px;">◌</span> Calculating ensemble…';
    }

    fetch('/api/ensemble_forecast', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker, horizon: horizon })
    })
    .then(res => {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
    })
    .then(ensData => {
        if (ensData && ensData.ensemble_path && activeKronosChart) {
            // Draw gold ensemble path on the drawer chart
            const ensembleSeries = activeKronosChart.addSeries(LightweightCharts.LineSeries, {
                color: '#fbbf24',
                lineWidth: 2,
                title: 'Ensemble'
            });
            const futureDates = generateFutureTradingDates(ensData.last_close_date, ensData.horizon);
            ensembleSeries.setData(
                ensData.ensemble_path.map((close, i) => ({ time: futureDates[i], value: close }))
            );

            // Add/update conviction badge in the drawer
            if (drawerBadge) {
                const ICONS = { HIGH: '🟢', MODERATE: '🟡', LOW: '🔴' };
                const LABELS = { HIGH: 'High Conviction', MODERATE: 'Moderate Conviction', LOW: 'Low Conviction ⚠️' };
                const conv = ensData.conviction || 'LOW';
                drawerBadge.className = `conviction-badge ${conv}`;
                drawerBadge.innerHTML = `<span style="margin-right: 4px;">${ICONS[conv] ?? '●'}</span> ${LABELS[conv] ?? conv}`;
            }
        } else {
            if (drawerBadge) {
                drawerBadge.className = 'conviction-badge';
                drawerBadge.innerHTML = '<span style="margin-right: 4px;">●</span> Ensemble unavailable';
            }
        }
    })
    .catch(err => {
        console.error('[EnsembleCast Drawer]', err);
        if (drawerBadge) {
            drawerBadge.className = 'conviction-badge';
            drawerBadge.innerHTML = '<span style="margin-right: 4px;">●</span> Ensemble unavailable';
        }
    });

    const backtestRow = document.getElementById('kronos-backtest-row');
    if (backtestRow) {
        backtestRow.style.display = 'flex';
        const backtestBtn = document.getElementById('btn-kronos-backtest');
        if (backtestBtn) {
            backtestBtn.onclick = () => {
                switchWorkspace('ai-forecast');
                const searchInput = document.getElementById('kronos-ticker-input');
                if (searchInput) {
                    searchInput.value = data.ticker;
                    renderAIForecastWorkspace(data.ticker);
                }
            };
        }
        
        fetch(`/api/kronos-backtest?ticker=${encodeURIComponent(data.ticker)}`)
            .then(res => res.json())
            .then(bdata => {
                const badge = document.getElementById('kronos-mae-badge');
                if (badge && bdata.backtest_runs && bdata.backtest_runs.length > 0) {
                    const latest = bdata.backtest_runs[0];
                    badge.textContent = `Latest Accuracy: Dir ${latest.direction_accuracy}%, Hit Rate ${latest.band_hit_rate}%`;
                    badge.style.backgroundColor = latest.direction_accuracy >= 55 ? 'rgba(16,185,129,0.15)' : 'rgba(245,158,11,0.15)';
                    badge.style.color = latest.direction_accuracy >= 55 ? '#10b981' : '#f59e0b';
                } else if (badge) {
                    badge.textContent = 'No past backtest runs yet';
                    badge.style.backgroundColor = 'rgba(255,255,255,0.05)';
                    badge.style.color = 'var(--color-text-secondary)';
                }
            });
    }
}

function renderAIForecastWorkspace(ticker) {
    const searchInput = document.getElementById('kronos-ticker-input');
    const symbol = ticker || (searchInput ? searchInput.value.trim().toUpperCase() : '') || 'RELIANCE';
    if (!symbol) return;

    if (searchInput) {
        searchInput.value = symbol;
    }

    const activeBtn = document.querySelector('.workspace-view#view-ai-forecast .kronos-len-btn.active');
    const isEnsemble = activeBtn && activeBtn.dataset.mode === 'ensemble';
    const predLen = activeBtn ? parseInt(activeBtn.dataset.len) : 5;

    const runBtn = document.getElementById('btn-run-kronos');

    if (isEnsemble) {
        if (runBtn) {
            runBtn.disabled = true;
            runBtn.textContent = 'Running...';
        }
        document.getElementById('ensemblePanel').style.display = 'block';
        loadEnsembleForecast(symbol, predLen, true)
            .finally(() => {
                if (runBtn) {
                    runBtn.disabled = false;
                    runBtn.textContent = 'Run Forecast';
                }
            });
        return;
    }

    // Otherwise standard Kronos mode
    document.getElementById('ensemblePanel').style.display = 'none';

    // Hide Ensemble Backtest elements
    document.getElementById('ensembleBacktestTable').style.display = 'none';
    const btKronosBtn = document.querySelector('.bt-mode-btn[data-mode="kronos"]');
    if (btKronosBtn) {
        document.querySelectorAll('.bt-mode-btn').forEach(b => b.classList.remove('active'));
        btKronosBtn.classList.add('active');
    }
    const metricsContainer = document.getElementById('kronos-accuracy-metrics');
    if (metricsContainer) metricsContainer.style.display = 'flex';

    if (runBtn) {
        runBtn.disabled = true;
        runBtn.textContent = 'Running...';
    }

    fetch(`/api/kronos-forecast?ticker=${encodeURIComponent(symbol)}&pred_len=${predLen}&sample_count=10`)
        .then(res => res.json())
        .then(data => {
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = 'Run Forecast';
            }
            if (data.error) {
                showToast("Error running forecast: " + data.error, "error");
                return;
            }

            // Render Verdict Strip (Item 11.1)
            const verdictContainer = document.getElementById('ai-verdict-container');
            if (verdictContainer) {
                const closeValues = data.forecast.map(f => f.close);
                const firstClose = data.last_close;
                const finalClose = closeValues[closeValues.length - 1];
                const returnPct = firstClose ? (((finalClose - firstClose) / firstClose) * 100) : 0;
                
                const direction = returnPct > 1.5 ? 'Bullish' : returnPct < -1.5 ? 'Bearish' : 'Neutral';
                const verdictClass = returnPct > 1.5 ? 'ai-verdict--bullish' : returnPct < -1.5 ? 'ai-verdict--bearish' : 'ai-verdict--neutral';
                
                verdictContainer.innerHTML = `
                    <div class="ai-verdict-strip ${verdictClass}" style="display: flex; gap: 1.5rem; padding: 0.6rem 1rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600; align-items: center;">
                        <span class="verdict-label" style="font-family: var(--font-display); font-size: 0.9rem; text-transform: uppercase;">AI Forecast View: ${direction}</span>
                        <span class="verdict-move">Expected Move: ${returnPct > 0 ? '+' : ''}${returnPct.toFixed(1)}%</span>
                        <span class="verdict-conf">Confidence Score: ${data.ai_confidence_score || 0}%</span>
                    </div>
                `;
            }

            destroyKronosFullChart();
            const container = document.getElementById('kronos-full-chart');
            if (container && typeof LightweightCharts !== 'undefined') {
                const currentTheme = document.body.getAttribute('data-theme') || 'dark';
                const isDark = currentTheme === 'dark';
                const chart = LightweightCharts.createChart(container, {
                    width: container.clientWidth,
                    height: 380,
                    layout: {
                        background: { color: 'transparent' },
                        textColor: isDark ? '#94a3b8' : '#475569'
                    },
                    grid: {
                        vertLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
                        horzLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' }
                    },
                    timeScale: { borderVisible: false },
                    rightPriceScale: { borderVisible: false },
                });
                activeKronosFullChart = chart;

                const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
                    upColor: '#6366f1', downColor: '#a78bfa',
                    borderUpColor: '#6366f1', borderDownColor: '#a78bfa',
                    wickUpColor: '#6366f1', wickDownColor: '#a78bfa',
                });
                candleSeries.setData(data.forecast.map(r => ({
                    time: r.date,
                    open: r.open, high: r.high, low: r.low, close: r.close,
                })));

                const bandLow = chart.addSeries(LightweightCharts.AreaSeries, {
                    lineColor: 'rgba(99,102,241,0.25)', topColor: 'rgba(99,102,241,0.06)',
                    bottomColor: 'transparent', lineWidth: 1.5,
                });
                bandLow.setData(data.forecast.map(r => ({ time: r.date, value: r.p10_close })));

                const bandHigh = chart.addSeries(LightweightCharts.AreaSeries, {
                    lineColor: 'rgba(99,102,241,0.25)', topColor: 'transparent',
                    bottomColor: 'rgba(99,102,241,0.06)', lineWidth: 1.5,
                });
                bandHigh.setData(data.forecast.map(r => ({ time: r.date, value: r.p90_close })));

                chart.timeScale().fitContent();

                // Add resize listener support
                const resizeObserver = new ResizeObserver(entries => {
                    if (entries.length === 0 || !entries[0].contentRect) return;
                    const { width, height } = entries[0].contentRect;
                    chart.resize(width, height);
                });
                resizeObserver.observe(container);
                container.resizeObserver = resizeObserver;
            }

            const tableWrap = document.getElementById('kronos-full-table-wrap');
            if (tableWrap) {
                const lastClose = data.last_close;
                tableWrap.innerHTML = `
                    <table class="kronos-forecast-table" style="width: 100%; border-collapse: collapse; font-size: 0.85rem; margin-top: 1rem;">
                        <thead>
                            <tr style="border-bottom: 2px solid rgba(255,255,255,0.1); padding-bottom: 0.5rem;">
                                <th style="text-align: left; padding: 8px; color: var(--color-text-muted);">Forecast Date</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">Open</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">High</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">Low</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">Predicted Close</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">Predicted Volume</th>
                                <th style="text-align: right; padding: 8px; color: var(--color-text-muted);">Monte Carlo Band (P10–P90)</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.forecast.map(row => {
                                const closeClass = row.close >= lastClose ? 'val-up' : 'val-down';
                                const band = `₹${row.p10_close.toFixed(2)} – ₹${row.p90_close.toFixed(2)}`;
                                return `
                                    <tr style="border-bottom: 1px solid rgba(255,255,255,0.05);">
                                        <td style="text-align: left; padding: 8px;">${row.date}</td>
                                        <td style="text-align: right; padding: 8px;">₹${row.open.toFixed(2)}</td>
                                        <td style="text-align: right; padding: 8px;">₹${row.high.toFixed(2)}</td>
                                        <td style="text-align: right; padding: 8px;">₹${row.low.toFixed(2)}</td>
                                        <td class="${closeClass}" style="text-align: right; padding: 8px; font-weight: 700;">₹${row.close.toFixed(2)}</td>
                                        <td style="text-align: right; padding: 8px;">${formatVolume(row.volume)}</td>
                                        <td style="text-align: right; padding: 8px; color: var(--color-text-secondary); font-size: 0.8rem;">${band}</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                `;
            }

            loadBacktestingMetrics(symbol);
        })
        .catch(err => {
            if (runBtn) {
                runBtn.disabled = false;
                runBtn.textContent = 'Run Forecast';
            }
            console.error("Kronos full forecast run error:", err);
        });
}

function loadBacktestingMetrics(symbol) {
    const backtestSection = document.getElementById('kronos-backtest-section');
    const metricsContainer = document.getElementById('kronos-accuracy-metrics');
    if (!backtestSection || !metricsContainer) return;

    const btModeActive = document.querySelector('.bt-mode-btn.active');
    const isEnsembleBt = btModeActive && btModeActive.dataset.mode === 'ensemble';

    if (isEnsembleBt) {
        document.getElementById('ensembleBacktestTable').style.display = 'block';
        metricsContainer.style.display = 'none';
        backtestSection.style.display = 'block';
        const activeBtn = document.querySelector('.workspace-view#view-ai-forecast .kronos-len-btn.active');
        const horizon = activeBtn ? parseInt(activeBtn.dataset.len) : 10;
        loadEnsembleBacktest(symbol, horizon);
        return;
    }

    // Otherwise standard Kronos metrics
    document.getElementById('ensembleBacktestTable').style.display = 'none';
    metricsContainer.style.display = 'flex';

    fetch(`/api/kronos-backtest?ticker=${encodeURIComponent(symbol)}`)
        .then(res => res.json())
        .then(data => {
            if (data.error || !data.backtest_runs || data.backtest_runs.length === 0) {
                backtestSection.style.display = 'none';
                return;
            }

            backtestSection.style.display = 'block';
            const latest = data.backtest_runs[0];

            const dirColor = latest.direction_accuracy >= 55 ? '#10b981' : '#f59e0b';
            const hitColor = latest.band_hit_rate >= 70 ? '#10b981' : '#f59e0b';
            metricsContainer.innerHTML = `
                <div style="font-family: 'Outfit', sans-serif; font-weight: 600; font-size: 1rem; color: #fff; margin-bottom: 0.5rem;">Latest Model Performance</div>
                <div style="display:flex; justify-content:space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.4rem;">
                    <span style="color:var(--color-text-secondary); font-size: 0.85rem;">Directional Accuracy</span>
                    <span style="font-weight: 700; color:${dirColor};">${latest.direction_accuracy}%</span>
                </div>
                <div style="display:flex; justify-content:space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.4rem;">
                    <span style="color:var(--color-text-secondary); font-size: 0.85rem;">Band Hit Rate (P10-P90)</span>
                    <span style="font-weight: 700; color:${hitColor};">${latest.band_hit_rate}%</span>
                </div>
                <div style="display:flex; justify-content:space-between; border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.4rem;">
                    <span style="color:var(--color-text-secondary); font-size: 0.85rem;">Mean Absolute Error (MAE)</span>
                    <span style="font-weight: 700; color:#c084fc;">₹${latest.mae.toFixed(2)}</span>
                </div>
                <div style="display:flex; justify-content:space-between; padding-bottom: 0.4rem;">
                    <span style="color:var(--color-text-secondary); font-size: 0.85rem;">Mean Abs Pct Error (MAPE)</span>
                    <span style="font-weight: 700; color:#c084fc;">${latest.mape.toFixed(2)}%</span>
                </div>
                <div style="font-size:0.75rem; color:var(--color-text-muted); margin-top:0.5rem; line-height: 1.3;">
                    Based on ${latest.total_comparisons} matching daily candles since the forecast generated on ${new Date(latest.generated_at).toLocaleDateString()}.
                </div>
            `;

            destroyKronosBacktestChart();
            const bContainer = document.getElementById('kronos-backtest-chart');
            if (bContainer && typeof LightweightCharts !== 'undefined') {
                const currentTheme = document.body.getAttribute('data-theme') || 'dark';
                const isDark = currentTheme === 'dark';
                const chart = LightweightCharts.createChart(bContainer, {
                    width: bContainer.clientWidth,
                    height: 280,
                    layout: {
                        background: { color: 'transparent' },
                        textColor: isDark ? '#94a3b8' : '#475569'
                    },
                    grid: {
                        vertLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
                        horzLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' }
                    },
                    timeScale: { borderVisible: false },
                    rightPriceScale: { borderVisible: false },
                });
                activeKronosBacktestChart = chart;

                const fSeries = chart.addSeries(LightweightCharts.LineSeries, {
                    color: '#6366f1',
                    lineWidth: 2.5,
                    title: 'Forecast',
                });
                fSeries.setData(latest.comparison_points.map(p => ({
                    time: p.date,
                    value: p.forecast_close
                })));

                const aSeries = chart.addSeries(LightweightCharts.LineSeries, {
                    color: '#10b981',
                    lineWidth: 2.5,
                    title: 'Actual',
                });
                aSeries.setData(latest.comparison_points.map(p => ({
                    time: p.date,
                    value: p.actual_close
                })));

                const bLow = chart.addSeries(LightweightCharts.AreaSeries, {
                    lineColor: 'rgba(99,102,241,0.15)', topColor: 'rgba(99,102,241,0.03)',
                    bottomColor: 'transparent', lineWidth: 1,
                });
                bLow.setData(latest.comparison_points.map(p => ({ time: p.date, value: p.p10_close })));

                const bHigh = chart.addSeries(LightweightCharts.AreaSeries, {
                    lineColor: 'rgba(99,102,241,0.15)', topColor: 'transparent',
                    bottomColor: 'rgba(99,102,241,0.03)', lineWidth: 1,
                });
                bHigh.setData(latest.comparison_points.map(p => ({ time: p.date, value: p.p90_close })));

                chart.timeScale().fitContent();

                // Add resize listener support
                const resizeObserver = new ResizeObserver(entries => {
                    if (entries.length === 0 || !entries[0].contentRect) return;
                    const { width, height } = entries[0].contentRect;
                    chart.resize(width, height);
                });
                resizeObserver.observe(bContainer);
                bContainer.resizeObserver = resizeObserver;
            }
        })
        .catch(err => {
            console.error("Backtest loading error:", err);
        });
}

// Export to window
window.renderAIForecastWorkspace = renderAIForecastWorkspace;
window.renderKronosForecastPanel = renderKronosForecastPanel;
window.destroyKronosChart = destroyKronosChart;
window.destroyKronosFullChart = destroyKronosFullChart;
window.destroyKronosBacktestChart = destroyKronosBacktestChart;

// ── EnsembleCast (Multi-Model Forecast) Helpers ──

function generateFutureTradingDates(lastDate, n) {
  // If window.nseHolidays is loaded dynamically from the backend, use it.
  // Otherwise, use a static fallback set spanning 2026 and 2027.
  const staticFallback = new Set([
    '2026-01-26','2026-03-03','2026-03-19','2026-04-02',
    '2026-04-03','2026-04-14','2026-05-01','2026-08-15',
    '2026-10-02','2026-10-20','2026-11-25','2026-12-25',
    '2027-01-26','2027-03-24','2027-03-26','2027-04-14',
    '2027-05-01','2027-08-15','2027-10-02','2027-11-09',
    '2027-12-25'
  ]);
  const holidays = window.nseHolidays || staticFallback;
  
  const curYear = new Date(lastDate).getFullYear();
  if (curYear > 2027 && !window.nseHolidays) {
    console.warn(`[EnsembleCast] Current year is ${curYear} but trading holidays were not fetched dynamically. Using 2027 fallback.`);
  }

  const dates = [];
  const cur = new Date(lastDate);
  while (dates.length < n) {
    cur.setDate(cur.getDate() + 1);
    const dow = cur.getDay();
    const iso = cur.toISOString().slice(0, 10);
    if (dow !== 0 && dow !== 6 && !holidays.has(iso)) {
      dates.push(iso);
    }
  }
  return dates;
}

function renderEnsembleChart(data) {
  // Guard: chart must exist before we can add series
  if (!activeKronosFullChart) {
    console.warn('[EnsembleCast] renderEnsembleChart called but activeKronosFullChart is null — attempting to create chart');
    const container = document.getElementById('kronos-full-chart');
    if (!container || typeof LightweightCharts === 'undefined') {
      console.error('[EnsembleCast] Cannot create chart: container missing or LightweightCharts not loaded');
      return;
    }
    const isDark = (document.body.getAttribute('data-theme') || 'dark') === 'dark';
    const chart = LightweightCharts.createChart(container, {
      width: container.clientWidth,
      height: 380,
      layout: { background: { color: 'transparent' }, textColor: isDark ? '#94a3b8' : '#475569' },
      grid: {
        vertLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
        horzLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' }
      },
      timeScale: { borderVisible: false },
      rightPriceScale: { borderVisible: false },
    });
    activeKronosFullChart = chart;
    const ro = new ResizeObserver(entries => {
      if (!entries[0]) return;
      chart.resize(entries[0].contentRect.width, entries[0].contentRect.height);
    });
    ro.observe(container);
    container.resizeObserver = ro;
  }

  const MODEL_COLORS = {
    kronos:  { color: 'rgba(124, 58, 237, 0.45)',  lineWidth: 1 },  // faint purple
    prophet: { color: 'rgba(234, 88,  12,  0.45)', lineWidth: 1 },  // faint orange
    arima:   { color: 'rgba(8,   145, 178, 0.45)', lineWidth: 1 },  // faint teal
  };
  const ENSEMBLE_STYLE = { color: '#fbbf24', lineWidth: 2.5 };      // gold bold path

  const showIndividual = document.getElementById('showIndividualModels')?.checked ?? false;

  // Generate future date labels aligned to the ensemble path
  const futureDates = generateFutureTradingDates(data.last_close_date, data.horizon);

  // Remove stale series from activeKronosFullChart
  Object.keys(activeEnsembleSeries).forEach(key => {
    if (activeEnsembleSeries[key] && activeKronosFullChart) {
      try { activeKronosFullChart.removeSeries(activeEnsembleSeries[key]); } catch (_) {}
    }
  });
  activeEnsembleSeries = {};

  // Draw individual model paths (toggled by checkbox)
  if (showIndividual && activeKronosFullChart) {
    Object.entries(data.model_paths).forEach(([modelName, path]) => {
      const style = MODEL_COLORS[modelName] || { color: '#888', lineWidth: 1 };
      const series = activeKronosFullChart.addSeries(LightweightCharts.LineSeries, {
        color: style.color,
        lineWidth: style.lineWidth,
        lineStyle: 2,   // dashed
        priceLineVisible: false,
        lastValueVisible: false,
      });
      series.setData(
        path.map((close, i) => ({ time: futureDates[i], value: close }))
      );
      activeEnsembleSeries[`${modelName}Series`] = series;
    });
  }

  // Draw bold ensemble path — final null check before calling
  if (!activeKronosFullChart) {
    console.error('[EnsembleCast] activeKronosFullChart still null after creation attempt — aborting chart draw');
    return;
  }
  const ensembleSeries = activeKronosFullChart.addSeries(LightweightCharts.LineSeries, {
    color: ENSEMBLE_STYLE.color,
    lineWidth: ENSEMBLE_STYLE.lineWidth,
    priceLineVisible: false,
    title: 'Ensemble',
  });
  ensembleSeries.setData(
    data.ensemble_path.map((close, i) => ({ time: futureDates[i], value: close }))
  );
  activeEnsembleSeries.ensembleSeries = ensembleSeries;
}

function renderConvictionBadge(conviction, divergenceScore) {
  const badge  = document.getElementById('convictionBadge');
  const icon   = document.getElementById('convictionIcon');
  const label  = document.getElementById('convictionLabel');
  if (!badge || !icon || !label) return;
  const ICONS  = { HIGH: '🟢', MODERATE: '🟡', LOW: '🔴', UNKNOWN: '⚪' };
  const LABELS = {
    HIGH:     `High Conviction  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
    MODERATE: `Moderate Conviction  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
    LOW:      `Low Conviction ⚠️  (divergence: ${(divergenceScore * 100).toFixed(1)}%)`,
    UNKNOWN:  `Unknown Conviction`
  };
  const key = conviction ?? 'UNKNOWN';
  badge.className = `conviction-badge ${key}`;
  icon.textContent  = ICONS[key]  ?? '●';
  label.textContent = LABELS[key] ?? key;
}

function renderModelWeightsBar(weights = {}) {
  const models = ['kronos', 'prophet', 'arima'];
  // Fallback to static weights if weights object is empty
  const w = (weights && Object.keys(weights).length > 0) ? weights : { kronos: 0.5, prophet: 0.3, arima: 0.2 };
  models.forEach(m => {
    const pct = Math.round((w[m] ?? 0) * 100);
    const seg = document.getElementById(`${m}WeightSeg`);
    const pctLabel = document.getElementById(`${m}WeightPct`);
    if (seg) seg.style.width  = `${pct}%`;
    if (pctLabel) pctLabel.textContent  = `${pct}%`;
  });
}

function renderAgreementMatrix(matrix = {}) {
  const MODELS = ['kronos', 'prophet', 'arima'];
  const tbody  = document.getElementById('agreementMatrixBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  MODELS.forEach(row => {
    const tr = document.createElement('tr');
    const th = document.createElement('th');
    th.textContent = row.charAt(0).toUpperCase() + row.slice(1);
    tr.appendChild(th);

    MODELS.forEach(col => {
      const td = document.createElement('td');
      if (row === col) {
        td.textContent = '—';
      } else {
        const key = [row, col].sort().join('_vs_');
        const val = matrix ? matrix[key] : null;
        if (val != null) {
          td.textContent = `${val}%`;
          td.className = val >= 75 ? 'agreement-cell-high'
                       : val >= 55 ? 'agreement-cell-medium'
                       :             'agreement-cell-low';
        } else {
          td.textContent = 'N/A';
        }
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function loadEnsembleForecast(ticker, horizon = 10, useDynamicWeights = false) {
  const panel = document.getElementById('ensemblePanel');
  if (panel) panel.style.display = 'block';
  const convictionLabel = document.getElementById('convictionLabel');
  const convictionBadge = document.getElementById('convictionBadge');
  if (convictionLabel) convictionLabel.textContent = 'Calculating\u2026';
  if (convictionBadge) convictionBadge.className = 'conviction-badge conviction-loading';

  try {
    const res = await fetch('/api/ensemble_forecast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ticker, horizon, use_dynamic_weights: useDynamicWeights })
    });
    let data;
    try {
      data = await res.json();
    } catch (e) {
      if (!res.ok) throw new Error('HTTP ' + res.status);
      throw e;
    }
    if (!res.ok || data.error) {
      throw new Error(data?.error || 'HTTP ' + res.status);
    }

    window.lastEnsembleData = data;

    destroyKronosFullChart();
    const container = document.getElementById('kronos-full-chart');

    // Defer to rAF so the panel is painted and container has a real offsetWidth
    requestAnimationFrame(() => {
      if (container && typeof LightweightCharts !== 'undefined') {
        const isDark = (document.body.getAttribute('data-theme') || 'dark') === 'dark';
        const chartWidth = container.offsetWidth || container.parentElement?.offsetWidth || 800;
        const chart = LightweightCharts.createChart(container, {
          width: chartWidth,
          height: 380,
          layout: {
            background: { color: 'transparent' },
            textColor: isDark ? '#94a3b8' : '#475569'
          },
          grid: {
            vertLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
            horzLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' }
          },
          timeScale: { borderVisible: false },
          rightPriceScale: { borderVisible: false }
        });
        activeKronosFullChart = chart;
        const ro = new ResizeObserver(entries => {
          if (!entries[0]) return;
          const { width, height } = entries[0].contentRect;
          if (width > 0) chart.resize(width, height);
        });
        ro.observe(container);
        container.resizeObserver = ro;
      }

      // Render Verdict Strip (Item 11.1)
      const verdictContainer = document.getElementById('ai-verdict-container');
      if (verdictContainer) {
        const closeValues = data.ensemble_path || [];
        const firstClose = data.last_close;
        const finalClose = closeValues[closeValues.length - 1];
        const returnPct = firstClose ? (((finalClose - firstClose) / firstClose) * 100) : 0;
        
        const direction = returnPct > 1.5 ? 'Bullish' : returnPct < -1.5 ? 'Bearish' : 'Neutral';
        const verdictClass = returnPct > 1.5 ? 'ai-verdict--bullish' : returnPct < -1.5 ? 'ai-verdict--bearish' : 'ai-verdict--neutral';
        
        verdictContainer.innerHTML = `
            <div class="ai-verdict-strip ${verdictClass}" style="display: flex; gap: 1.5rem; padding: 0.6rem 1rem; border-radius: 6px; font-size: 0.85rem; font-weight: 600; align-items: center;">
                <span class="verdict-label" style="font-family: var(--font-display); font-size: 0.9rem; text-transform: uppercase;">⚡ Ensemble View: ${direction}</span>
                <span class="verdict-move">Expected Move: ${returnPct > 0 ? '+' : ''}${returnPct.toFixed(1)}%</span>
                <span class="verdict-conf">Consensus Conviction: ${data.conviction}</span>
            </div>
        `;
      }

      renderEnsembleChart(data);
      renderConvictionBadge(data.conviction, data.divergence_score);
      renderModelWeightsBar(data.weights);
      renderAgreementMatrix(data.agreement_matrix);

      const tableWrap = document.getElementById('kronos-full-table-wrap');
      if (tableWrap) {
        const lastClose = data.last_close;
        const futureDates = generateFutureTradingDates(data.last_close_date, data.horizon);
        const rows = (data.ensemble_path || []).map((val, idx) => {
          const cls = val >= lastClose ? 'val-up' : 'val-down';
          const fmt = (arr) => (arr && arr[idx] != null) ? '\u20B9' + arr[idx].toFixed(2) : 'N/A';
          return '<tr style="border-bottom:1px solid rgba(255,255,255,0.05);">'
            + '<td style="padding:8px;">' + (futureDates[idx] || '') + '</td>'
            + '<td class="' + cls + '" style="text-align:right;padding:8px;font-weight:700;">\u20B9' + val.toFixed(2) + '</td>'
            + '<td style="text-align:right;padding:8px;color:var(--color-text-secondary);">' + fmt(data.model_paths.kronos) + '</td>'
            + '<td style="text-align:right;padding:8px;color:var(--color-text-secondary);">' + fmt(data.model_paths.prophet) + '</td>'
            + '<td style="text-align:right;padding:8px;color:var(--color-text-secondary);">' + fmt(data.model_paths.arima) + '</td>'
            + '</tr>';
        }).join('');
        tableWrap.innerHTML = '<table class="kronos-forecast-table" style="width:100%;border-collapse:collapse;font-size:0.85rem;margin-top:1rem;">'
          + '<thead><tr style="border-bottom:2px solid rgba(255,255,255,0.1);">'
          + '<th style="text-align:left;padding:8px;color:var(--color-text-muted);">Forecast Date</th>'
          + '<th style="text-align:right;padding:8px;color:var(--color-text-muted);">Ensemble Close</th>'
          + '<th style="text-align:right;padding:8px;color:var(--color-text-muted);">Kronos Close</th>'
          + '<th style="text-align:right;padding:8px;color:var(--color-text-muted);">Prophet Close</th>'
          + '<th style="text-align:right;padding:8px;color:var(--color-text-muted);">ARIMA Close</th>'
          + '</tr></thead><tbody>' + rows + '</tbody></table>';
      }

      loadBacktestingMetrics(ticker);
    });

  } catch (err) {
    if (convictionLabel) convictionLabel.textContent = 'Ensemble unavailable';
    if (convictionBadge) convictionBadge.className = 'conviction-badge';
    const convictionIcon = document.getElementById('convictionIcon');
    if (convictionIcon) convictionIcon.textContent = '⚠️';
    console.error('[EnsembleCast]', err);
  }
}


async function loadEnsembleBacktest(ticker, horizon = 10) {
  try {
    const res = await fetch(`/api/ensemble-backtest?ticker=${ticker}&horizon=${horizon}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    
    // Cache backtest data for toggle checkbox
    window.lastEnsembleBacktestData = data;

    renderBacktestComparisonTable(data.per_model_metrics);
    renderEnsembleBacktestChart(data);
  } catch (err) {
    console.error('[EnsembleCast Backtest]', err);
  }
}

function renderBacktestComparisonTable(metrics) {
  const tbody = document.getElementById('btComparisonBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const BT_MODEL_LABELS = {
    kronos: 'Kronos',
    prophet: 'Prophet',
    arima: 'ARIMA',
    ensemble: '⚡ Ensemble'
  };

  const ORDER = ['kronos', 'prophet', 'arima', 'ensemble'];
  ORDER.forEach(name => {
    const m = metrics[name];
    if (!m) return;
    const tr = document.createElement('tr');
    if (name === 'ensemble') tr.classList.add('ensemble-row');
    tr.innerHTML = `
      <td>${BT_MODEL_LABELS[name] ?? name}</td>
      <td>${m.mae}</td>
      <td>${m.mape}%</td>
      <td>${m.direction_accuracy}%</td>
    `;
    tbody.appendChild(tr);
  });
}

function renderEnsembleBacktestChart(data) {
    destroyKronosBacktestChart();
    const container = document.getElementById('kronos-backtest-chart');
    if (!container || typeof LightweightCharts === 'undefined') return;

    const currentTheme = document.body.getAttribute('data-theme') || 'dark';
    const isDark = currentTheme === 'dark';
    const chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 280,
        layout: {
            background: { color: 'transparent' },
            textColor: isDark ? '#94a3b8' : '#475569'
        },
        grid: {
            vertLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' },
            horzLines: { color: isDark ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.03)' }
        },
        timeScale: { borderVisible: false },
        rightPriceScale: { borderVisible: false },
    });
    activeKronosBacktestChart = chart;

    // Actual series (green)
    const actualSeries = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#10b981',
        lineWidth: 2.5,
        title: 'Actual',
    });
    actualSeries.setData(data.comparison_points.map(pt => ({
        time: pt.date,
        value: pt.actual
    })));

    // Ensemble series (gold)
    const ensembleSeries = chart.addSeries(LightweightCharts.LineSeries, {
        color: '#fbbf24',
        lineWidth: 2.5,
        title: 'Ensemble',
    });
    ensembleSeries.setData(data.comparison_points.map(pt => ({
        time: pt.date,
        value: pt.ensemble
    })));

    // Individual models faint dashed lines if present
    const showIndividual = document.getElementById('showIndividualModels')?.checked ?? false;
    if (showIndividual) {
        const MODEL_COLORS = {
            kronos: 'rgba(124, 58, 237, 0.45)',
            prophet: 'rgba(234, 88, 12, 0.45)',
            arima: 'rgba(8, 145, 178, 0.45)'
        };
        ['kronos', 'prophet', 'arima'].forEach(model => {
            const path = data.comparison_points.map(pt => pt[model] ? { time: pt.date, value: pt[model] } : null).filter(x => x !== null);
            if (path.length > 0) {
                const s = chart.addSeries(LightweightCharts.LineSeries, {
                    color: MODEL_COLORS[model],
                    lineWidth: 1,
                    lineStyle: 2, // dashed
                    title: model.toUpperCase()
                });
                s.setData(path);
            }
        });
    }

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(entries => {
        if (entries.length === 0 || !entries[0].contentRect) return;
        const { width, height } = entries[0].contentRect;
        chart.resize(width, height);
    });
    resizeObserver.observe(container);
    container.resizeObserver = resizeObserver;
}

window.loadEnsembleForecast = loadEnsembleForecast;
window.loadEnsembleBacktest = loadEnsembleBacktest;
window.renderEnsembleChart = renderEnsembleChart;
window.renderEnsembleBacktestChart = renderEnsembleBacktestChart;
window.generateFutureTradingDates = generateFutureTradingDates;

// -----------------------------------------------------------------------------
// Phase 4: R:R Auto-Screener Logic (FEAT-005)
// -----------------------------------------------------------------------------

let rrSetupsData = [];

function computeRRSetups(stocks, params) {
  const {
    minRR       = 2.5,
    atrMult     = 1.5,
    targetExt   = 10.0,
    maxRiskPct  = 7.0,
    minSwing    = 5,
    minRvol     = 0.8,
  } = params;

  const results = [];

  for (const s of stocks) {
    const close     = parseFloat(s.close);
    const atrPct    = parseFloat(s.atr_pct);
    const high52w   = parseFloat(s.price_52_week_high);
    const swingscore = parseFloat(s.swingscore) || 0;
    const rvol      = parseFloat(s.relative_volume) || 0;

    // Quality gates
    if (!close || !atrPct || !high52w) continue;
    if (swingscore < minSwing)         continue;
    if (rvol < minRvol)                continue;

    const atrAbs = close * (atrPct / 100);
    const isBreakout = ['Breakout Ready', 'Sector Leader'].includes(s.setupLabel);

    // Entry
    const entry = isBreakout ? high52w * 1.005 : close;

    // Stop — ATR-based with low structural refinement
    const dayLow = parseFloat(s.day_low) || parseFloat(s.low) || (entry - atrAbs * atrMult);
    const atrStop = entry - (atrMult * atrAbs);
    const structStop = (entry - dayLow) < atrAbs ? dayLow * 0.999 : atrStop;
    const stop = Math.max(structStop, entry * 0.85); // 15% floor

    const risk = entry - stop;
    if (risk <= 0) continue;

    const riskPct = (risk / entry) * 100;
    if (riskPct > maxRiskPct) continue;

    // Target
    const breakoutTarget = high52w * (1 + targetExt / 100);
    const atrTarget      = entry + (minRR * risk);  // fallback: exactly at min_rr
    const target = isBreakout
      ? Math.max(breakoutTarget, atrTarget)
      : atrTarget;

    const reward = target - entry;
    if (reward <= 0) continue;

    const rr = reward / risk;
    if (rr < minRR) continue;

    results.push({
      ...s,
      rr_entry:   parseFloat(entry.toFixed(2)),
      rr_stop:    parseFloat(stop.toFixed(2)),
      rr_target:  parseFloat(target.toFixed(2)),
      rr_risk:    parseFloat(risk.toFixed(2)),
      rr_reward:  parseFloat(reward.toFixed(2)),
      rr_ratio:   parseFloat(rr.toFixed(2)),
      rr_risk_pct: parseFloat(riskPct.toFixed(2)),
      rr_method:  isBreakout ? '52w_breakout' : 'atr_projection',
    });
  }

  // Sort by R:R descending, cap at 20 results
  results.sort((a, b) => b.rr_ratio - a.rr_ratio);
  return results.slice(0, 20);
}

function renderRRTable(setups) {
    const table = document.getElementById('rr-table');
    const tbody = document.getElementById('rr-table-body');
    const emptyState = document.getElementById('rr-setups-empty');
    
    if (!tbody || !table) return;
    
    tbody.innerHTML = '';
    
    if (setups.length === 0) {
        table.style.display = 'none';
        if (emptyState) {
            emptyState.style.display = 'block';
            if (!stocksData || stocksData.length === 0) {
                emptyState.querySelector('span').textContent = 'Run a scan first to fetch market listings.';
            } else {
                emptyState.querySelector('span').textContent = 'No setups meet the current R:R criteria. Try lowering Min R:R or relaxing the quality gates.';
            }
        }
        return;
    }
    
    if (emptyState) emptyState.style.display = 'none';
    table.style.display = 'table';
    
    let html = '';
    setups.forEach(stock => {
        let rrClass = '';
        if (stock.rr_ratio >= 3.0) {
            rrClass = 'rr-gold';
        } else if (stock.rr_ratio >= 2.5) {
            rrClass = 'rr-green';
        }
        
        const methodClass = stock.rr_method === '52w_breakout' ? 'rr-method-breakout' : 'rr-method-atr';
        const methodLabel = stock.rr_method === '52w_breakout' ? 'Breakout' : 'ATR Proj';
        const entryStyle = stock.rr_method === '52w_breakout' ? 'color: var(--accent-green); font-weight: 700;' : 'color: var(--color-text-secondary);';
        
        const label = stock.setupLabel || 'Early Watch';
        const setupPillHtml = makeSetupPill(label, stock.setupConfidence || 0, stock.setupTags || []);
        
        const swingScore = stock.swingscore != null ? stock.swingscore : 0;
        const swingBand = stock.swingband || 'weak';
        const swingBadgeClass = 'badge-swing-' + swingBand;
        const rvol = parseFloat(stock.relative_volume) || 0;
        
        html += `
            <tr onclick="openTradeDrawerFromRR('${stock.clean_ticker}')">
                <td class="ticker-col">
                    <span class="ticker-box">${stock.clean_ticker}</span>
                </td>
                <td class="text-center">
                    ${setupPillHtml}
                </td>
                <td class="text-right" style="${entryStyle}">₹${stock.rr_entry.toFixed(2)}</td>
                <td class="text-right" style="color: var(--accent-red); font-weight: 600;">₹${stock.rr_stop.toFixed(2)} <span style="font-size:0.75rem; color: var(--color-text-muted);">(${stock.rr_risk_pct.toFixed(1)}%)</span></td>
                <td class="text-right" style="color: var(--accent-green); font-weight: 600;">₹${stock.rr_target.toFixed(2)}</td>
                <td class="text-right">₹${stock.rr_risk.toFixed(2)}</td>
                <td class="text-right">₹${stock.rr_reward.toFixed(2)}</td>
                <td class="text-center ${rrClass}" style="font-size: 1rem;">${stock.rr_ratio.toFixed(2)}x</td>
                <td class="text-center">
                    <span class="rr-method-badge ${methodClass}">${methodLabel}</span>
                </td>
                <td class="text-center">
                    <span class="badge ${swingBadgeClass}" style="padding: 0.3rem 0.6rem; font-size: 0.75rem; font-weight:700;">${swingScore} (${swingBand.toUpperCase()})</span>
                </td>
                <td class="text-right" style="font-weight: 600;">${rvol.toFixed(2)}x</td>
                <td class="text-center" onclick="event.stopPropagation();">
                    <button class="btn-table-chart" onclick="openTradeDrawerFromRR('${stock.clean_ticker}')">
                        📐 Analyse
                    </button>
                </td>
            </tr>
        `;
    });
    
    tbody.innerHTML = html;
}

function runRRScreen() {
    const minRR = parseFloat(document.getElementById('rr-min-input')?.value) || 2.5;
    const atrMult = parseFloat(document.getElementById('rr-atr-mult')?.value) || 1.5;
    const targetExt = parseFloat(document.getElementById('rr-target-ext')?.value) || 10.0;
    const maxRiskPct = parseFloat(document.getElementById('rr-max-risk')?.value) || 7.0;
    const minSwing = parseFloat(document.getElementById('rr-min-swing')?.value) || 5;
    
    const params = {
        minRR,
        atrMult,
        targetExt,
        maxRiskPct,
        minSwing,
        minRvol: 0.8
    };
    
    // Save to localStorage
    localStorage.setItem('rr_screen_prefs', JSON.stringify(params));
    
    // Filter stocksData by global search and sector select before screening
    const searchVal = document.getElementById('search-input')?.value.toLowerCase().trim() || '';
    const sectorVal = selectedSector || 'all';
    
    let targetStocks = stocksData || [];
    if (searchVal || sectorVal !== 'all') {
        targetStocks = targetStocks.filter(stock => {
            const matchesSearch = !searchVal || 
                                  stock.clean_ticker.toLowerCase().includes(searchVal) || 
                                  stock.description.toLowerCase().includes(searchVal) ||
                                  (stock.setupLabel && stock.setupLabel.toLowerCase().includes(searchVal));
            const matchesSector = sectorVal === 'all' || stock.sector === sectorVal;
            return matchesSearch && matchesSector;
        });
    }
    
    // Run computation
    rrSetupsData = computeRRSetups(targetStocks, params);
    
    // Update badge count on tab button
    const countBadge = document.getElementById('rr-setups-count');
    if (countBadge) {
        countBadge.textContent = rrSetupsData.length;
        countBadge.style.display = rrSetupsData.length > 0 ? 'inline-flex' : 'none';
    }
    
    // Summary line
    const summary = document.getElementById('rr-result-summary');
    if (summary) {
        summary.textContent = rrSetupsData.length > 0
            ? `${rrSetupsData.length} setup${rrSetupsData.length > 1 ? 's' : ''} pass ≥${minRR}:1 R:R from ${targetStocks.length} scanned`
            : `No setups pass ≥${minRR}:1 R:R`;
        summary.style.color = rrSetupsData.length > 0 ? 'var(--accent-green)' : 'var(--color-text-muted)';
    }
    
    // Render the table
    renderRRTable(rrSetupsData);
}

function openTradeDrawerFromRR(ticker) {
    const stock = rrSetupsData.find(s => s.clean_ticker === ticker) || (stocksData && stocksData.find(s => s.clean_ticker === ticker));
    if (!stock) return;
    
    // Open the drawer as normal
    openTradeDrawer(stock.clean_ticker);
    
    // Pre-fill the Risk Calculator fields if we have R:R values computed
    if (stock.rr_entry !== undefined) {
        setTimeout(() => {
            const entryEl = document.getElementById('drawer-entry-input');
            const stopEl = document.getElementById('drawer-stop-input');
            
            if (entryEl) entryEl.value = stock.rr_entry;
            if (stopEl) stopEl.value = stock.rr_stop;
            
            // Trigger recalculation
            const calcEvent = new Event('input', { bubbles: true });
            if (entryEl) entryEl.dispatchEvent(calcEvent);
        }, 300);
    }
}

function restoreRRPrefs() {
    const saved = localStorage.getItem('rr_screen_prefs');
    if (saved) {
        try {
            const params = JSON.parse(saved);
            if (params.minRR !== undefined && document.getElementById('rr-min-input')) {
                document.getElementById('rr-min-input').value = params.minRR;
            }
            if (params.atrMult !== undefined && document.getElementById('rr-atr-mult')) {
                document.getElementById('rr-atr-mult').value = params.atrMult;
            }
            if (params.targetExt !== undefined && document.getElementById('rr-target-ext')) {
                document.getElementById('rr-target-ext').value = params.targetExt;
            }
            if (params.maxRiskPct !== undefined && document.getElementById('rr-max-risk')) {
                document.getElementById('rr-max-risk').value = params.maxRiskPct;
            }
            if (params.minSwing !== undefined && document.getElementById('rr-min-swing')) {
                document.getElementById('rr-min-swing').value = params.minSwing;
            }
        } catch(e) {
            console.error("Error restoring R:R screen preferences:", e);
        }
    }
}

// Expose functions to window
window.computeRRSetups = computeRRSetups;
window.renderRRTable = renderRRTable;
window.runRRScreen = runRRScreen;
window.openTradeDrawerFromRR = openTradeDrawerFromRR;
window.restoreRRPrefs = restoreRRPrefs;

