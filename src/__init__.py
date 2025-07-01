"""
Palworld Dedicated Server Management System
Main package initialization
"""

__version__ = "1.0.0"
__author__ = "supersunho"
 
from .config_loader import get_config, PalworldConfig 

__all__ = ['get_config', 'PalworldConfig']
