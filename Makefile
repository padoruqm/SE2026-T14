.DEFAULT_GOAL := help
.PHONY: help dev test lint

help:
	@printf '%s\n' 'Available targets: dev, test, lint'
	@printf '%s\n' 'The application scaffold has not been added yet; these targets intentionally stop.'

dev test lint:
	@printf '%s\n' 'Application scaffold is not available yet. See README.md.'
	@exit 1
