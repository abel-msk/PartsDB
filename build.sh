#!/bin/bash

pyinstaller  --windowed  -y  --clean --name="ElPartsCatalog" --icon="icons/ElPartsCatalog.icns" main.py

#pyinstaller --windowed --name="Hello World" --iconpwd="Hello World.icns" --add-data="icons/hand.png:icons" --add-data="icons/lightning.png:icons" app.py
