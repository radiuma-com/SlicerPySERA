# SlicerPySera/CMakeLists.txt
cmake_minimum_required(VERSION 3.16.3)
project(PySera)

set(EXTENSION_HOMEPAGE "https://github.com/MohammadRSalmanpour/SlicerPySERA")
set(EXTENSION_CATEGORY "Radiomics")
set(EXTENSION_CONTRIBUTORS "Mohammad R. Salmanpour, Sirwan Barichin")
set(EXTENSION_DESCRIPTION "PySERA radiomics extraction library integrated into 3D Slicer.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/refs/heads/main/Resources/Icons/SlicerPySERA_png_icon.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/refs/heads/main/Resources/Screenshots/screenshoturls.png")

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

# Add the scripted module (PySera_Ext)
add_subdirectory(PySera_Ext)

# Optionally: add CLI and Qt modules if needed
add_subdirectory(PySeraCLI)
add_subdirectory(PySeraQt)

include(${Slicer_EXTENSION_CPACK})




