from kri_space_autonomy.scenario import load_scenario
from kri_space_autonomy.simulation import run_episode


def test_nominal_protected_controller_completes_approach():
    scenario = load_scenario("scenarios/nominal.json")
    result = run_episode(scenario, "protected")
    assert result.success
    assert not result.collision


def test_sensor_dropout_triggers_intervention():
    scenario = load_scenario("scenarios/sensor-dropout.json")
    result = run_episode(scenario, "protected")
    assert result.interventions > 0
