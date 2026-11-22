"""M09 listener proof: loopback only, released on stop, no thread survives."""
import json
import os
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "scripts", "listener_check.py")


class ListenerCheckTests(unittest.TestCase):
    def run_check(self):
        result = subprocess.run([sys.executable, SCRIPT, "--json"], capture_output=True,
                                text=True, timeout=120)
        return result.returncode, json.loads(result.stdout), result.stderr

    def test_the_only_surface_is_loopback_and_it_is_released(self):
        code, payload, err = self.run_check()
        self.assertEqual(0, code, err)
        self.assertTrue(payload["bound_is_loopback"], payload)
        self.assertEqual("loopback", payload["bound_address_class"])
        self.assertTrue(payload["public_bind_refused"])
        self.assertTrue(payload["port_released_after_stop"])
        self.assertTrue(payload["no_thread_survives_stop"])
        self.assertTrue(payload["ok"])
        # the report never carries a host inventory or a path
        self.assertNotIn("/home", json.dumps(payload))


if __name__ == "__main__":
    unittest.main()
