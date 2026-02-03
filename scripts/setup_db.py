#!/usr/bin/env python
"""
Database setup script.

Creates the 'ecommerce' schema in PostgreSQL and runs migrations.

Usage:
    cd /path/to/ecommerce_recomendator
    python scripts/setup_db.py [--force-recreate]
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def load_env() -> None:
    """Load environment variables from .env file."""
    env_file = project_root / ".env"
    if not env_file.exists():
        return

    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                os.environ.setdefault(key, value)


def create_schema_raw(force_recreate: bool = False) -> None:
    """
    Create the 'ecommerce' schema using raw psycopg connection.

    This runs BEFORE Django is initialized to avoid search_path issues.
    """
    import psycopg

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    schema_name = os.environ.get("DB_SCHEMA", "ecommerce")

    print(f"Setting up schema '{schema_name}'...")

    # Connect without schema restriction (to public)
    with psycopg.connect(database_url) as conn:
        conn.autocommit = True
        with conn.cursor() as cursor:
            # Check if schema exists
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s",
                (schema_name,),
            )
            exists = cursor.fetchone() is not None

            if exists and force_recreate:
                print(f"Dropping existing schema '{schema_name}'...")
                cursor.execute(f'DROP SCHEMA "{schema_name}" CASCADE')
                exists = False

            if not exists:
                cursor.execute(f'CREATE SCHEMA "{schema_name}"')
                print(f"Schema '{schema_name}' created successfully.")
            else:
                print(f"Schema '{schema_name}' already exists.")


def setup_django() -> None:
    """Setup Django."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

    import django

    django.setup()


def run_migrations() -> None:
    """Run Django migrations."""
    from django.core.management import call_command

    print("\nRunning migrations...")
    call_command("migrate", verbosity=1)
    print("Migrations completed.")


def load_fixtures() -> None:
    """Load initial data fixtures."""
    from django.core.management import call_command

    print("\nLoading fixtures...")
    call_command("loaddata", "marketplaces", verbosity=1)
    call_command("loaddata", "import_tax_rates", verbosity=1)
    print("Fixtures loaded.")


def create_user(email: str, password: str) -> None:
    """Create a user with the given credentials."""
    from apps.accounts.models import User

    if User.objects.filter(email=email).exists():
        print(f"\nUser '{email}' already exists.")
        return

    print(f"\nCreating user '{email}'...")
    # Use email prefix as username
    username = email.split("@")[0]
    user = User.objects.create_user(username=username, email=email, password=password)
    print(f"User '{user.email}' created successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup database")
    parser.add_argument(
        "--force-recreate",
        action="store_true",
        help="Drop and recreate schema (WARNING: destroys all data)",
    )
    args = parser.parse_args()

    # Load environment first
    load_env()

    # Create schema BEFORE Django initialization (to avoid search_path issues)
    create_schema_raw(force_recreate=args.force_recreate)

    # Now setup Django (which will use the schema)
    setup_django()

    # Run migrations and setup
    run_migrations()
    load_fixtures()

    # Create default user
    create_user(
        email="pablo@test.com",
        password="1%8/4&AZ",
    )

    print("\n✓ Database setup complete!")
