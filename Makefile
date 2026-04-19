.PHONY: test test-algo test-core test-api test-sim lint

test:
	cd tms && pytest tests/ -v

test-algo:
	cd tms && pytest tests/test_algorithms/ -v

test-core:
	cd tms && pytest tests/test_core/ -v

test-api:
	cd tms && pytest tests/test_api/ -v

test-sim:
	cd tms && pytest tests/test_algorithms/test_reproducibility.py -v

lint:
	cd tms && black --check . && isort --check .
