from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawJob:
    external_id: str
    company: str
    title: str
    url: str
    location: str | None
    remote: bool | None
    salary: str | None
    description: str | None
    department: str | None
    seniority: str | None
    scraped_at: datetime

    @property
    def db_id(self) -> str:
        return f"{self.company}:{self.external_id}"


class BaseScraper(ABC):
    company_name: str

    @abstractmethod
    def fetch_jobs(self) -> list[RawJob]: ...

    def is_job_live(self, url: str) -> bool | None:
        """Check if a job listing URL is still live.
        Returns True (live), False (dead), None (ambiguous/unsupported).
        Subclasses override with ATS-specific logic.
        """
        return None
