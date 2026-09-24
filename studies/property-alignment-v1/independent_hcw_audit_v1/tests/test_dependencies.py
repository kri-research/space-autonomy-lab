"""Static import inspection is complemented by actual source-isolated execution."""

import ast
import sys
import unittest
from independent_hcw_audit_v1.protocol import ROOT, source_inventory


class DependencyTests(unittest.TestCase):
    def test_no_original_numerical_or_third_party_import(self):
        paths = list(ROOT.rglob("*.py")) + [ROOT / "reference_inputs/independent_hcw_check.py.txt"]
        for path in paths:
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [x.name for x in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    self.assertTrue(
                        top in sys.stdlib_module_names or top == "independent_hcw_audit_v1",
                        (path.name, name),
                    )

    def test_full_numerical_dependency_inventory_present(self):
        files = source_inventory()
        for name in (
            "arithmetic.py",
            "hcw.py",
            "schema.py",
            "certificates.py",
            "reader.py",
            "jobs.py",
            "runner.py",
            "worker.py",
            "protocol.py",
            "contract.json",
            "DERIVATION.md",
            "calibration_plan.json",
        ):
            self.assertIn(name, files)

    def test_literal_reader_has_no_dynamic_code_execution(self):
        tree = ast.parse((ROOT / "reader.py").read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, ("eval", "exec", "compile", "__import__"))


if __name__ == "__main__":
    unittest.main()
