import sys
from pathlib import Path
from time import time

from loguru import logger

logger.debug("Importing piltover.tl...")

start_time = time()
import piltover.tl

logger.debug(f"Importing tl piltover.tl module took {time() - start_time:.2f} seconds.")
del start_time
