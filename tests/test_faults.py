from kri_space_autonomy.controllers import LearnedPolicyController
from kri_space_autonomy.faults import SensorDropoutFault, SingleEventUpsetFault
from kri_space_autonomy.types import Observation


def test_sensor_dropout_sets_quality_to_zero():
    fault = SensorDropoutFault(start_step=2, end_step=3)
    obs = Observation(2, 100.0, -0.1, 1.0, 1.0)
    faulted = fault.apply_observation(obs)
    assert faulted.range_m is None
    assert faulted.sensor_quality == 0.0


def test_seu_changes_model_hash_once():
    controller = LearnedPolicyController()
    fault = SingleEventUpsetFault(step=4)
    before = controller.model_hash
    event = fault.apply_model(4, controller)
    assert event is not None
    assert controller.model_hash != before
    assert fault.apply_model(4, controller) is None
