from __future__ import annotations

import argparse

from backend.app.operations.demo_seed import default_operations_demo_db_path, seed_operations_demo_store


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a local Operations Center demo SQLite store.")
    parser.add_argument(
        "--db-path",
        default=str(default_operations_demo_db_path()),
        help="Local SQLite path to seed. Defaults to the OS temp demo database.",
    )
    args = parser.parse_args()

    result = seed_operations_demo_store(args.db_path)
    print(f"Seeded Operations Center demo store: {result.db_path}")
    print(f"Demo account: {result.account_id}")
    print(f"Demo deployment: {result.deployment_id}")
    print("Start the backend with:")
    print("  SEED_OPERATIONS_DEMO=1")
    print(f"  OPERATIONS_RUNTIME_DB_PATH={result.db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
