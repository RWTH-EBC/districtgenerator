"""
Logging of the districtgenerator.

Every module logs with its own logger (``logging.getLogger(__name__)``). As a library, the districtgenerator only adds
a ``NullHandler`` to the package logger (see ``districtgenerator/__init__.py``) and does not change the logging setup
of the calling application. Users who just want output call :func:`setup_logging`.

Worker processes of the demand generation do not inherit the handlers of the main process. :func:`worker_logging`
sends their log records through a queue to the main process, where they are handled by the same handlers.

Long loops (demand generation, optimization of the clusters) show a tqdm progress bar if progress bars are enabled
(:func:`setup_logging` does this by default, applications call :func:`set_progress`). With a bar, the messages per
building or cluster are logged on DEBUG instead of INFO, so that the console is not flooded.
"""

import contextlib
import datetime
import logging
import logging.handlers
import os
import sys

from districtgenerator.utilities.paths import RESULTS_DIR

PACKAGE_LOGGER = "districtgenerator"
FILE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
CONSOLE_FORMAT = "%(asctime)s - %(shortname)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
#: Subfolder of the result folder for the default log files.
LOG_SUBFOLDER = "logs"

# Progress bars are off by default, so that the package does not print anything without setup
_progress_enabled = False

# Marks the handlers added by setup_logging, so that a repeated call replaces them instead of adding more
_HANDLER_FLAG = "_districtgenerator_handler"
# Marks the file handler whose file was chosen automatically, so that the Datahandler can move it to its result folder
_DEFAULT_FILE_FLAG = "_districtgenerator_default_file"


class ColorFormatter(logging.Formatter):
    """Console format with the last part of the logger name and a color per level."""

    COLORS = {
        logging.DEBUG: "\033[36m",                  # cyan
        logging.INFO: "\033[32m",                   # green
        logging.WARNING: "\033[33m",                # yellow
        logging.ERROR: "\033[31m",                  # red
        logging.CRITICAL: "\033[41m\033[37m",       # white on red
    }
    RESET = "\033[0m"

    def __init__(self, color=True):
        super().__init__(CONSOLE_FORMAT, datefmt=DATE_FORMAT)
        self.color = color

    def format(self, record):
        # e.g. "districtgenerator.buildings.profiles.demand_generation" -> "demand_generation"
        record.shortname = record.name.rsplit(".", 1)[-1]
        text = super().format(record)
        if self.color and record.levelno in self.COLORS:
            text = self.COLORS[record.levelno] + text + self.RESET
        return text


class TqdmStreamHandler(logging.StreamHandler):
    """Console handler that writes with ``tqdm.write``, so that messages appear above an active progress bar."""

    def emit(self, record):
        try:
            from tqdm import tqdm
            tqdm.write(self.format(record), file=self.stream)
        except Exception:
            self.handleError(record)


def set_progress(enabled=True):
    """
    Enable or disable the progress bars of the districtgenerator.

    :func:`setup_logging` enables them by default. Applications with their own logging setup call this function and
    should route the console output of the logger ``districtgenerator`` through tqdm as well, e.g. with
    ``tqdm.contrib.logging.logging_redirect_tqdm``.
    """
    global _progress_enabled
    _progress_enabled = bool(enabled)


def progress_enabled():
    """Return True if progress bars are shown."""
    return _progress_enabled


def progress_level():
    """Level for messages per step of a loop: DEBUG if a progress bar shows the progress, otherwise INFO."""
    return logging.DEBUG if _progress_enabled else logging.INFO


def progress_bar(total, desc, unit):
    """
    Return a tqdm progress bar, disabled if progress bars are off.

    The bar is written to stdout like the console messages of :func:`setup_logging`. Inside another bar (e.g. of the
    calling application) it is removed when finished.
    """
    from tqdm import tqdm
    return tqdm(total=total, desc=desc, unit=unit, file=sys.stdout, disable=not _progress_enabled,
                leave=None, dynamic_ncols=True)


def _remove_own_handlers(logger):
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            logger.removeHandler(handler)
            handler.close()


def default_log_file(log_dir=None):
    """Return a new log file name with a time stamp, by default in ``RESULTS_DIR/logs``."""
    log_dir = log_dir or os.path.join(RESULTS_DIR, LOG_SUBFOLDER)
    time_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(log_dir, f"districtgenerator_{time_stamp}.log")


class _LazyFileHandler(logging.FileHandler):
    """File handler that creates the folder and the file only when the first message is written."""

    def __init__(self, filename):
        super().__init__(filename, mode="a", encoding="utf-8", delay=True)

    def _open(self):
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        return super()._open()


