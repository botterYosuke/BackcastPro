import pandas as pd
import pytest

from BackcastPro.api.lib.jquants import (
    _normalize_columns,
    _rename_daily_quote_columns,
    jquants,
)


def _reset_singleton() -> None:
    jquants._instance = None


def test_get_daily_quotes_requires_code() -> None:
    _reset_singleton()
    jq = jquants()
    with pytest.raises(ValueError):
        jq.get_daily_quotes(code="")


def test_get_daily_quotes_adds_suffix_and_normalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_singleton()
    monkeypatch.setenv("JQUANTS_API_KEY", "dummy-key")
    jq = jquants()

    captured = {}

    def fake_get_all_pages(endpoint: str, params: dict) -> list:
        captured["endpoint"] = endpoint
        captured["params"] = params
        return [
            {
                "Date": "2024-01-02",
                "Code": "72030",
                "O": 100,
                "H": 110,
                "L": 90,
                "C": 105,
                "V": 1000,
            }
        ]

    monkeypatch.setattr(jq, "_get_all_pages", fake_get_all_pages)

    df = jq.get_daily_quotes(code="7203", from_=None, to=None)
    assert captured["endpoint"] == "/v2/equities/bars/daily"
    assert captured["params"]["code"] == "72030"
    assert not df.empty
    assert df.loc[0, "Open"] == 100.0
    assert df.loc[0, "Close"] == 105.0
    assert df.loc[0, "Volume"] == 1000.0
    assert df.loc[0, "source"] == "j-quants"
    assert isinstance(df.loc[0, "Date"], pd.Timestamp)


def test_get_listed_info_renames(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_singleton()
    monkeypatch.setenv("JQUANTS_API_KEY", "dummy-key")
    jq = jquants()

    def fake_get_all_pages(endpoint: str, params: dict) -> list:
        return [{"code": "72030", "Name": "Toyota"}]

    monkeypatch.setattr(jq, "_get_all_pages", fake_get_all_pages)
    df = jq.get_listed_info(code="7203")
    assert df.loc[0, "Code"] == "72030"
    assert df.loc[0, "CompanyName"] == "Toyota"
    assert df.loc[0, "source"] == "j-quants"


def test_ensure_api_key_refreshes(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_singleton()
    monkeypatch.delenv("JQUANTS_API_KEY", raising=False)
    jq = jquants()
    assert jq.isEnable is False

    monkeypatch.setenv("JQUANTS_API_KEY", "dummy-key")
    assert jq._ensure_api_key() is True
    assert jq.headers["x-api-key"] == "dummy-key"


def test_normalize_columns_adds_date_from_index() -> None:
    df = pd.DataFrame(
        {"Code": ["72030"], "Open": [100]}, index=pd.to_datetime(["2024-01-02"])
    )
    normalized = _normalize_columns(df)
    assert "Date" in normalized.columns
    assert normalized.iloc[0]["Date"] == pd.Timestamp("2024-01-02")
    assert normalized.iloc[0]["Open"] == 100.0


def test_rename_daily_quote_columns_maps_short_names() -> None:
    df = pd.DataFrame(
        {
            "date": ["2024-01-02"],
            "code": ["72030"],
            "O": [100],
            "H": [110],
            "L": [90],
            "C": [105],
            "Vo": [1000],
            "AdjC": [95],
        }
    )
    renamed = _rename_daily_quote_columns(df)
    assert {
        "Date",
        "Code",
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
        "AdjustmentClose",
    }.issubset(renamed.columns)
