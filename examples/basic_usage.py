#!/usr/bin/env python3
"""Basic usage example for Ananta."""

from pathlib import Path

from ananta import Ananta


def main() -> None:
    """Demonstrate basic Ananta usage."""
    # Initialize Ananta
    ananta = Ananta(
        model="claude-sonnet-4-20250514",
        storage_path="./example_data",
    )

    # Create a project
    project = ananta.create_project("demo")

    # Upload some documents
    docs_dir = Path(__file__).parent / "sample_docs"
    if docs_dir.exists():
        uploaded = project.upload(docs_dir, recursive=True)
        print(f"Uploaded {len(uploaded)} documents: {uploaded}")
    else:
        print("No sample_docs directory found. Create some documents to query.")
        return

    # Query the documents
    result = project.query("What are the main topics discussed in these documents?")

    # Print the answer
    print("=" * 60)
    print("ANSWER:")
    print("=" * 60)
    print(result.answer)

    # Print execution stats
    print()
    print("=" * 60)
    print("STATS:")
    print("=" * 60)
    print(f"Execution time: {result.execution_time:.2f}s")
    print(f"Total tokens: {result.token_usage.total_tokens}")
    print(f"Trace steps: {len(result.trace.steps)}")

    # Optionally print the trace
    print()
    print("=" * 60)
    print("TRACE:")
    print("=" * 60)
    for step in result.trace.steps:
        print(f"[{step.iteration}] {step.type.value}")
        content_preview = step.content[:200] + "..." if len(step.content) > 200 else step.content
        print(f"    {content_preview}")
        print()


if __name__ == "__main__":
    main()
