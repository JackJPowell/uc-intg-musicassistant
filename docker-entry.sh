#!/bin/bash
# Docker entrypoint script
# TODO: Update the path if you rename the intg-musicassistant folder

cd /usr/src/app
pip install --no-cache-dir -q -r requirements.txt
python intg-musicassistant/driver.py