# -------------------------------
# PySeraQt.py
# -------------------------------

import qt, slicer, logging
from slicer.ScriptedLoadableModule import ScriptedLoadableModule, ScriptedLoadableModuleTest
from PySera import PySeraWidget, PySERALogic

# -------------------------------
# Logger
# -------------------------------
logger = logging.getLogger("PySeraQt")
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)

# -------------------------------
# Qt Module Wrapper
# -------------------------------
class PySeraQt(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        logger.info("PySeraQt module initialized")

# -------------------------------
# GUI Widget
# -------------------------------
class PySeraQtWidget(PySeraWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("PySeraQtWidget initialized using PySeraWidget GUI and logic")

# -------------------------------
# Test Class
# -------------------------------
class PySeraQtTest(ScriptedLoadableModuleTest):
    def runTest(self):
        self.delayDisplay("Running PySeraQt tests...")
        try:
            logic = PySERALogic()
            assert logic is not None
            self.delayDisplay("PySERALogic instantiation: OK")
            logger.info("PySERALogic test passed")
        except Exception as e:
            self.delayDisplay(f"Test failed: {e}")
            logger.error(f"PySeraQtTest failed: {e}")
