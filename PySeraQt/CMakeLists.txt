# SlicerPySera/PySeraQt/CMakeLists.txt
set(MODULE_NAME PySeraQt)

set(MODULE_PYTHON_SCRIPTS
  PySeraQt.py
  )

set(MODULE_PYTHON_RESOURCES
  Resources/Icons/SlicerPySERA_png_icon.png
  PySeraQt.ui
  )

slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
)

