from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


class TableStore:
    """Small local table store.

    ParquetDB is used when compatible. Plain single-file Parquet is always kept as
    a safe/readable fallback. ParquetDB 1.0.1 reserves an ``id`` column, so user
    data with its own ``id`` column must use fallback storage.
    """

    def __init__(self, root_dir: Path, table_name: str) -> None:
        self.root_dir = Path(root_dir)
        self.table_name = table_name
        self.table_dir = self.root_dir / table_name
        self.fallback_path = self.root_dir / f"{table_name}.parquet"
        self._parquetdb: Any | None = self._try_make_parquetdb()

    def read(self) -> pd.DataFrame:
        """Read table as a DataFrame.

        Prefer the single-file Parquet fallback when it exists because it is the
        compatibility surface used by tests, Streamlit, and tools outside
        ParquetDB.
        """
        if self.fallback_path.exists():
            return pd.read_parquet(self.fallback_path)

        pickle_path = self.fallback_path.with_suffix(".pkl")
        if pickle_path.exists():
            return pd.read_pickle(pickle_path)

        if self._parquetdb is not None and self.table_dir.exists():
            try:
                data = self._parquetdb.read()
                if hasattr(data, "to_pandas"):
                    return data.to_pandas()
                if isinstance(data, pd.DataFrame):
                    return data
            except Exception as exc:
                logger.warning("ParquetDB read failed for {}: {!r}", self.table_name, exc)

        return pd.DataFrame()

    def replace(self, data: pd.DataFrame) -> None:
        """Replace whole table atomically where possible."""
        clean = data.reset_index(drop=True).copy()
        self.root_dir.mkdir(parents=True, exist_ok=True)

        wrote_parquetdb = False
        if self._can_use_parquetdb(clean):
            wrote_parquetdb = self._replace_parquetdb(clean)

        self._atomic_parquet_write(clean, self.fallback_path)
        logger.info(
            "Wrote table {} rows={} parquetdb={}",
            self.table_name,
            len(clean),
            wrote_parquetdb,
        )

    def append_upsert(self, data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
        """Append rows, then keep the last row per key.

        Returns the combined table for easy testing and caller diagnostics.
        """
        if not keys:
            raise ValueError("keys must not be empty")

        missing_keys = set(keys) - set(data.columns)
        if missing_keys:
            raise ValueError(f"Missing upsert key columns: {sorted(missing_keys)}")

        existing = self.read()
        if existing.empty:
            combined = data.copy()
        else:
            combined = pd.concat([existing, data], ignore_index=True)

        combined = combined.drop_duplicates(subset=keys, keep="last")
        combined = combined.reset_index(drop=True)
        self.replace(combined)
        return combined

    def _replace_parquetdb(self, data: pd.DataFrame) -> bool:
        if self._parquetdb is None:
            return False

        try:
            if self.table_dir.exists():
                shutil.rmtree(self.table_dir)
            self._parquetdb = self._try_make_parquetdb()
            if self._parquetdb is None:
                return False
            self._parquetdb.create(data)
            return True
        except Exception as exc:
            logger.warning(
                "ParquetDB write failed for {}; using parquet fallback: {!r}",
                self.table_name,
                exc,
            )
            return False

    def _try_make_parquetdb(self) -> Any | None:
        try:
            from parquetdb import ParquetDB  # type: ignore
        except Exception:
            return None

        try:
            return ParquetDB(db_path=str(self.table_dir))
        except Exception as exc:
            logger.warning(
                "ParquetDB unavailable for {}: {!r}; using parquet fallback",
                self.table_name,
                exc,
            )
            return None

    @staticmethod
    def _can_use_parquetdb(data: pd.DataFrame) -> bool:
        # ParquetDB reserves `id`; callers may have a legitimate domain id.
        return "id" not in data.columns

    @staticmethod
    def _atomic_parquet_write(data: pd.DataFrame, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp.parquet")
        try:
            data.to_parquet(tmp_path, index=False)
            tmp_path.replace(path)
        except ImportError:
            # Dev/test fallback only. Runtime install declares pyarrow.
            pickle_path = path.with_suffix(".pkl")
            tmp_pickle = pickle_path.with_suffix(".tmp.pkl")
            data.to_pickle(tmp_pickle)
            tmp_pickle.replace(pickle_path)
