PORT ?= 8000

.PHONY: help data tiles check test shots serve stop refresh refresh-apply clean clean-tiles \
        chart chart-check chart-render clean-chart

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t-/' | column -t -s "$$(printf '\t')"

data: ## Rebuild data.js from port_tasks.list + locations.tsv
	python3 parse_list.py
	python3 build.py

tiles: ## Download map tiles into tiles/ (~11MB, needed once for offline use)
	python3 fetch_tiles.py

check: data ## Fast unit tests: python pipeline + JS logic in a real browser
	python3 -m unittest discover -p 'test_*.py'
	python3 js_test.py

test: check ## Unit tests plus the full end-to-end browser run
	python3 smoke_test.py

shots: data ## Same as test, but also write screenshots into shots/
	python3 smoke_test.py --shots

serve: data ## Serve the app at http://localhost:$(PORT)
	@echo "Serving on http://localhost:$(PORT)/"
	python3 -m http.server $(PORT) --bind 127.0.0.1

stop: ## Kill any server on $(PORT)
	-@pkill -f "http.server $(PORT)" && echo "stopped"

refresh: ## Re-check locations.tsv against the wiki (fills blanks, keeps your edits)
	python3 refresh_wiki.py

refresh-apply: ## Same, but let the wiki overwrite your edited values
	python3 refresh_wiki.py --apply

chart: ## Build the sea graph and the port distance matrix (needs `make tiles`)
	python3 -m routing.build_graph
	python3 -m routing.portmatrix

chart-check: ## Report port pairs the lattice still routes the long way round
	python3 -m routing.check_graph

chart-render: ## Draw the graph, the sea lanes, and a sample of routes
	python3 -m routing.render_graph --tiles
	python3 -m routing.render_graph --lanes
	python3 -m routing.render_sample

clean-chart: ## Remove the generated caches and renders under routing/
	rm -rf routing/cache routing/renders

clean: ## Remove generated files (keeps downloaded tiles)
	rm -f src/generated.js port_tasks.json port_tasks.csv

clean-tiles: ## Remove downloaded tiles, e.g. after changing tile_version
	rm -rf tiles
