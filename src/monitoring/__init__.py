"""
Monitoring package for Palworld server
Simplified to include only metrics collection
"""

from .metrics_collector import get_metrics_collector, MetricsCollector

__all__ = ['get_metrics_collector', 'MetricsCollector']
