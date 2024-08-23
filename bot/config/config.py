from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    WAKE_UP: int = 8

    MIN_AVAILABLE_ENERGY: int = 200
    SLEEP_BY_MIN_ENERGY: list[int] = [1800, 3600]

    AUTO_UPGRADE: bool = False
    MAX_LEVEL: int = 20
    MAX_PRICE: int = 50_000_000

    BUY_RATIO: float = 0.00007

    BALANCE_TO_SAVE: int = 1_000_000
    UPGRADES_COUNT: int = 7

    MAX_COMBO_PRICE: int = 10000000

    APPLY_COMBO: bool = True

    APPLY_PROMO_CODES: bool = True
    PER_ENTERED_KEYS: int = 100

    APPLY_DAILY_CIPHER: bool = True
    APPLY_DAILY_REWARD: bool = True
    APPLY_DAILY_ENERGY: bool = True
    APPLY_DAILY_MINI_GAME: bool = True
    
    AUTO_BUY_SKINS: bool = False
    MAX_PRICE_SKIN: int = 1_000_000

    USE_RANDOM_MINI_GAME_KEY: bool = True

    AUTO_COMPLETE_TASKS: bool = True

    USE_TAPS: bool = True
    RANDOM_TAPS_COUNT: list[int] = [10, 50]
    SLEEP_BETWEEN_TAP: list[int] = [10, 25]

    USE_RANDOM_DELAY_IN_RUN: bool = False
    RANDOM_DELAY_IN_RUN: list[int] = [0, 15]

    USE_RANDOM_USERAGENT: bool = False


settings = Settings()
