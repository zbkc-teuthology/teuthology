"""
Sleep task
"""
import logging
import time

log = logging.getLogger(__name__)


def task(ctx, config):
    """
    Sleep for some number of seconds.

    Example::


       tasks:
       - install:
       - zbkc:
       - sleep:
           duration: 10
       - interactive:

    :param ctx: Context
    :param config: Configuration
    """
    if not config:
        config = {}
    assert isinstance(config, dict)
    duration = int(config.get('duration', 5))
    log.info('Sleeping for %d', duration)
    time.sleep(duration)
