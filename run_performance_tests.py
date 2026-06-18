#!/usr/bin/env python3
"""
Script to run performance tests for the stock screener application.
"""
import subprocess
import sys
import time

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

def main():
    """Main function to run all tests."""
    print("=" * 60)
    print("STOCK SCREENER PERFORMANCE TEST SUITE")
    print("=" * 60)

    # Check if we're in the right directory
    import os
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

    print("\n" + "=" * 60)
    if success:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("=" * 60)

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)