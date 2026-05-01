from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase  # type: ignore


LAND_COLLECTION_NAME = "land_records"


async def upsert_land_record(
    db: AsyncIOMotorDatabase,
    record: Dict[str, Any],
) -> str:
    """
    Upsert a land record based on (district, village, khasra_number).
    Returns the string id of the record.
    """
    key = {
        "district": record.get("district"),
        "village": record.get("village"),
        "khasra_number": record.get("khasra_number"),
    }

    # Basic safety: don't upsert if key fields missing
    if not key["district"] or not key["village"] or not key["khasra_number"]:
        result = await db[LAND_COLLECTION_NAME].insert_one(record)
        return str(result.inserted_id)

    existing = await db[LAND_COLLECTION_NAME].find_one(key)
    if existing:
        await db[LAND_COLLECTION_NAME].update_one({"_id": existing["_id"]}, {"$set": record})
        return str(existing["_id"])

    result = await db[LAND_COLLECTION_NAME].insert_one(record)
    return str(result.inserted_id)


async def find_land_record(
    db: AsyncIOMotorDatabase,
    district: str,
    village: str,
    khasra_number: str,
) -> Optional[Dict[str, Any]]:
    """Find a single land record by district, village, and khasra_number."""
    return await db[LAND_COLLECTION_NAME].find_one(
        {
            "district": district,
            "village": village,
            "khasra_number": khasra_number,
        }
    )

