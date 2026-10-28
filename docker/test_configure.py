"""Offline reviewer configuration: no Docker, credentials or provider calls."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

spec = importlib.util.spec_from_file_location('configure', Path(__file__).with_name('configure.py'))
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)


class ConfigurationTests(unittest.TestCase):
    def test_independent_private_profiles_never_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root/'data/one.env', root/'data/two.env'
            configure.create_configuration(root, first, 5188)
            before = first.read_bytes()
            with self.assertRaises(FileExistsError):
                configure.create_configuration(root, first, 5280)
            self.assertEqual(first.read_bytes(), before)
            configure.create_configuration(root, second, 5296)
            self.assertNotEqual(first.read_bytes(), second.read_bytes())
            self.assertRegex(second.read_text(), r'^TALENTTRACE_DB_PASSWORD=[0-9a-f]{64}\nTALENTTRACE_HTTP_PORT=5296\n$')

    def test_invalid_destination_or_port_writes_nothing(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for target, port in [(root/'outside.env', 5188), (root/'data/private.txt', 5188), (root/'data/demo.env', 0)]:
                with self.assertRaises(ValueError):
                    configure.create_configuration(root, target, port)
                self.assertFalse(target.exists())
