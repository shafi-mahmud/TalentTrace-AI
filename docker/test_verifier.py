"""Regression for Windows-to-Linux password pipes and sanitized CLI failures."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('verify', Path(__file__).with_name('verify.py'))
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerifierTests(unittest.TestCase):
    def test_operator_input_is_bytes_without_windows_newline_translation(self):
        synthetic = 'fictional account\nfictional password\n'
        with patch.object(verify.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=b'created\n', stderr=b'')) as process:
            self.assertEqual(verify.run(['docker', 'synthetic-test'], stdin=synthetic), 'created\n')
            self.assertEqual(process.call_args.kwargs['input'], synthetic.encode('utf-8'))
            self.assertNotIn('text', process.call_args.kwargs)

    def test_subprocess_failure_never_discloses_private_output(self):
        with patch.object(verify.subprocess, 'run', return_value=SimpleNamespace(
                returncode=1, stdout=b'private output sentinel', stderr=b'private error sentinel')):
            with self.assertRaises(RuntimeError) as error:
                verify.run(['docker', 'synthetic-test'])
        self.assertNotIn('sentinel', str(error.exception))


if __name__ == '__main__':
    unittest.main()
