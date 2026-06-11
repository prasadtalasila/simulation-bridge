"""Tests for the synthetic performance-log generator."""

import csv

import generate_performance_data as gen


def test_build_profiles_cover_all_agents():
    """All three agents are described with the expected engine labels."""

    profiles = gen.build_profiles()
    assert set(profiles) == {"base", "python", "matlab"}
    assert profiles["matlab"].engine_label == "MATLAB"
    assert profiles["python"].engine_label == "Python"
    assert profiles["base"].engine_label == "ENGINE"


def test_matlab_overheads_match_paper(tmp_path):
    """MATLAB streaming/batch overheads reproduce the published figures."""

    profile = gen.build_profiles()["matlab"]
    path = gen.generate_log(profile, tmp_path, gen.DEFAULT_SEED)

    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    by_id = {row["Operation ID"]: row for row in rows}
    assert "batch" in by_id
    assert "streaming_10ms" in by_id

    # Overhead = total - startup - simulation, in milliseconds.
    def overhead_ms(row):
        total = float(row["Total Duration (s)"])
        startup = float(row["MATLAB Startup Duration (s)"])
        sim = float(row["Simulation Duration (s)"])
        return (total - startup - sim) * 1000.0

    # Values are jittered, so check they land close to the paper means.
    assert abs(overhead_ms(by_id["batch"]) - 2.7) < 1.0
    assert abs(overhead_ms(by_id["streaming_70ms"]) - 5.6) < 1.5


def test_base_agent_has_no_engine_time(tmp_path):
    """The base agent records zero startup and simulation durations."""

    profile = gen.build_profiles()["base"]
    path = gen.generate_log(profile, tmp_path, gen.DEFAULT_SEED)

    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    assert rows
    for row in rows:
        assert float(row["ENGINE Startup Duration (s)"]) == 0.0
        assert float(row["Simulation Duration (s)"]) == 0.0
        assert float(row["Total Duration (s)"]) > 0.0


def test_generate_is_deterministic(tmp_path):
    """The same seed yields identical logs across runs."""

    profile = gen.build_profiles()["python"]
    first = gen.generate_log(profile, tmp_path / "a", gen.DEFAULT_SEED)
    second = gen.generate_log(profile, tmp_path / "b", gen.DEFAULT_SEED)
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_generate_all_writes_three_logs(tmp_path):
    """generate_all writes one log per agent with the full header schema."""

    paths = gen.generate_all(tmp_path, gen.DEFAULT_SEED)
    assert len(paths) == 3
    for path in paths:
        assert path.exists()
        with open(path, newline="", encoding="utf-8") as handle:
            header = next(csv.reader(handle))
        assert "Operation ID" in header
        assert "Total Duration (s)" in header
