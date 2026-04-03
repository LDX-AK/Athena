PYTHON ?= d:/Projects/Athena/.venv/Scripts/python.exe

.PHONY: install smoke-imports smoke-athena test train backtest paper

install:
	$(PYTHON) -m pip install -r requirements.txt

smoke-imports:
	$(PYTHON) test_imports.py

smoke-athena:
	$(PYTHON) test_athena_smoke.py

test:
	$(PYTHON) -m unittest discover -s tests -p "test_*.py" -v

train:
	$(PYTHON) -m athena --mode train

backtest:
	$(PYTHON) -m athena --mode backtest

paper:
	$(PYTHON) -m athena --mode paper
