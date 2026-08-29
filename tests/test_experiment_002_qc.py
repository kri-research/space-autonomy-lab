import inspect

from kri_space_autonomy.experiment_002 import evaluator
from kri_space_autonomy.experiment_002.config import load_config
from kri_space_autonomy.experiment_002.qc import numerical_integration_check


def test_evaluator_module_does_not_import_runtime_gate():
    source = inspect.getsource(evaluator)
    assert "from .monitor" not in source
    assert "import monitor" not in source


def test_numerical_integration_check_is_fixed_command_and_separate():
    result = numerical_integration_check(load_config("experiments/002/config.json"))
    assert result["command_times_changed"] is False
    assert result["passed"], result
