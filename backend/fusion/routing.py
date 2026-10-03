"""Issue type -> responsible Warsaw department (spec §C5)."""
from __future__ import annotations

from backend.models import Department, IssueType

ROUTING: dict[str, Department] = {
    IssueType.ROAD_DAMAGE: Department.ZDM,  # potholes, pavement damage: Zarząd Dróg Miejskich
    IssueType.STREETLIGHT: Department.ZDM,  # street lighting is run by ZDM (and its contractor)
    IssueType.TRAM_TRACK: Department.TRAMWAJE,
    IssueType.FLOODING: Department.MPWIK,  # flooding, sewers, water mains
    IssueType.WASTE: Department.STRAZ_MIEJSKA,  # litter, illegal dumping, public order
    IssueType.OTHER: Department.OTHER,
}


def department_for(issue_type: str) -> str:
    """Department name (stored verbatim in `incidents.department`); unknown types -> 'inne'."""
    return ROUTING.get(str(issue_type), Department.OTHER).value
