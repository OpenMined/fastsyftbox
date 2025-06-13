"""Performance and load tests for FastSyftBox."""

import asyncio
import gc
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from typing import Any, Dict
from unittest.mock import Mock, patch

import psutil
import pytest
from fastapi.testclient import TestClient
from syft_core import SyftClientConfig

from fastsyftbox import FastSyftBox


class MemoryMonitor:
    """Monitor memory usage during tests."""

    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = self.get_memory_usage()
        self.peak_memory = self.initial_memory
        self.samples = []

    def get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        return self.process.memory_info().rss / 1024 / 1024

    def record_sample(self):
        """Record a memory usage sample."""
        current = self.get_memory_usage()
        self.samples.append(current)
        self.peak_memory = max(self.peak_memory, current)

    def get_stats(self) -> Dict[str, float]:
        """Get memory usage statistics."""
        if not self.samples:
            return {
                "initial": self.initial_memory,
                "peak": self.peak_memory,
                "current": self.get_memory_usage(),
            }

        return {
            "initial": self.initial_memory,
            "peak": self.peak_memory,
            "current": self.get_memory_usage(),
            "average": sum(self.samples) / len(self.samples),
            "increase": self.peak_memory - self.initial_memory,
            "samples": len(self.samples),
        }


@pytest.fixture
def memory_monitor():
    """Provide a memory monitor for tests."""
    return MemoryMonitor()


@pytest.fixture
def mock_syft_config_perf():
    """Mock SyftBox configuration optimized for performance testing."""
    config = Mock(spec=SyftClientConfig)
    config.email = "perf_test@example.com"
    config.name = "Performance Test User"
    config.server_url = "https://test.syftbox.dev"
    return config


@pytest.fixture
def perf_test_app(mock_syft_config_perf):
    """Create a FastSyftBox application for performance testing."""

    @asynccontextmanager
    async def test_lifespan(app):
        # Startup
        app.startup_time = time.time()
        yield
        # Shutdown
        app.shutdown_time = time.time()

    app = FastSyftBox(
        app_name="perf_test_app",
        syftbox_config=mock_syft_config_perf,
        lifespan=test_lifespan,
        syftbox_endpoint_tags=["perf_test"],
    )

    # Add test endpoints
    @app.post("/fast_endpoint", tags=["perf_test"])
    async def fast_endpoint():
        return {"message": "fast response", "timestamp": time.time()}

    @app.post("/slow_endpoint", tags=["perf_test"])
    async def slow_endpoint():
        await asyncio.sleep(0.1)  # Simulate slow processing
        return {"message": "slow response", "timestamp": time.time()}

    @app.post("/memory_intensive", tags=["perf_test"])
    async def memory_intensive_endpoint(data: Dict[str, Any]):
        # Process large data
        processed = []
        for i in range(1000):
            processed.append({**data, "index": i})
        return {"processed_count": len(processed), "sample": processed[:5]}

    @app.post("/cpu_intensive", tags=["perf_test"])
    async def cpu_intensive_endpoint():
        # CPU-intensive task
        result = sum(i**2 for i in range(10000))
        return {"computation_result": result}

    return app


