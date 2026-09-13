from pathlib import Path
from urllib.parse import unquote

import database
import init_data


def get_sqlite_path() -> Path:
    database_url = database.SQLALCHEMY_DATABASE_URL

    if not database_url.startswith("sqlite:///"):
        raise RuntimeError("reset_db.py only supports sqlite database URLs.")

    raw_path = unquote(database_url.replace("sqlite:///", "", 1))
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path

    return db_path.resolve()


def reset_database():
    db_path = get_sqlite_path()
    database.engine.dispose()

    if db_path.exists():
        db_path.unlink()

    database.ensure_schema()
    init_data.seed_materials()
    return db_path


if __name__ == "__main__":
    reset_path = reset_database()
    print(f"Database reset complete: {reset_path}")
