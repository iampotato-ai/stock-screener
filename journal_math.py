def compute_pnl_and_r(entry, stop, qty, exit_price, risk_amount=None):
    """
    Computes P&L and R-multiple achieved for a long trade.
    
    Formula:
      pnl = (exit_price - entry) * qty
      risk = abs(entry - stop) * qty (or risk_amount if provided)
      r_achieved = pnl / risk
      
    If exit_price matches stop, R-multiple will be exactly -1.0.
    """
    entry = float(entry or 0.0)
    qty = int(qty or 0)
    exit_price = float(exit_price or 0.0)
    
    pnl = round((exit_price - entry) * qty, 2)
    
    if risk_amount is not None:
        try:
            r_amount = float(risk_amount)
            if r_amount > 0.0:
                risk = r_amount
            else:
                stop_val = float(stop or 0.0)
                risk = abs(entry - stop_val) * qty if stop_val else 1.0
        except (ValueError, TypeError):
            stop_val = float(stop or 0.0)
            risk = abs(entry - stop_val) * qty if stop_val else 1.0
    else:
        stop_val = float(stop or 0.0)
        risk = abs(entry - stop_val) * qty if stop_val else 1.0
        
    r_achieved = round(pnl / risk, 2) if risk != 0.0 else 0.0
    return pnl, r_achieved
