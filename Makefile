PYTHON ?= python
ANIME ?= Naruto

.PHONY: install run gui lint clean

install:
	$(PYTHON) -m pip install -r requirements.txt

run:
	$(PYTHON) main.py --anime "$(ANIME)"

gui:
	$(PYTHON) main_gui.py

lint:
	$(PYTHON) -m py_compile main.py main_gui.py crypolt_shorts\cli.py crypolt_shorts\pipeline.py crypolt_shorts\config.py crypolt_shorts\utils.py crypolt_shorts\app\settings.py crypolt_shorts\app\localization.py crypolt_shorts\app\gui.py crypolt_shorts\domain\models.py crypolt_shorts\infrastructure\runtime_service.py crypolt_shorts\services\anime_service.py crypolt_shorts\services\assets_service.py crypolt_shorts\services\render_service.py

clean:
	if exist output rmdir /s /q output
	if exist .cache rmdir /s /q .cache
	if exist __pycache__ rmdir /s /q __pycache__
	if exist crypolt_shorts\__pycache__ rmdir /s /q crypolt_shorts\__pycache__
	if exist crypolt_shorts\app\__pycache__ rmdir /s /q crypolt_shorts\app\__pycache__
	if exist crypolt_shorts\domain\__pycache__ rmdir /s /q crypolt_shorts\domain\__pycache__
	if exist crypolt_shorts\infrastructure\__pycache__ rmdir /s /q crypolt_shorts\infrastructure\__pycache__
	if exist crypolt_shorts\services\__pycache__ rmdir /s /q crypolt_shorts\services\__pycache__
