"""
Начальное заполнение БД данными из config.yaml.
Вызывается при старте приложения до приёма запросов.
"""
import hashlib
import logging
import uuid

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from data.models import Doctor
from data.repository import DoctorRepository

logger = logging.getLogger(__name__)


def _load_config(config_path: str = "config/config.yaml") -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def seed_doctors(session: AsyncSession, config_path: str = "config/config.yaml") -> None:
    """
    Idempotent upsert врачей из config.yaml.
    external_doctor_id_hash = SHA-256 от config-id (НФТ-4/ФЗ-152).
    """
    config = _load_config(config_path)
    doctors_cfg = config.get("doctors", [])
    repo = DoctorRepository(session)
    all_doctors = await repo.get_all()
    existing_hashes = {d.external_doctor_id_hash for d in all_doctors}

    created = 0
    for doc_data in doctors_cfg:
        hash_val = hashlib.sha256(doc_data["id"].encode()).hexdigest()
        if hash_val in existing_hashes:
            continue
        doctor = Doctor(
            id=uuid.uuid4(),
            external_doctor_id_hash=hash_val,
            specializations=doc_data["specializations"],
            productivity_rate=doc_data.get("productivity_rate", 1.0),
            is_available=True,
            current_load=0.0,
        )
        session.add(doctor)
        created += 1

    if created:
        await session.flush()
        logger.info("Seed: создано %d врачей", created)
    else:
        logger.info("Seed: врачи уже загружены, пропуск")
