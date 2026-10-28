import argparse
import json

from sqlalchemy.engine import make_url

from app.config import get_settings


def inspect_database_url(value: str) -> dict[str, object]:
    try:
        parsed = make_url(value)
        if parsed.drivername not in {
            "postgresql",
            "postgresql+psycopg",
            "sqlite",
            "sqlite+pysqlite",
        }:
            return {"valid": False, "issue": "Unsupported database scheme."}
        if parsed.drivername.startswith("postgres") and (
            not parsed.host or not parsed.database
        ):
            return {"valid": False, "issue": "PostgreSQL URL is missing host or database."}
        return {
            "valid": True,
            "driver": parsed.drivername,
            "host_present": bool(parsed.host),
            "database_present": bool(parsed.database),
            "password_present": parsed.password is not None,
            "password_requires_url_encoding": bool(
                parsed.password
                and any(character in parsed.password for character in "@:/?#%")
            ),
        }
    except Exception:
        return {
            "valid": False,
            "issue": "DATABASE_URL is not a valid SQLAlchemy database URL.",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate DATABASE_URL format without connecting.")
    parser.parse_args()
    result = inspect_database_url(get_settings().database_url.get_secret_value())
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
