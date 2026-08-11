import importlib.util
from pathlib import Path


def _load_validation_module():
    script = Path(__file__).parents[1] / "scripts" / "validation" / "validate_m0a_mapping.py"
    spec = importlib.util.spec_from_file_location("validate_m0a_mapping", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_m0_validation_fails_closed_without_samples():
    module = _load_validation_module()
    assert module.validation_verdict(0, 0) == "FAIL"
    assert module.validation_verdict(20, 0) == "PASS"
    assert module.validation_verdict(20, 1) == "FAIL"
