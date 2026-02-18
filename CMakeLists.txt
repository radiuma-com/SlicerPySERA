cmake_minimum_required(VERSION 3.20.6...3.22.6 FATAL_ERROR)
project(PySERA)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/radiuma-com/SlicerPySERA")
set(EXTENSION_CATEGORY "Analysis")
set(EXTENSION_CONTRIBUTORS "Mohammad R. Salmanpour, Sirwan Barichin")
set(EXTENSION_DESCRIPTION "PySERA radiomics extraction library integrated into 3D Slicer.")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/main/Resources/Icons/SlicerPySERA_png_icon.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/radiuma-com/SlicerPySERA/main/Resources/Screenshots/screenshoturls.png")
set(EXTENSION_DEPENDS "NA")  # Specified as a list or "NA" if no dependencies

find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

add_subdirectory(PySERA)

include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})
