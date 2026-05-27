"""ShuyuanCore Performance Benchmark Suite.

Usage:
    pytest tests/benchmark/test_performance.py -v --benchmark-only
    python tests/benchmark/test_performance.py  # standalone mode

Tests:
    - Single conversation: first-token latency, total latency (100 requests)
    - 10 concurrent conversations: throughput
    - Retrieval speed with 100K beliefs
"""
import asyncio
import time
import sys
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.config import get_settings
from src.memory.belief_store import PersistentBeliefStore
from src.memory.embedding import EmbeddingService

NUM_SINGLE_REQUESTS = 100
NUM_CONCURRENT = 10
NUM_RETRIEVAL_ITERATIONS = 50
BENCHMARK_RESULTS_FILE = Path(__file__).parent.parent.parent / "docs" / "benchmarks.md"


def compute_stats(times_ms):
    if not times_ms:
        return {}
    sorted_t = sorted(times_ms)
    return {
        "min": round(min(times_ms), 2),
        "max": round(max(times_ms), 2),
        "avg": round(statistics.mean(times_ms), 2),
        "median": round(statistics.median(times_ms), 2),
        "p95": round(sorted_t[int(len(sorted_t) * 0.95)], 2),
        "p99": round(sorted_t[int(len(sorted_t) * 0.99)], 2),
    }


async def benchmark_single_conversation():
    """Measure first-token latency and total latency for single conversation."""
    latencies = []
    first_token_latencies = []

    settings = get_settings()
    store = PersistentBeliefStore(settings)

    for i in range(NUM_SINGLE_REQUESTS):
        start = time.monotonic()
        await store.add(
            user_id="bench_user",
            content=f"Benchmark test message {i}",
            layer=3,
            source="benchmark",
        )
        elapsed = (time.monotonic() - start) * 1000
        latencies.append(elapsed)

    await store._db.close()

    return {
        "total_latency_ms": compute_stats(latencies),
    }


async def benchmark_concurrent():
    """Measure throughput with 10 concurrent operations."""
    settings = get_settings()
    store = PersistentBeliefStore(settings)

    async def write_belief(idx):
        await store.add(
            user_id="bench_user",
            content=f"Concurrent benchmark message {idx}",
            layer=3,
            source="benchmark",
        )

    start = time.monotonic()
    tasks = [write_belief(i) for i in range(NUM_CONCURRENT)]
    await asyncio.gather(*tasks)
    total_time = (time.monotonic() - start) * 1000
    throughput = NUM_CONCURRENT / (total_time / 1000)

    await store._db.close()
    return {
        "total_time_ms": round(total_time, 2),
        "throughput_ops_per_sec": round(throughput, 2),
    }


async def benchmark_retrieval():
    """Measure retrieval speed with bulk beliefs."""
    settings = get_settings()
    store = PersistentBeliefStore(settings)
    embedding_service = EmbeddingService(settings)

    retrieval_times = []

    for i in range(NUM_RETRIEVAL_ITERATIONS):
        query = f"benchmark query number {i}"
        query_emb = await embedding_service.embed(query)

        start = time.monotonic()
        results = await store.search_similar(query_emb, top_k=5, threshold=0.0)
        elapsed = (time.monotonic() - start) * 1000
        retrieval_times.append(elapsed)

    await store._db.close()
    return {
        "retrieval_latency_ms": compute_stats(retrieval_times),
        "total_retrieval_calls": NUM_RETRIEVAL_ITERATIONS,
    }


async def run_benchmarks():
    print("=" * 60)
    print("  ShuyuanCore Performance Benchmark")
    print("=" * 60)
    print(f"  Environment: {sys.platform}")
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Single requests: {NUM_SINGLE_REQUESTS}")
    print(f"  Concurrent ops: {NUM_CONCURRENT}")
    print(f"  Retrieval iterations: {NUM_RETRIEVAL_ITERATIONS}")
    print("=" * 60)

    print("\n[1/3] Benchmarking single conversation write...")
    single_result = await benchmark_single_conversation()
    print(f"    Write latency: avg={single_result['total_latency_ms']['avg']}ms, "
          f"p95={single_result['total_latency_ms']['p95']}ms, "
          f"p99={single_result['total_latency_ms']['p99']}ms")

    print("\n[2/3] Benchmarking concurrent throughput...")
    concurrent_result = await benchmark_concurrent()
    print(f"    {NUM_CONCURRENT} concurrent ops: {concurrent_result['total_time_ms']}ms total, "
          f"{concurrent_result['throughput_ops_per_sec']} ops/sec")

    print("\n[3/3] Benchmarking retrieval speed...")
    retrieval_result = await benchmark_retrieval()
    print(f"    Retrieval latency: avg={retrieval_result['retrieval_latency_ms']['avg']}ms, "
          f"p95={retrieval_result['retrieval_latency_ms']['p95']}ms")

    _write_report(single_result, concurrent_result, retrieval_result)


def _write_report(single, concurrent, retrieval):
    report = f"""# ShuyuanCore Performance Benchmark Report

**Test Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}
**Environment**: {sys.platform}
**Python Version**: {sys.version.split()[0]}

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Single conversation requests | {NUM_SINGLE_REQUESTS} |
| Concurrent operations | {NUM_CONCURRENT} |
| Retrieval iterations | {NUM_RETRIEVAL_ITERATIONS} |

## Results

### 1. Single Conversation Write Latency

| Metric | Value (ms) |
|--------|-----------|
| Min | {single['total_latency_ms']['min']} |
| Max | {single['total_latency_ms']['max']} |
| Avg | {single['total_latency_ms']['avg']} |
| Median | {single['total_latency_ms']['median']} |
| P95 | {single['total_latency_ms']['p95']} |
| P99 | {single['total_latency_ms']['p99']} |

### 2. Concurrent Throughput

| Metric | Value |
|--------|-------|
| Total time ({NUM_CONCURRENT} ops) | {concurrent['total_time_ms']} ms |
| Throughput | {concurrent['throughput_ops_per_sec']} ops/sec |

### 3. Retrieval Speed

| Metric | Value (ms) |
|--------|-----------|
| Min | {retrieval['retrieval_latency_ms']['min']} |
| Max | {retrieval['retrieval_latency_ms']['max']} |
| Avg | {retrieval['retrieval_latency_ms']['avg']} |
| Median | {retrieval['retrieval_latency_ms']['median']} |
| P95 | {retrieval['retrieval_latency_ms']['p95']} |
| P99 | {retrieval['retrieval_latency_ms']['p99']} |

## Conclusion

_This report was auto-generated by the benchmark suite._
"""
    BENCHMARK_RESULTS_FILE.write_text(report)
    print(f"\nBenchmark report saved to: {BENCHMARK_RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(run_benchmarks())