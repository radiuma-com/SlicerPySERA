# SlicerPySera/PySera_Ext/CMakeLists.txt

set(MODULE_NAME PySera)

# Python scripts that must be installed
set(MODULE_PYTHON_SCRIPTS
  ${MODULE_NAME}.py
  pysera_lib/__init__.py
  pysera_lib/version.py
)

# Resources that must be packaged with the module
set(MODULE_PYTHON_RESOURCES
  pysera_lib/parameters.yaml
  pysera_lib/parameters.json
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
