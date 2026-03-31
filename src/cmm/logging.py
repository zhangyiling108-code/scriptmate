from loguru import logger


def configure_logging(verbose=False):
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(lambda msg: print(msg, end=""), level=level)
    return logger
