# -*- coding: utf-8 -*-
# PySERA ScriptedLoadableModule for 3D Slicer

# Packaging-safe rules:
# - No pip-dependency imports at file level (pysera, yaml, pandas, etc.)
# - Only install/import pip packages inside Logic at runtime
# - Parameters loaded from: <ThisModuleDir>/parameters.yaml or parameters.json

# UI rules:
# - "Extracted Features" table must show ONLY two columns: Feature | Value (read-only)
# - Categories/Dimensions: NO per-panel Select/Clear buttons; use ONE global Select/Clear outside
# - Support both: (A) single image+mask files, (B) folder batch inputs
# - Keep Value column narrow; prevent first column from stretching too wide

import os
import json
import datetime
import random
import logging
import importlib
import csv
import time

import qt, ctk, slicer
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleTest,
)

# -------------------------------
# UI Text (single source of truth)
# -------------------------------
UI_TEXT = {
    # Tabs
    "tab_io": "Input/Output",
    "tab_mode": "Extraction Mode",
    "tab_settings": "Advanced Settings",
    "tab_select": "Feature Selection",
    "tab_run": "Run and Results",
    # Groups
    "grp_inputs_outputs": "Inputs / Outputs",
    "grp_common": "Common Settings",
    "grp_handcrafted": "Handcrafted Radiomics Settings",
    "grp_selection": "Feature Selection",
    "grp_results": "Results",
    # Input type
    "lbl_input_type": "Input Type",
    "opt_single": "Single Case (Image + Mask)",
    "opt_batch": "Batch Processing (Folders)",
    # I/O Labels
    "lbl_image": "Image File",
    "lbl_mask": "Mask File",
    "lbl_image_folder": "Image Folder",
    "lbl_mask_folder": "Mask Folder",
    "lbl_output_folder": "Output Folder",
    # Buttons
    "btn_run": "Run",
    "btn_select_all": "Select All",
    "btn_clear_all": "Clear All",
    # Results
    "lbl_summary": "Summary",
    "lbl_extracted": "Extracted Features",
    # Common settings
    "chk_preprocess": "Enable Preprocessing",
    "chk_parallel": "Enable Parallel Processing",
    "chk_aggregate": "Aggregate per ROI",
    "lab_workers": "Worker Processes",
    "lab_min_roi": "Minimum ROI Volume",
    "lab_roi_mode": "ROI Selection Mode",
    "lab_log_level": "Log Level",
    # Feature selection panels
    "panel_categories": "Categories",
    "panel_dimensions": "Dimensions",
    # Extraction mode
    "lab_extraction_mode": "Extraction Mode",
    "lab_deep_model": "Deep Model",
    "mode_hand": "Handcrafted Radiomics",
    "mode_deep": "Deep Features",
}

# -------------------------------
# Logger Helper
# -------------------------------
class Logger:
    def __init__(self, name="PySERA"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        if not self.logger.handlers:
            console = logging.StreamHandler()
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(console)

    def info(self, msg):
        self._emit(self.logger.info, msg)

    def debug(self, msg):
        self._emit(self.logger.debug, msg)

    def warning(self, msg):
        self._emit(self.logger.warning, msg)

    def error(self, msg):
        self._emit(self.logger.error, msg)

    @staticmethod
    def _emit(fn, msg):
        fn(msg)
        try:
            slicer.app.processEvents()
        except Exception:
            pass


logger = Logger()

# -------------------------------
# Parameters loader (import-safe)
# -------------------------------
MODULE_DIR = os.path.dirname(__file__)
YAML_PATH = os.path.join(MODULE_DIR, "parameters.yaml")
JSON_PATH = os.path.join(MODULE_DIR, "parameters.json")


def _load_yaml_if_possible(path: str) -> dict:
    """
    Import-safe YAML loader:
    - Do NOT install PyYAML here.
    - If PyYAML isn't available, return {} so we can fall back to JSON.
    """
    try:
        yaml = importlib.import_module("yaml")
    except Exception:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def load_parameters() -> dict:
    """
    Load config from YAML (if readable) else JSON else {}.
    Called at module import time, so it must be safe.
    """
    logger.debug(f"MODULE_DIR: {MODULE_DIR}")
    logger.debug(f"YAML_PATH: {YAML_PATH} (exists={os.path.exists(YAML_PATH)})")
    logger.debug(f"JSON_PATH: {JSON_PATH} (exists={os.path.exists(JSON_PATH)})")

    try:
        if os.path.exists(YAML_PATH):
            cfg = _load_yaml_if_possible(YAML_PATH)
            if cfg:
                logger.info(f"Parameters loaded from {YAML_PATH}")
                return cfg

        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f) or {}
            logger.info(f"Parameters loaded from {JSON_PATH}")
            return cfg

        logger.warning("No parameter file found (parameters.yaml or parameters.json). Using empty defaults.")
        return {}
    except Exception as e:
        logger.error(f"Failed to load parameters: {e}")
        return {}


CFG_FILE = load_parameters()
RDEF = CFG_FILE.get("radiomics") or {}
CLI_MAP = CFG_FILE.get("cli_key_map") or {}

