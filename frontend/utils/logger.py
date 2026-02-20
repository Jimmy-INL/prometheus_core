import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme


console = Console(theme=Theme({"logging.level.warning": "yellow", "logging.level.info": "blue"}))

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(rich_tracebacks=True, show_time=False, show_path=False, console=console),
    ],
)
logger = logging.getLogger("rich")
logger.setLevel(logging.INFO)
