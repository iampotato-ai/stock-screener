"""
Performance tests for ScreenerService.
"""
import time
import statistics
import os
import sys
import pytest
from datetime import date

# Add project root to sys.path to allow standalone execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import create_app
from app.models import db, ScanHistory, ScanPriceLog
from app.services.screener_service import screener_service

# Use a shared SQLite in-memory database configuration for performance test session
SQLALCHEMY_PERF_DATABASE_URI = 'sqlite:///file:perf_test_db?mode=memory&cache=shared&uri=true'


def create_test_data(app, num_scan_dates=10, num_tickers_per_date=50):
    """Create test data for performance testing."""
    # Clear existing data
    db.session.query(ScanPriceLog).delete()
    db.session.query(ScanHistory).delete()

    # Create scan history records for different dates
    scan_dates = [date(2023, 1, i+1) for i in range(num_scan_dates)]

    scan_history_records = []
    for d in scan_dates:
        # Create different tickers for each date to avoid unique constraint violations
        for i in range(num_tickers_per_date):
            ticker = f'TICKER{i:03d}'
            scan_history = ScanHistory(date=d, ticker=ticker)
            scan_history_records.append(scan_history)
            db.session.add(scan_history)

    db.session.flush()

    # Create scan price log records
    price_log_records = []
    for scan_history in scan_history_records:
        # Create price data for each scan history record
        close_price = 100.0 + (hash(scan_history.ticker + str(scan_history.date)) % 50)
        price_log = ScanPriceLog(
            date=scan_history.date,
            ticker=scan_history.ticker,
            close=close_price,
            setupLabel=f'Setup {(hash(scan_history.ticker) % 10)}'
        )
        price_log_records.append(price_log)
        db.session.add(price_log)

    db.session.commit()
    return len(scan_history_records), len(price_log_records)


def benchmark_get_scan_results(app, iterations=100):
    """Benchmark the get_scan_results method."""
    times = []

    with app.app_context():
        # Warmup call to initialize connections and query plans
        screener_service.get_scan_results(limit=50)

        for _ in range(iterations):
            start_time = time.perf_counter()
            screener_service.get_scan_results(limit=50)
            end_time = time.perf_counter()
            times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    return times


def benchmark_get_stock_details(app, iterations=100):
    """Benchmark the get_stock_details method."""
    times = []

    with app.app_context():
        # Use a ticker that exists in our test data
        test_ticker = 'TICKER000'

        # Warmup call to initialize connections and query plans
        screener_service.get_stock_details(test_ticker)

        for _ in range(iterations):
            start_time = time.perf_counter()
            screener_service.get_stock_details(test_ticker)
            end_time = time.perf_counter()
            times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    return times


def benchmark_get_scan_results_different_limits(app):
    """Benchmark get_scan_results with different limit values."""
    limits = [10, 25, 50, 100, 200]
    results = {}

    with app.app_context():
        for limit in limits:
            times = []
            # Warm up
            screener_service.get_scan_results(limit=limit)

            # Actual benchmark
            for _ in range(50):
                start_time = time.perf_counter()
                screener_service.get_scan_results(limit=limit)
                end_time = time.perf_counter()
                times.append((end_time - start_time) * 1000)  # Convert to milliseconds

            results[limit] = {
                'times': times,
                'avg': statistics.mean(times),
                'median': statistics.median(times),
                'min': min(times),
                'max': max(times),
                'stddev': statistics.stdev(times) if len(times) > 1 else 0.0
            }

    return results


@pytest.fixture(scope="module")
def app_with_data():
    """Pytest fixture to initialize app and seed database once for performance tests."""
    # Set environment variables for config loading
    shared_db = 'file:perf_test_db?mode=memory&cache=shared&uri=true'
    os.environ['DATABASE'] = shared_db
    os.environ['TEST_DATABASE_URL'] = f'sqlite:///{shared_db}'

    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_PERF_DATABASE_URI
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        from app.database import init_db_app
        init_db_app()
        db.create_all()
        create_test_data(app, num_scan_dates=5, num_tickers_per_date=100)
        yield app
        db.drop_all()

    os.environ.pop('DATABASE', None)
    os.environ.pop('TEST_DATABASE_URL', None)


