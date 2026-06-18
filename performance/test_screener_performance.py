"""
Performance tests for ScreenerService.
"""
import time
import statistics
import tempfile
import os
from app import create_app
from app.models import db, ScanHistory, ScanPriceLog
from app.services.screener_service import screener_service


def create_test_data(app, num_records=100):
    """Create test data for performance testing."""
    with app.app_context():
        # Clear existing data
        db.session.query(ScanPriceLog).delete()
        db.session.query(ScanHistory).delete()

        # Create scan history records
        base_date = '2023-01-01'
        scan_dates = [f'2023-01-{i:02d}' for i in range(1, min(32, num_records//10 + 1))]

        scan_history_records = []
        for date in scan_dates:
            scan_history = ScanHistory(date=date, ticker=f'TEST{i}' if i < 10 else 'TEST')
            scan_history_records.append(scan_history)
            db.session.add(scan_history)

        db.session.flush()

        # Create scan price log records
        price_log_records = []
        for i in range(num_records):
            scan_history = scan_history_records[i % len(scan_history_records)]
            price_log = ScanPriceLog(
                date=scan_history.date,
                ticker=scan_history.ticker if hasattr(scan_history, 'ticker') else 'TEST',
                close=100.0 + (i % 50),
                setupLabel=f'Setup {i % 10}'
            )
            price_log_records.append(price_log)
            db.session.add(price_log)

        db.session.commit()
        return len(scan_history_records), len(price_log_records)


def benchmark_get_scan_results(app, iterations=100):
    """Benchmark the get_scan_results method."""
    times = []

    with app.app_context():
        for _ in range(iterations):
            start_time = time.perf_counter()
            result = screener_service.get_scan_results(limit=50)
            end_time = time.perf_counter()
            times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    return times


def benchmark_get_stock_details(app, iterations=100):
    """Benchmark the get_stock_details method."""
    times = []

    with app.app_context():
        # Use a ticker that exists in our test data
        test_ticker = 'TEST'

        for _ in range(iterations):
            start_time = time.perf_counter()
            result = screener_service.get_stock_details(test_ticker)
            end_time = time.perf_counter()
            times.append((end_time - start_time) * 1000)  # Convert to milliseconds

    return times


def run_performance_tests():
    """Run all performance tests."""
    # Create app with test configuration
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        db.create_all()

    print("Creating test data...")
    scan_count, price_log_count = create_test_data(app, num_records=1000)
    print(f"Created {scan_count} scan history records and {price_log_count} price log records")

    print("\nRunning performance tests...")

    # Benchmark get_scan_results
    print("\nBenchmarking get_scan_results()...")
    scan_times = benchmark_get_scan_results(app, iterations=50)
    print(f"  Average: {statistics.mean(scan_times):.2f} ms")
    print(f"  Median:  {statistics.median(scan_times):.2f} ms")
    print(f"  Min:     {min(scan_times):.2f} ms")
    print(f"  Max:     {max(scan_times):.2f} ms")
    print(f"  StdDev:  {statistics.stdev(scan_times) if len(scan_times) > 1 else 0:.2f} ms")

    # Benchmark get_stock_details
    print("\nBenchmarking get_stock_details()...")
    stock_times = benchmark_get_stock_details(app, iterations=50)
    print(f"  Average: {statistics.mean(stock_times):.2f} ms")
    print(f"  Median:  {statistics.median(stock_times):.2f} ms")
    print(f"  Min:     {min(stock_times):.2f} ms")
    print(f"  Max:     {max(stock_times):.2f} ms")
    print(f"  StdDev:  {statistics.stdev(stock_times) if len(stock_times) > 1 else 0:.2f} ms")

    # Performance analysis
    print("\n" + "="*50)
    print("PERFORMANCE ANALYSIS")
    print("="*50)

    scan_avg = statistics.mean(scan_times)
    stock_avg = statistics.mean(stock_times)

    print(f"get_scan_results() average response time: {scan_avg:.2f} ms")
    print(f"get_stock_details() average response time: {stock_avg:.2f} ms")

    # Performance thresholds (adjust based on requirements)
    scan_threshold = 100.0  # ms
    stock_threshold = 50.0   # ms

    if scan_avg > scan_threshold:
        print(f"⚠️  get_scan_results() exceeds threshold of {scan_threshold} ms")
    else:
        print(f"✅ get_scan_results() within threshold of {scan_threshold} ms")

    if stock_avg > stock_threshold:
        print(f"⚠️  get_stock_details() exceeds threshold of {stock_threshold} ms")
    else:
        print(f"✅ get_stock_details() within threshold of {stock_threshold} ms")

    return {
        'get_scan_results': scan_times,
        'get_stock_details': stock_times
    }


if __name__ == '__main__':
    run_performance_tests()