# SlicerPySera/PySeraCLI/CMakeLists.txt
set(MODULE_NAME PySeraCLI)
set(MODULE_EXE_SCRIPTS
  PySeraCLIModule.py
)

# This will install the script as a Python module in Slicer's module path.
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_EXE_SCRIPTS}
)