def setup_logging(level="INFO", log_file=None, console=True, color=None, capture_warnings=True, progress=True):
    """
    Set up console output and a log file for the districtgenerator.

    Only the logger of the districtgenerator is changed, the root logger of the application is not touched.
    Calling the function again replaces the handlers of the previous call.

    Parameters
    ----------
    level : str or int, optional
        Minimum level of the messages, e.g. "DEBUG", "INFO", "WARNING" or "ERROR". Default is "INFO".
    log_file : str or bool, optional
        Path of the log file. Messages are appended, the folder is created if needed.
        None (default): a new file with a time stamp in the ``logs`` folder of the results. The Datahandler moves it
        to the ``logs`` folder of its own result folder, e.g. ``<project_path>/results/logs``.
        False: no log file.
    console : bool, optional
        Print the messages to the console (stdout). Default is True.
    color : bool, optional
        Color the console messages by level. Default is True unless the environment variable NO_COLOR is set.
    capture_warnings : bool, optional
        Route warnings of the ``warnings`` module (e.g. deprecations) into the log as well. Default is True.
    progress : bool, optional
        Show progress bars for the demand generation and the optimization (only with ``console=True``).
        The messages per building and cluster are then logged on DEBUG. Default is True.

    Returns
    -------
    logging.Logger
        The logger of the districtgenerator.
    """
    if isinstance(level, str):
        level = level.strip().upper()
    if color is None:
        color = "NO_COLOR" not in os.environ
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.setLevel(level)
    # The handlers of this function are the output of the package, the root logger would print the messages again
    logger.propagate = False
    _remove_own_handlers(logger)

    handlers = []
    if console:
        handler = TqdmStreamHandler(sys.stdout)
        handler.setFormatter(ColorFormatter(color=color))
        handlers.append(handler)
    if log_file is not False:
        handler = _LazyFileHandler(os.fspath(log_file) if log_file else default_log_file())
        handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
        setattr(handler, _DEFAULT_FILE_FLAG, not log_file)
        handlers.append(handler)
    for handler in handlers:
        setattr(handler, _HANDLER_FLAG, True)
        logger.addHandler(handler)

    # Warnings of the warnings module are logged to "py.warnings", which gets the same handlers
    warnings_logger = logging.getLogger("py.warnings")
    _remove_own_handlers(warnings_logger)
    logging.captureWarnings(capture_warnings)
    if capture_warnings:
        warnings_logger.propagate = False
        for handler in handlers:
            warnings_logger.addHandler(handler)
    else:
        warnings_logger.propagate = True

    set_progress(progress and console)
    return logger


def reset_logging():
    """
    Undo :func:`setup_logging`: remove its handlers, close the log files and turn off the progress bars.

    Log files stay open until this is called or the process ends. On Windows an open file cannot be deleted, so call
    this function before removing the result folder, e.g. a temporary folder in tests.
    """
    for name in (PACKAGE_LOGGER, "py.warnings"):
        logger = logging.getLogger(name)
        _remove_own_handlers(logger)
        logger.propagate = True
    logging.getLogger(PACKAGE_LOGGER).setLevel(logging.NOTSET)
    logging.captureWarnings(False)
    set_progress(False)


def use_log_dir(log_dir):
    """
    Move the default log file of :func:`setup_logging` to ``log_dir``.

    The Datahandler calls this with ``<result folder>/logs``, so that the log ends up next to the results.
    Explicitly given log files and handlers of the application are not changed.
    """
    for handler in logging.getLogger(PACKAGE_LOGGER).handlers:
        if not getattr(handler, _DEFAULT_FILE_FLAG, False):
            continue
        new_file = os.path.join(os.path.abspath(log_dir), os.path.basename(handler.baseFilename))
        if new_file == handler.baseFilename:
            continue
        handler.acquire()
        try:
            # The file is opened again (lazily) at the next message
            handler.close()
            handler.baseFilename = new_file
        finally:
            handler.release()


def current_log_files():
    """Return the paths of the log files set up by :func:`setup_logging`."""
    return [h.baseFilename for h in logging.getLogger(PACKAGE_LOGGER).handlers
            if getattr(h, _HANDLER_FLAG, False) and isinstance(h, logging.FileHandler)]


class _ForwardHandler(logging.Handler):
    """Hand a record from a worker process to the logger of the same name in this process."""

    def handle(self, record):
        logger = logging.getLogger(record.name)
        if not logger.disabled:
            logger.handle(record)
        return True

    def emit(self, record):  # pragma: no cover - handle() is overridden
        pass


def _init_worker(queue, level, capture_warnings):
    """Initializer of worker processes: send all records of the package (and warnings) to the main process."""
    queue_handler = logging.handlers.QueueHandler(queue)
    logger = logging.getLogger(PACKAGE_LOGGER)
    logger.handlers[:] = [queue_handler]
    logger.setLevel(level)
    logger.propagate = False
    if capture_warnings:
        logging.captureWarnings(True)
        warnings_logger = logging.getLogger("py.warnings")
        warnings_logger.handlers[:] = [queue_handler]
        warnings_logger.propagate = False


@contextlib.contextmanager
def worker_logging(mp_context):
    """
    Collect the log records of worker processes in this process.

    Use the returned initializer for the process pool and create the pool inside the ``with`` block, so that the
    pool is shut down before the listener stops::

        with worker_logging(mp_ctx) as (initializer, initargs):
            with ProcessPoolExecutor(mp_context=mp_ctx, initializer=initializer, initargs=initargs) as ex:
                ...

    Parameters
    ----------
    mp_context : multiprocessing context
        Context of the process pool, e.g. ``multiprocessing.get_context("spawn")``.

    Yields
    ------
    tuple
        Initializer function and its arguments for the process pool.
    """
    queue = mp_context.Queue()
    listener = logging.handlers.QueueListener(queue, _ForwardHandler())
    level = logging.getLogger(PACKAGE_LOGGER).getEffectiveLevel()
    capture_warnings = bool(logging.getLogger("py.warnings").handlers)
    listener.start()
    try:
        yield _init_worker, (queue, level, capture_warnings)
    finally:
        listener.stop()
        queue.close()
        queue.join_thread()
