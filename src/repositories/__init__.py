"""
Repositories Package
"""

from .analysis_report_repository import AnalysisReportRepository
from .base_repository import (
    BaseRepository,
    DuplicateEntity,
    EntityNotFound,
    RepositoryError,
    RepositoryException,
)
from .company_repository import CompanyRepository
from .generated_report_repository import GeneratedReportRepository
from .report_job_repository import ReportJobRepository
from .source_material_repository import SourceMaterialRepository

__all__ = [
    # Base Classes
    "BaseRepository",
    # Concrete Repositories
    "CompanyRepository",
    "AnalysisReportRepository",
    "SourceMaterialRepository",
    "GeneratedReportRepository",
    "ReportJobRepository",
    # Exceptions
    "RepositoryException",
    "EntityNotFound",
    "DuplicateEntity",
    "RepositoryError",
]
