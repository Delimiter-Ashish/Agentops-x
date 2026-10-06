import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    database_url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://aopx:aopx@127.0.0.1:55432/agentops")
    api_key = os.environ.get("AGENTOPS_API_KEY") or None   # if set, ingestion requires X-AgentOps-Key
    root_path = os.environ.get("ROOT_PATH", "")            # when served behind a path-prefix proxy
    # Self-hosted models are priced by GPU time, amortized over concurrent requests (batching).
    self_hosted_models = [m.strip().lower() for m in os.environ.get("SELF_HOSTED_MODELS", "").split(",") if m.strip()]
    gpu_hourly_usd = float(os.environ.get("GPU_HOURLY_USD", "2.00"))   # on-demand cloud price of the GPU


settings = Settings()
