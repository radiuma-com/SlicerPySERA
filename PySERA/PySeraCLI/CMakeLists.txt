# SlicerPySera/PySeraCLI/CMakeLists.txt
set(MODULE_NAME PySeraCLI)

set(MODULE_PYTHON_SCRIPTS
  PySeraCLIModule.py
  pysera_cli_lib/__init__.py
)

set(MODULE_PYTHON_RESOURCES
  PySeraCLI.xml
  pysera_cli_lib/parameters.yaml
  pysera_cli_lib/parameters.json
)

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
)
