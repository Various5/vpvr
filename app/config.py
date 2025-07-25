from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str = "sqlite:///./iptv_pvr.db"
    secret_key: str = "your-secret-key-change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    
    recording_path: str = "./recordings"
    max_concurrent_recordings: int = 4
    
    hdhr_device_id: str = "IPTV-PVR"
    hdhr_device_uuid: str = "12345678-1234-1234-1234-123456789012"
    hdhr_friendly_name: str = "IPTV PVR HDHomeRun"
    hdhr_lineup_url: str = "http://localhost:8000/lineup.json"
    hdhr_port: int = 5004
    server_port: int = 8000  # Main server port
    
    default_m3u_url: str = ""
    default_epg_url: str = ""
    
    credit_cost_1_limit: int = 1
    credit_cost_5_limits: int = 4
    credit_cost_10_limits: int = 8
    
    # Streaming configuration
    require_auth_for_streaming: bool = False  # Set to True to require authentication for stream endpoints
    stream_auth_grace_period: int = 300  # Seconds to allow streaming after token expiration
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()