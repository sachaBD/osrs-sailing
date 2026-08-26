PORT ?= 8000

.PHONY: help data serve stop refresh refresh-apply clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t-/' | column -t -s "$$(printf '\t')"

data: ## Rebuild data.js from port_tasks.list + locations.tsv
	python3 parse_list.py
	python3 build.py

serve: data ## Serve the app at http://localhost:$(PORT)
	@echo "Serving on http://localhost:$(PORT)/"
	python3 -m http.server $(PORT) --bind 127.0.0.1

stop: ## Kill any server on $(PORT)
	-@pkill -f "http.server $(PORT)" && echo "stopped"

refresh: ## Re-check locations.tsv against the wiki (fills blanks, keeps your edits)
	python3 refresh_wiki.py

refresh-apply: ## Same, but let the wiki overwrite your edited values
	python3 refresh_wiki.py --apply

clean: ## Remove generated files
	rm -f data.js port_tasks.json port_tasks.csv
