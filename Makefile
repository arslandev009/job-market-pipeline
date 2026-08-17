# Convenience commands. Every command here is just a shortcut for the docker
# compose commands documented in docs/RUNBOOK.md — read that file if a `make`
# target ever does something you don't understand.

.PHONY: up down migrate scrape extract ml score report pipeline logs test build clean

up:
	docker compose up -d postgres
	docker compose run --rm migrate

down:
	docker compose down

migrate:
	docker compose run --rm migrate

scrape:
	docker compose run --rm scraper

extract:
	docker compose run --rm extractor

ml:
	docker compose run --rm ml

score:
	docker compose run --rm scorer

report:
	docker compose run --rm sheets-writer

# Runs the full pipeline once, stage by stage, in order — the manual equivalent
# of what the scheduler container does automatically on an interval.
pipeline: scrape extract ml score report

schedule:
	docker compose --profile scheduled up -d scheduler

logs:
	docker compose logs -f

test:
	pytest -v

build:
	docker compose build

clean:
	docker compose down -v
