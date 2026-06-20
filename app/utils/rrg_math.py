def compute_jdk_rs(sector_return, bench_return):
    """
    Computes JDK RS relative return value.
    Formula:
      jdk_rs = ((100.0 + sector_return) / (100.0 + bench_return) * 100.0)
    Guards against divide-by-zero by returning 100.0 if (100.0 + bench_return) == 0.
    """
    sector_return = float(sector_return or 0.0)
    bench_return = float(bench_return or 0.0)
    
    denom = 100.0 + bench_return
    if denom == 0.0:
        return 100.0
    return (100.0 + sector_return) / denom * 100.0

def compute_quadrant(jdk_rs, rs_momentum):
    """
    Maps JDK RS and RS Momentum to one of the four RRG quadrants:
      - RS >= 100 and Momentum >= 0: Leading
      - RS >= 100 and Momentum < 0: Weakening
      - RS < 100 and Momentum < 0: Lagging
      - RS < 100 and Momentum >= 0: Improving
    """
    jdk_rs = float(jdk_rs or 0.0)
    rs_momentum = float(rs_momentum or 0.0)
    
    if jdk_rs >= 100.0 and rs_momentum >= 0.0:
        return 'Leading'
    elif jdk_rs >= 100.0 and rs_momentum < 0.0:
        return 'Weakening'
    elif jdk_rs < 100.0 and rs_momentum < 0.0:
        return 'Lagging'
    else:
        return 'Improving'
