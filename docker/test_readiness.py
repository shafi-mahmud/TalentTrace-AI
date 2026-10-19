"""Offline regression checks for schema readiness; no database/provider calls."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
spec = importlib.util.spec_from_file_location('backend_ready', ROOT / 'docker/backend_ready.py')
ready = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ready)


class ReadinessTests(unittest.TestCase):
    def check_revisions(self, revisions=None, failure=None, http_status=200):
        connection = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = revisions
        connection.execute = AsyncMock(return_value=result, side_effect=failure)
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=connection)
        context.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.connect.return_value = context
        engine.dispose = AsyncMock()
        http = MagicMock()
        http.__enter__.return_value.status = http_status
        with patch.object(ready, 'urlopen', return_value=http), \
             patch.object(ready, 'create_database_engine', return_value=engine), \
             patch.object(ready.ScriptDirectory, 'from_config', return_value=SimpleNamespace(get_current_head=lambda: 'current')):
            try:
                return asyncio.run(ready.ready())
            finally:
                if http_status == 200:
                    engine.dispose.assert_awaited_once()
                else:
                    engine.connect.assert_not_called()

    def test_current_schema_ready(self):
        self.assertTrue(self.check_revisions(['current']))

    def test_old_schema_not_ready(self):
        self.assertFalse(self.check_revisions(['old']))

    def test_empty_revision_not_ready(self):
        self.assertFalse(self.check_revisions([]))

    def test_multiple_heads_not_ready(self):
        self.assertFalse(self.check_revisions(['current', 'competing']))

    def test_database_error_disposes_engine(self):
        with self.assertRaises(RuntimeError):
            self.check_revisions(failure=RuntimeError('synthetic unavailable database'))

    def test_failed_http_does_not_report_ready(self):
        self.assertFalse(self.check_revisions(http_status=503))


if __name__ == '__main__':
    unittest.main()
