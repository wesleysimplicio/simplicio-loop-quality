import unittest

from simplicio_loop_quality.install_smoke import build_install_smoke_plan, normalize_install_smoke


class InstallSmokeTest(unittest.TestCase):
    def test_plan_installs_from_the_repository_and_invokes_cli(self):
        plan = build_install_smoke_plan(".")
        self.assertEqual(plan.commands[-1][-2:], ("simplicio_loop_quality", "--help"))

    def test_failed_smoke_is_not_a_pass(self):
        result = normalize_install_smoke(return_code=1, stdout="", stderr="missing dependency")
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