def test_get_scan_results_performance(app_with_data):
    """Test get_scan_results performance meets threshold."""
    times = benchmark_get_scan_results(app_with_data, iterations=50)
    avg_ms = statistics.mean(times)
    scan_threshold = 100.0  # ms
    assert avg_ms < scan_threshold, f"get_scan_results() average response time ({avg_ms:.2f} ms) exceeds threshold ({scan_threshold} ms)"


def test_get_stock_details_performance(app_with_data):
    """Test get_stock_details performance meets threshold."""
    times = benchmark_get_stock_details(app_with_data, iterations=50)
    avg_ms = statistics.mean(times)
    stock_threshold = 50.0  # ms
    assert avg_ms < stock_threshold, f"get_stock_details() average response time ({avg_ms:.2f} ms) exceeds threshold ({stock_threshold} ms)"


def run_performance_tests():
    """Run all performance tests for direct execution."""
    # Set environment variables for config loading
    shared_db = 'file:perf_test_db_run?mode=memory&cache=shared&uri=true'
    os.environ['DATABASE'] = shared_db
    os.environ['TEST_DATABASE_URL'] = f'sqlite:///{shared_db}'

    # Create app with test configuration
    app = create_app('testing')
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{shared_db}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        from app.database import init_db_app
        init_db_app()
        db.create_all()
        scan_count, price_log_count = create_test_data(app, num_scan_dates=5, num_tickers_per_date=100)
        print(f"Created {scan_count} scan history records and {price_log_count} price log records")

        print("\nRunning performance tests...")

        # Benchmark get_scan_results
        print("\nBenchmarking get_scan_results()...")
        scan_times = benchmark_get_scan_results(app, iterations=100)
        print(f"  Average: {statistics.mean(scan_times):.2f} ms")
        print(f"  Median:  {statistics.median(scan_times):.2f} ms")
        print(f"  Min:     {min(scan_times):.2f} ms")
        print(f"  Max:     {max(scan_times):.2f} ms")
        print(f"  StdDev:  {statistics.stdev(scan_times) if len(scan_times) > 1 else 0:.2f} ms")

        # Benchmark get_stock_details
        print("\nBenchmarking get_stock_details()...")
        stock_times = benchmark_get_stock_details(app, iterations=100)
        print(f"  Average: {statistics.mean(stock_times):.2f} ms")
        print(f"  Median:  {statistics.median(stock_times):.2f} ms")
        print(f"  Min:     {min(stock_times):.2f} ms")
        print(f"  Max:     {max(stock_times):.2f} ms")
        print(f"  StdDev:  {statistics.stdev(stock_times) if len(stock_times) > 1 else 0:.2f} ms")

        # Benchmark different limits
        print("\nBenchmarking get_scan_results() with different limits...")
        limit_results = benchmark_get_scan_results_different_limits(app)
        for limit, stats in limit_results.items():
            print(f"  Limit {limit:3d}: Avg={stats['avg']:6.2f} ms, Median={stats['median']:6.2f} ms")

        # Performance thresholds checking
        scan_avg = statistics.mean(scan_times)
        stock_avg = statistics.mean(stock_times)
        scan_threshold = 100.0  # ms
        stock_threshold = 50.0   # ms

        print("\n" + "="*60)
        print("PERFORMANCE ANALYSIS")
        print("="*60)
        if scan_avg > scan_threshold:
            print(f"[WARNING] get_scan_results() exceeds threshold of {scan_threshold} ms ({scan_avg:.2f} ms)")
        else:
            print(f"[OK] get_scan_results() within threshold of {scan_threshold} ms ({scan_avg:.2f} ms)")

        if stock_avg > stock_threshold:
            print(f"[WARNING] get_stock_details() exceeds threshold of {stock_threshold} ms ({stock_avg:.2f} ms)")
        else:
            print(f"[OK] get_stock_details() within threshold of {stock_threshold} ms ({stock_avg:.2f} ms)")

        db.drop_all()

    os.environ.pop('DATABASE', None)
    os.environ.pop('TEST_DATABASE_URL', None)


if __name__ == '__main__':
    run_performance_tests()