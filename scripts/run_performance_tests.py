#!/usr/bin/env python3
"""
Script to run performance tests for the stock screener application.
"""
import subprocess
import sys
import time
import os

def run_unit_tests():
    """Run unit tests."""
    print("Running unit tests...")
    start_time = time.time()
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/unit/",
        "-v",
        "--tb=short"
    ], capture_output=True, text=True)
    end_time = time.time()

    print(f"Unit tests completed in {end_time - start_time:.2f} seconds")
    if result.returncode != 0:
        print("Unit tests FAILED:")
        print(result.stdout)
        print(result.stderr)
        return False
    else:
        print("Unit tests PASSED")
        return True

def run_performance_tests():
    """Run performance tests."""
    print("\nRunning performance tests...")
    start_time = time.time()
    result = subprocess.run([
        sys.executable, "-m", "pytest",
        "tests/unit/test_screener_service_performance.py",
        "-v",
        "--tb=short",
        "-s"  # Don't capture output so we can see print statements
    ], capture_output=True, text=True)
    end_time = time.time()

    print(f"Performance tests completed in {end_time - start_time:.2f} seconds")
    if result.returncode != 0:
        print("Performance tests FAILED:")
        print(result.stdout)
        print(result.stderr)
        return False
    else:
        print("Performance tests PASSED")
        return True

def run_specific_performance_test():
    """Run the performance test script directly."""
    print("\nRunning standalone performance test...")
    start_time = time.time()
    result = subprocess.run([
        sys.executable,
        "tests/unit/test_screener_service_performance.py"
    ], capture_output=True, text=True)
    end_time = time.time()

    print(f"Standalone performance test completed in {end_time - start_time:.2f} seconds")
    if result.returncode != 0:
        print("Standalone performance test FAILED:")
        print(result.stdout)
        print(result.stderr)
        return False
    else:
        print("Standalone performance test PASSED:")
        print(result.stdout)
        return True

