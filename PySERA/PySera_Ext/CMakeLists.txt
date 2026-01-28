set(MODULE_NAME PySera)

set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
)

set(MODULE_PYTHON_RESOURCES
)

# Optional icon (do not fail packaging if missing)
set(_ICON_PATH "${CMAKE_CURRENT_SOURCE_DIR}/Resources/Icons/SlicerPySERA_png_icon.png")
if(EXISTS "${_ICON_PATH}")
  list(APPEND MODULE_PYTHON_RESOURCES Resources/Icons/SlicerPySERA_png_icon.png)
endif()

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
)

# Install pysera_lib Python package
install(
  DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/pysera_lib
  DESTINATION ${Slicer_INSTALL_QTSCRIPTEDMODULES_LIB_DIR}/PySera
  PATTERN "__pycache__" EXCLUDE
  PATTERN "*.pyc" EXCLUDE
)
