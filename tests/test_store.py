import pandas as pd

from stock_13f_screener.parquet_store import TableStore


def test_append_upsert(tmp_path) -> None:
    store = TableStore(tmp_path, "demo")
    one = pd.DataFrame([{"id": 1, "value": "a"}, {"id": 2, "value": "b"}])
    two = pd.DataFrame([{"id": 2, "value": "c"}])
    store.append_upsert(one, keys=["id"])
    out = store.append_upsert(two, keys=["id"])
    assert len(out) == 2
    assert out.loc[out["id"].eq(2), "value"].item() == "c"
