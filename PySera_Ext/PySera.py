# -*- coding: utf-8 -*-
# Fully YAML-driven PySERA Slicer module
# - Tabs UI
# - Settings split into:
#     1) Common Set (Handcrafted Feature and Deep Feature)
#     2) Just Set for (Handcrafted Feature)
# - Compact editors (shorter inputs), even spacing
# - 2-line IBSI checkbox row
# - Categories<->Dimensions sync
# - Deep-feature mode supported
# - Report level forwarded to CLI and Python logger

# -------------------------------
# Imports
# -------------------------------
import os
import json
import yaml
import qt, ctk, slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleTest,
)
import pysera
import datetime
import random
import logging

# -------------------------------
# Logger Helper
# -------------------------------
class Logger:
    def __init__(self, name="PySera"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            console = logging.StreamHandler()
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
            self.logger.addHandler(console)

    def info(self, msg):   self._emit(self.logger.info, msg)
    def debug(self, msg):  self._emit(self.logger.debug, msg)
    def warning(self, msg):self._emit(self.logger.warning, msg)
    def error(self, msg):  self._emit(self.logger.error, msg)

    @staticmethod
    def _emit(fn, msg):
        fn(msg)
        try:
            slicer.app.processEvents()
        except Exception:
            pass

logger = Logger()

# -------------------------------
# Load parameters (YAML/JSON)
# -------------------------------
PROJECT_ROOT = os.path.dirname(__file__)
YAML_PATH = os.path.join(PROJECT_ROOT, "pysera_lib", "parameters.yaml")
JSON_PATH = os.path.join(PROJECT_ROOT, "pysera_lib", "parameters.json")

def load_parameters():
    cfg = {}
    try:
        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r") as f:
                cfg = json.load(f) or {}
            logger.info(f"Parameters loaded from {JSON_PATH}")
        elif os.path.exists(YAML_PATH):
            with open(YAML_PATH, "r") as f:
                cfg = yaml.safe_load(f) or {}
            logger.info(f"Parameters loaded from {YAML_PATH}")
        else:
            logger.warning("No parameter file found (pysera_lib/parameters.yaml or .json). Using empty defaults.")
    except Exception as e:
        logger.error(f"Failed to load parameters: {e}")
    return cfg

CFG_FILE = load_parameters()
RDEF     = CFG_FILE.get("radiomics")   or {}   # defaults block
CLI_MAP  = CFG_FILE.get("cli_key_map") or {}   # mapping block

# -------------------------------
# Slicer Module class
# -------------------------------
class PySera(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "PySera"
        self.parent.categories = ["Analysis"]
        self.parent.dependencies = []
        self.parent.contributors = ["Mohammad R. Salmanpour"]
        self.parent.helpText = "YAML-driven PySERA feature extraction."
        self.parent.acknowledgementText = "Thanks to ..."

# -------------------------------
# Logic class (YAML → CLI kwargs)
# -------------------------------
class PySERALogic(ScriptedLoadableModuleLogic):

    @staticmethod
    def _normalize(v):
        """Coerce strings to numbers/None, keep 'auto', parse comma-lists, bool→0/1."""
        if v is None:
            return None
        if isinstance(v, bool):
            return int(v)
        if isinstance(v, (int, float)):
            return v
        s = str(v).strip()
        if s == "":
            return ""
        lo = s.lower()
        if lo == "none":
            return None
        if lo == "auto":
            return "auto"
        if "," in s:
            out = []
            for part in s.split(","):
                part = part.strip()
                if part.lower() == "none":
                    out.append(None); continue
                try:
                    out.append(int(part) if part.isdigit() else float(part))
                except Exception:
                    out.append(part)
            return out
        try:
            if "." in s or "e" in lo:
                return float(s)
            return int(s)
        except Exception:
            return s

    def _compose_cfg(self, params_from_ui: dict) -> dict:
        cfg = {}
        for k, v in (RDEF or {}).items():
            cfg["radiomics_" + k] = v
        if "destination_folder" in RDEF:
            cfg["radiomics_destination_folder"] = RDEF["destination_folder"]
        if "temporary_files_path" in RDEF:
            cfg["radiomics_temporary_files_path"] = RDEF["temporary_files_path"]
        for k, v in (CFG_FILE or {}).items():
            if isinstance(k, str) and k.startswith("radiomics_"):
                cfg[k] = v
        cfg.update(params_from_ui or {})
        return cfg

    def _build_cli_kwargs(self, cfg: dict, output_csv: str) -> dict:
        cli = {}
        PASSTHRU_STR = {
            "categories", "dimensions",
            "extraction_mode", "deep_learning_model", "optional_params",
            "report",
        }

        for src_key, dst_key in (CLI_MAP or {}).items():
            if src_key in cfg:
                raw = cfg[src_key]
                if raw is None or raw == "":
                    continue
                if dst_key in PASSTHRU_STR:
                    cli[dst_key] = str(raw)
                else:
                    val = self._normalize(raw)
                    if val is not None and val != "":
                        cli[dst_key] = val

        # Ensure mode/model/optional/report present even if not in CLI_MAP
        cli["extraction_mode"] = str(cfg.get("radiomics_extraction_mode", "handcrafted_feature"))

        model = cfg.get("radiomics_deep_learning_model", None)
        if model is not None and str(model).strip().lower() not in {"", "none"}:
            cli["deep_learning_model"] = str(model)

        opt = cfg.get("radiomics_optional_params", None)
        if opt is not None and str(opt).strip() != "":
            cli["optional_params"] = str(opt)

        if "radiomics_report" in cfg and str(cfg["radiomics_report"]).strip() != "":
            cli["report"] = str(cfg["radiomics_report"])

        return cli

    def run_single_pair(self, image_path, mask_path, params=None):
        cfg = self._compose_cfg(params)
        out_dir = cfg.get("radiomics_destination_folder") or os.path.join(os.path.expanduser("~"), "Desktop", "output")
        os.makedirs(out_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        random_suffix = random.randint(1000, 9999)
        output_csv = os.path.join(out_dir, f"extracted_radiomics_features_{timestamp}_{random_suffix}.csv")

        logger.debug(f"Output directory: {out_dir}")
        logger.info(f"Output CSV path: {output_csv}")

        cli_kwargs = self._build_cli_kwargs(cfg, output_csv)
        cli_kwargs.setdefault("categories", str(cfg.get("radiomics_categories", "all")))
        cli_kwargs.setdefault("dimensions", str(cfg.get("radiomics_dimensions", "all")))

        # Mirror 'report' into Python logging level
        level_map = {
            "none":    logging.CRITICAL + 1,
            "error":   logging.ERROR,
            "warning": logging.WARNING,
            "info":    logging.INFO,
            "all":     logging.DEBUG,
        }
        report_sel = str(cfg.get("radiomics_report", "all")).strip().lower()
        level = level_map.get(report_sel, logging.DEBUG)
        logger.logger.setLevel(level)
        for h in logger.logger.handlers:
            h.setLevel(level)

        try:
            result = pysera.process_batch(
                image_input=image_path,
                mask_input=mask_path,
                output_path=output_csv,
                **cli_kwargs
            )
            logger.info(f"Feature extraction completed: {output_csv}")
            return output_csv, result
        except Exception as e:
            logger.error(f"Feature extraction failed: {e}")
            raise

# -------------------------------
# Widget (GUI) with Tabs & Split Settings
# -------------------------------
class PySeraWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logic = PySERALogic()
        self.param_widgets = {}
        self.categoryChecks = []
        self.dimensionChecks = []
        self._categoryByName = {}
        self._dimensionByName = {}

    # ---------- small helpers ----------
    @staticmethod
    def _wtext(widget) -> str:
        t = getattr(widget, "text", None)
        if callable(t):
            try: return t()
            except TypeError: pass
        return t if isinstance(t, str) else str(t) if t is not None else ""

    @staticmethod
    def _val_from_widget(w):
        if isinstance(w, qt.QCheckBox):
            return 1 if w.checked else 0
        if isinstance(w, (qt.QSpinBox, qt.QDoubleSpinBox)):
            return w.value
        if isinstance(w, qt.QComboBox):
            ct = getattr(w, "currentText", None)
            return ct() if callable(ct) else ct
        if isinstance(w, qt.QLineEdit):
            t = getattr(w, "text", None)
            return t() if callable(t) else (t or "")
        return ""

    @staticmethod
    def _set_combo_safe(combo: qt.QComboBox, value: str):
        if value is None:
            return
        for i in range(combo.count):
            if combo.itemText(i).lower() == str(value).lower():
                combo.setCurrentIndex(i)
                return

    def _combo_text_safe(self, combo: qt.QComboBox) -> str:
        ct = getattr(combo, "currentText", None)
        if callable(ct):
            try:
                return ct()
            except TypeError:
                pass
        return ct if isinstance(ct, str) else (str(ct) if ct is not None else "")

    @staticmethod
    def _shrink_editor(w, fixed_width=140):
        if isinstance(w, (qt.QLineEdit, qt.QComboBox, qt.QSpinBox, qt.QDoubleSpinBox)):
            w.setFixedWidth(fixed_width)
            w.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Preferred)
        return w

    def _add_two_grid(self, grid: qt.QGridLayout, row: int, label1: str, widget1, label2: str, widget2):
        lbl1 = qt.QLabel(label1); lbl2 = qt.QLabel(label2)
        lbl1.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Preferred)
        lbl2.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Preferred)
        w1 = self._shrink_editor(widget1)
        w2 = self._shrink_editor(widget2)
        grid.addWidget(lbl1, row, 0)
        grid.addWidget(w1,   row, 1)
        grid.addWidget(lbl2, row, 2)
        grid.addWidget(w2,   row, 3)

    def _build_categories_panel(self, options, default_str):
        gb = qt.QGroupBox("Categories")
        gb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        v = qt.QVBoxLayout(gb)
        grid = qt.QGridLayout()
        grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(15); grid.setVerticalSpacing(4)
        checks = []
        cols = 4
        default_all = (str(default_str).strip().lower() == "all")
        wanted = set()
        if not default_all and isinstance(default_str, str):
            wanted = set([x.strip().lower() for x in default_str.split(",") if x.strip()])
        for idx, name in enumerate(options):
            cb = qt.QCheckBox(name)
            cb.setChecked(True if default_all else (name.lower() in wanted))
            r = idx // cols
            c = idx % cols
            grid.addWidget(cb, r, c)
            checks.append(cb)
        btnRow = qt.QHBoxLayout()
        selAll = qt.QPushButton("Select all"); clrAll = qt.QPushButton("Clear all")
        def _select_all():   [cb.setChecked(True)  for cb in checks]
        def _clear_all():    [cb.setChecked(False) for cb in checks]
        selAll.clicked.connect(_select_all); clrAll.clicked.connect(_clear_all)
        btnRow.addStretch(1); btnRow.addWidget(selAll); btnRow.addWidget(clrAll)
        v.addLayout(grid); v.addLayout(btnRow)
        return gb, checks

    def _build_dimensions_panel(self, options, default_str):
        gb = qt.QGroupBox("Dimensions")
        gb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        v = qt.QVBoxLayout(gb)
        grid = qt.QGridLayout()
        grid.setContentsMargins(0,0,0,0); grid.setHorizontalSpacing(15); grid.setVerticalSpacing(4)
        checks = []
        cols = 4
        default_all = (str(default_str).strip().lower() == "all")
        wanted = set()
        if not default_all and isinstance(default_str, str):
            wanted = set([x.strip().lower() for x in default_str.split(",") if x.strip()])
        for idx, name in enumerate(options):
            cb = qt.QCheckBox(name)
            cb.setChecked(True if default_all else (name.lower() in wanted))
            r = idx // cols
            c = idx % cols
            grid.addWidget(cb, r, c)
            checks.append(cb)
        btnRow = qt.QHBoxLayout()
        selAll = qt.QPushButton("Select all"); clrAll = qt.QPushButton("Clear all")
        def _select_all():   [cb.setChecked(True)  for cb in checks]
        def _clear_all():    [cb.setChecked(False) for cb in checks]
        selAll.clicked.connect(_select_all); clrAll.clicked.connect(_clear_all)
        btnRow.addStretch(1); btnRow.addWidget(selAll); btnRow.addWidget(clrAll)
        v.addLayout(grid); v.addLayout(btnRow)
        return gb, checks

    def _on_dimension_changed(self, dim_to_cats: dict, *_):
        checked_dims = []
        for cb in getattr(self, "dimensionChecks", []):
            if cb.isChecked():
                checked_dims.append(self._wtext(cb).strip().lower())

        if "all" in checked_dims:
            for dcb in self.dimensionChecks:
                if not dcb.isChecked():
                    dcb.setChecked(True)
            for ccb in self.categoryChecks:
                if not ccb.isChecked():
                    ccb.setChecked(True)
            return

        if not checked_dims:
            for ccb in self.categoryChecks:
                if ccb.isChecked():
                    ccb.setChecked(False)
            return

        wanted = set()
        for d in checked_dims:
            d_key = "2_5d" if d in ("2_5d", "2.5d") else d
            cats = dim_to_cats.get(d_key, [])
            wanted.update(c.lower() for c in cats)

        for name, ccb in getattr(self, "_categoryByName", {}).items():
            ccb.setChecked(name in wanted)

    # ---------- UI scaffold helpers ----------
    def _make_scroll_tab(self, title: str, tabs: qt.QTabWidget):
        page = qt.QWidget()
        page.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        page_v = qt.QVBoxLayout(page); page_v.setContentsMargins(6,6,6,6); page_v.setSpacing(10)

        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        scroll.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

        inner = qt.QWidget()
        inner.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        inner_v = qt.QVBoxLayout(inner); inner_v.setContentsMargins(0,0,0,0); inner_v.setSpacing(10)

        scroll.setWidget(inner)
        page_v.addWidget(scroll)
        tabs.addTab(page, title)
        return inner_v

    def setup(self):
        super().setup()
        root = self.layout
        root.setSpacing(10)

        # --- Tabs container ---
        tabs = qt.QTabWidget()
        tabs.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        root.addWidget(tabs, 1)

        # Tabs
        ioTab       = self._make_scroll_tab("I/O", tabs)
        deepTab     = self._make_scroll_tab("Features Extraction Mode", tabs)
        settingsTab = self._make_scroll_tab("Settings", tabs)
        selectTab   = self._make_scroll_tab("Feature Subset", tabs)
        runTab      = self._make_scroll_tab("Run and Results", tabs)

        # -------------------------------
        # I/O tab
        # -------------------------------
        ioGroup = qt.QGroupBox("Inputs and Outputs")
        ioGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        ioGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        ioForm = qt.QFormLayout(ioGroup)

        self.imagePathEdit = ctk.ctkPathLineEdit(); self.imagePathEdit.filters = ctk.ctkPathLineEdit.Files
        self.maskPathEdit  = ctk.ctkPathLineEdit(); self.maskPathEdit.filters  = ctk.ctkPathLineEdit.Files
        ioForm.addRow("Image File:", self.imagePathEdit)
        ioForm.addRow("Mask File:",  self.maskPathEdit)

        self.outputDirEdit = ctk.ctkPathLineEdit(); self.outputDirEdit.filters = ctk.ctkPathLineEdit.Dirs
        self.tmpDirEdit    = ctk.ctkPathLineEdit(); self.tmpDirEdit.filters    = ctk.ctkPathLineEdit.Dirs
        self.outputDirEdit.currentPath = RDEF.get('destination_folder', "./output_result")
        self.tmpDirEdit.currentPath    = RDEF.get('temporary_files_path', "./temporary_files_path")
        ioForm.addRow("Destination Folder:", self.outputDirEdit)
        ioForm.addRow("Temporary Files Path:", self.tmpDirEdit)

        ioTab.addWidget(ioGroup)

        # -------------------------------
        # Settings tab (split into Common + Handcrafted-only)
        # -------------------------------
        settingsGroup = qt.QGroupBox("Settings")
        settingsGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        settingsGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        settingsLay = qt.QVBoxLayout(settingsGroup); settingsLay.setSpacing(10)

        # ========== Common Set (Handcrafted Feature and Deep Feature) ==========
        commonGroup = qt.QGroupBox("Common Set (Handcrafted Feature and Deep Feature)")
        commonGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        commonLay = qt.QVBoxLayout(commonGroup); commonLay.setSpacing(8)

        # Row A: preprocessing/parallelism/aggregation (even spacing)
        applyPreChk = qt.QCheckBox("Apply Preprocessing"); applyPreChk.checked = bool(RDEF.get('apply_preprocessing', False))
        enParChk    = qt.QCheckBox("Enable Parallelism");  enParChk.checked    = bool(RDEF.get('enable_parallelism', True))
        aggrChk     = qt.QCheckBox("Aggregation (Lesion)");aggrChk.checked     = bool(RDEF.get('aggregation_lesion', 0))

        togglesRow = qt.QWidget()
        togglesGrid = qt.QGridLayout(togglesRow)
        togglesGrid.setContentsMargins(0,0,0,0)
        togglesGrid.setHorizontalSpacing(12)
        togglesGrid.setVerticalSpacing(0)
        for i, cb in enumerate([applyPreChk, enParChk, aggrChk]):
            cb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred)
            togglesGrid.addWidget(cb, 0, i)
            togglesGrid.setColumnStretch(i, 1)
        commonLay.addWidget(togglesRow)

        # Row B: Num workers / Min ROI volume
        commonGrid = qt.QGridLayout()
        commonGrid.setHorizontalSpacing(12); commonGrid.setVerticalSpacing(8)
        for c in range(4): commonGrid.setColumnStretch(c, 0)

        numWorkersEdit = qt.QLineEdit(); numWorkersEdit.setPlaceholderText("auto or int")
        numWorkersEdit.setText(str(RDEF.get('num_workers', "auto")))
        minRoiSpin = qt.QDoubleSpinBox(); minRoiSpin.setRange(0.0, 1e12); minRoiSpin.setDecimals(0)
        minRoiSpin.setValue(float(RDEF.get('min_roi_volume', 10)))
        self._add_two_grid(commonGrid, 0, "Num Workers", numWorkersEdit, "Min ROI Volume", minRoiSpin)

        # Row C: ROI selection mode / Report level (both common)
        roiSel  = qt.QComboBox(); roiSel.addItems(["per_Img","per_region"])
        self._set_combo_safe(roiSel, RDEF.get('roi_selection_mode', "per_Img"))
        reportC = qt.QComboBox(); reportC.addItems(["none","error","warning","info","all"])
        self._set_combo_safe(reportC, RDEF.get('report', "all"))
        self._add_two_grid(commonGrid, 1, "ROI Selection Mode", roiSel, "Report", reportC)

        commonLay.addLayout(commonGrid)
        settingsLay.addWidget(commonGroup)

        # bind common params
        self.param_widgets.update({
            "radiomics_apply_preprocessing": applyPreChk,
            "radiomics_enable_parallelism": enParChk,
            "radiomics_aggregation_lesion": aggrChk,
            "radiomics_num_workers": numWorkersEdit,
            "radiomics_min_roi_volume": minRoiSpin,
            "radiomics_roi_selection_mode": roiSel,
            "radiomics_report": reportC,
        })

        # ========== Just Set for (Handcrafted Feature) ==========
        hcGroup = qt.QGroupBox("Just Set for (Handcrafted Feature)")
        hcGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        hcLay = qt.QVBoxLayout(hcGroup); hcLay.setSpacing(8)

        # 2-line IBSI toggles (even distribution)
        def mkchk(label_text: str, key: str, default_val: int = 0) -> qt.QCheckBox:
            cb = qt.QCheckBox(label_text)
            cb.checked = bool(RDEF.get(key, default_val))
            cb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred)
            self.param_widgets["radiomics_" + key] = cb
            return cb

        flagsWidget = qt.QWidget()
        flagsGrid = qt.QGridLayout(flagsWidget)
        flagsGrid.setContentsMargins(0,0,0,0)
        flagsGrid.setHorizontalSpacing(12)
        flagsGrid.setVerticalSpacing(6)

        # Order reflects your list
        flags = [
            mkchk("GL Round",         "isGLround",   0),
            mkchk("Scale",            "isScale",     0),
            mkchk("Re-Seg Range",     "isReSegRng",  0),
            mkchk("Outliers",         "isOutliers",  0),
            mkchk("Quantized Stats",  "isQuntzStat", 1),
            mkchk("2D Isotropic",     "isIsot2D",    0),
        ]
        for i, cb in enumerate(flags):
            r = 0 if i < 3 else 1
            c = i if i < 3 else (i - 3)
            flagsGrid.addWidget(cb, r, c)
        for c in range(3):
            flagsGrid.setColumnStretch(c, 1)
        hcLay.addWidget(flagsWidget)

        # Grid for all Handcrafted-only numeric/enum editors
        INTERP_OPTIONS = ["Nearest", "linear", "bilinear", "trilinear", "tricubic-spline", "cubic", "bspline", "None"]

        gridHC = qt.QGridLayout()
        gridHC.setHorizontalSpacing(12); gridHC.setVerticalSpacing(8)
        for c in range(4): gridHC.setColumnStretch(c, 0)

        # Editors
        binSizeSpin = qt.QSpinBox(); binSizeSpin.setRange(1, 10**9); binSizeSpin.setValue(int(RDEF.get('BinSize', 25)))
        fvm         = qt.QComboBox(); fvm.addItems(["REAL_VALUE","APPROXIMATE_VALUE"]); self._set_combo_safe(fvm, RDEF.get('feature_value_mode', "REAL_VALUE"))

        dtype       = qt.QComboBox(); dtype.addItems(["CT","MR","PET","OTHER"]); self._set_combo_safe(dtype, RDEF.get('DataType', "OTHER"))
        discType    = qt.QComboBox(); discType.addItems(["FBS","FBN"]); self._set_combo_safe(discType, RDEF.get('DiscType', "FBS"))

        voxI        = qt.QComboBox(); voxI.addItems(INTERP_OPTIONS); self._set_combo_safe(voxI, RDEF.get('VoxInterp', "Nearest"))
        roiI        = qt.QComboBox(); roiI.addItems(INTERP_OPTIONS); self._set_combo_safe(roiI, RDEF.get('ROIInterp', "Nearest"))

        iso3D       = qt.QDoubleSpinBox(); iso3D.setRange(0.0,1e12); iso3D.setSingleStep(0.1); iso3D.setValue(float(RDEF.get('isotVoxSize', 2)))
        iso2D       = qt.QDoubleSpinBox(); iso2D.setRange(0.0,1e12); iso2D.setSingleStep(0.1); iso2D.setValue(float(RDEF.get('isotVoxSize2D', 2)))

        reSeg01Edit = qt.QLineEdit(); reSeg01Edit.setPlaceholderText("None or value"); reSeg01Edit.setText(str(RDEF.get('ReSegIntrvl01', -1000)))
        reSeg02Edit = qt.QLineEdit(); reSeg02Edit.setPlaceholderText("None or value"); reSeg02Edit.setText(str(RDEF.get('ReSegIntrvl02', 400)))

        roiPvSpin   = qt.QDoubleSpinBox(); roiPvSpin.setRange(0.0,1.0); roiPvSpin.setSingleStep(0.05); roiPvSpin.setValue(float(RDEF.get('ROI_PV', 0.5)))

        qntzCombo   = qt.QComboBox(); qntzCombo.addItems(["Uniform","Lloyd-Max"]); self._set_combo_safe(qntzCombo, RDEF.get('qntz', "Uniform"))
        ivhType     = qt.QSpinBox();  ivhType.setRange(0,10**9); ivhType.setValue(int(RDEF.get('IVH_Type', 3)))
        ivhDisc     = qt.QSpinBox();  ivhDisc.setRange(0,10**9); ivhDisc.setValue(int(RDEF.get('IVH_DiscCont', 1)))
        ivhBin      = qt.QDoubleSpinBox(); ivhBin.setRange(0.0,1e12); ivhBin.setSingleStep(0.1); ivhBin.setValue(float(RDEF.get('IVH_binSize', 2.0)))

        # Place rows (compact, 2-per row)
        self._add_two_grid(gridHC, 0, "Bin Size", binSizeSpin, "Feature Value Mode", fvm)
        self._add_two_grid(gridHC, 1, "Data Type", dtype, "Discretization", discType)
        self._add_two_grid(gridHC, 2, "Voxel Interp", voxI, "ROI Interp", roiI)
        self._add_two_grid(gridHC, 3, "Isotropic Vox 3D", iso3D, "Isotropic Vox 2D", iso2D)
        self._add_two_grid(gridHC, 4, "ReSeg Low", reSeg01Edit, "ReSeg High", reSeg02Edit)
        self._add_two_grid(gridHC, 5, "ROI PV", roiPvSpin, "Quantization", qntzCombo)
        self._add_two_grid(gridHC, 6, "IVH Type", ivhType, "IVH DiscCont", ivhDisc)
        self._add_two_grid(gridHC, 7, "IVH BinSize", ivhBin, "", qt.QLabel(""))

        hcLay.addLayout(gridHC)
        settingsLay.addWidget(hcGroup)

        # bind handcrafted-only params
        self.param_widgets.update({
            "radiomics_BinSize": binSizeSpin,
            "radiomics_feature_value_mode": fvm,
            "radiomics_DataType": dtype,
            "radiomics_DiscType": discType,
            "radiomics_isScale": self.param_widgets.get("radiomics_isScale", None),  # already set by mkchk
            "radiomics_VoxInterp": voxI,
            "radiomics_ROIInterp": roiI,
            "radiomics_isotVoxSize": iso3D,
            "radiomics_isotVoxSize2D": iso2D,
            "radiomics_isIsot2D": self.param_widgets.get("radiomics_isIsot2D", None),
            "radiomics_isGLround": self.param_widgets.get("radiomics_isGLround", None),
            "radiomics_isReSegRng": self.param_widgets.get("radiomics_isReSegRng", None),
            "radiomics_isOutliers": self.param_widgets.get("radiomics_isOutliers", None),
            "radiomics_isQuntzStat": self.param_widgets.get("radiomics_isQuntzStat", None),
            "radiomics_ReSegIntrvl01": reSeg01Edit,
            "radiomics_ReSegIntrvl02": reSeg02Edit,
            "radiomics_ROI_PV": roiPvSpin,
            "radiomics_qntz": qntzCombo,
            "radiomics_IVH_Type": ivhType,
            "radiomics_IVH_DiscCont": ivhDisc,
            "radiomics_IVH_binSize": ivhBin,
        })

        settingsTab.addWidget(settingsGroup)

        # -------------------------------
        # Feature Subset tab (categories & dimensions)
        # -------------------------------
        DIM_OPTIONS = ["all", "1st", "2D", "2_5D", "3D"]
        CAT_OPTIONS = ["diag","morph","ip","stat","ih","ivh","glcm","glrlm","glszm","gldzm","ngtdm","ngldm","mi"]
        DIM_TO_CATS = {
            "1st":  ["morph", "ip", "stat", "ih", "ivh"],
            "2d":   ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
            "2_5d": ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
            "3d":   ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
        }

        selGroup = qt.QGroupBox("Feature Subset")
        selGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        selGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        selLay = qt.QHBoxLayout(selGroup); selLay.setContentsMargins(6,6,6,6); selLay.setSpacing(15)

        cats_default = str(RDEF.get('categories', 'all'))
        catWidget, checks = self._build_categories_panel(CAT_OPTIONS, cats_default)
        self.categoryChecks = checks

        dims_default = str(RDEF.get('dimensions', 'all'))
        dimWidget, dchecks = self._build_dimensions_panel(DIM_OPTIONS, dims_default)
        self.dimensionChecks = dchecks

        selLay.addWidget(catWidget, 3)
        selLay.addWidget(dimWidget, 2)
        selectTab.addWidget(selGroup)

        self._categoryByName = {self._wtext(cb).strip().lower(): cb for cb in self.categoryChecks}
        self._dimensionByName = {self._wtext(cb).strip().lower(): cb for cb in self.dimensionChecks}
        from functools import partial
        for cb in self.dimensionChecks:
            cb.toggled.connect(partial(self._on_dimension_changed, DIM_TO_CATS))
        qt.QTimer.singleShot(0, lambda: self._on_dimension_changed(DIM_TO_CATS))

        # -------------------------------
        # Extraction Mode tab
        # -------------------------------
        deepGroup = qt.QGroupBox("Feature Extraction Mode")
        deepGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        deepGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        deepLay = qt.QVBoxLayout(deepGroup); deepLay.setSpacing(10)

        extrMode = qt.QComboBox()
        # Show pretty labels, map to canonical on submit
        extrMode.addItems(["handcrafted feature","deep feature"])
        # default
        pretty_default = "handcrafted feature" if str(RDEF.get('extraction_mode', "handcrafted_feature")).replace("_"," ") == "handcrafted feature" else "deep feature"
        self._set_combo_safe(extrMode, pretty_default)

        deepModel   = qt.QComboBox(); deepModel.addItems(["resnet50","vgg16","densenet121","none"])
        self._set_combo_safe(deepModel, RDEF.get('deep_learning_model', "none"))

        optParams   = qt.QLineEdit(); optParams.setPlaceholderText("key1=val1; key2=val2 ... (optional)")
        optParams.setText(str(RDEF.get('optional_params', "")))
        self._shrink_editor(optParams, fixed_width=280)

        row = qt.QWidget()
        rowLay = qt.QHBoxLayout(row); rowLay.setContentsMargins(0,0,0,0); rowLay.setSpacing(12)
        rowLay.addWidget(qt.QLabel("Extraction Mode")); rowLay.addWidget(self._shrink_editor(extrMode))
        rowLay.addSpacing(10)
        rowLay.addWidget(qt.QLabel("Deep Model"));      rowLay.addWidget(self._shrink_editor(deepModel))
        rowLay.addStretch(1)
        deepLay.addWidget(row)

        deepLay.addWidget(qt.QLabel("Optional Params"))
        deepLay.addWidget(optParams)

        deepTab.addWidget(deepGroup)

        self.param_widgets.update({
            "radiomics_extraction_mode": extrMode,          # pretty → canonical handled in onCompute()
            "radiomics_deep_learning_model": deepModel,
            "radiomics_optional_params": optParams,
        })

        # Disable handcrafted-only panels when deep feature is selected
        def _toggle_for_mode():
            pretty = self._combo_text_safe(extrMode).strip().lower()
            canonical = "handcrafted_feature" if "handcrafted" in pretty else "deep_feature"
            is_hand = (canonical == "handcrafted_feature")
            hcGroup.setEnabled(is_hand)  # handcrafted-only settings group
            selGroup.setEnabled(is_hand)  # feature subset tab group (categories/dimensions)

        # Call once after widgets are created:
        _toggle_for_mode()

        # Use a signal that exists everywhere:
        extrMode.currentIndexChanged.connect(lambda *_: _toggle_for_mode())

        # -------------------------------
        # Run and Results tab
        # -------------------------------
        runGroup = qt.QGroupBox("Run and Results")
        runGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        runGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay = qt.QVBoxLayout(runGroup); runLay.setSpacing(10)

        topRow = qt.QWidget()
        topLay = qt.QHBoxLayout(topRow); topLay.setContentsMargins(0,0,0,0); topLay.setSpacing(10)
        self.computeButton = qt.QPushButton("Apply")
        self.computeButton.setMinimumHeight(30)
        self.computeButton.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Maximum)
        self.computeButton.clicked.connect(self.onCompute)
        self.statusLabel = qt.QLabel("Ready.")
        self.statusLabel.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        self.statusLabel.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        topLay.addWidget(self.computeButton)
        topLay.addWidget(self.statusLabel, 1)
        runLay.addWidget(topRow)

        self.summaryTable = qt.QTableWidget(); self.summaryTable.setColumnCount(2)
        self.summaryTable.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.summaryTable.horizontalHeader().setStretchLastSection(True)
        self.summaryTable.verticalHeader().setVisible(False)
        self.summaryTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.summaryTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.summaryTable.setAlternatingRowColors(True)
        self.summaryTable.setMaximumHeight(140)
        runLay.addWidget(qt.QLabel("Summary:")); runLay.addWidget(self.summaryTable)

        self.featureTable = qt.QTableWidget(); self.featureTable.setColumnCount(2)
        self.featureTable.setHorizontalHeaderLabels(["Feature", "Value"])
        self.featureTable.horizontalHeader().setStretchLastSection(True)
        self.featureTable.verticalHeader().setVisible(False)
        self.featureTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.featureTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.featureTable.setAlternatingRowColors(True)
        self.featureTable.setMinimumHeight(220)
        self.featureTable.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay.addWidget(qt.QLabel("Extracted Features:")); runLay.addWidget(self.featureTable, 1)

        runTab.addWidget(runGroup)

    # -------------------------------
    # Compute handler
    # -------------------------------
    def onCompute(self):
        import time
        import pandas as pd

        image_path = self.imagePathEdit.currentPath
        mask_path  = self.maskPathEdit.currentPath

        if not image_path:
            self.statusLabel.text = "Please select an image."
            self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
            logger.warning("No image selected.")
            return

        params = {}
        params["radiomics_destination_folder"] = self.outputDirEdit.currentPath or RDEF.get('destination_folder', "./output_result")
        params["radiomics_temporary_files_path"] = self.tmpDirEdit.currentPath or RDEF.get('temporary_files_path', "./temporary_files_path")

        # Categories/dimensions (union/all logic)
        total = len(getattr(self, "categoryChecks", []))
        selected = [self._wtext(cb) for cb in getattr(self, "categoryChecks", []) if cb.isChecked()]
        params["radiomics_categories"] = "all" if (not selected or (total and len(selected) == total)) else ",".join(selected)

        dtotal = len(getattr(self, "dimensionChecks", []))
        dselected = [self._wtext(cb) for cb in getattr(self, "dimensionChecks", []) if cb.isChecked()]
        params["radiomics_dimensions"] = "all" if (not dselected or (dtotal and len(dselected) == dtotal)) else ",".join(dselected)

        # Read standard widgets
        for key, widget in self.param_widgets.items():
            if widget is None:
                continue
            params[key] = self._val_from_widget(widget)

        # Map pretty UI value → canonical extraction_mode
        pretty = params.get("radiomics_extraction_mode", "handcrafted feature").strip().lower()
        params["radiomics_extraction_mode"] = "handcrafted_feature" if "handcrafted" in pretty else "deep_feature"

        self.statusLabel.text = "Computing features..."
        self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
        qt.QApplication.processEvents()

        try:
            t0 = time.time()
            output_csv, result = self.logic.run_single_pair(image_path, mask_path, params)
            dt = time.time() - t0

            self.statusLabel.text = f"Features saved to: {output_csv}"
            self.statusLabel.setStyleSheet("color: green; font-weight: bold;")

            self.summaryTable.setRowCount(0)
            summary_data = {
                "output_path": output_csv,
                "processed_files": (result.get("processed_files", "N/A") if isinstance(result, dict) else "N/A"),
                "features_extracted": (result.get("features_extracted", "N/A") if isinstance(result, dict) else "N/A"),
                "processing_time (s)": round(dt, 3)
            }
            for i, (k, v) in enumerate(summary_data.items()):
                self.summaryTable.insertRow(i)
                self.summaryTable.setItem(i, 0, qt.QTableWidgetItem(str(k)))
                self.summaryTable.setItem(i, 1, qt.QTableWidgetItem(str(v)))

            self.featureTable.setRowCount(0); self.featureTable.setColumnCount(0)
            df = None
            if isinstance(result, dict) and "features_extracted" in result:
                try:
                    import pandas as _pd
                    if isinstance(result["features_extracted"], _pd.DataFrame):
                        df = result["features_extracted"]
                except Exception:
                    df = None

            if df is None:
                try:
                    df = pd.read_csv(output_csv)
                except Exception as e:
                    logger.error(f"Failed to read features from CSV: {e}")
                    self.statusLabel.text = f"Failed to read features from CSV: {e}"
                    self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                    return

            if df is not None:
                df = df.T
                self.featureTable.setRowCount(len(df))
                self.featureTable.setColumnCount(len(df.columns) + 1)
                self.featureTable.setHorizontalHeaderLabels(["Feature"] + [f"Sample {i+1}" for i in range(len(df.columns))])
                for i, (feat_name, row) in enumerate(df.iterrows()):
                    self.featureTable.setItem(i, 0, qt.QTableWidgetItem(str(feat_name)))
                    for j, val in enumerate(row):
                        if pd.isna(val): val = "NaN"
                        self.featureTable.setItem(i, j+1, qt.QTableWidgetItem(str(val)))

        except Exception as e:
            self.statusLabel.text = f"Error: {e}"
            self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
            logger.error(f"Feature computation failed: {e}")

# -------------------------------
# Tests
# -------------------------------
class PySeraTest(ScriptedLoadableModuleTest):
    def runTest(self):
        self.delayDisplay("Running PySera tests...")
        try:
            logic = PySERALogic()
            assert logic is not None
            self.delayDisplay("PySERALogic instantiation: OK")
            logger.info("PySERALogic instantiation test passed")
        except Exception as e:
            self.delayDisplay(f"Test failed: {e}")
            logger.error(f"PySeraTest failed: {e}")


