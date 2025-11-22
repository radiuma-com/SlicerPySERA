# SlicerPySera/CMakeLists.txt
cmake_minimum_required(VERSION 3.16.3)
project(SlicerPySera)

set(EXTENSION_HOMEPAGE "https://github.com/radiuma-com/SlicerPySERA")
set(EXTENSION_CATEGORY "Radiomics")
set(EXTENSION_CONTRIBUTORS "Mohammad R. Salmanpour")
set(EXTENSION_DESCRIPTION "PySERA radiomics extraction library + Slicer ScriptedLoadableModule UI wrapper")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/Resources/Icons/SlicerPySERA_icon.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/Resources/Screenshots")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

# Add the scripted module (PySera_Ext)
add_subdirectory(PySera_Ext)

# Optionally: add CLI and Qt modules if needed
add_subdirectory(PySeraCLI)
add_subdirectory(PySeraQt)

include(${Slicer_EXTENSION_CPACK})

