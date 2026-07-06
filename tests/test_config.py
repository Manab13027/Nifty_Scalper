from backend.config import load_settings


def test_load_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DHAN_CLIENT_ID", "abc123")
    monkeypatch.setenv("DHAN_ACCESS_TOKEN", "tok456")
    monkeypatch.setenv("SL_METHOD", "swing")
    monkeypatch.setenv("DB_PATH", "test.db")
    settings = load_settings()
    assert settings.dhan_client_id == "abc123"
    assert settings.dhan_access_token == "tok456"
    assert settings.sl_method == "swing"
    assert settings.db_path == "test.db"


def test_load_settings_reads_futures_security_id(monkeypatch):
    monkeypatch.setenv("NIFTY_FUT_SECURITY_ID", "55555")
    settings = load_settings()
    assert settings.nifty_fut_security_id == "55555"


def test_load_settings_reads_strategy_params(monkeypatch):
    monkeypatch.setenv("FAST_EMA_PERIOD", "5")
    monkeypatch.setenv("SLOW_EMA_PERIOD", "13")
    monkeypatch.setenv("ATR_MULTIPLIER", "2.0")
    monkeypatch.setenv("RISK_REWARD", "2.0")
    settings = load_settings()
    assert settings.fast_ema_period == 5
    assert settings.slow_ema_period == 13
    assert settings.atr_multiplier == 2.0
    assert settings.risk_reward == 2.0


def test_load_settings_defaults(monkeypatch):
    monkeypatch.delenv("SL_METHOD", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    settings = load_settings()
    assert settings.sl_method == "atr"
    assert settings.db_path == "signals.db"
