PORT ?= 8000
PY ?= python3

.PHONY: help install data tiles check test lint shot serve stop refresh refresh-apply \
        survey survey-check survey-render sim clean clean-tiles clean-out

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t-/' | column -t -s "$$(printf '\t')"

install: ## Install the package and its dev tools, editable
	$(PY) -m pip install -e '.[survey,dev]'

data: ## Rebuild web/js/generated.js from tables
	$(PY) -m porttasks.tables.tasks
	$(PY) -m porttasks.generate

tiles: ## Download map tiles into web/tiles (~11MB, needed once for offline use)
	$(PY) -m porttasks.tiles.fetch

check: ## Fast tests: everything that does not need a browser
	$(PY) -m pytest -m 'not browser'

test: ## Every test, including the browser runs
	$(PY) -m pytest

lint: ## Style and import checks
	$(PY) -m ruff check .

shot: ## Screenshot the app into out/shots/
	$(PY) tools/screenshot.py

serve: data ## Serve the app at http://localhost:$(PORT)
	@echo "Serving on http://localhost:$(PORT)/"
	$(PY) -m http.server $(PORT) --bind 127.0.0.1 --directory web

stop: ## Kill any server on $(PORT)
	-@pkill -f "http.server $(PORT)" && echo "stopped"

refresh: ## Re-check tables/locations.tsv against the wiki (fills blanks, keeps your edits)
	$(PY) -m porttasks.wiki

refresh-apply: ## Same, but let the wiki overwrite your edited values
	$(PY) -m porttasks.wiki --apply

survey: ## Re-measure sailing distances off the map (one-off; needs `make tiles`)
	$(PY) -m porttasks.routing.world.survey.build
	$(PY) -m porttasks.routing.world.survey.measure

survey-check: ## Report port pairs the lattice still routes the long way round
	$(PY) -m porttasks.routing.world.survey.check

survey-render: ## Draw the graph, the sea lanes, and a sample of routes
	$(PY) -m porttasks.routing.world.survey.render --tiles
	$(PY) -m porttasks.routing.world.survey.render --lanes
	$(PY) -m porttasks.routing.world.survey.sample

sim: ## Walk the simulator one action at a time, in marimo
	$(PY) -m marimo edit tools/sim_walkthrough.marimo.py

clean: ## Remove generated files (keeps downloaded tiles and out/)
	rm -f web/js/generated.js derived/port_tasks.json derived/port_tasks.csv

clean-out: ## Remove the generated output: survey caches, renders, screenshots
	rm -rf out

clean-tiles: ## Remove downloaded tiles, e.g. after changing tile_version
	rm -rf web/tiles
