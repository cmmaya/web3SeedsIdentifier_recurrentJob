# models.py
"""
Models for the project data structures.

This file contains Pydantic models that represent the structure of our data.
These models help with type checking and data validation, even though
we're using Firebase/Firestore as our database.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class EthGlobalWinner(BaseModel):
    title: str
    description: str
    link: str
    fetched_at: datetime


class DevpostWinner(BaseModel):
    """Model for a Devpost winner project."""
    title: str
    link: str
    hackathon: Optional[str] = None
    fetched_at: datetime

class GitcoinCheckerProject(BaseModel):
    """Model for a project from checker.gitcoin.co."""
    name: str
    description: Optional[str] = ""
    project_url: str
    website: Optional[str] = ""
    twitter: Optional[str] = ""
    github: Optional[str] = ""
    image_url: Optional[str] = ""
    created_at_text: Optional[str] = ""
    fetched_at: datetime

class AllianceDAOWinner(BaseModel):
    """Model for an Alliance DAO winner project."""
    title: str
    link: str
    hackathon: Optional[str] = None
    fetched_at: datetime

class AllianceCompany(BaseModel):
    """Model for a company from Alliance.xyz."""
    name: str
    link: str
    description: Optional[str] = None
    categories: Optional[List[str]] = None
    fetched_at: datetime

class CrunchbaseOrg(BaseModel):
    """Model for a Crunchbase organization."""
    name: str
    permalink: Optional[str] = None
    website: Optional[str] = None
    description: Optional[str] = None
    fetched_at: datetime

class Project(BaseModel):
    """Unified model for projects from various sources."""
    id: str
    name: str
    link: str
    source: str
    description: Optional[str] = None
    categories: Optional[List[str]] = None
    hackathon: Optional[str] = None
    score: int = 0
    last_seen: datetime = Field(default_factory=datetime.utcnow)
