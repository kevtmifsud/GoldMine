from __future__ import annotations

from app.config.settings import settings
from app.data_access.interfaces import DataAccessProvider

_provider: DataAccessProvider | None = None


def get_data_provider() -> DataAccessProvider:
    global _provider
    if _provider is not None:
        return _provider

    if settings.DATA_PROVIDER == "supabase":
        from app.data_access.supabase_provider import SupabaseDataAccessProvider
        _provider = SupabaseDataAccessProvider()
    elif settings.DATA_PROVIDER == "csv":
        from app.data_access.csv_provider import CsvDataAccessProvider
        _provider = CsvDataAccessProvider()
    else:
        raise ValueError(f"Unknown data provider: {settings.DATA_PROVIDER}")

    return _provider
