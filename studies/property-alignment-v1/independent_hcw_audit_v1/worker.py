"""Standard-library-only worker with a recorded runtime dependency check."""

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
PACKAGE = "independent_hcw_audit_v1"


class DependencyBoundary:
    """Deny nonstandard external imports before executing their module body."""

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split(".")[0]
        if (
            top not in sys.stdlib_module_names
            and top not in sys.builtin_module_names
            and top not in (PACKAGE, "__main__")
        ):
            raise ModuleNotFoundError("Independent-auditor dependency boundary: " + fullname)
        return None


def main():
    if not sys.flags.isolated or not sys.flags.no_site:
        raise RuntimeError("Invoke with Python -I -S -B")
    sys.meta_path.insert(0, DependencyBoundary())
    sys.path.insert(0, str(ROOT.parent))
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--job", type=Path)
    modes.add_argument("--calibrate", action="store_true")
    modes.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    started, cpu = time.perf_counter(), time.process_time()
    if args.selftest:
        import unittest

        tests = unittest.defaultTestLoader.discover(
            str(ROOT / "tests"), top_level_dir=str(ROOT.parent)
        )
        run = unittest.TextTestRunner(stream=sys.stderr).run(tests)
        result = {
            "passed": run.wasSuccessful(),
            "tests": run.testsRun,
            "failures": len(run.failures),
            "errors": len(run.errors),
        }
    elif args.calibrate:
        from independent_hcw_audit_v1.calibration import run

        result = run()
    else:
        from independent_hcw_audit_v1.schema import strict_json, require
        from independent_hcw_audit_v1.jobs import execute

        require(args.job is not None, "Explicit job file required")
        doc = strict_json(args.job.read_bytes())
        require(set(doc) == {"job", "settings"}, "Worker input fields")
        result = execute(doc["job"], doc["settings"])
    unexpected = [
        name
        for name in sys.modules
        if name.split(".")[0] not in sys.stdlib_module_names
        and name.split(".")[0] not in sys.builtin_module_names
        and name.split(".")[0] not in (PACKAGE, "__main__")
    ]
    if unexpected:
        raise RuntimeError("Unexpected numerical dependency: " + repr(unexpected))
    result["dependency_trace"] = {
        "modules": sorted(sys.modules),
        "nonstdlib_dependencies": unexpected,
        "isolated_python": True,
        "site_disabled": True,
        "external_imports_blocked_before_execution": True,
        "package_only_export_required_for_isolation_test": True,
        "human_independence_claim": False,
    }
    result["worker_wall_s"] = time.perf_counter() - started
    result["worker_cpu_s"] = time.process_time() - cpu
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if (args.calibrate or args.selftest) and not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
