"""Pydantic models for OCR document API responses."""

from typing import List, Optional

from pydantic import BaseModel, Field


class OwnershipEntry(BaseModel):
    """One co-owner row on UP Khatauni (खातेदार का विवरण: नाम / पिता; हिस्से में; क्षेत्रफल में हे०)."""

    owner: str = Field("", description="खातेदार name (native script); one row per co-owner when table lists several")
    father: str = Field("", description="पिता (after first /); for minors, father before guardian सं० …")
    share: str = Field("", description='Column हिस्से में fraction, e.g. "1/6" or "1/2"')
    area_ha: str = Field("", description="That row’s share area in hectares (क्षेत्रफल में हे०), not the गाटे का कुल total")


class RegistryOCRResponse(BaseModel):
    """Structured JSON returned after OCR and field parsing."""

    owner: str = Field("", description="Owner / vendee name when detected (native script)")
    owner_display: str = Field(
        "",
        description="Owner for UI: English romanization plus native in parentheses when Hindi",
    )
    father: str = Field("", description="Father's name (S/o) when detected")
    father_display: str = Field(
        "",
        description="Father for UI: English romanization plus native in parentheses when Hindi",
    )
    khasra: str = Field("", description="खसरा/गाटा number (often matches plot digits inside भू-आईडी, e.g. 113)")
    area: str = Field("", description="Total plot area when shown (e.g. गाटे का कुल क्षेत्रफल हे०); per-owner ha are in ownership_entries")
    district: str = Field("", description="जनपद / district when detected (e.g. Khatauni header)")
    tehsil: str = Field("", description="तहसील / tehsil when detected")
    village: str = Field("", description="ग्राम / village when detected")
    khata_number: str = Field("", description="खाता संख्या when detected")
    ownership_entries: List[OwnershipEntry] = Field(
        default_factory=list,
        description="Co-parceners with per-row share and area when parsed from Khatauni",
    )
    date: str = Field("", description="Registry or execution date")
    stamp_id: str = Field("", description="Stamp paper / judicial stamp identifier")
    raw_text: Optional[str] = Field(
        None, description="Full OCR text; only when include_raw_text is requested"
    )

    class Config:
        schema_extra = {
            "example": {
                "owner": "Ramesh Kumar",
                "owner_display": "Ramesh Kumar",
                "father": "Suresh Kumar",
                "father_display": "Suresh Kumar",
                "khasra": "142/1",
                "area": "2 Bigha 5 Biswa",
                "date": "15/03/2023",
                "stamp_id": "RJ-1234567",
                "raw_text": None,
            }
        }
