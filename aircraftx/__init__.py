"""AircraftX — ADS-B / Mode S receiver and aircraft tracker for HackRF."""

__version__ = "1.0.0"
__app_name__ = "AircraftX"

from aircraftx.app.sniffer import AircraftXSniffer
from aircraftx.config import SnifferConfig

__all__ = ["AircraftXSniffer", "SnifferConfig", "__app_name__", "__version__"]
