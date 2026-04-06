from pathlib import Path
import importlib.util
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class Test15mScriptSupport(unittest.TestCase):
    def _load_module(self, filename: str, module_name: str):
        module_path = REPO_ROOT / filename
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def test_train_model_tf_exists_and_defaults_to_15m_path(self):
        module = self._load_module("train_model_tf.py", "train_model_tf")
        self.assertEqual(
            module.default_model_path("15m"),
            REPO_ROOT / "athena/model/athena_brain_15m.pkl",
        )

    def test_compare_runner_uses_repo_relative_root(self):
        module = self._load_module("run_compare_15m_fast.py", "run_compare_15m_fast")
        self.assertEqual(module.ROOT, REPO_ROOT)
        self.assertTrue((module.ROOT / "athena/model/athena_brain_15m.pkl").exists())


if __name__ == "__main__":
    unittest.main()