# -------------------------------
# Slicer module metadata
# -------------------------------
class PySera(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = "PySERA"
        self.parent.categories = ["Analysis"]
        self.parent.dependencies = []
        self.parent.contributors = ["Mohammad R. Salmanpour", "Sirwan Barichin"]
        self.parent.helpText = "PySERA radiomics feature extraction integrated into 3D Slicer."
        self.parent.acknowledgementText = "Thanks to the 3D Slicer community."


# -------------------------------
# Logic
# -------------------------------
class PySERALogic(ScriptedLoadableModuleLogic):

    # ---------- pip install/import helpers ----------
    @staticmethod
    def _ensure_package_available(package_name: str, import_name: str = None):
        import_name = import_name or package_name
        try:
            importlib.import_module(import_name)
            return
        except Exception:
            pass

        try:
            logger.info(f"Installing '{package_name}' via slicer.util.pip_install ...")
            slicer.util.pip_install(package_name)
            importlib.import_module(import_name)
            logger.info(f"'{package_name}' installed and importable.")
        except Exception as e:
            raise ImportError(f"Python package '{package_name}' is required but could not be installed.") from e

    @staticmethod
    def _import_pysera():
        PySERALogic._ensure_package_available("pysera", "pysera")
        return importlib.import_module("pysera")

    @staticmethod
    def _normalize(v):
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
                    out.append(None)
                    continue
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
        for k, v in (CFG_FILE or {}).items():
            if isinstance(k, str) and k.startswith("radiomics_"):
                cfg[k] = v
        cfg.update(params_from_ui or {})
        return cfg

    def _build_cli_kwargs(self, cfg: dict) -> dict:
        cli = {}
        passthru_str = {"categories", "dimensions", "extraction_mode", "deep_learning_model", "report"}

        for src_key, dst_key in (CLI_MAP or {}).items():
            if src_key not in cfg:
                continue
            raw = cfg[src_key]
            if raw is None or raw == "":
                continue

            if dst_key in passthru_str:
                cli[dst_key] = str(raw)
            else:
                val = self._normalize(raw)
                if val is not None and val != "":
                    cli[dst_key] = val

        cli["extraction_mode"] = str(cfg.get("radiomics_extraction_mode", "handcrafted_feature"))

        model = cfg.get("radiomics_deep_learning_model", None)
        if model is not None and str(model).strip().lower() not in {"", "none"}:
            cli["deep_learning_model"] = str(model)

        rep = cfg.get("radiomics_report", None)
        if rep is not None and str(rep).strip() != "":
            cli["report"] = str(rep)

        return cli

    @staticmethod
    def _configure_logging_level(cfg: dict):
        level_map = {
            "none": logging.CRITICAL + 1,
            "error": logging.ERROR,
            "warning": logging.WARNING,
            "info": logging.INFO,
            "all": logging.DEBUG,
        }
        report_sel = str(cfg.get("radiomics_report", "all")).strip().lower()
        level = level_map.get(report_sel, logging.DEBUG)
        logger.logger.setLevel(level)
        for h in logger.logger.handlers:
            h.setLevel(level)

    def _make_output_csv(self, cfg: dict, prefix: str):
        out_dir = cfg.get("radiomics_destination_folder") or os.path.join(
            os.path.expanduser("~"), "Desktop", "output_result"
        )
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        random_suffix = random.randint(1000, 9999)
        output_csv = os.path.join(out_dir, f"{prefix}_{timestamp}_{random_suffix}.csv")

        logger.debug(f"Output directory: {out_dir}")
        logger.info(f"Output CSV path: {output_csv}")
        return output_csv

    def _run_process_batch(self, image_input, mask_input, cfg: dict):
        pysera = self._import_pysera()
        cli_kwargs = self._build_cli_kwargs(cfg)
        cli_kwargs.setdefault("categories", str(cfg.get("radiomics_categories", "all")))
        cli_kwargs.setdefault("dimensions", str(cfg.get("radiomics_dimensions", "all")))
        self._configure_logging_level(cfg)

        return pysera.process_batch(
            image_input=image_input,
            mask_input=mask_input,
            output_path=cfg["_output_csv_path"],
            **cli_kwargs,
        )

    def run_single_case(self, image_path, mask_path, params=None):
        cfg = self._compose_cfg(params)
        cfg["_output_csv_path"] = self._make_output_csv(cfg, "extracted_radiomics_features")
        result = self._run_process_batch(image_path, mask_path, cfg)
        logger.info(f"Feature extraction completed: {cfg['_output_csv_path']}")
        return cfg["_output_csv_path"], result

    def run_batch_folders(self, image_folder, mask_folder, params=None):
        cfg = self._compose_cfg(params)
        cfg["_output_csv_path"] = self._make_output_csv(cfg, "extracted_radiomics_features_BATCH")
        result = self._run_process_batch(image_folder, mask_folder, cfg)
        logger.info(f"Batch feature extraction completed: {cfg['_output_csv_path']}")
        return cfg["_output_csv_path"], result

    # ---------- Result → (Feature, Value) rows ----------
    def feature_rows_from_result(self, result):
        if not isinstance(result, dict):
            return []

        fx = result.get("features_extracted", None)
        if fx is None:
            return []

        def _filter_meta(pairs):
            drop = {"patientid", "roi", "case", "subject", "image", "mask"}
            out = []
            for k, v in pairs:
                if str(k).strip().lower() in drop:
                    continue
                out.append([k, v])
            return out

        # DataFrame-like (duck-typing)
        try:
            has_columns = hasattr(fx, "columns")
            has_to_dict = hasattr(fx, "to_dict") and callable(getattr(fx, "to_dict"))
            if has_columns and has_to_dict:
                row_dict = None
                try:
                    recs = fx.to_dict(orient="records")
                    if recs and isinstance(recs[0], dict):
                        row_dict = recs[0]
                except Exception:
                    row_dict = None

                if row_dict is None and hasattr(fx, "iloc"):
                    try:
                        row_dict = fx.iloc[0].to_dict()
                    except Exception:
                        row_dict = None

                if row_dict is None:
                    try:
                        col_map = fx.to_dict()
                        row_dict = {}
                        for k, v in col_map.items():
                            if isinstance(v, dict) and v:
                                row_dict[k] = next(iter(v.values()))
                            else:
                                row_dict[k] = v
                    except Exception:
                        row_dict = None

                if isinstance(row_dict, dict) and row_dict:
                    try:
                        cols = list(fx.columns)
                    except Exception:
                        cols = list(row_dict.keys())
                    pairs = [(str(c), row_dict.get(c)) for c in cols]
                    return _filter_meta(pairs)
        except Exception:
            pass

        if isinstance(fx, dict):
            keys = list(fx.keys())
            try:
                keys.sort()
            except Exception:
                pass
            return _filter_meta([(str(k), fx[k]) for k in keys])

        if isinstance(fx, list):
            # 2×N -> transpose
            if (
                len(fx) == 2
                and isinstance(fx[0], (list, tuple))
                and isinstance(fx[1], (list, tuple))
                and len(fx[0]) == len(fx[1])
                and len(fx[0]) > 0
            ):
                names = fx[0]
                values = fx[1]
                return _filter_meta([(str(names[i]), values[i]) for i in range(len(names))])

            pairs = []
            for item in fx:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    pairs.append((str(item[0]), item[1]))
                elif isinstance(item, dict):
                    if "feature" in item and "value" in item:
                        pairs.append((str(item["feature"]), item["value"]))
                    else:
                        for k, v in item.items():
                            pairs.append((str(k), v))
            return _filter_meta(pairs)

        if isinstance(fx, str):
            s = fx.strip()
            try:
                obj = json.loads(s)
                if isinstance(obj, dict):
                    keys = list(obj.keys())
                    try:
                        keys.sort()
                    except Exception:
                        pass
                    return _filter_meta([(str(k), obj[k]) for k in keys])
            except Exception:
                pass
            return [["features_extracted", fx]]

        return [["features_extracted", str(fx)]]

    # ---------- CSV fallback ----------
    @staticmethod
    def _wait_for_readable_file(path: str, retries: int = 160, delay: float = 0.25):
        last_err = None
        for _ in range(retries):
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    with open(path, "r", encoding="utf-8", newline=""):
                        return True
            except Exception as e:
                last_err = e
            time.sleep(delay)
        if last_err:
            raise last_err
        return False

    def load_features_as_feature_value_rows(self, output_csv: str):
        ok = self._wait_for_readable_file(output_csv)
        if not ok:
            return []

        with open(output_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)

        if not rows:
            return []

        header = rows[0]
        header_l = [h.strip().lower() for h in header]

        # long format: Feature,Value
        if len(header) >= 2 and header_l[0] in ("feature", "name") and header_l[1] in ("value", "val"):
            out = []
            for r in rows[1:]:
                if len(r) >= 2:
                    out.append([r[0], r[1]])
            return out

        # wide format: headers are features, 2nd row contains values
        if len(rows) >= 2 and len(rows[1]) == len(header) and len(header) >= 2:
            values = rows[1]
            return [[header[i], values[i]] for i in range(len(header))]

        out = []
        for r in rows[1:]:
            if not r:
                continue
            out.append([",".join(r), ""])
        return out

# -------------------------------
# Widget
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
        self._csvPollRemaining = 0
        self._ignoreDimSync = False

    # ---------- helpers ----------
    @staticmethod
    def _wtext(widget) -> str:
        # Some Qt wrappers expose .text as property (string), others as method.
        try:
            t = getattr(widget, "text", "")
            if callable(t):
                return t()
            if isinstance(t, str):
                return t
            return str(t)
        except Exception:
            return ""

    @staticmethod
    def _val_from_widget(w):
        if isinstance(w, qt.QCheckBox):
            return 1 if w.isChecked() else 0
        if isinstance(w, (qt.QSpinBox, qt.QDoubleSpinBox)):
            return w.value() if callable(getattr(w, "value", None)) else w.value
        if isinstance(w, qt.QComboBox):
            return w.currentText() if callable(getattr(w, "currentText", None)) else str(w.currentText)
        if isinstance(w, qt.QLineEdit):
            return w.text() if callable(getattr(w, "text", None)) else str(getattr(w, "text", ""))
        return ""

    @staticmethod
    def _set_combo_safe(combo: qt.QComboBox, value: str):
        if value is None:
            return
        try:
            count = combo.count
        except Exception:
            count = combo.count()
        for i in range(count):
            try:
                it = combo.itemText(i)
            except Exception:
                it = combo.itemText(i)
            if str(it).lower() == str(value).lower():
                combo.setCurrentIndex(i)
                return

    def _combo_text_safe(self, combo: qt.QComboBox) -> str:
        try:
            return combo.currentText()
        except Exception:
            return str(getattr(combo, "currentText", ""))

    @staticmethod
    def _shrink_editor(w, fixed_width=160):
        if isinstance(w, (qt.QLineEdit, qt.QComboBox, qt.QSpinBox, qt.QDoubleSpinBox)):
            w.setFixedWidth(int(fixed_width))
            w.setSizePolicy(qt.QSizePolicy.Fixed, qt.QSizePolicy.Preferred)
        return w

    def _add_two_grid(self, grid: qt.QGridLayout, row: int, label1: str, widget1, label2: str, widget2):
        lbl1 = qt.QLabel(label1)
        lbl2 = qt.QLabel(label2)
        lbl1.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Preferred)
        lbl2.setSizePolicy(qt.QSizePolicy.Maximum, qt.QSizePolicy.Preferred)
        w1 = self._shrink_editor(widget1)
        w2 = self._shrink_editor(widget2)
        grid.addWidget(lbl1, row, 0)
        grid.addWidget(w1, row, 1)
        grid.addWidget(lbl2, row, 2)
        grid.addWidget(w2, row, 3)

    def _build_check_grid_panel(self, title, options, default_str):
        gb = qt.QGroupBox(title)
        gb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        v = qt.QVBoxLayout(gb)

        grid = qt.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(15)
        grid.setVerticalSpacing(4)

        checks = []
        cols = 4
        default_all = (str(default_str).strip().lower() == "all")
        wanted = set()
        if not default_all and isinstance(default_str, str):
            wanted = {x.strip().lower() for x in default_str.split(",") if x.strip()}

        for idx, name in enumerate(options):
            cb = qt.QCheckBox(name)
            cb.setChecked(True if default_all else (name.lower() in wanted))
            r = idx // cols
            c = idx % cols
            grid.addWidget(cb, r, c)
            checks.append(cb)

        v.addLayout(grid)
        return gb, checks

    def _on_dimension_changed(self, dim_to_cats: dict, *_):
        if getattr(self, "_ignoreDimSync", False):
            return

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

    @staticmethod
    def _shorten_for_cell(v, max_len=90):
        s = "" if v is None else str(v)
        s = s.replace("\n", " ").strip()
        if len(s) <= max_len:
            return s
        return s[: max_len - 1] + "…"

    def _polish_table_after_fill(self, table: qt.QTableWidget):
        """
        Call after filling table to force a stable/clean layout.
        Prevents header jitter and makes sure stretch/fixed works.
        """
        table.setUpdatesEnabled(False)
        try:
            table.resizeRowsToContents()
            # keep rows from becoming too tall
            for r in range(table.rowCount):
                if table.rowHeight(r) > 26:
                    table.setRowHeight(r, 26)
        except Exception:
            pass
        table.setUpdatesEnabled(True)
        table.viewport().update()

    def _apply_two_column_widths(
            self,
            table: qt.QTableWidget,
            value_width: int = 220,
            min_feature_width: int = 180,
    ):
        """
        Standard 2-column table layout:
          - Column 0 (Feature/Parameter): Stretch (fills remaining space)
          - Column 1 (Value): Fixed width
          - No weird auto-resize jumps
          - Nice headers + elide long text
        """

        # ---- general table look ----
        table.setWordWrap(False)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(False)
        table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)

        # compact rows
        try:
            table.verticalHeader().setDefaultSectionSize(22)
        except Exception:
            pass
        table.verticalHeader().setVisible(False)

        # ellipsis for long text
        try:
            table.setTextElideMode(qt.Qt.ElideRight)
        except Exception:
            pass

        # ---- header behavior ----
        header = table.horizontalHeader()
        header.setStretchLastSection(False)

        # Column 0: stretch, Column 1: fixed
        try:
            header.setSectionResizeMode(0, qt.QHeaderView.Stretch)
            header.setSectionResizeMode(1, qt.QHeaderView.Fixed)
        except Exception:
            # older Qt API fallback
            try:
                header.setResizeMode(0, qt.QHeaderView.Stretch)
                header.setResizeMode(1, qt.QHeaderView.Fixed)
            except Exception:
                pass

        table.setColumnWidth(1, int(value_width))

        # ensure column 0 doesn't collapse too small
        try:
            table.setColumnWidth(0, int(min_feature_width))
        except Exception:
            pass

    def _make_scroll_tab(self, title: str, tabs: qt.QTabWidget):
        page = qt.QWidget()
        page.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        page_v = qt.QVBoxLayout(page)
        page_v.setContentsMargins(6, 6, 6, 6)
        page_v.setSpacing(10)

        scroll = qt.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qt.QFrame.NoFrame)
        scroll.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)

        inner = qt.QWidget()
        inner.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        inner_v = qt.QVBoxLayout(inner)
        inner_v.setContentsMargins(0, 0, 0, 0)
        inner_v.setSpacing(10)

        scroll.setWidget(inner)
        page_v.addWidget(scroll)
        tabs.addTab(page, title)
        return inner_v

    def _fill_extracted_features_table(self, rows):
        self.featureTable.clear()
        self.featureTable.setRowCount(0)
        self.featureTable.setColumnCount(2)
        self.featureTable.setHorizontalHeaderLabels(["Feature", "Value"])

        for feat, val in rows:
            r = self.featureTable.rowCount
            self.featureTable.insertRow(r)
            self.featureTable.setItem(r, 0, qt.QTableWidgetItem("" if feat is None else str(feat)))
            self.featureTable.setItem(r, 1, qt.QTableWidgetItem(self._shorten_for_cell(val, 120)))

        self._apply_two_column_widths(self.featureTable, value_width=200, min_feature_width=260)
        self._polish_table_after_fill(self.featureTable)

    def _fill_summary_table(self, items):
        self.summaryTable.clear()
        self.summaryTable.setRowCount(0)
        self.summaryTable.setColumnCount(2)
        self.summaryTable.setHorizontalHeaderLabels(["Parameter", "Value"])

        for i, (k, v) in enumerate(items):
            self.summaryTable.insertRow(i)
            self.summaryTable.setItem(i, 0, qt.QTableWidgetItem(str(k)))
            self.summaryTable.setItem(i, 1, qt.QTableWidgetItem(self._shorten_for_cell(v, 80)))

        self._apply_two_column_widths(self.summaryTable, value_width=260, min_feature_width=220)
        self._polish_table_after_fill(self.summaryTable)

    def _poll_csv_until_ready(self, output_csv, tries=160, interval_ms=250):
        self._csvPollRemaining = tries

        def _tick():
            self._csvPollRemaining -= 1
            try:
                rows = self.logic.load_features_as_feature_value_rows(output_csv)
                if rows:
                    self._fill_extracted_features_table(rows)
                    self.statusLabel.setText(f"Done. Loaded features from CSV.")
                    self.statusLabel.setStyleSheet("color: green; font-weight: bold;")
                    logger.info(f"Loaded features from CSV: {output_csv}")
                    print(f"[PySera] Loaded features from CSV: {output_csv}")
                    return
            except Exception:
                pass

            if self._csvPollRemaining > 0:
                qt.QTimer.singleShot(interval_ms, _tick)
            else:
                self._fill_extracted_features_table([["Error", "Could not load features (CSV not ready/locked)"]])
                self.statusLabel.setText("Error: CSV was not ready in time.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                logger.error(f"CSV not ready in time: {output_csv}")
                print(f"[PySera] CSV not ready in time: {output_csv}")

        self.statusLabel.setText("Running... waiting for output file to finalize.")
        self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
        qt.QTimer.singleShot(interval_ms, _tick)

    def setup(self):
        super().setup()
        root = self.layout
        root.setSpacing(10)

        tabs = qt.QTabWidget()
        tabs.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        root.addWidget(tabs, 1)

        ioTab = self._make_scroll_tab(UI_TEXT["tab_io"], tabs)
        deepTab = self._make_scroll_tab(UI_TEXT["tab_mode"], tabs)
        settingsTab = self._make_scroll_tab(UI_TEXT["tab_settings"], tabs)
        selectTab = self._make_scroll_tab(UI_TEXT["tab_select"], tabs)
        runTab = self._make_scroll_tab(UI_TEXT["tab_run"], tabs)

        # -----------------------------
        # Input/Output
        # -----------------------------
        ioGroup = qt.QGroupBox(UI_TEXT["grp_inputs_outputs"])
        ioGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        ioGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        ioForm = qt.QFormLayout(ioGroup)

        # Input type selector
        self.inputModeGroup = qt.QButtonGroup()
        self.singleModeRadio = qt.QRadioButton(UI_TEXT["opt_single"])
        self.folderModeRadio = qt.QRadioButton(UI_TEXT["opt_batch"])
        self.singleModeRadio.setChecked(True)
        self.inputModeGroup.addButton(self.singleModeRadio, 0)
        self.inputModeGroup.addButton(self.folderModeRadio, 1)

        modeRow = qt.QWidget()
        modeLay = qt.QHBoxLayout(modeRow)
        modeLay.setContentsMargins(0, 0, 0, 0)
        modeLay.setSpacing(12)
        modeLay.addWidget(qt.QLabel(UI_TEXT["lbl_input_type"] + ":"))
        modeLay.addWidget(self.singleModeRadio)
        modeLay.addWidget(self.folderModeRadio)
        modeLay.addStretch(1)
        ioForm.addRow(modeRow)

        # Single file inputs
        self.imagePathEdit = ctk.ctkPathLineEdit()
        self.imagePathEdit.filters = ctk.ctkPathLineEdit.Files
        self.maskPathEdit = ctk.ctkPathLineEdit()
        self.maskPathEdit.filters = ctk.ctkPathLineEdit.Files
        ioForm.addRow(UI_TEXT["lbl_image"] + ":", self.imagePathEdit)
        ioForm.addRow(UI_TEXT["lbl_mask"] + ":", self.maskPathEdit)

        # Folder inputs (batch mode)
        self.imageFolderEdit = ctk.ctkPathLineEdit()
        self.imageFolderEdit.filters = ctk.ctkPathLineEdit.Dirs
        self.maskFolderEdit = ctk.ctkPathLineEdit()
        self.maskFolderEdit.filters = ctk.ctkPathLineEdit.Dirs
        ioForm.addRow(UI_TEXT["lbl_image_folder"] + ":", self.imageFolderEdit)
        ioForm.addRow(UI_TEXT["lbl_mask_folder"] + ":", self.maskFolderEdit)

        # Output dirs
        self.outputDirEdit = ctk.ctkPathLineEdit()
        self.outputDirEdit.filters = ctk.ctkPathLineEdit.Dirs
        self.tmpDirEdit = ctk.ctkPathLineEdit()
        self.tmpDirEdit.filters = ctk.ctkPathLineEdit.Dirs

        self.outputDirEdit.currentPath = RDEF.get("destination_folder", "./output_result")

        ioForm.addRow(UI_TEXT["lbl_output_folder"] + ":", self.outputDirEdit)

        def _update_input_mode_ui(*_):
            is_single = self.singleModeRadio.isChecked()
            self.imagePathEdit.setEnabled(is_single)
            self.maskPathEdit.setEnabled(is_single)
            self.imageFolderEdit.setEnabled(not is_single)
            self.maskFolderEdit.setEnabled(not is_single)

        self.singleModeRadio.toggled.connect(_update_input_mode_ui)
        self.folderModeRadio.toggled.connect(_update_input_mode_ui)
        _update_input_mode_ui()

        ioTab.addWidget(ioGroup)

        # -----------------------------
        # Advanced Settings (clean layout)
        # -----------------------------
        settingsSection = qt.QWidget()
        settingsSection.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        settingsRoot = qt.QVBoxLayout(settingsSection)
        settingsRoot.setContentsMargins(0, 0, 0, 0)
        settingsRoot.setSpacing(10)

        # ---------- Common Settings (Collapsible) ----------
        commonColl = ctk.ctkCollapsibleButton()
        commonColl.text = UI_TEXT["grp_common"]
        commonColl.collapsed = False
        commonColl.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        commonForm = qt.QFormLayout(commonColl)
        commonForm.setLabelAlignment(qt.Qt.AlignRight)
        commonForm.setFormAlignment(qt.Qt.AlignTop)
        commonForm.setHorizontalSpacing(12)
        commonForm.setVerticalSpacing(8)

        # toggles row
        applyPreChk = qt.QCheckBox(UI_TEXT["chk_preprocess"])
        applyPreChk.setChecked(bool(RDEF.get("apply_preprocessing", False)))
        applyPreChk.setToolTip("Apply IBSI-aligned preprocessing steps before feature extraction.")

        enParChk = qt.QCheckBox(UI_TEXT["chk_parallel"])
        enParChk.setChecked(bool(RDEF.get("enable_parallelism", True)))
        enParChk.setToolTip("Enable multiprocessing (if supported).")

        aggrChk = qt.QCheckBox(UI_TEXT["chk_aggregate"])
        aggrChk.setChecked(bool(RDEF.get("aggregation_lesion", 0)))
        aggrChk.setToolTip("Aggregate features per ROI (multi-lesion support).")

        togRow = qt.QWidget()
        togLay = qt.QHBoxLayout(togRow)
        togLay.setContentsMargins(0, 0, 0, 0)
        togLay.setSpacing(14)
        togLay.addWidget(applyPreChk)
        togLay.addWidget(enParChk)
        togLay.addWidget(aggrChk)
        togLay.addStretch(1)
        commonForm.addRow(qt.QLabel(""), togRow)

        # worker processes
        numWorkersEdit = qt.QLineEdit()
        numWorkersEdit.setPlaceholderText("auto or integer")
        numWorkersEdit.setText(str(RDEF.get("num_workers", "auto")))
        numWorkersEdit.setToolTip("Number of worker processes. Use 'auto' to let PySERA decide.")

        # min ROI
        minRoiSpin = qt.QDoubleSpinBox()
        minRoiSpin.setRange(0.0, 1e12)
        minRoiSpin.setDecimals(0)
        minRoiSpin.setValue(float(RDEF.get("min_roi_volume", 10)))
        minRoiSpin.setToolTip("Minimum ROI volume threshold (mm³).")

        # ROI mode
        roiSel = qt.QComboBox()
        roiSel.addItems(["per_Img", "per_region"])
        self._set_combo_safe(roiSel, RDEF.get("roi_selection_mode", "per_Img"))
        roiSel.setToolTip("ROI grouping mode: per image or per region.")

        # log level
        reportC = qt.QComboBox()
        reportC.addItems(["none", "error", "warning", "info", "all"])
        self._set_combo_safe(reportC, RDEF.get("report", "all"))
        reportC.setToolTip("Logging verbosity.")

        # small consistent editors
        self._shrink_editor(numWorkersEdit, 160)
        self._shrink_editor(minRoiSpin, 160)
        self._shrink_editor(roiSel, 160)
        self._shrink_editor(reportC, 160)

        # arrange as two columns (nice compact form)
        row1 = qt.QWidget()
        row1Lay = qt.QHBoxLayout(row1)
        row1Lay.setContentsMargins(0, 0, 0, 0)
        row1Lay.setSpacing(12)
        row1Lay.addWidget(qt.QLabel(UI_TEXT["lab_workers"]))
        row1Lay.addWidget(numWorkersEdit)
        row1Lay.addSpacing(18)
        row1Lay.addWidget(qt.QLabel(UI_TEXT["lab_min_roi"]))
        row1Lay.addWidget(minRoiSpin)
        row1Lay.addStretch(1)
        commonForm.addRow(row1)

        row2 = qt.QWidget()
        row2Lay = qt.QHBoxLayout(row2)
        row2Lay.setContentsMargins(0, 0, 0, 0)
        row2Lay.setSpacing(12)
        row2Lay.addWidget(qt.QLabel(UI_TEXT["lab_roi_mode"]))
        row2Lay.addWidget(roiSel)
        row2Lay.addSpacing(18)
        row2Lay.addWidget(qt.QLabel(UI_TEXT["lab_log_level"]))
        row2Lay.addWidget(reportC)
        row2Lay.addStretch(1)
        commonForm.addRow(row2)

        # register widgets
        self.param_widgets.update({
            "radiomics_apply_preprocessing": applyPreChk,
            "radiomics_enable_parallelism": enParChk,
            "radiomics_aggregation_lesion": aggrChk,
            "radiomics_num_workers": numWorkersEdit,
            "radiomics_min_roi_volume": minRoiSpin,
            "radiomics_roi_selection_mode": roiSel,
            "radiomics_report": reportC,
        })

        settingsRoot.addWidget(commonColl)

        # ---------- Handcrafted Settings (Collapsible) ----------
        handColl = ctk.ctkCollapsibleButton()
        handColl.text = UI_TEXT["grp_handcrafted"]
        handColl.collapsed = True
        handColl.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        handLay = qt.QVBoxLayout(handColl)
        handLay.setContentsMargins(8, 8, 8, 8)
        handLay.setSpacing(10)

        # (A) Flags (compact grid)
        flagsBox = qt.QGroupBox("Flags")
        flagsGrid = qt.QGridLayout(flagsBox)
        flagsGrid.setHorizontalSpacing(14)
        flagsGrid.setVerticalSpacing(6)
        flagsGrid.setContentsMargins(8, 8, 8, 8)

        def mkchk(label_text: str, key: str, default_val: int = 0, tip: str = "") -> qt.QCheckBox:
            cb = qt.QCheckBox(label_text)
            cb.setChecked(bool(RDEF.get(key, default_val)))
            if tip:
                cb.setToolTip(tip)
            self.param_widgets["radiomics_" + key] = cb
            return cb

        flags = [
            mkchk("GL Round", "isGLround", 0, "Enable intensity rounding."),
            mkchk("Scale", "isScale", 0, "Enable voxel scaling/resampling."),
            mkchk("Re-segmentation Range", "isReSegRng", 0, "Enable re-segmentation by intensity range."),
            mkchk("Outlier Removal", "isOutliers", 0, "Enable outlier handling."),
            mkchk("Quantized Statistics", "isQuntzStat", 1, "Use quantized intensity statistics."),
            mkchk("2D Isotropic", "isIsot2D", 0, "Use isotropic spacing for 2D mode."),
        ]
        for i, cb in enumerate(flags):
            r = i // 3
            c = i % 3
            flagsGrid.addWidget(cb, r, c)
        for c in range(3):
            flagsGrid.setColumnStretch(c, 1)

        handLay.addWidget(flagsBox)

        # (B) Main parameters in a neat form-like grid
        paramsBox = qt.QGroupBox("Parameters")
        gridHC = qt.QGridLayout(paramsBox)
        gridHC.setContentsMargins(8, 8, 8, 8)
        gridHC.setHorizontalSpacing(12)
        gridHC.setVerticalSpacing(8)

        INTERP_OPTIONS = ["Nearest", "linear", "bilinear", "trilinear", "tricubic-spline", "cubic", "bspline", "None"]

        binSizeSpin = qt.QSpinBox()
        binSizeSpin.setRange(1, 10 ** 9)
        binSizeSpin.setValue(int(RDEF.get("BinSize", 25)))
        self._shrink_editor(binSizeSpin, 160)

        fvm = qt.QComboBox()
        fvm.addItems(["REAL_VALUE", "APPROXIMATE_VALUE"])
        self._set_combo_safe(fvm, RDEF.get("feature_value_mode", "REAL_VALUE"))
        self._shrink_editor(fvm, 160)

        dtype = qt.QComboBox()
        dtype.addItems(["CT", "MR", "PET", "OTHER"])
        self._set_combo_safe(dtype, RDEF.get("DataType", "OTHER"))
        self._shrink_editor(dtype, 160)

        discType = qt.QComboBox()
        discType.addItems(["FBS", "FBN"])
        self._set_combo_safe(discType, RDEF.get("DiscType", "FBS"))
        self._shrink_editor(discType, 160)

        voxI = qt.QComboBox()
        voxI.addItems(INTERP_OPTIONS)
        self._set_combo_safe(voxI, RDEF.get("VoxInterp", "Nearest"))
        self._shrink_editor(voxI, 160)

        roiI = qt.QComboBox()
        roiI.addItems(INTERP_OPTIONS)
        self._set_combo_safe(roiI, RDEF.get("ROIInterp", "Nearest"))
        self._shrink_editor(roiI, 160)

        iso3D = qt.QDoubleSpinBox()
        iso3D.setRange(0.0, 1e12)
        iso3D.setSingleStep(0.1)
        iso3D.setValue(float(RDEF.get("isotVoxSize", 2)))
        self._shrink_editor(iso3D, 160)

        iso2D = qt.QDoubleSpinBox()
        iso2D.setRange(0.0, 1e12)
        iso2D.setSingleStep(0.1)
        iso2D.setValue(float(RDEF.get("isotVoxSize2D", 2)))
        self._shrink_editor(iso2D, 160)

        reSeg01Edit = qt.QLineEdit()
        reSeg01Edit.setPlaceholderText("None or value")
        reSeg01Edit.setText(str(RDEF.get("ReSegIntrvl01", -1000)))
        self._shrink_editor(reSeg01Edit, 160)

        reSeg02Edit = qt.QLineEdit()
        reSeg02Edit.setPlaceholderText("None or value")
        reSeg02Edit.setText(str(RDEF.get("ReSegIntrvl02", 400)))
        self._shrink_editor(reSeg02Edit, 160)

        roiPvSpin = qt.QDoubleSpinBox()
        roiPvSpin.setRange(0.0, 1.0)
        roiPvSpin.setSingleStep(0.05)
        roiPvSpin.setValue(float(RDEF.get("ROI_PV", 0.5)))
        self._shrink_editor(roiPvSpin, 160)

        qntzCombo = qt.QComboBox()
        qntzCombo.addItems(["Uniform", "Lloyd-Max"])
        self._set_combo_safe(qntzCombo, RDEF.get("qntz", "Uniform"))
        self._shrink_editor(qntzCombo, 160)

        ivhType = qt.QSpinBox()
        ivhType.setRange(0, 10 ** 9)
        ivhType.setValue(int(RDEF.get("IVH_Type", 3)))
        self._shrink_editor(ivhType, 160)

        ivhDisc = qt.QSpinBox()
        ivhDisc.setRange(0, 10 ** 9)
        ivhDisc.setValue(int(RDEF.get("IVH_DiscCont", 1)))
        self._shrink_editor(ivhDisc, 160)

        ivhBin = qt.QDoubleSpinBox()
        ivhBin.setRange(0.0, 1e12)
        ivhBin.setSingleStep(0.1)
        ivhBin.setValue(float(RDEF.get("IVH_binSize", 2.0)))
        self._shrink_editor(ivhBin, 160)

        # helper for aligned 2x2 rows
        def add_row(row, l1, w1, l2, w2):
            gridHC.addWidget(qt.QLabel(l1), row, 0)
            gridHC.addWidget(w1, row, 1)
            gridHC.addWidget(qt.QLabel(l2), row, 2)
            gridHC.addWidget(w2, row, 3)

        add_row(0, "Bin Size", binSizeSpin, "Feature Value Mode", fvm)
        add_row(1, "Modality", dtype, "Discretization", discType)
        add_row(2, "Voxel Interpolation", voxI, "ROI Interpolation", roiI)
        add_row(3, "Isotropic Voxel Size (3D)", iso3D, "Isotropic Voxel Size (2D)", iso2D)
        add_row(4, "Re-seg Low", reSeg01Edit, "Re-seg High", reSeg02Edit)
        add_row(5, "Partial Volume (ROI)", roiPvSpin, "Quantization", qntzCombo)
        add_row(6, "IVH Type", ivhType, "IVH Disc/Cont", ivhDisc)
        add_row(7, "IVH Bin Size", ivhBin, "", qt.QLabel(""))

        # make columns behave nicely
        gridHC.setColumnStretch(0, 0)
        gridHC.setColumnStretch(1, 1)
        gridHC.setColumnStretch(2, 0)
        gridHC.setColumnStretch(3, 1)

        handLay.addWidget(paramsBox)

        # register widgets
        self.param_widgets.update({
            "radiomics_BinSize": binSizeSpin,
            "radiomics_feature_value_mode": fvm,
            "radiomics_DataType": dtype,
            "radiomics_DiscType": discType,
            "radiomics_VoxInterp": voxI,
            "radiomics_ROIInterp": roiI,
            "radiomics_isotVoxSize": iso3D,
            "radiomics_isotVoxSize2D": iso2D,
            "radiomics_ReSegIntrvl01": reSeg01Edit,
            "radiomics_ReSegIntrvl02": reSeg02Edit,
            "radiomics_ROI_PV": roiPvSpin,
            "radiomics_qntz": qntzCombo,
            "radiomics_IVH_Type": ivhType,
            "radiomics_IVH_DiscCont": ivhDisc,
            "radiomics_IVH_binSize": ivhBin,
        })

        settingsRoot.addWidget(handColl)

        # Add the whole section into the tab
        settingsTab.addWidget(settingsSection)

        # keep references (so mode toggle can enable/disable it)
        hcGroup = handColl

        # -----------------------------
        # Feature Selection
        # -----------------------------
        DIM_OPTIONS = ["1st", "2D", "2_5D", "3D"]
        CAT_OPTIONS = ["DIAG", "MORPH", "IP", "STAT", "IH", "IVH", "GLCM", "GLRLM", "GLSZM", "GLDZM", "NGTDM", "NGLDM", "MI"]
        DIM_TO_CATS = {
            "1st": ["MORPH", "IP", "STAT", "IH", "IVH"],
            "2d": ["GLCM", "GLRLM", "GLSZM", "GLDZM", "NGTDM", "NGLDM"],
            "2_5d": ["GLCM", "GLRLM", "GLSZM", "GLDZM", "NGTDM", "NGLDM"],
            "3d": ["GLCM", "GLRLM", "GLSZM", "GLDZM", "NGTDM", "NGLDM"],
        }

        selGroup = qt.QGroupBox(UI_TEXT["grp_selection"])
        selGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        selGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)

        selLay = qt.QVBoxLayout(selGroup)
        selLay.setContentsMargins(6, 6, 6, 6)
        selLay.setSpacing(10)

        panelsRow = qt.QHBoxLayout()

        cats_default = str(RDEF.get("categories", "all"))
        catWidget, self.categoryChecks = self._build_check_grid_panel(UI_TEXT["panel_categories"], CAT_OPTIONS, cats_default)

        dims_default = str(RDEF.get("dimensions"))
        dimWidget, self.dimensionChecks = self._build_check_grid_panel(UI_TEXT["panel_dimensions"], DIM_OPTIONS, dims_default)

        panelsRow.addWidget(catWidget, 3)
        panelsRow.addWidget(dimWidget, 2)
        selLay.addLayout(panelsRow)

        # Global Select/Clear outside panels
        btnRow = qt.QHBoxLayout()
        btnRow.addStretch(1)
        btnSelectAll = qt.QPushButton(UI_TEXT["btn_select_all"])
        btnClearAll = qt.QPushButton(UI_TEXT["btn_clear_all"])

        def _global_select_all():
            self._ignoreDimSync = True
            try:
                for cb in self.dimensionChecks:
                    cb.setChecked(True)
                for cb in self.categoryChecks:
                    cb.setChecked(True)
            finally:
                self._ignoreDimSync = False

        def _global_clear_all():
            self._ignoreDimSync = True
            try:
                for cb in self.categoryChecks:
                    cb.setChecked(False)
                for cb in self.dimensionChecks:
                    cb.setChecked(False)
            finally:
                self._ignoreDimSync = False

        btnSelectAll.clicked.connect(_global_select_all)
        btnClearAll.clicked.connect(_global_clear_all)
        btnRow.addWidget(btnSelectAll)
        btnRow.addWidget(btnClearAll)
        selLay.addLayout(btnRow)

        selectTab.addWidget(selGroup)

        # Robust mapping (no cb.text() callable assumption)
        self._categoryByName = {self._wtext(cb).strip().lower(): cb for cb in self.categoryChecks}
        self._dimensionByName = {self._wtext(cb).strip().lower(): cb for cb in self.dimensionChecks}

        from functools import partial
        for cb in self.dimensionChecks:
            cb.toggled.connect(partial(self._on_dimension_changed, DIM_TO_CATS))
        qt.QTimer.singleShot(0, lambda: self._on_dimension_changed(DIM_TO_CATS))

        # -----------------------------
        # Extraction Mode
        # -----------------------------
        modeGroup = qt.QGroupBox(UI_TEXT["tab_mode"])
        modeGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        modeGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        modeLay = qt.QVBoxLayout(modeGroup)
        modeLay.setSpacing(10)

        extrMode = qt.QComboBox()
        extrMode.addItems([UI_TEXT["mode_hand"], UI_TEXT["mode_deep"]])

        default_mode_raw = str(RDEF.get("extraction_mode", "handcrafted_feature")).strip().lower()
        pretty_default = UI_TEXT["mode_hand"] if "hand" in default_mode_raw else UI_TEXT["mode_deep"]
        self._set_combo_safe(extrMode, pretty_default)

        deepModel = qt.QComboBox()
        deepModel.addItems(["resnet50", "vgg16", "densenet121", "none"])
        self._set_combo_safe(deepModel, RDEF.get("deep_learning_model", "none"))

        row = qt.QWidget()
        rowLay = qt.QHBoxLayout(row)
        rowLay.setContentsMargins(0, 0, 0, 0)
        rowLay.setSpacing(12)
        rowLay.addWidget(qt.QLabel(UI_TEXT["lab_extraction_mode"]))
        rowLay.addWidget(self._shrink_editor(extrMode, 200))
        rowLay.addSpacing(10)
        rowLay.addWidget(qt.QLabel(UI_TEXT["lab_deep_model"]))
        rowLay.addWidget(self._shrink_editor(deepModel, 160))
        rowLay.addStretch(1)
        modeLay.addWidget(row)

        deepTab.addWidget(modeGroup)

        self.param_widgets.update({
            "radiomics_extraction_mode": extrMode,
            "radiomics_deep_learning_model": deepModel,
        })

        def _toggle_for_mode():
            pretty = self._combo_text_safe(extrMode).strip().lower()
            is_hand = ("handcrafted" in pretty)
            hcGroup.setEnabled(is_hand)
            selGroup.setEnabled(is_hand)

        _toggle_for_mode()
        extrMode.currentIndexChanged.connect(lambda *_: _toggle_for_mode())

        # -----------------------------
        # Run & Results
        # -----------------------------
        runGroup = qt.QGroupBox(UI_TEXT["grp_results"])
        runGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        runGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay = qt.QVBoxLayout(runGroup)
        runLay.setSpacing(10)

        topRow = qt.QWidget()
        topLay = qt.QHBoxLayout(topRow)
        topLay.setContentsMargins(0, 0, 0, 0)
        topLay.setSpacing(10)

        self.computeButton = qt.QPushButton(UI_TEXT["btn_run"])
        self.computeButton.setMinimumHeight(30)
        self.computeButton.clicked.connect(self.onCompute)

        self.statusLabel = qt.QLabel("Ready.")
        self.statusLabel.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        self.statusLabel.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)

        topLay.addWidget(self.computeButton)
        topLay.addWidget(self.statusLabel, 1)
        runLay.addWidget(topRow)

        # Summary table
        runLay.addWidget(qt.QLabel(UI_TEXT["lbl_summary"] + ":"))
        self.summaryTable = qt.QTableWidget()
        self.summaryTable.setColumnCount(2)
        self.summaryTable.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.summaryTable.verticalHeader().setVisible(False)
        self.summaryTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.summaryTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.summaryTable.setAlternatingRowColors(True)
        self.summaryTable.setMaximumHeight(140)
        runLay.addWidget(self.summaryTable)

        # Extracted Features table
        runLay.addWidget(qt.QLabel(UI_TEXT["lbl_extracted"] + ":"))
        self.featureTable = qt.QTableWidget()
        self.featureTable.setColumnCount(2)
        self.featureTable.setHorizontalHeaderLabels(["Feature", "Value"])
        self.featureTable.verticalHeader().setVisible(False)
        self.featureTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.featureTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.featureTable.setAlternatingRowColors(True)
        self.featureTable.setMinimumHeight(220)
        self.featureTable.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay.addWidget(self.featureTable, 1)

        runTab.addWidget(runGroup)

        # initial widths
        self._apply_two_column_widths(self.summaryTable)
        self._apply_two_column_widths(self.featureTable)

    def onCompute(self):
        is_single = self.singleModeRadio.isChecked()

        if is_single:
            image_path = self.imagePathEdit.currentPath
            mask_path = self.maskPathEdit.currentPath
            if not image_path:
                self.statusLabel.setText(f"Error: Select an {UI_TEXT['lbl_image'].lower()} file.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                logger.warning("No image file selected.")
                return
            if not mask_path:
                self.statusLabel.setText(f"Error: Select a {UI_TEXT['lbl_mask'].lower()} file.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                logger.warning("No mask file selected.")
                return
        else:
            image_path = self.imageFolderEdit.currentPath
            mask_path = self.maskFolderEdit.currentPath
            if not image_path or not os.path.isdir(image_path):
                self.statusLabel.setText(f"Error: Select an {UI_TEXT['lbl_image_folder'].lower()}.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                logger.warning("No image folder selected.")
                return
            if not mask_path or not os.path.isdir(mask_path):
                self.statusLabel.setText(f"Error: Select a {UI_TEXT['lbl_mask_folder'].lower()}.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                logger.warning("No mask folder selected.")
                return

        params = {}
        params["radiomics_destination_folder"] = self.outputDirEdit.currentPath or RDEF.get("destination_folder", "./output_result")

        # categories/dimensions selections (meaningful for handcrafted)
        total = len(getattr(self, "categoryChecks", []))
        selected = [self._wtext(cb) for cb in getattr(self, "categoryChecks", []) if cb.isChecked()]
        params["radiomics_categories"] = "all" if (not selected or (total and len(selected) == total)) else ",".join(selected)

        dtotal = len(getattr(self, "dimensionChecks", []))
        dselected = [self._wtext(cb) for cb in getattr(self, "dimensionChecks", []) if cb.isChecked()]
        params["radiomics_dimensions"] = "all" if (not dselected or (dtotal and len(dselected) == dtotal)) else ",".join(dselected)

        # gather all UI params
        for key, widget in self.param_widgets.items():
            if widget is None:
                continue
            params[key] = self._val_from_widget(widget)

        # map Extraction Mode UI text -> canonical value
        pretty = str(params.get("radiomics_extraction_mode", UI_TEXT["mode_hand"])).strip().lower()
        params["radiomics_extraction_mode"] = "handcrafted_feature" if "handcrafted" in pretty else "deep_feature"

        mode_str = "Single Case" if is_single else "Batch (Folders)"
        self.statusLabel.setText(f"Running ({mode_str})...")
        self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
        qt.QApplication.processEvents()

        try:
            t0 = time.time()
            if is_single:
                output_csv, result = self.logic.run_single_case(image_path, mask_path, params)
            else:
                output_csv, result = self.logic.run_batch_folders(image_path, mask_path, params)
            dt = time.time() - t0

            # Extracted Features from result (preferred)
            rows = self.logic.feature_rows_from_result(result)
            if rows:
                self._fill_extracted_features_table(rows)
                extracted_count = len(rows)
            else:
                self._fill_extracted_features_table([["Info", "Waiting for CSV to load..."]])
                extracted_count = 0

            processed_files = "N/A"
            if isinstance(result, dict) and "processed_files" in result:
                processed_files = result.get("processed_files")

            self._fill_summary_table([
                ("input_type", mode_str),
                ("output_csv", output_csv),
                ("processed_files", processed_files),
                ("features_count", extracted_count),
                ("runtime_seconds", round(dt, 3)),
            ])

            self.statusLabel.setText(f"Done. {extracted_count} features. Output saved.")
            self.statusLabel.setStyleSheet("color: green; font-weight: bold;")

            logger.info(f"Done. InputType={mode_str}. Extracted={extracted_count}. Output={output_csv}")

            if not rows:
                self._poll_csv_until_ready(output_csv)

        except Exception as e:
            self.statusLabel.setText(f"Error: {e}")
            self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
            logger.error(f"Feature computation failed: {e}")
            print(f"[PySera] ERROR: {e}")


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
