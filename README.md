# PartsDB
PartsDB is a small application for cataloguing microelectronics components and their datasheets.
All components are divided by types and subtypes. For example, type "Diode" abd subtype "diodes shotkey".

Parts of some type displayed in the table view with a wide range of predefined fields.  
Field can be renamed or hide.
There is addition space for keeping links to datasheet files, 
schemas, or images per part. Link to local file or public URL. 
Link can be opened from within application locally defined viewers.

# Installing
You need python 3.11 or greater installed on your system.

```commandline
    git cline https://github.com/abel-msk/PartsDB
    cd PartsDB
```
It is strongly recommended to use virtual environment: 
```commandline
    python -m venv ./venv 
```
For more information about creation and using virtual environment see : https://docs.python.org/3/library/venv.html

At this moment install required libs witch listed below.
So now ypu can build executable application for your system:

```commandline
    /bin/bash ./build.sh
```
This will create subdirectory "dist" and build application "ElPartsCatalog" inside.

### Required libs
The librarays you need to install before build:
```
Package                   Version
------------------------- -------
altgraph                  0.17.4
click                     8.1.7
coloredlogs               15.0.1
et-xmlfile                1.1.0
hiredis                   2.3.2
humanfriendly             10.0
importlib-resources       5.13.0
macholib                  1.16.3
numpy                     1.26.4
openpyxl                  3.1.2
org-python                0.3.2
packaging                 24.0
pyinstaller               6.7.0
pyinstaller-hooks-contrib 2024.6
PyQt6                     6.7.0
PyQt6-Qt6                 6.7.0
PyQt6-sip                 13.6.0
PyYAML                    6.0.1
setuptools                65.5.1
tabulate                  0.9.0
winapi                    0.0.0
```

