# Developer shortcuts for Windows PowerShell.   Usage:  .\dev.ps1 <command>
param(
    [Parameter(Position = 0)][string]$Command = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest
)

switch ($Command) {
    "up"      { docker compose up -d --build; "API docs: http://localhost:8000/docs" }
    "down"    { docker compose down }
    "reset"   { docker compose down -v }          # also deletes the database volume
    "logs"    { docker compose logs -f --tail=100 @Rest }
    "test"    { docker compose run --rm api pytest @Rest }
    "cov"     { docker compose run --rm api pytest --cov=app --cov-report=term-missing }
    "lint"    { docker compose run --rm api ruff check . }
    "fmt"     { docker compose run --rm api ruff check . --fix }
    "migrate" { docker compose run --rm api alembic upgrade head }
    "revision"{ docker compose run --rm api alembic revision --autogenerate -m ($Rest -join " ") }
    "psql"    { docker compose exec db psql -U payforge payforge }
    "shell"   { docker compose run --rm api sh }
    "demo"    { python scripts/demo.py @Rest }
    default   {
        "Commands: up | down | reset | logs | test | cov | lint | fmt | migrate | revision <msg> | psql | shell | demo"
    }
}
