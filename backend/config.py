import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    dhan_client_id: str
    dhan_access_token: str
    sl_method: str
    db_path: str


def load_settings() -> Settings:
    return Settings(
        dhan_client_id=os.environ.get("DHAN_CLIENT_ID", ""),
        dhan_access_token=os.environ.get("DHAN_ACCESS_TOKEN", ""),
        sl_method=os.environ.get("SL_METHOD", "atr"),
        db_path=os.environ.get("DB_PATH", "signals.db"),
    )
