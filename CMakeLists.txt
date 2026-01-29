cmake_minimum_required(VERSION 3.16.3)
project(PySERA)

set(EXTENSION_HOMEPAGE "https://github.com/radiuma-com/SlicerPySERA")
set(EXTENSION_CATEGORY "Analysis")
set(EXTENSION_CONTRIBUTORS "Mohammad R. Salmanpour, Sirwan Barichin")
set(EXTENSION_DESCRIPTION "PySERA radiomics extraction library integrated into 3D Slicer.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/main/Resources/Icons/SlicerPySERA_png_icon.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/main/Resources/Screenshots/screenshoturls.png")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})


# -------------------------------
# Modules
# -------------------------------
add_subdirectory(PySERA/PySera_Ext)
add_subdirectory(PySERA/PySeraCLI)

include(${Slicer_EXTENSION_CPACK})