def benchmark_forecast_latency():
    """Benchmark forecast API endpoints (setup-analysis and kronos-forecast) latency."""
    print("\nBenchmarking forecast API latency...")
    
    import sys
    import os
    # Add project root to sys.path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    
    import torch
    print(f"Initial torch threads: {torch.get_num_threads()}")
    torch.set_num_threads(8)
    print(f"Set torch threads to: {torch.get_num_threads()}")
    
    # Set environment variables for config loading to keep tests safe and isolated
    shared_db = 'file:perf_test_db_forecast?mode=memory&cache=shared&uri=true'
    os.environ['DATABASE'] = shared_db
    os.environ['TEST_DATABASE_URL'] = f'sqlite:///{shared_db}'
    
    # Clear physical database cache file for a clean start
    import sqlite3
    try:
        conn = sqlite3.connect("scan_history.db")
        c = conn.cursor()
        c.execute("DELETE FROM kronos_forecasts WHERE ticker LIKE 'BENCHMARK_TICKER%'")
        conn.commit()
        conn.close()
        print("Cleared benchmark ticker entries from persistent DB cache.")
    except Exception as db_err:
        print(f"Note: Persistent DB cache clean skipped: {db_err}")
    
    from app import create_app
    from unittest.mock import patch
    import datetime
    
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{shared_db}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        from app.models import db
        from app.database import init_db_app
        init_db_app()
        db.create_all()
        
    start_date = datetime.date(2026, 1, 1)
    mock_history = []
    for i in range(120):
        d = start_date + datetime.timedelta(days=i)
        mock_history.append({
            "date": d.strftime("%Y-%m-%d"),
            "open": 100.0, "high": 102.0, "low": 98.0, "close": 100.0, "volume": 10000.0
        })

    # We patch fetch_historical_prices to return mock_history
    with patch('app.api.v1.legacy_routes.fetch_historical_prices', return_value=mock_history):
        from app.api.v1.legacy_routes import get_kronos_predictor
        print("Pre-loading Kronos predictor model to exclude weights loading/downloading time from benchmark...")
        get_kronos_predictor()
        
        with app.test_client() as client:
            # Perform a warmup inference call on /api/kronos-forecast to compile PyTorch graph
            print("Performing warmup inference request to compile PyTorch graph...")
            client.get("/api/kronos-forecast?ticker=BENCHMARK_TICKER_WARMUP&pred_len=5&sample_count=5")
            
            # Clear any in-memory cache keys for clean measurement
            from app.api.v1.legacy_routes import _kronos_cache
            with patch.dict(_kronos_cache, {}, clear=True):
                # Ensure BENCHMARK_TICKER_LIVE is not cached in DB
                try:
                    conn = sqlite3.connect("scan_history.db")
                    c = conn.cursor()
                    c.execute("DELETE FROM kronos_forecasts WHERE ticker = 'BENCHMARK_TICKER_LIVE'")
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                
                print("1. Testing live model inference latency via /api/kronos-forecast...")
                t_start = time.perf_counter()
                res1 = client.get("/api/kronos-forecast?ticker=BENCHMARK_TICKER_LIVE&pred_len=5&sample_count=5")
                t_end = time.perf_counter()
                live_latency = t_end - t_start
                
                if res1.status_code != 200:
                    print(f"Error: /api/kronos-forecast failed with status code {res1.status_code}")
                    print(res1.data)
                    return False
                    
                print(f"  Live inference latency (kronos-forecast): {live_latency:.3f} s")
                
                # Now populate memory cache with a 10-day forecast via setup-analysis
                print("Populating 10-day forecast in memory cache via setup-analysis...")
                res_setup = client.get("/api/setup-analysis?ticker=BENCHMARK_TICKER_LIVE")
                if res_setup.status_code != 200:
                    print("Error populating memory cache")
                    return False
                
                # 2. Test memory cache hit and slicing latency via /api/kronos-forecast
                print("2. Testing sliced cache hit latency via /api/kronos-forecast (pred_len=5)...")
                t_start = time.perf_counter()
                res2 = client.get("/api/kronos-forecast?ticker=BENCHMARK_TICKER_LIVE&pred_len=5")
                t_end = time.perf_counter()
                cache_hit_latency_ms = (t_end - t_start) * 1000.0
                
                if res2.status_code != 200:
                    print(f"Error: /api/kronos-forecast cache hit failed with status code {res2.status_code}")
                    return False
                    
                print(f"  Cache hit sliced forecast latency: {cache_hit_latency_ms:.2f} ms")
                data2 = res2.get_json()
                if len(data2["forecast"]) != 5:
                    print(f"Error: Expected forecast length of 5, got {len(data2['forecast'])}")
                    return False
                
                # Check that confidence envelopes p10_close and p90_close are present in the response
                for f_item in data2["forecast"]:
                    if "p10_close" not in f_item or "p90_close" not in f_item:
                        print("Error: Missing p10_close or p90_close in sliced forecast output")
                        return False
                
                # 3. Test DB cache hit latency via /api/kronos-forecast (with memory cache cleared)
                print("3. Testing DB cache hit latency via /api/kronos-forecast (with memory cache cleared)...")
                _kronos_cache.clear()
                t_start = time.perf_counter()
                res3 = client.get("/api/kronos-forecast?ticker=BENCHMARK_TICKER_LIVE&pred_len=5")
                t_end = time.perf_counter()
                db_hit_latency_ms = (t_end - t_start) * 1000.0
                
                if res3.status_code != 200:
                    print(f"Error: /api/kronos-forecast (DB cache) failed with status code {res3.status_code}")
                    return False
                    
                print(f"  DB cache hit latency: {db_hit_latency_ms:.2f} ms")
                
                # Clean up DB
                with app.app_context():
                    db.drop_all()
                
                os.environ.pop('DATABASE', None)
                os.environ.pop('TEST_DATABASE_URL', None)
                
                # Threshold checks
                success = True
                if live_latency > 3.0:
                    print(f"[FAIL] Live inference latency ({live_latency:.2f} s) exceeds threshold of 3.0 s")
                    success = False
                else:
                    print(f"[OK] Live inference latency ({live_latency:.2f} s) is within threshold of 3.0 s")
                    
                if cache_hit_latency_ms > 10.0:
                    print(f"[FAIL] Cache hit response time ({cache_hit_latency_ms:.2f} ms) exceeds threshold of 10.0 ms")
                    success = False
                else:
                    print(f"[OK] Cache hit response time ({cache_hit_latency_ms:.2f} ms) is within threshold of 10.0 ms")
                    
                return success

def main():
    """Main function to run all tests."""
    print("=" * 60)
    print("STOCK SCREENER PERFORMANCE TEST SUITE")
    print("=" * 60)

    # Check if we're in the right directory
    if not os.path.exists("app"):
        print("Error: Please run this script from the stock-screener project root directory")
        return False

    success = True

    # Run unit tests
    if not run_unit_tests():
        success = False

    # Run performance tests via pytest
    if not run_performance_tests():
        success = False

    # Run standalone performance test
    if not run_specific_performance_test():
        success = False

    # Run forecast latency benchmark
    if not benchmark_forecast_latency():
        success = False

    print("\n" + "=" * 60)
    if success:
        print("ALL TESTS PASSED [OK]")
    else:
        print("SOME TESTS FAILED [FAIL]")
    print("=" * 60)

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
