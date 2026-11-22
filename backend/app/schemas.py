from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["seed", "plant", "tissue_sample"]
Relation = Literal["female_parent", "male_parent", "derived_from"]


class ParentLink(BaseModel):
    parent_id: str
    relation: Relation


class EntityCreate(BaseModel):
    barcode: str = Field(min_length=3, max_length=64, examples=["PT-TS-0042"])
    kind: Kind
    species: str = Field(default="Solanum tuberosum")
    parents: list[ParentLink] = Field(default_factory=list)


class BatchCreate(BaseModel):
    # A plate is 96 wells; allow a few plates per call.
    items: list[EntityCreate] = Field(min_length=1, max_length=384)


class Entity(BaseModel):
    id: str
    barcode: str
    kind: Kind
    species: str
    created_at: datetime
    lab_job_status: str | None = None


class PedigreeNode(BaseModel):
    id: str
    barcode: str
    kind: Kind
    child_id: str
    relation: Relation
    depth: int


class LabJob(BaseModel):
    id: int
    entity_id: str
    barcode: str
    assay: str
    status: str
    created_at: datetime
