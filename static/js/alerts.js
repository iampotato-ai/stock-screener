const AlertEngine = (() => {
  const DEDUP_PREFIX = 'alert_fired_';
  let _alertCount = 0;
  const today = () => new Date().toISOString().slice(0, 10);

  function _isSettingEnabled(type) {
    try {
      const settingsStr = localStorage.getItem('alert_settings');
      if (!settingsStr) return true;
      const settings = JSON.parse(settingsStr);
      return settings[type] !== false;
    } catch (e) {
      return true;
    }
  }

  function _canFire(key, type) {
    if (!_isSettingEnabled(type)) return false;
    const dedupKey = DEDUP_PREFIX + key;
    if (sessionStorage.getItem(dedupKey)) return false;
    sessionStorage.setItem(dedupKey, '1');
    return true;
  }

  function _updateAlertCount(delta) {
    _alertCount += delta;
    const countBadge = document.getElementById('alert-log-count');
    if (countBadge) {
      countBadge.textContent = _alertCount.toString();
    }
  }

  function appendToAlertLog({ title, body, type, firedAt }) {
    const logBody = document.getElementById('alert-log-body');
    if (!logBody) return;

    const placeholder = logBody.querySelector('.alert-log-empty');
    if (placeholder) {
      placeholder.remove();
    }

    const date = new Date(firedAt);
    const timeStr = date.toTimeString().split(' ')[0];

    const entry = document.createElement('div');
    entry.className = `alert-log-entry alert-log-entry--${type}`;
    entry.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 2px;">
        <span class="alert-log-title" style="font-weight: 600; font-size: 0.82rem; color: #fff;">${title}</span>
        <span class="alert-log-time" style="font-size: 0.72rem; color: var(--color-text-muted); font-family: monospace;">${timeStr}</span>
      </div>
      <span class="alert-log-body" style="font-size: 0.78rem; color: var(--color-text-secondary); line-height: 1.35; display: block;">${body}</span>
    `;

    logBody.insertBefore(entry, logBody.firstChild);
    _updateAlertCount(1);
  }

  function _fire(title, body, type = 'info') {
    // 1. Browser push notification
    if ('Notification' in window && Notification.permission === 'granted') {
      try {
        new Notification(title, { body, icon: '/static/favicon.ico' });
      } catch (e) {
        console.error('Failed to trigger native notification:', e);
      }
    }
    // 2. Append to in-session alert log
    appendToAlertLog({ title, body, type, firedAt: new Date().toISOString() });
  }

  function checkRegimeDelta(currentScore, historyArr) {
    if (!historyArr || historyArr.length < 2) return;
    const prevScore = historyArr[1]?.regimeScore ?? currentScore;
    const delta = currentScore - prevScore;
    if (delta >= 15) {
      const key = `regime_delta_${today()}_${currentScore}`;
      if (_canFire(key, 'regime')) {
        let band = 'Neutral';
        if (currentScore >= 75) band = 'Bull Run';
        else if (currentScore >= 55) band = 'Bullish';
        else if (currentScore >= 35) band = 'Neutral';
        else band = 'Bearish';

        _fire(
          'Market Regime Surge',
          `Regime jumped ▲${delta} → ${band} (${currentScore}/100)`,
          'bullish'
        );
      }
    }
  }

  function checkSwingFlips(prevMap, currentStocks, watchlistSymbols) {
    if (!currentStocks || !watchlistSymbols || watchlistSymbols.size === 0) return;
    currentStocks.forEach(stock => {
      if (!watchlistSymbols.has(stock.clean_ticker)) return;
      const prev = prevMap[stock.clean_ticker];
      if (!prev) return;
      if (prev.swingscore < 6 && stock.swingscore >= 8) {
        const key = `swing_flip_${stock.clean_ticker}_${today()}`;
        if (_canFire(key, 'swing')) {
          _fire(
            `Swing Flip: ${stock.clean_ticker}`,
            `${stock.clean_ticker} Swing Score flipped → ${stock.swingscore}/10 (${stock.swingband || 'Elite'})`,
            'swing'
          );
        }
      }
    });
  }

  function checkKronosSpikes(rankings, watchlistSymbols) {
    if (!rankings || !watchlistSymbols || watchlistSymbols.size === 0) return;
    Object.entries(rankings).forEach(([ticker, data]) => {
      if (!watchlistSymbols.has(ticker)) return;
      if ((data.predicted_return_pct ?? 0) > 5.0) {
        const key = `kronos_spike_${ticker}_${today()}`;
        if (_canFire(key, 'kronos')) {
          _fire(
            `Kronos Spike: ${ticker}`,
            `${ticker} Kronos forecast: +${data.predicted_return_pct.toFixed(2)}% in 5d (${data.ai_forecast_bias || 'Bullish'})`,
            'kronos'
          );
        }
      }
    });
  }

  function checkDeals(deals, watchlistSymbols) {
    if (!deals || !watchlistSymbols || watchlistSymbols.size === 0) return;
    deals.forEach(deal => {
      const sym = (deal.symbol || '').replace(/[^A-Z0-9]/gi, '').toUpperCase();
      if (!watchlistSymbols.has(sym)) return;
      const key = `deal_${sym}_${deal.tradeDate || today()}_${deal.clientName}`;
      if (_canFire(key, 'deals')) {
        const qtyFormatted = typeof deal.volume === 'number' ? deal.volume.toLocaleString('en-IN') : deal.volume;
        _fire(
          `Deal Alert: ${sym}`,
          `${deal.dealType || 'Block Deal'} — ${qtyFormatted} shares @ ₹${deal.price} by ${deal.clientName}`,
          'deal'
        );
      }
    });
  }

  function clearAlerts() {
    const logBody = document.getElementById('alert-log-body');
    if (!logBody) return;
    logBody.innerHTML = `
      <div class="alert-log-empty" style="text-align: center; color: var(--color-text-muted); font-size: 0.8rem; padding: 2rem 0; font-style: italic;">
        No alerts triggered in this session.
      </div>
    `;
    _alertCount = 0;
    const countBadge = document.getElementById('alert-log-count');
    if (countBadge) {
      countBadge.textContent = '0';
    }
  }

  function init() {
    const settingsStr = localStorage.getItem('alert_settings');
    let settings = { regime: true, swing: true, kronos: true, deals: true };
    if (settingsStr) {
      try {
        settings = { ...settings, ...JSON.parse(settingsStr) };
      } catch (e) {}
    }

    const types = ['regime', 'swing', 'kronos', 'deals'];
    types.forEach(t => {
      const checkbox = document.getElementById(`alert-set-${t}`);
      if (checkbox) {
        checkbox.checked = settings[t] !== false;
        checkbox.addEventListener('change', () => {
          settings[t] = checkbox.checked;
          localStorage.setItem('alert_settings', JSON.stringify(settings));
        });
      }
    });

    const clearBtn = document.getElementById('btn-clear-alerts');
    if (clearBtn) {
      clearBtn.addEventListener('click', () => clearAlerts());
    }

    const settingsBtn = document.getElementById('btn-alert-settings');
    const settingsPanel = document.getElementById('alert-settings-panel');
    if (settingsBtn && settingsPanel) {
      settingsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        settingsPanel.classList.toggle('hidden');
      });
      document.addEventListener('click', (e) => {
        if (!settingsPanel.contains(e.target) && !settingsBtn.contains(e.target)) {
          settingsPanel.classList.add('hidden');
        }
      });
    }

    const closeSettingsBtn = document.getElementById('btn-close-alert-settings');
    if (closeSettingsBtn && settingsPanel) {
      closeSettingsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        settingsPanel.classList.add('hidden');
      });
    }

    if (location.search.includes('runAlertTests')) {
      setTimeout(() => {
        runSelfTest();
      }, 1000);
    }
  }

  function runSelfTest() {
    console.log('[AlertEngine] Starting self-test suite...');
    const originalSessionStorage = {};
    
    const testKeys = [
      DEDUP_PREFIX + `regime_delta_${today()}_80`,
      DEDUP_PREFIX + `swing_flip_RELIANCE_${today()}`,
      DEDUP_PREFIX + `kronos_spike_RELIANCE_${today()}`,
      DEDUP_PREFIX + `deal_RELIANCE_${today()}_JPMORGAN`
    ];
    testKeys.forEach(k => {
      originalSessionStorage[k] = sessionStorage.getItem(k);
      sessionStorage.removeItem(k);
    });

    // 1. Test Regime Shift
    checkRegimeDelta(80, [{ regimeScore: 60 }]);

    // 2. Test Swing Flip
    checkSwingFlips({ "RELIANCE": { swingscore: 5 } }, [{ clean_ticker: "RELIANCE", swingscore: 9, swingband: "Elite" }], new Set(["RELIANCE"]));

    // 3. Test Kronos Forecast Spikes
    checkKronosSpikes({ "RELIANCE": { predicted_return_pct: 7.2, ai_forecast_bias: "Strong Bullish" } }, new Set(["RELIANCE"]));

    // 4. Test Deals
    checkDeals([{ symbol: "RELIANCE", volume: 150000, price: 2500, clientName: "JPMORGAN", dealType: "Block Deal", tradeDate: today() }], new Set(["RELIANCE"]));

    testKeys.forEach(k => {
      if (originalSessionStorage[k] !== null) {
        sessionStorage.setItem(k, originalSessionStorage[k]);
      } else {
        sessionStorage.removeItem(k);
      }
    });

    console.log('[AlertEngine] Self-test suite completed.');
    return true;
  }

  return {
    checkRegimeDelta,
    checkSwingFlips,
    checkKronosSpikes,
    checkDeals,
    checkLargeDeals: checkDeals,
    appendToAlertLog,
    clearAlerts,
    runSelfTest,
    init,
    initUI: init
  };
})();
