#!/usr/bin/env python3
"""
LoCoMo Benchmark: Compare ShuyuanCore-style, Mem0-style, and Letta-style memory systems.

All three systems are implemented directly in this script without importing from the
ShuyuanCore src/ package (which has pipeline issues with database and API).
"""

import json
import csv
import time
import argparse
import logging
import asyncio
import sys
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from openai import AsyncOpenAI

DEEPSEEK_API_KEY = "sk-53f60b31a0134e5b9cb096d4c584ceb0"
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"

DATASET_PATH = "/workspace/locomo_data/data/locomo10.json"
OUTPUT_DIR = Path("/workspace/reports/locomo_benchmark")

MAX_RETRIES = 3
BASE_DELAY = 1.0
CONCURRENCY = 30

CATEGORY_NAMES = {
    1: "single-session",
    2: "multi-session",
    3: "reasoning",
    4: "temporal",
    5: None,
}


def setup_logging():
    logger = logging.getLogger("locomo_benchmark")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


logger = setup_logging()


def load_dataset(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def extract_conversation_lines(conv_block: dict):
    """
    Extract all dialogue lines from a LoCoMo conversation block.
    
    The conversation has session_1 through session_35. Sessions that only have
    *_date_time keys but no dialogue list are skipped.
    """
    lines = []
    for i in range(1, 36):
        session_key = f"session_{i}"
        session_list = conv_block.get(session_key)
        if session_list is not None and isinstance(session_list, list):
            for turn in session_list:
                text = turn.get("text", "")
                speaker = turn.get("speaker", "unknown")
                lines.append(f"[{speaker}]: {text}")
    return lines


def prepare_benchmark_items(data):
    """
    Parse all items from the dataset. Each item is one conversation with its QA pairs.
    Returns list of (sample_id, conversation_lines, qa_pairs_info) tuples.
    Only keeps QA pairs with category 1-4 (skips category 5).
    """
    items = []
    for entry in data:
        sample_id = entry.get("sample_id", "unknown")
        conv_block = entry.get("conversation", {})
        conv_lines = extract_conversation_lines(conv_block)

        qa_pairs = []
        for qa in entry.get("qa", []):
            cat = qa.get("category", 0)
            if cat == 5:
                continue
            qa_pairs.append({
                "question": qa["question"],
                "answer": qa["answer"],
                "category": cat,
                "evidence": qa.get("evidence", []),
            })

        if conv_lines and qa_pairs:
            items.append((sample_id, conv_lines, qa_pairs))

    return items


async def deepseek_chat(client: AsyncOpenAI, messages: list, task_name: str = "") -> str:
    """Call DeepSeek API with retry logic and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=1024,
            )
            content = response.choices[0].message.content
            return content if content else ""
        except Exception as e:
            delay = BASE_DELAY * (2 ** attempt)
            if attempt < MAX_RETRIES - 1:
                logger.warning(f"{task_name}: attempt {attempt + 1} failed ({e}), retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"{task_name}: all {MAX_RETRIES} attempts failed: {e}")
                return "[ERROR]"


# ---------------------------------------------------------------------------
# Memory System 1: ShuyuanCore-style (belief store + reader pipeline)
# ---------------------------------------------------------------------------
class ShuyuanCoreMemory:
    """
    Simulates ShuyuanCore's belief store approach:
    - Splits conversation into chunks and stores them in a dict.
    - When answering, constructs a prompt with ALL stored context.
    """
    def __init__(self):
        self.chunks = {}
        self.chunk_size = 20
        self.name = "ShuyuanCore"

    def feed(self, conv_lines: list):
        self.chunks.clear()
        for i in range(0, len(conv_lines), self.chunk_size):
            chunk_id = f"chunk_{i // self.chunk_size}"
            chunk_text = "\n".join(conv_lines[i:i + self.chunk_size])
            self.chunks[chunk_id] = chunk_text

    def build_answer_prompt(self, question: str) -> list:
        context_parts = []
        for cid, ctext in sorted(self.chunks.items()):
            context_parts.append(f"[{cid}]\n{ctext}")
        context = "\n\n".join(context_parts)

        system = (
            "You are a memory system that answers questions based on a conversation history. "
            "Read the entire conversation below and answer the user's question accurately. "
            "If the information is not in the conversation, say so. Be concise."
        )
        user = (
            f"CONVERSATION HISTORY:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            f"Answer the question based ONLY on the conversation history above."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


# ---------------------------------------------------------------------------
# Memory System 2: Mem0-style (keyword-matching retrieval)
# ---------------------------------------------------------------------------
class Mem0Memory:
    """
    Simulates Mem0's memory.add() + memory.search() approach:
    - Stores each conversation line individually.
    - Uses keyword overlap to retrieve the most relevant lines.
    - Constructs answer prompt with retrieved context only.
    """
    def __init__(self, top_k=20):
        self.lines = []
        self.top_k = top_k
        self.name = "Mem0"

    def feed(self, conv_lines: list):
        self.lines = list(conv_lines)

    def _keyword_score(self, query: str, line: str) -> float:
        query_words = set(query.lower().split())
        line_words = set(line.lower().split())
        if not query_words:
            return 0.0
        overlap = query_words & line_words
        return len(overlap) / len(query_words)

    def retrieve(self, question: str) -> list:
        scored = []
        for i, line in enumerate(self.lines):
            score = self._keyword_score(question, line)
            scored.append((score, i, line))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:self.top_k]
        top.sort(key=lambda x: x[1])
        return [line for _, _, line in top]

    def build_answer_prompt(self, question: str) -> list:
        retrieved = self.retrieve(question)
        context = "\n".join(retrieved)

        system = (
            "You are a memory system that answers questions based on retrieved "
            "conversation snippets. Read the retrieved context below and answer "
            "the user's question accurately. If the information is not in the "
            "context, say so. Be concise."
        )
        user = (
            f"RETRIEVED CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            f"Answer the question based ONLY on the retrieved context above."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


# ---------------------------------------------------------------------------
# Memory System 3: Letta-style (session + reflection / summarization)
# ---------------------------------------------------------------------------
class LettaMemory:
    """
    Simulates Letta's session + reflection approach:
    - Summarizes the entire conversation into a compressed memory block.
    - Stores only the summary.
    - Answers questions using only the summary.
    """
    def __init__(self):
        self.summary = ""
        self.name = "Letta"

    async def summarize(self, client: AsyncOpenAI, conv_lines: list) -> str:
        full_text = "\n".join(conv_lines)
        system = (
            "You are a memory compression system. Read the conversation below "
            "and produce a detailed, structured summary. Preserve all facts, dates, "
            "names, events, relationships, and key details. Organize by topic and "
            "chronology. This summary will be the ONLY source of information for "
            "answering future questions."
        )
        user = (
            f"CONVERSATION:\n{full_text}\n\n"
            f"Write a comprehensive structured summary of this conversation."
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        result = await deepseek_chat(client, messages, "letta-summarize")
        return result

    def feed(self, summary: str):
        self.summary = summary

    def build_answer_prompt(self, question: str) -> list:
        system = (
            "You are a memory system that answers questions based on a summary "
            "of a conversation. Read the summary below and answer the user's "
            "question accurately. If the information is not in the summary, say so. "
            "Be concise."
        )
        user = (
            f"CONVERSATION SUMMARY:\n{self.summary}\n\n"
            f"QUESTION: {question}\n\n"
            f"Answer the question based ONLY on the summary above."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


# ---------------------------------------------------------------------------
# LLM Judge
# ---------------------------------------------------------------------------
async def judge_answer(client: AsyncOpenAI, question: str, correct_answer,
                       predicted_answer: str) -> dict:
    """
    Use DeepSeek as LLM judge to score the predicted answer against the
    correct answer on a scale of 1-10.
    """
    system = (
        "You are an impartial judge evaluating answer quality. "
        "Compare the predicted answer to the correct answer. "
        "Consider factual correctness, completeness, and relevance. "
        "Score from 1 (completely wrong) to 10 (exactly correct). "
        "Output ONLY a JSON with fields: score (integer 1-10), "
        "and reason (brief one-sentence explanation)."
    )
    user = (
        f"QUESTION: {question}\n"
        f"CORRECT ANSWER: {correct_answer}\n"
        f"PREDICTED ANSWER: {predicted_answer}\n\n"
        f"Evaluate and output JSON."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    response = await deepseek_chat(client, messages, "judge")
    try:
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1]
            if response.endswith("```"):
                response = response[:-3]
        result = json.loads(response)
        score = int(result.get("score", 1))
        reason = result.get("reason", "")
        return {"score": max(1, min(10, score)), "reason": reason}
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse judge response: {e}, raw: {response[:200]}")
        return {"score": 1, "reason": "parse error"}


# ---------------------------------------------------------------------------
# Main benchmark logic
# ---------------------------------------------------------------------------
async def run_single_answer(client, memory, qa_info, sem):
    """Run a single QA: build prompt, call model, judge."""
    async with sem:
        messages = memory.build_answer_prompt(qa_info["question"])
        predicted = await deepseek_chat(client, messages, "answer")
        judge_result = await judge_answer(
            client, qa_info["question"], qa_info["answer"], predicted
        )
        return {
            "question": qa_info["question"],
            "correct_answer": qa_info["answer"],
            "predicted_answer": predicted,
            "category": qa_info["category"],
            "score": judge_result["score"],
            "judge_reason": judge_result["reason"],
        }


async def run_letta_summarize(client, memory, conv_lines):
    """Summarize conversation for Letta-style memory."""
    summary = await memory.summarize(client, conv_lines)
    memory.feed(summary)


async def benchmark_system(client, memory, items, sem, desc: str) -> list:
    """Run a single memory system against all benchmark items."""
    all_results = []

    for sample_id, conv_lines, qa_pairs in tqdm(items, desc=f"  Processing conversations"):
        memory.feed(conv_lines)

        tasks = []
        for qa in qa_pairs:
            tasks.append(run_single_answer(client, memory, qa, sem))

        conv_results = await asyncio.gather(*tasks)
        for r in conv_results:
            r["sample_id"] = sample_id
            r["system"] = memory.name
        all_results.extend(conv_results)

    return all_results


async def benchmark_letta(client, items, sem) -> list:
    """Run Letta-style benchmark (needs async summarization per conversation)."""
    all_results = []

    for sample_id, conv_lines, qa_pairs in tqdm(items, desc="  Processing conversations (Letta)"):
        memory = LettaMemory()
        summary = await memory.summarize(client, conv_lines)
        memory.feed(summary)

        tasks = []
        for qa in qa_pairs:
            tasks.append(run_single_answer(client, memory, qa, sem))

        conv_results = await asyncio.gather(*tasks)
        for r in conv_results:
            r["sample_id"] = sample_id
            r["system"] = memory.name
        all_results.extend(conv_results)

    return all_results


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------
def generate_charts(results: list, output_dir: Path):
    """Generate bar chart and radar chart from benchmark results."""
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results)

    sns.set_style("whitegrid")
    sns.set_palette("muted")

    # --- Bar chart: average score per system per category ---
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # Overall bar chart
    ax = axes[0]
    overall = df.groupby("system")["score"].agg(["mean", "std"]).reset_index()
    bars = ax.bar(overall["system"], overall["mean"], yerr=overall["std"],
                  capsize=8, color=sns.color_palette("muted")[:3], edgecolor="white")
    ax.set_ylabel("Average Score (1-10)")
    ax.set_title("Overall Score by Memory System")
    ax.set_ylim(0, 11)
    for bar, val in zip(bars, overall["mean"]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                f"{val:.2f}", ha="center", fontweight="bold")

    # Per-category bar chart
    ax = axes[1]
    pivot = df.pivot_table(values="score", index="system", columns="category",
                           aggfunc="mean")
    pivot.columns = [CATEGORY_NAMES.get(c, f"cat-{c}") for c in pivot.columns]
    pivot.plot(kind="bar", ax=ax, edgecolor="white")
    ax.set_ylabel("Average Score (1-10)")
    ax.set_title("Score by Category and System")
    ax.set_ylim(0, 11)
    ax.legend(title="Category", fontsize=8)
    ax.tick_params(axis="x", rotation=0)

    plt.tight_layout()
    bar_path = output_dir / "bar_chart.png"
    fig.savefig(bar_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Bar chart saved to {bar_path}")

    # --- Radar chart ---
    categories = sorted(df["category"].unique())
    cat_labels = [CATEGORY_NAMES.get(c, f"cat-{c}") for c in categories]
    systems = sorted(df["system"].unique())
    num_vars = len(categories)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
    colors = sns.color_palette("muted", len(systems))

    for idx, sys_name in enumerate(systems):
        sys_df = df[df["system"] == sys_name]
        means = []
        for cat in categories:
            cat_df = sys_df[sys_df["category"] == cat]
            means.append(cat_df["score"].mean() if len(cat_df) > 0 else 0)
        values = means + means[:1]
        ax.fill(angles, values, alpha=0.15, color=colors[idx])
        ax.plot(angles, values, "o-", linewidth=2, label=sys_name, color=colors[idx])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(cat_labels, fontsize=10)
    ax.set_ylim(0, 10)
    ax.set_yticks([2, 4, 6, 8, 10])
    ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=8)
    ax.set_title("Radar Chart: Score by Category", fontsize=14, pad=25)
    ax.legend(loc="upper right", bbox_to_anchor=(1.2, 1.1))

    radar_path = output_dir / "radar_chart.png"
    fig.savefig(radar_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Radar chart saved to {radar_path}")


def generate_csv(results: list, output_dir: Path):
    """Save detailed results to CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "results.csv"
    df = pd.DataFrame(results)
    cols = ["system", "sample_id", "category", "question", "correct_answer",
            "predicted_answer", "score", "judge_reason"]
    df = df[[c for c in cols if c in df.columns]]
    df.to_csv(csv_path, index=False)
    logger.info(f"CSV results saved to {csv_path}")

    # Summary CSV
    summary_path = output_dir / "summary.csv"
    summary_rows = []
    for sys_name in sorted(df["system"].unique()):
        sys_df = df[df["system"] == sys_name]
        for cat in sorted(df["category"].unique()):
            cat_df = sys_df[sys_df["category"] == cat]
            summary_rows.append({
                "system": sys_name,
                "category": CATEGORY_NAMES.get(cat, f"cat-{cat}"),
                "count": len(cat_df),
                "mean_score": round(cat_df["score"].mean(), 3),
                "std_score": round(cat_df["score"].std(), 3),
                "median_score": round(cat_df["score"].median(), 3),
            })
        summary_rows.append({
            "system": sys_name,
            "category": "ALL",
            "count": len(sys_df),
            "mean_score": round(sys_df["score"].mean(), 3),
            "std_score": round(sys_df["score"].std(), 3),
            "median_score": round(sys_df["score"].median(), 3),
        })

    with open(summary_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["system", "category", "count",
                                                "mean_score", "std_score", "median_score"])
        writer.writeheader()
        writer.writerows(summary_rows)
    logger.info(f"Summary CSV saved to {summary_path}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
async def main(args):
    logger.info("=" * 60)
    logger.info("LoCoMo Memory Benchmark")
    logger.info("=" * 60)

    logger.info(f"Loading dataset from {DATASET_PATH}")
    data = load_dataset(DATASET_PATH)
    logger.info(f"Loaded {len(data)} conversations")

    items = prepare_benchmark_items(data)
    total_qa = sum(len(qa) for _, _, qa in items)
    logger.info(f"Prepared {len(items)} conversations, {total_qa} QA pairs (excluding category 5)")

    if args.limit > 0 and args.limit < total_qa:
        logger.info(f"Limiting to {args.limit} QA pairs")
        limited_items = []
        count = 0
        for sid, conv_lines, qa_pairs in items:
            if count >= args.limit:
                break
            take = min(len(qa_pairs), args.limit - count)
            limited_items.append((sid, conv_lines, qa_pairs[:take]))
            count += take
        items = limited_items
        logger.info(f"Limited to {len(items)} conversations, {count} QA pairs")

    client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    sem = asyncio.Semaphore(CONCURRENCY)

    systems_to_run = args.systems
    if systems_to_run == "all":
        systems_to_run = "shuyuan,mem0,letta"
    systems_list = [s.strip() for s in systems_to_run.split(",")]

    all_results = []

    for sys_name in systems_list:
        logger.info(f"\n{'=' * 40}")
        if sys_name == "shuyuan":
            logger.info("Benchmarking ShuyuanCore-style system (belief store)")
            memory = ShuyuanCoreMemory()
            results = await benchmark_system(client, memory, items, sem, "ShuyuanCore")
            all_results.extend(results)
        elif sys_name == "mem0":
            logger.info("Benchmarking Mem0-style system (keyword retrieval)")
            memory = Mem0Memory(top_k=20)
            results = await benchmark_system(client, memory, items, sem, "Mem0")
            all_results.extend(results)
        elif sys_name == "letta":
            logger.info("Benchmarking Letta-style system (summarization)")
            results = await benchmark_letta(client, items, sem)
            all_results.extend(results)
        else:
            logger.warning(f"Unknown system '{sys_name}', skipping")

    logger.info(f"\n{'=' * 60}")
    logger.info("Benchmark complete. Generating outputs...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_csv(all_results, OUTPUT_DIR)
    generate_charts(all_results, OUTPUT_DIR)

    # Print summary to console
    df = pd.DataFrame(all_results)
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)
    for sys_name in sorted(df["system"].unique()):
        sys_df = df[df["system"] == sys_name]
        mean_score = sys_df["score"].mean()
        print(f"  {sys_name}: mean={mean_score:.3f}, n={len(sys_df)}")

    print(f"\nOutputs saved to {OUTPUT_DIR}")
    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LoCoMo Memory Benchmark")
    parser.add_argument(
        "--limit", type=int, default=50,
        help="Max QA pairs to evaluate (-1 for all, default: 50)"
    )
    parser.add_argument(
        "--systems", type=str, default="all",
        help="Systems to benchmark: shuyuan,mem0,letta or 'all' (comma-separated)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=30,
        help="Max concurrent API calls (default: 30)"
    )
    args = parser.parse_args()
    CONCURRENCY = args.concurrency
    asyncio.run(main(args))