import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://aopx:aopx@127.0.0.1:55432/agentops")
    api_key = os.environ.get("AGENTOPS_API_KEY") or None   # if set, ingestion requires X-AgentOps-Key
    root_path = os.environ.get("ROOT_PATH", "")            # when served behind a path-prefix proxy


settings = Settings()
