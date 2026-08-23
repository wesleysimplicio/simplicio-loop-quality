import unittest

from simplicio_loop_quality.native_adapters import normalize_native_report, plan_native_adapter


class NativeAdapterTest(unittest.TestCase):
    def test_cmake_c_and_cpp_sanitizers_are_discovered(self):
        plan = plan_native_adapter(["CMakeLists.txt", "src/main.c", "src/lib.cpp"])
        self.assertEqual(plan.status, "PLANNED")
        self.assertEqual(plan.languages, ("c", "cpp"))
        self.assertIn("address", plan.sanitizers)

    def test_missing_build_file_blocks(self):
        self.assertEqual(plan_native_adapter(["main.cpp"]).status, "BLOCKED")

    def test_sanitizer_diagnostic_fails_closed(self):
        self.assertEqual(normalize_native_report({"status": "FAIL", "sanitizer": "address"})["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
