from pathlib import Path


def test_public_benchmark_surface_reflects_completed_experiment_005_programme() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    guide = Path("docs/benchmark-guide.md").read_text(encoding="utf-8")
    roadmap = Path("docs/research-roadmap.md").read_text(encoding="utf-8")
    demo_index = Path("demo/README.md").read_text(encoding="utf-8")

    assert "Experiment 005" in readme
    assert "Valid, reproducible, inconclusive" in readme
    assert "What v0.1 tests" not in readme
    assert "1,068 paired blocks" in guide
    assert "2,136 episodes" in guide
    assert "current experimental series ends at Experiment 005" in roadmap
    assert "Experiments 004 and 005" in demo_index


def test_demo_and_scientific_evidence_boundaries_remain_separate() -> None:
    guide = Path("docs/benchmark-guide.md").read_text(encoding="utf-8")
    demo = Path("docs/public-rpo-demo.md").read_text(encoding="utf-8")

    assert "engineering example, not a scientific result" in guide
    assert "Later programme evidence" in demo
    assert "Do not pool" in guide
