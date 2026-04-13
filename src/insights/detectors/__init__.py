"""Detector exports for automatic insights engine."""

from src.insights.detectors.anomalies import detect_anomalies
from src.insights.detectors.benchmarking import detect_benchmarking_gaps
from src.insights.detectors.correlations import detect_metric_correlations
from src.insights.detectors.opportunities import detect_opportunities
from src.insights.detectors.trends import detect_concerning_trends

__all__ = [
    "detect_anomalies",
    "detect_concerning_trends",
    "detect_benchmarking_gaps",
    "detect_metric_correlations",
    "detect_opportunities",
]

