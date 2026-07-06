import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    dhan_client_id: str
    dhan_access_token: str
    nifty_fut_security_id: str
    sl_method: str
    db_path: str
    fast_ema_period: int
    slow_ema_period: int
    atr_multiplier: float
    risk_reward: float


def load_settings() -> Settings:
    return Settings(
        dhan_client_id=os.environ.get("DHAN_CLIENT_ID", ""),
        dhan_access_token=os.environ.get("DHAN_ACCESS_TOKEN", ""),
        nifty_fut_security_id=os.environ.get("NIFTY_FUT_SECURITY_ID", ""),
        sl_method=os.environ.get("SL_METHOD", "atr"),
        db_path=os.environ.get("DB_PATH", "signals.db"),
        fast_ema_period=int(os.environ.get("FAST_EMA_PERIOD", "9")),
        slow_ema_period=int(os.environ.get("SLOW_EMA_PERIOD", "21")),
        atr_multiplier=float(os.environ.get("ATR_MULTIPLIER", "1.5")),
        risk_reward=float(os.environ.get("RISK_REWARD", "3.0")),
    )
