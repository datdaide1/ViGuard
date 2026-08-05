"""Deterministic domain-tool to policy-intent mapping."""

from .mapper import (
    DEFAULT_MAPPING_RULES,
    CanonicalAction,
    MappedProposal,
    MappingCoverageReport,
    MappingEvent,
    MappingReadinessError,
    MappingRule,
    ToolMapper,
    UnsupportedToolMappingError,
    build_coverage_report,
    load_default_mapper,
)

__all__ = [
    "DEFAULT_MAPPING_RULES",
    "CanonicalAction",
    "MappedProposal",
    "MappingCoverageReport",
    "MappingEvent",
    "MappingReadinessError",
    "MappingRule",
    "ToolMapper",
    "UnsupportedToolMappingError",
    "build_coverage_report",
    "load_default_mapper",
]
