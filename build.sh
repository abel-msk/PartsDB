#!/bin/bash

pyinstaller  -F --onefile --windowed  -y  --clean --name="ElPartsDB" --icon="icons/ElPartsCatalog.icns" main.py

#pyinstaller --windowed --name="Hello World" --iconpwd="Hello World.icns" --add-data="icons/hand.png:icons" --add-data="icons/lightning.png:icons" app.py
#--onefile