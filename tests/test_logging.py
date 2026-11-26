# -*- coding: utf-8 -*-
"""Tests for the logging of the districtgenerator (setup_logging, NullHandler and worker processes)."""

import logging
import multiprocessing as mp
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from concurrent.futures import ProcessPoolExecutor

from districtgenerator import setup_logging
from districtgenerator import set_progress
from districtgenerator.utilities.log import (PACKAGE_LOGGER, current_log_files, progress_bar, progress_enabled,
                                             progress_level, use_log_dir, worker_logging)


def _log_in_worker(i):
    """Runs in a worker process."""
    logging.getLogger("districtgenerator.tests.worker").info("message from worker %s", i)
    logging.getLogger("districtgenerator.tests.worker").debug("debug from worker %s", i)
    return i


def _reset_logging():
    for name in (PACKAGE_LOGGER, "py.warnings"):
        logger = logging.getLogger(name)
        for handler in list(logger.handlers):
            if not isinstance(handler, logging.NullHandler):
                logger.removeHandler(handler)
                handler.close()
        logger.propagate = True
    logging.getLogger(PACKAGE_LOGGER).setLevel(logging.NOTSET)
    logging.captureWarnings(False)
    set_progress(False)


class TestLogging(unittest.TestCase):

    def tearDown(self):
        _reset_logging()

    def test_silent_without_setup(self):
        """As a library, the package prints nothing unless logging is set up"""
        code = ("import logging, districtgenerator; "
                "logging.getLogger('districtgenerator.x').warning('should not be printed')")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(out.stdout + out.stderr, "")

    def test_log_file_and_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "sub", "run.log")
            setup_logging(level="WARNING", log_file=log_file, console=False)
            logger = logging.getLogger("districtgenerator.tests")
            logger.info("not in file")
            logger.warning("in file")
            warnings.warn("captured warning")
            # A second call replaces the handlers instead of adding more
            setup_logging(level="INFO", log_file=log_file, console=False)
            logger.info("info in file")
            self.assertEqual(len(logging.getLogger(PACKAGE_LOGGER).handlers), 2)  # NullHandler + file
            _reset_logging()
            with open(log_file, encoding="utf-8") as f:
                content = f.read()
        self.assertNotIn("not in file", content)
        self.assertIn("in file", content)
        self.assertIn("captured warning", content)
        self.assertEqual(content.count("info in file"), 1)

    def test_default_log_file_moves_to_result_folder(self):
        """Without log_file, the file gets a time stamp and is created only at the first message"""
        with tempfile.TemporaryDirectory() as tmp:
            setup_logging(level="INFO", console=False)
            default_file = current_log_files()[0]
            self.assertTrue(os.path.basename(default_file).startswith("districtgenerator_"))
            use_log_dir(os.path.join(tmp, "results", "logs"))
            log_file = current_log_files()[0]
            self.assertEqual(os.path.dirname(log_file), os.path.join(tmp, "results", "logs"))
            self.assertFalse(os.path.exists(default_file))
            logging.getLogger("districtgenerator.tests").info("into the result folder")
            _reset_logging()
            with open(log_file, encoding="utf-8") as f:
                self.assertIn("into the result folder", f.read())

    def test_explicit_log_file_is_not_moved(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "my.log")
            setup_logging(level="INFO", log_file=log_file, console=False)
            use_log_dir(os.path.join(tmp, "elsewhere"))
            self.assertEqual(current_log_files(), [log_file])
            _reset_logging()

    def test_console_format(self):
        """Console: time without milliseconds, short logger name, level, colored"""
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            setup_logging(level="INFO", log_file=False, color=True)
        logging.getLogger("districtgenerator.buildings.profiles.demand_generation").warning("hello")
        _reset_logging()
        line = buffer.getvalue()
        self.assertRegex(line, r"^\x1b\[33m\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - demand_generation - WARNING - hello")

    def test_progress_bars(self):
        """Bars only with setup_logging (or set_progress); then the messages per step move to DEBUG"""
        self.assertFalse(progress_enabled())
        self.assertEqual(progress_level(), logging.INFO)
        with progress_bar(total=2, desc="Test", unit="step") as bar:
            bar.update(2)
        self.assertTrue(bar.disable)

        setup_logging(level="INFO", log_file=False)
        self.assertTrue(progress_enabled())
        self.assertEqual(progress_level(), logging.DEBUG)
        setup_logging(level="INFO", log_file=False, progress=False)
        self.assertFalse(progress_enabled())
        setup_logging(level="INFO", log_file=False, console=False)
        self.assertFalse(progress_enabled())  # no bar without console output

    def test_worker_processes(self):
        """Messages of worker processes end up in the log file of the main process"""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "run.log")
            setup_logging(level="INFO", log_file=log_file, console=False)
            mp_ctx = mp.get_context("spawn")
            with worker_logging(mp_ctx) as (initializer, initargs):
                with ProcessPoolExecutor(max_workers=2, mp_context=mp_ctx,
                                         initializer=initializer, initargs=initargs) as ex:
                    self.assertEqual(sorted(ex.map(_log_in_worker, range(4))), [0, 1, 2, 3])
            _reset_logging()
            with open(log_file, encoding="utf-8") as f:
                content = f.read()
        for i in range(4):
            self.assertIn(f"message from worker {i}", content)
        self.assertNotIn("debug from worker", content)  # the level of the main process applies

    def test_log_settings_in_config(self):
        """DG_LOG_LEVEL and DG_LOG_FILE are read from a .env.CONFIG file; empty or None means not set"""
        from districtgenerator.config.settings import Scenario
        with tempfile.TemporaryDirectory() as tmp:
            env_file = os.path.join(tmp, ".env.CONFIG.LOGTEST")
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("DG_LOG_LEVEL=debug\nDG_LOG_FILE=None\n")
            scenario = Scenario(_env_file=env_file)
            self.assertEqual(scenario.dg_log_level, "DEBUG")
            self.assertIsNone(scenario.dg_log_file)
            with open(env_file, "w", encoding="utf-8") as f:
                f.write("DG_LOG_LEVEL=LOUD\n")
            with self.assertRaises(ValueError):
                Scenario(_env_file=env_file)


if __name__ == '__main__':
    unittest.main()