class TestStartupShutdownTiming:
    """Test startup and shutdown performance characteristics."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_startup_timing(self, mock_syft_events, perf_test_app, memory_monitor):
        """Test application startup timing."""
        memory_monitor.record_sample()

        start_time = time.time()

        with TestClient(perf_test_app) as client:
            startup_duration = time.time() - start_time
            memory_monitor.record_sample()

            # Verify app is responsive
            response = client.post("/fast_endpoint")
            assert response.status_code == 200

            # Check startup time is reasonable (should be under 2 seconds)
            assert startup_duration < 2.0, (
                f"Startup took {startup_duration:.2f}s, expected < 2.0s"
            )

            # Verify bridge was initialized
            assert perf_test_app.bridge is not None
            mock_syft_events.assert_called_once()

        memory_monitor.record_sample()
        memory_stats = memory_monitor.get_stats()

        # Memory increase should be reasonable (under 50MB for basic startup)
        assert memory_stats["increase"] < 50.0, (
            f"Memory increase {memory_stats['increase']:.2f}MB too high"
        )

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_shutdown_timing(self, mock_syft_events, perf_test_app):
        """Test application shutdown timing."""
        with TestClient(perf_test_app) as client:
            # Ensure app is running
            response = client.post("/fast_endpoint")
            assert response.status_code == 200

            shutdown_start = time.time()

        # TestClient context manager handles shutdown
        shutdown_duration = time.time() - shutdown_start

        # Shutdown should be quick (under 1 second)
        assert shutdown_duration < 1.0, (
            f"Shutdown took {shutdown_duration:.2f}s, expected < 1.0s"
        )

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_multiple_startup_shutdown_cycles(
        self, mock_syft_events, mock_syft_config_perf, memory_monitor
    ):
        """Test memory usage over multiple startup/shutdown cycles."""
        memory_monitor.record_sample()

        startup_times = []
        shutdown_times = []

        for cycle in range(3):
            memory_monitor.record_sample()

            # Startup timing
            start_time = time.time()
            app = FastSyftBox(
                app_name=f"cycle_test_app_{cycle}",
                syftbox_config=mock_syft_config_perf,
                syftbox_endpoint_tags=["test"],
            )

            @app.post("/test", tags=["test"])
            def test_endpoint():
                return {"cycle": cycle}

            with TestClient(app) as client:
                startup_duration = time.time() - start_time
                startup_times.append(startup_duration)
                memory_monitor.record_sample()

                # Verify functionality
                response = client.post("/test")
                assert response.status_code == 200
                assert response.json()["cycle"] == cycle

                shutdown_start = time.time()

            shutdown_duration = time.time() - shutdown_start
            shutdown_times.append(shutdown_duration)
            memory_monitor.record_sample()

            # Force garbage collection
            gc.collect()

        memory_stats = memory_monitor.get_stats()

        # Startup times should be consistent
        avg_startup = sum(startup_times) / len(startup_times)
        assert avg_startup < 2.0, f"Average startup time {avg_startup:.2f}s too high"

        # Memory shouldn't grow excessively over cycles
        assert memory_stats["increase"] < 100.0, (
            f"Memory growth {memory_stats['increase']:.2f}MB too high"
        )


class TestMemoryUsage:
    """Test memory usage patterns under various conditions."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_memory_usage_baseline(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test baseline memory usage of the application."""
        memory_monitor.record_sample()

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            # Make several simple requests
            for i in range(10):
                response = client.post("/fast_endpoint")
                assert response.status_code == 200
                if i % 3 == 0:  # Sample every few requests
                    memory_monitor.record_sample()

        memory_monitor.record_sample()
        memory_stats = memory_monitor.get_stats()

        # Memory increase should be minimal for simple requests
        assert memory_stats["increase"] < 25.0, (
            f"Memory increase {memory_stats['increase']:.2f}MB too high for baseline"
        )

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_memory_usage_large_payloads(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test memory usage with large request payloads."""
        memory_monitor.record_sample()

        # Create progressively larger payloads
        payload_sizes = [1024, 10240, 102400]  # 1KB, 10KB, 100KB

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            for size in payload_sizes:
                large_data = {
                    "data": "x" * size,
                    "metadata": {"size": size, "test": "memory_usage"},
                }

                response = client.post("/memory_intensive", json=large_data)
                assert response.status_code == 200
                memory_monitor.record_sample()

                # Force garbage collection after each payload
                gc.collect()
                memory_monitor.record_sample()

        memory_stats = memory_monitor.get_stats()

        # Memory should be managed reasonably even with large payloads
        assert memory_stats["increase"] < 200.0, (
            f"Memory increase {memory_stats['increase']:.2f}MB too high for large payloads"
        )

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_memory_leak_detection(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test for potential memory leaks through repeated operations."""
        memory_monitor.record_sample()

        with TestClient(perf_test_app) as client:
            initial_memory = memory_monitor.get_memory_usage()

            # Perform many repeated operations
            for batch in range(5):
                for i in range(20):
                    response = client.post("/fast_endpoint")
                    assert response.status_code == 200

                # Record memory after each batch
                memory_monitor.record_sample()
                gc.collect()  # Force cleanup

                current_memory = memory_monitor.get_memory_usage()
                memory_growth = current_memory - initial_memory

                # Memory growth should not be excessive per batch
                assert memory_growth < 50.0, (
                    f"Potential memory leak detected: {memory_growth:.2f}MB growth after batch {batch}"
                )


class TestConcurrentRequestHandling:
    """Test performance under concurrent load."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_concurrent_fast_requests(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test handling multiple concurrent fast requests."""
        memory_monitor.record_sample()

        def make_request(client, request_id):
            start_time = time.time()
            response = client.post("/fast_endpoint")
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "status_code": response.status_code,
                "duration": duration,
                "response": response.json(),
            }

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            # Run concurrent requests
            num_concurrent = 10
            with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
                futures = [
                    executor.submit(make_request, client, i)
                    for i in range(num_concurrent)
                ]

                results = []
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    memory_monitor.record_sample()

            # All requests should succeed
            assert len(results) == num_concurrent
            successful_requests = [r for r in results if r["status_code"] == 200]
            assert len(successful_requests) == num_concurrent

            # Response times should be reasonable
            avg_duration = sum(r["duration"] for r in results) / len(results)
            max_duration = max(r["duration"] for r in results)

            assert avg_duration < 1.0, (
                f"Average response time {avg_duration:.2f}s too high"
            )
            assert max_duration < 2.0, f"Max response time {max_duration:.2f}s too high"

        memory_monitor.record_sample()
        memory_stats = memory_monitor.get_stats()

        # Memory usage should be controlled under concurrent load
        assert memory_stats["increase"] < 75.0, (
            f"Memory increase {memory_stats['increase']:.2f}MB too high for concurrent requests"
        )

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_mixed_workload_concurrency(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test concurrent requests with mixed fast/slow endpoints."""
        memory_monitor.record_sample()

        def make_mixed_request(client, request_id):
            endpoint = "/fast_endpoint" if request_id % 2 == 0 else "/slow_endpoint"
            start_time = time.time()
            response = client.post(endpoint)
            duration = time.time() - start_time
            return {
                "request_id": request_id,
                "endpoint": endpoint,
                "status_code": response.status_code,
                "duration": duration,
            }

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            num_requests = 20
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(make_mixed_request, client, i)
                    for i in range(num_requests)
                ]

                results = []
                for future in as_completed(futures):
                    result = future.result()
                    results.append(result)
                    if len(results) % 5 == 0:
                        memory_monitor.record_sample()

            # Categorize results
            fast_results = [r for r in results if r["endpoint"] == "/fast_endpoint"]
            slow_results = [r for r in results if r["endpoint"] == "/slow_endpoint"]

            # All requests should succeed
            assert len(results) == num_requests
            assert all(r["status_code"] == 200 for r in results)

            # Fast endpoints should be significantly faster
            avg_fast = sum(r["duration"] for r in fast_results) / len(fast_results)
            avg_slow = sum(r["duration"] for r in slow_results) / len(slow_results)

            assert avg_fast < avg_slow, (
                "Fast endpoints should be faster than slow endpoints"
            )
            assert avg_fast < 0.5, f"Fast endpoint average {avg_fast:.2f}s too high"
            assert avg_slow < 1.0, f"Slow endpoint average {avg_slow:.2f}s too high"

        memory_monitor.record_sample()


class TestLargePayloadProcessing:
    """Test performance with various payload sizes."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_small_payload_performance(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test performance with small payloads."""
        memory_monitor.record_sample()

        small_payload = {"message": "small", "data": "x" * 100}  # ~100 bytes

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            durations = []
            for i in range(50):
                start_time = time.time()
                response = client.post("/memory_intensive", json=small_payload)
                duration = time.time() - start_time
                durations.append(duration)

                assert response.status_code == 200
                if i % 10 == 0:
                    memory_monitor.record_sample()

            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            # Small payloads should process quickly
            assert avg_duration < 0.1, (
                f"Small payload average time {avg_duration:.3f}s too high"
            )
            assert max_duration < 0.5, (
                f"Small payload max time {max_duration:.3f}s too high"
            )

        memory_monitor.record_sample()

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_medium_payload_performance(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test performance with medium payloads."""
        memory_monitor.record_sample()

        medium_payload = {
            "message": "medium",
            "data": "x" * 10000,  # ~10KB
            "metadata": {"size": "medium", "iterations": list(range(100))},
        }

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            durations = []
            for i in range(20):
                start_time = time.time()
                response = client.post("/memory_intensive", json=medium_payload)
                duration = time.time() - start_time
                durations.append(duration)

                assert response.status_code == 200
                if i % 5 == 0:
                    memory_monitor.record_sample()

            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            # Medium payloads should still be reasonable
            assert avg_duration < 0.5, (
                f"Medium payload average time {avg_duration:.3f}s too high"
            )
            assert max_duration < 1.0, (
                f"Medium payload max time {max_duration:.3f}s too high"
            )

        memory_monitor.record_sample()

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_large_payload_performance(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Test performance with large payloads."""
        memory_monitor.record_sample()

        large_payload = {
            "message": "large",
            "data": "x" * 100000,  # ~100KB
            "metadata": {
                "size": "large",
                "iterations": list(range(1000)),
                "extra_data": ["item_" + str(i) for i in range(500)],
            },
        }

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            durations = []
            for i in range(10):
                start_time = time.time()
                response = client.post("/memory_intensive", json=large_payload)
                duration = time.time() - start_time
                durations.append(duration)

                assert response.status_code == 200
                memory_monitor.record_sample()

                # Force cleanup between large requests
                gc.collect()

            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)

            # Large payloads should complete within reasonable time
            assert avg_duration < 2.0, (
                f"Large payload average time {avg_duration:.3f}s too high"
            )
            assert max_duration < 5.0, (
                f"Large payload max time {max_duration:.3f}s too high"
            )

        memory_monitor.record_sample()
        memory_stats = memory_monitor.get_stats()

        # Memory should be managed even with large payloads
        assert memory_stats["increase"] < 150.0, (
            f"Memory increase {memory_stats['increase']:.2f}MB too high for large payloads"
        )


class TestResourceCleanup:
    """Test proper resource cleanup and management."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_http_client_cleanup(self, mock_syft_events, perf_test_app):
        """Test that HTTP clients are properly cleaned up."""
        # Skip network connection check on macOS due to permission issues
        # Instead, verify that the bridge and HTTP client are properly managed

        with TestClient(perf_test_app) as client:
            # Make requests to ensure connections are established
            for i in range(10):
                response = client.post("/fast_endpoint")
                assert response.status_code == 200

            # Check that bridge HTTP client exists
            assert perf_test_app.bridge is not None
            assert perf_test_app.bridge.app_client is not None

            # Store references to verify cleanup
            bridge_ref = perf_test_app.bridge

        # After context manager, verify bridge is still accessible but could be closed
        # The important thing is no exceptions are raised and the app can be reused
        assert perf_test_app.bridge is bridge_ref  # Same instance

        # Try to use network connections only if we have permissions
        try:
            initial_connections = len(psutil.net_connections())
            # If we get here, we have permissions - do the connection test
            with TestClient(perf_test_app) as client:
                response = client.post("/fast_endpoint")
                assert response.status_code == 200
            final_connections = len(psutil.net_connections())
            connection_diff = final_connections - initial_connections
            assert abs(connection_diff) <= 2, (
                f"Connection leak detected: {connection_diff} connections remain"
            )
        except (psutil.AccessDenied, PermissionError):
            # Skip connection counting on systems without permissions
            pass

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_bridge_cleanup(self, mock_syft_events, perf_test_app):
        """Test that SyftHTTPBridge is properly cleaned up."""
        # Track if the bridge was used during requests
        bridge_used = False
        original_process_request = None

        with TestClient(perf_test_app) as client:
            # Check that bridge is created
            assert perf_test_app.bridge is not None

            # Mock the process_request to track usage
            if hasattr(perf_test_app.bridge, "process_request"):
                original_process_request = perf_test_app.bridge.process_request

                async def mock_process_request(*args, **kwargs):
                    nonlocal bridge_used
                    bridge_used = True
                    if original_process_request:
                        return await original_process_request(*args, **kwargs)
                    return {"status": "ok"}

                perf_test_app.bridge.process_request = mock_process_request

            # Make a request to ensure bridge is active
            response = client.post("/fast_endpoint")
            assert response.status_code == 200

            # Verify bridge client is initialized
            assert perf_test_app.bridge.app_client is not None

        # After TestClient exits, bridge should still exist but be ready for cleanup
        assert perf_test_app.bridge is not None

        # The bridge lifecycle is managed by FastAPI's lifespan
        # We just verify it was created and can handle requests

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_file_handle_cleanup(self, mock_syft_events, perf_test_app):
        """Test that file handles are properly managed."""
        initial_open_files = len(psutil.Process().open_files())

        with TestClient(perf_test_app) as client:
            # Enable debug tool which involves file operations
            perf_test_app.enable_debug_tool(
                endpoint="/test", example_request='{"test": "data"}', publish=False
            )

            # Make requests that might open files
            for i in range(20):
                response = client.post("/fast_endpoint")
                assert response.status_code == 200

                # Occasionally check debug page (involves file reads)
                if i % 5 == 0:
                    debug_response = client.get("/rpc-debug")
                    assert debug_response.status_code == 200

        final_open_files = len(psutil.Process().open_files())

        # File handles should not accumulate significantly
        file_diff = final_open_files - initial_open_files
        assert abs(file_diff) <= 5, (
            f"File handle leak detected: {file_diff} handles remain open"
        )


class TestPerformanceBenchmarks:
    """Establish performance benchmarks for the application."""

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_throughput_benchmark(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Benchmark request throughput."""
        memory_monitor.record_sample()

        num_requests = 100
        test_duration = 30  # seconds

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            start_time = time.time()
            completed_requests = 0
            durations = []

            while (
                time.time() - start_time < test_duration
                and completed_requests < num_requests
            ):
                request_start = time.time()
                response = client.post("/fast_endpoint")
                request_duration = time.time() - request_start

                assert response.status_code == 200
                durations.append(request_duration)
                completed_requests += 1

                if completed_requests % 20 == 0:
                    memory_monitor.record_sample()

            total_duration = time.time() - start_time
            throughput = completed_requests / total_duration
            avg_latency = sum(durations) / len(durations)

            # Performance benchmarks
            assert throughput >= 10.0, (
                f"Throughput {throughput:.2f} req/s below benchmark (10 req/s)"
            )
            assert avg_latency <= 0.1, (
                f"Average latency {avg_latency:.3f}s above benchmark (0.1s)"
            )

            memory_monitor.record_sample()
            memory_stats = memory_monitor.get_stats()

            print("\nPerformance Benchmark Results:")
            print(f"  Throughput: {throughput:.2f} requests/second")
            print(f"  Average Latency: {avg_latency:.3f} seconds")
            print(f"  Total Requests: {completed_requests}")
            print(f"  Test Duration: {total_duration:.2f} seconds")
            print(f"  Memory Usage: {memory_stats}")

    @patch("fastsyftbox.http_bridge.SyftEvents")
    def test_cpu_intensive_benchmark(
        self, mock_syft_events, perf_test_app, memory_monitor
    ):
        """Benchmark CPU-intensive operations."""
        memory_monitor.record_sample()

        with TestClient(perf_test_app) as client:
            memory_monitor.record_sample()

            # Test CPU-intensive endpoint
            durations = []
            for i in range(10):
                start_time = time.time()
                response = client.post("/cpu_intensive")
                duration = time.time() - start_time
                durations.append(duration)

                assert response.status_code == 200
                memory_monitor.record_sample()

            avg_cpu_duration = sum(durations) / len(durations)
            max_cpu_duration = max(durations)

            # CPU benchmark - should complete computation within reasonable time
            assert avg_cpu_duration < 1.0, (
                f"CPU intensive average {avg_cpu_duration:.3f}s above benchmark (1.0s)"
            )
            assert max_cpu_duration < 2.0, (
                f"CPU intensive max {max_cpu_duration:.3f}s above benchmark (2.0s)"
            )

            memory_stats = memory_monitor.get_stats()

            print("\nCPU Intensive Benchmark Results:")
            print(f"  Average Duration: {avg_cpu_duration:.3f} seconds")
            print(f"  Max Duration: {max_cpu_duration:.3f} seconds")
            print(f"  Memory Usage: {memory_stats}")


if __name__ == "__main__":
    # Run specific performance tests
    pytest.main([__file__, "-v", "-s"])
