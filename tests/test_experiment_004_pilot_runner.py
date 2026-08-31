from dataclasses import replace

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004_pilot.config import load_case_matrix, load_pilot_config
from kri_space_autonomy.experiment_004_pilot.runner import run_block, run_episode
from kri_space_autonomy.experiment_004_pilot.seeds import PilotStreams
from kri_space_autonomy.experiment_004_pilot.seeds import (
    test_fixture_scenario as make_test_fixture_scenario,
)


def inputs():
    return (
        load_pilot_config("experiments/004-pilot/config.json"),
        load_config("experiments/004/config.json"),
        load_case_matrix("experiments/004-pilot/case-matrix.json"),
    )


def short_streams(streams):
    return PilotStreams(
        streams.process_acceleration_mps2[:4],
        streams.primary_measurement_noise[:2],
        streams.monitor_measurement_noise[:2],
        streams.actuator_uncertainty_mps2[:1],
    )


def test_forced_collision_block_is_complete_and_byte_deterministic_on_fixture_partition():
    pilot, foundation, cases = inputs()
    case = next(item for item in cases if item.id == "P01_forced_collision")
    scenario, _ = make_test_fixture_scenario(pilot, foundation, case, 0)
    first = run_block(pilot, foundation, case, scenario)
    replay = run_block(pilot, foundation, case, scenario)
    assert len(first) == 2
    assert [row.to_dict() for row in first] == [row.to_dict() for row in replay]
    assert all(row.physical_collision and row.physical_keep_out_entry for row in first)
    assert {row.run_order for row in first} == {1, 2}
    assert {row.configuration_id for row in first} == set(pilot.configuration_ids)
    assert all(row.root_seed_id.startswith("experiment004:941:") for row in first)


def test_primary_monitor_shared_logic_actuation_and_disturbance_activate_separately():
    pilot, foundation, cases = inputs()
    checks = {
        "P04_primary_navigation_bias": "primary",
        "P06_monitor_navigation_bias": "monitor",
        "P07_monitor_logic_false_trip": "logic",
        "P08_shared_navigation_bias": "shared",
        "P09_actuation_degradation": "actuation",
        "P10_disturbance_burst": "disturbance",
    }
    for case_id, expected in checks.items():
        case = next(item for item in cases if item.id == case_id)
        scenario, streams = make_test_fixture_scenario(pilot, foundation, case, 0)
        scenario = replace(scenario, horizon_s=1.0, fault_onset_s=0.0, fault_end_s=2.0)
        configuration = "independent_monitor_gate"
        order = scenario.configuration_run_order.index(configuration) + 1
        row = run_episode(
            pilot,
            foundation,
            case,
            scenario,
            short_streams(streams),
            configuration,
            order,
        )
        if expected == "primary":
            assert row.primary_fault_active_packets == 1
            assert row.monitor_fault_active_packets == 0
            assert row.primary_estimator_fault and not row.monitor_estimator_fault
        elif expected == "monitor":
            assert row.primary_fault_active_packets == 0
            assert row.monitor_fault_active_packets == 1
            assert row.monitor_estimator_fault and not row.primary_estimator_fault
        elif expected == "logic":
            assert row.monitor_logic_active_commands == 1
            assert row.monitor_logic_fault
        elif expected == "shared":
            assert row.primary_fault_active_packets == 1
            assert row.monitor_fault_active_packets == 1
            assert row.shared_cause_fault
            assert not row.primary_estimator_fault and not row.monitor_estimator_fault
        elif expected == "actuation":
            assert row.actuation_degradation_active_commands == 1
            assert row.actuation_degradation_scheduled
            assert not row.disturbance_scheduled
        else:
            assert row.disturbance_active_substeps == 4
            assert row.disturbance_scheduled
            assert not row.actuation_degradation_scheduled


def test_runner_rows_keep_physical_and_technical_domains_separate():
    pilot, foundation, cases = inputs()
    case = next(item for item in cases if item.id == "P03_forced_corridor_departure")
    scenario, _ = make_test_fixture_scenario(pilot, foundation, case, 1)
    rows = run_block(pilot, foundation, case, scenario)
    assert all(row.physical_corridor_departure for row in rows)
    assert all(not row.physical_collision and not row.physical_keep_out_entry for row in rows)
    assert all(
        not row.primary_estimator_fault
        and not row.monitor_estimator_fault
        and not row.monitor_logic_fault
        and not row.shared_cause_fault
        for row in rows
    )
