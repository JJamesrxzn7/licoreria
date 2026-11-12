import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import restablecer_contrasena


class PasswordResetTests(unittest.TestCase):
    def test_postgresql_does_not_prompt_or_connect_to_mariadb(self):
        with patch.dict(os.environ, {"DATABASE_BACKEND": "postgresql"}), \
             patch("builtins.input") as prompt, \
             patch("mysql.connector.connect") as connect, \
             patch("builtins.print") as output:
            self.assertEqual(restablecer_contrasena.main(), 1)
            prompt.assert_not_called()
            connect.assert_not_called()
            self.assertIn("PostgreSQL", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
