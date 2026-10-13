from loguru import logger


def configure_logging(verbose=False, stream=None):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(lambda msg: print(msg, end="", file=stream), level=level)
    return logger
