# -*- coding: utf-8 -*-
# PySERA ScriptedLoadableModule for 3D Slicer
#
# Packaging-safe rules:
# - No pip-dependency imports at file level (pysera, yaml, pandas, etc.)
# - Only install/import pip packages inside Logic at runtime
# - Parameters loaded from: <ExtensionRoot>/pysera_lib/parameters.yaml or parameters.json
#
# UI rule:
# - "Extracted Features" table must show ONLY two columns: Feature | Value (no edits)

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

    def info(self, msg):    self._emit(self.logger.info, msg)
    def debug(self, msg):   self._emit(self.logger.debug, msg)
    def warning(self, msg): self._emit(self.logger.warning, msg)
    def error(self, msg):   self._emit(self.logger.error, msg)

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


def _find_pysera_lib_dir():
    """
    Locate pysera_lib directory.

    Your project layout:
      <ExtensionRoot>/pysera_lib/parameters.yaml|json
      <ExtensionRoot>/PySera_Ext/PySera.py

    We also support <ModuleDir>/pysera_lib for robustness.
    """
    candidates = [
        os.path.join(MODULE_DIR, "pysera_lib"),
        os.path.join(os.path.dirname(MODULE_DIR), "pysera_lib"),                  # Extension root
        os.path.join(os.path.dirname(os.path.dirname(MODULE_DIR)), "pysera_lib"), # extra fallback
    ]

    for d in candidates:
        if os.path.exists(os.path.join(d, "parameters.yaml")) or os.path.exists(os.path.join(d, "parameters.json")):
            return d

    return candidates[0]


PARAM_DIR = _find_pysera_lib_dir()
YAML_PATH = os.path.join(PARAM_DIR, "parameters.yaml")
JSON_PATH = os.path.join(PARAM_DIR, "parameters.json")


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
    logger.debug(f"PARAM_DIR: {PARAM_DIR}")
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

        logger.warning("No parameter file found (pysera_lib/parameters.yaml or .json). Using empty defaults.")
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
        self.parent.contributors = ["Mohammad R. Salmanpour"]
        self.parent.helpText = "PySERA feature extraction for 3D Slicer."
        self.parent.acknowledgementText = "Thanks to ..."


# -------------------------------
# Logic
# -------------------------------
class PySERALogic(ScriptedLoadableModuleLogic):

    # ---------- pip install/import helpers ----------
    @staticmethod
    def _ensure_package_available(package_name: str, import_name: str = None):
        """
        Ensure a pip package is importable. Must run at runtime only.
        """
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

    # ---------- normalization ----------
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

        # defaults from "radiomics" block
        for k, v in (RDEF or {}).items():
            cfg["radiomics_" + k] = v

        # explicit I/O defaults
        if "destination_folder" in RDEF:
            cfg["radiomics_destination_folder"] = RDEF["destination_folder"]
        if "temporary_files_path" in RDEF:
            cfg["radiomics_temporary_files_path"] = RDEF["temporary_files_path"]

        # allow top-level "radiomics_*" overrides
        for k, v in (CFG_FILE or {}).items():
            if isinstance(k, str) and k.startswith("radiomics_"):
                cfg[k] = v

        # UI overrides last
        cfg.update(params_from_ui or {})
        return cfg

    def _build_cli_kwargs(self, cfg: dict) -> dict:
        cli = {}
        passthru_str = {"categories", "dimensions", "extraction_mode", "deep_learning_model", "optional_params", "report"}

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

        opt = cfg.get("radiomics_optional_params", None)
        if opt is not None and str(opt).strip() != "":
            cli["optional_params"] = str(opt)

        rep = cfg.get("radiomics_report", None)
        if rep is not None and str(rep).strip() != "":
            cli["report"] = str(rep)

        return cli

    # ---------- Windows CSV lock fix ----------
    @staticmethod
    def _wait_for_readable_file(path: str, retries: int = 160, delay: float = 0.25):
        """
        Wait until file exists, has size, and is readable.
        Useful as a fallback only (UI should prefer result['features_extracted']).
        """
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

    # ---------- CSV → (Feature, Value) rows (fallback) ----------
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

        # fallback: show each row as a single feature string
        out = []
        for r in rows[1:]:
            if not r:
                continue
            out.append([",".join(r), ""])
        return out

    # ---------- Result → (Feature, Value) rows (primary) ----------
    def feature_rows_from_result(self, result):
        if not isinstance(result, dict):
            return []

        fx = result.get("features_extracted", None)
        if fx is None:
            return []

        # DataFrame-like: [1 rows x N columns] -> N rows x 2 columns
        try:
            has_shape = hasattr(fx, "shape")
            has_columns = hasattr(fx, "columns")
            has_to_dict = hasattr(fx, "to_dict") and callable(getattr(fx, "to_dict"))
            if has_shape and has_columns and has_to_dict:
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
                        return [[str(c), row_dict.get(c)] for c in cols]
                    except Exception:
                        keys = list(row_dict.keys())
                        return [[str(k), row_dict[k]] for k in keys]
        except Exception:
            pass

        # dict {feature: value}
        if isinstance(fx, dict):
            keys = list(fx.keys())
            try:
                keys.sort()
            except Exception:
                pass
            return [[str(k), fx[k]] for k in keys]

        # list formats
        if isinstance(fx, list):
            if (
                len(fx) == 2
                and isinstance(fx[0], (list, tuple))
                and isinstance(fx[1], (list, tuple))
                and len(fx[0]) == len(fx[1])
                and len(fx[0]) > 0
            ):
                names = fx[0]
                values = fx[1]
                return [[str(names[i]), values[i]] for i in range(len(names))]

            rows = []
            for item in fx:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    rows.append([str(item[0]), item[1]])
                elif isinstance(item, dict):
                    if "feature" in item and "value" in item:
                        rows.append([str(item["feature"]), item["value"]])
                    else:
                        for k, v in item.items():
                            rows.append([str(k), v])
            return rows

        # string (maybe JSON dict)
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
                    return [[str(k), obj[k]] for k in keys]
            except Exception:
                pass
            return [["features_extracted", fx]]

        return [["features_extracted", str(fx)]]

    def run_single_pair(self, image_path, mask_path, params=None):
        pysera = self._import_pysera()
        cfg = self._compose_cfg(params)

        out_dir = cfg.get("radiomics_destination_folder") or os.path.join(
            os.path.expanduser("~"), "Desktop", "output_result"
        )
        out_dir = os.path.abspath(out_dir)
        os.makedirs(out_dir, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        random_suffix = random.randint(1000, 9999)
        output_csv = os.path.join(out_dir, f"extracted_radiomics_features_{timestamp}_{random_suffix}.csv")

        logger.debug(f"Output directory: {out_dir}")
        logger.info(f"Output CSV path: {output_csv}")

        cli_kwargs = self._build_cli_kwargs(cfg)
        cli_kwargs.setdefault("categories", str(cfg.get("radiomics_categories", "all")))
        cli_kwargs.setdefault("dimensions", str(cfg.get("radiomics_dimensions", "all")))

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

        result = pysera.process_batch(
            image_input=image_path,
            mask_input=mask_path,
            output_path=output_csv,
            **cli_kwargs,
        )

        logger.info(f"Feature extraction completed: {output_csv}")
        return output_csv, result


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

    # ---------- helpers ----------
    @staticmethod
    def _wtext(widget) -> str:
        if hasattr(widget, "text") and callable(getattr(widget, "text", None)):
            try:
                return widget.text()
            except Exception:
                pass
        t = getattr(widget, "text", "")
        return t if isinstance(t, str) else str(t)

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
        for i in range(combo.count):
            if combo.itemText(i).lower() == str(value).lower():
                combo.setCurrentIndex(i)
                return

    def _combo_text_safe(self, combo: qt.QComboBox) -> str:
        return combo.currentText() if callable(getattr(combo, "currentText", None)) else str(getattr(combo, "currentText", ""))

    @staticmethod
    def _shrink_editor(w, fixed_width=140):
        if isinstance(w, (qt.QLineEdit, qt.QComboBox, qt.QSpinBox, qt.QDoubleSpinBox)):
            w.setFixedWidth(fixed_width)
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

    def _apply_two_column_widths(self, table, value_width=160, feature_max_width=420):
        """
        Column 0 (Feature/Parameter): ResizeToContents but capped (no endless stretching)
        Column 1 (Value): Fixed and small
        """
        table.setWordWrap(False)
        try:
            table.setTextElideMode(qt.Qt.ElideRight)
        except Exception:
            pass

        header = table.horizontalHeader()
        try:
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, qt.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(1, qt.QHeaderView.Fixed)
        except Exception:
            # older Qt fallback
            try:
                header.setResizeMode(0, qt.QHeaderView.ResizeToContents)
                header.setResizeMode(1, qt.QHeaderView.Fixed)
            except Exception:
                pass

        # Value column fixed
        table.setColumnWidth(1, int(value_width))

        # Let Qt compute Feature width, then cap it
        table.resizeColumnToContents(0)
        w = table.columnWidth(0)
        if w > int(feature_max_width):
            table.setColumnWidth(0, int(feature_max_width))

    @staticmethod
    def _make_item(text, tooltip=None, align_right=False):
        it = qt.QTableWidgetItem("" if text is None else str(text))
        if tooltip is not None:
            it.setToolTip(str(tooltip))
        if align_right:
            it.setTextAlignment(int(qt.Qt.AlignVCenter | qt.Qt.AlignRight))
        else:
            it.setTextAlignment(int(qt.Qt.AlignVCenter | qt.Qt.AlignLeft))
        return it

    @staticmethod
    def _shorten_for_cell(value, max_len=120):
        s = "" if value is None else str(value)
        if len(s) <= max_len:
            return s, s
        return s[:max_len - 1] + "…", s

    def _fill_extracted_features_table(self, rows):
        self.featureTable.clear()
        self.featureTable.setRowCount(0)
        self.featureTable.setColumnCount(2)
        self.featureTable.setHorizontalHeaderLabels(["Feature", "Value"])

        for feat, val in rows:
            r = self.featureTable.rowCount
            self.featureTable.insertRow(r)

            feat_txt, feat_tip = self._shorten_for_cell(feat, max_len=200)
            val_txt, val_tip = self._shorten_for_cell(val, max_len=200)

            self.featureTable.setItem(r, 0, self._make_item(feat_txt, tooltip=feat_tip, align_right=False))
            self.featureTable.setItem(r, 1, self._make_item(val_txt, tooltip=val_tip, align_right=True))

        self._apply_two_column_widths(self.featureTable, left_min=300, right_width=160)

    def _poll_csv_until_ready(self, output_csv, tries=160, interval_ms=250):
        """
        Fallback only: if result['features_extracted'] is not parseable.
        This is async and DOES NOT return rows.
        """
        self._csvPollRemaining = tries

        def _tick():
            self._csvPollRemaining -= 1
            try:
                rows = self.logic.load_features_as_feature_value_rows(output_csv)
                if rows:
                    self._fill_extracted_features_table(rows)
                    self.statusLabel.setText(f"Features loaded from: {output_csv}")
                    self.statusLabel.setStyleSheet("color: green; font-weight: bold;")
                    print(f"[PySera] Done. Loaded features from CSV: {output_csv}")
                    logger.info(f"Done. Loaded features from CSV: {output_csv}")
                    return
            except Exception:
                pass

            if self._csvPollRemaining > 0:
                qt.QTimer.singleShot(interval_ms, _tick)
            else:
                self._fill_extracted_features_table([["Error", "Could not load features (CSV not ready/locked)"]])
                self.statusLabel.setText("CSV was not ready in time.")
                self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
                print(f"[PySera] Failed to load CSV in time: {output_csv}")
                logger.error(f"Failed to load CSV in time: {output_csv}")

        self.statusLabel.setText("Waiting for output CSV to be finalized...")
        self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
        print(f"[PySera] Processing finished, waiting for CSV finalize: {output_csv}")
        logger.info(f"Processing finished, waiting for CSV finalize: {output_csv}")
        qt.QTimer.singleShot(interval_ms, _tick)

    def _build_categories_panel(self, options, default_str):
        gb = qt.QGroupBox("Categories")
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

        btnRow = qt.QHBoxLayout()
        selAll = qt.QPushButton("Select all")
        clrAll = qt.QPushButton("Clear all")

        def _select_all():
            for cb in checks:
                cb.setChecked(True)

        def _clear_all():
            for cb in checks:
                cb.setChecked(False)

        selAll.clicked.connect(_select_all)
        clrAll.clicked.connect(_clear_all)
        btnRow.addStretch(1)
        btnRow.addWidget(selAll)
        btnRow.addWidget(clrAll)

        v.addLayout(grid)
        v.addLayout(btnRow)
        return gb, checks

    def _build_dimensions_panel(self, options, default_str):
        gb = qt.QGroupBox("Dimensions")
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

        btnRow = qt.QHBoxLayout()
        selAll = qt.QPushButton("Select all")
        clrAll = qt.QPushButton("Clear all")

        def _select_all():
            for cb in checks:
                cb.setChecked(True)

        def _clear_all():
            for cb in checks:
                cb.setChecked(False)

        selAll.clicked.connect(_select_all)
        clrAll.clicked.connect(_clear_all)
        btnRow.addStretch(1)
        btnRow.addWidget(selAll)
        btnRow.addWidget(clrAll)

        v.addLayout(grid)
        v.addLayout(btnRow)
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

    def setup(self):
        super().setup()
        root = self.layout
        root.setSpacing(10)

        tabs = qt.QTabWidget()
        tabs.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        root.addWidget(tabs, 1)

        ioTab = self._make_scroll_tab("I/O", tabs)
        deepTab = self._make_scroll_tab("Features Extraction Mode", tabs)
        settingsTab = self._make_scroll_tab("Settings", tabs)
        selectTab = self._make_scroll_tab("Feature Subset", tabs)
        runTab = self._make_scroll_tab("Run and Results", tabs)

        # I/O
        ioGroup = qt.QGroupBox("Inputs and Outputs")
        ioGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        ioGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        ioForm = qt.QFormLayout(ioGroup)

        self.imagePathEdit = ctk.ctkPathLineEdit()
        self.imagePathEdit.filters = ctk.ctkPathLineEdit.Files
        self.maskPathEdit = ctk.ctkPathLineEdit()
        self.maskPathEdit.filters = ctk.ctkPathLineEdit.Files
        ioForm.addRow("Image File:", self.imagePathEdit)
        ioForm.addRow("Mask File:", self.maskPathEdit)

        self.outputDirEdit = ctk.ctkPathLineEdit()
        self.outputDirEdit.filters = ctk.ctkPathLineEdit.Dirs
        self.tmpDirEdit = ctk.ctkPathLineEdit()
        self.tmpDirEdit.filters = ctk.ctkPathLineEdit.Dirs

        self.outputDirEdit.currentPath = RDEF.get("destination_folder", "./output_result")
        self.tmpDirEdit.currentPath = RDEF.get("temporary_files_path", "./temporary_files_path")

        ioForm.addRow("Destination Folder:", self.outputDirEdit)
        ioForm.addRow("Temporary Files Path:", self.tmpDirEdit)

        ioTab.addWidget(ioGroup)

        # Settings
        settingsGroup = qt.QGroupBox("Settings")
        settingsGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        settingsGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        settingsLay = qt.QVBoxLayout(settingsGroup)
        settingsLay.setSpacing(10)

        commonGroup = qt.QGroupBox("Common Set (Handcrafted Feature and Deep Feature)")
        commonGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        commonLay = qt.QVBoxLayout(commonGroup)
        commonLay.setSpacing(8)

        applyPreChk = qt.QCheckBox("Apply Preprocessing")
        applyPreChk.setChecked(bool(RDEF.get("apply_preprocessing", False)))
        enParChk = qt.QCheckBox("Enable Parallelism")
        enParChk.setChecked(bool(RDEF.get("enable_parallelism", True)))
        aggrChk = qt.QCheckBox("Aggregation (Lesion)")
        aggrChk.setChecked(bool(RDEF.get("aggregation_lesion", 0)))

        togglesRow = qt.QWidget()
        togglesGrid = qt.QGridLayout(togglesRow)
        togglesGrid.setContentsMargins(0, 0, 0, 0)
        togglesGrid.setHorizontalSpacing(12)
        togglesGrid.setVerticalSpacing(0)
        for i, cb in enumerate([applyPreChk, enParChk, aggrChk]):
            cb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred)
            togglesGrid.addWidget(cb, 0, i)
            togglesGrid.setColumnStretch(i, 1)
        commonLay.addWidget(togglesRow)

        commonGrid = qt.QGridLayout()
        commonGrid.setHorizontalSpacing(12)
        commonGrid.setVerticalSpacing(8)

        numWorkersEdit = qt.QLineEdit()
        numWorkersEdit.setPlaceholderText("auto or int")
        numWorkersEdit.setText(str(RDEF.get("num_workers", "auto")))

        minRoiSpin = qt.QDoubleSpinBox()
        minRoiSpin.setRange(0.0, 1e12)
        minRoiSpin.setDecimals(0)
        minRoiSpin.setValue(float(RDEF.get("min_roi_volume", 10)))

        self._add_two_grid(commonGrid, 0, "Num Workers", numWorkersEdit, "Min ROI Volume", minRoiSpin)

        roiSel = qt.QComboBox()
        roiSel.addItems(["per_Img", "per_region"])
        self._set_combo_safe(roiSel, RDEF.get("roi_selection_mode", "per_Img"))

        reportC = qt.QComboBox()
        reportC.addItems(["none", "error", "warning", "info", "all"])
        self._set_combo_safe(reportC, RDEF.get("report", "all"))
        self._add_two_grid(commonGrid, 1, "ROI Selection Mode", roiSel, "Report", reportC)

        commonLay.addLayout(commonGrid)
        settingsLay.addWidget(commonGroup)

        self.param_widgets.update({
            "radiomics_apply_preprocessing": applyPreChk,
            "radiomics_enable_parallelism": enParChk,
            "radiomics_aggregation_lesion": aggrChk,
            "radiomics_num_workers": numWorkersEdit,
            "radiomics_min_roi_volume": minRoiSpin,
            "radiomics_roi_selection_mode": roiSel,
            "radiomics_report": reportC,
        })

        # Handcrafted-only
        hcGroup = qt.QGroupBox("Just Set for (Handcrafted Feature)")
        hcGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        hcLay = qt.QVBoxLayout(hcGroup)
        hcLay.setSpacing(8)

        def mkchk(label_text: str, key: str, default_val: int = 0) -> qt.QCheckBox:
            cb = qt.QCheckBox(label_text)
            cb.setChecked(bool(RDEF.get(key, default_val)))
            cb.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Preferred)
            self.param_widgets["radiomics_" + key] = cb
            return cb

        flagsWidget = qt.QWidget()
        flagsGrid = qt.QGridLayout(flagsWidget)
        flagsGrid.setContentsMargins(0, 0, 0, 0)
        flagsGrid.setHorizontalSpacing(12)
        flagsGrid.setVerticalSpacing(6)

        flags = [
            mkchk("GL Round", "isGLround", 0),
            mkchk("Scale", "isScale", 0),
            mkchk("Re-Seg Range", "isReSegRng", 0),
            mkchk("Outliers", "isOutliers", 0),
            mkchk("Quantized Stats", "isQuntzStat", 1),
            mkchk("2D Isotropic", "isIsot2D", 0),
        ]
        for i, cb in enumerate(flags):
            r = 0 if i < 3 else 1
            c = i if i < 3 else (i - 3)
            flagsGrid.addWidget(cb, r, c)
        for c in range(3):
            flagsGrid.setColumnStretch(c, 1)
        hcLay.addWidget(flagsWidget)

        INTERP_OPTIONS = ["Nearest", "linear", "bilinear", "trilinear", "tricubic-spline", "cubic", "bspline", "None"]

        gridHC = qt.QGridLayout()
        gridHC.setHorizontalSpacing(12)
        gridHC.setVerticalSpacing(8)

        binSizeSpin = qt.QSpinBox()
        binSizeSpin.setRange(1, 10**9)
        binSizeSpin.setValue(int(RDEF.get("BinSize", 25)))

        fvm = qt.QComboBox()
        fvm.addItems(["REAL_VALUE", "APPROXIMATE_VALUE"])
        self._set_combo_safe(fvm, RDEF.get("feature_value_mode", "REAL_VALUE"))

        dtype = qt.QComboBox()
        dtype.addItems(["CT", "MR", "PET", "OTHER"])
        self._set_combo_safe(dtype, RDEF.get("DataType", "OTHER"))

        discType = qt.QComboBox()
        discType.addItems(["FBS", "FBN"])
        self._set_combo_safe(discType, RDEF.get("DiscType", "FBS"))

        voxI = qt.QComboBox()
        voxI.addItems(INTERP_OPTIONS)
        self._set_combo_safe(voxI, RDEF.get("VoxInterp", "Nearest"))

        roiI = qt.QComboBox()
        roiI.addItems(INTERP_OPTIONS)
        self._set_combo_safe(roiI, RDEF.get("ROIInterp", "Nearest"))

        iso3D = qt.QDoubleSpinBox()
        iso3D.setRange(0.0, 1e12)
        iso3D.setSingleStep(0.1)
        iso3D.setValue(float(RDEF.get("isotVoxSize", 2)))

        iso2D = qt.QDoubleSpinBox()
        iso2D.setRange(0.0, 1e12)
        iso2D.setSingleStep(0.1)
        iso2D.setValue(float(RDEF.get("isotVoxSize2D", 2)))

        reSeg01Edit = qt.QLineEdit()
        reSeg01Edit.setPlaceholderText("None or value")
        reSeg01Edit.setText(str(RDEF.get("ReSegIntrvl01", -1000)))

        reSeg02Edit = qt.QLineEdit()
        reSeg02Edit.setPlaceholderText("None or value")
        reSeg02Edit.setText(str(RDEF.get("ReSegIntrvl02", 400)))

        roiPvSpin = qt.QDoubleSpinBox()
        roiPvSpin.setRange(0.0, 1.0)
        roiPvSpin.setSingleStep(0.05)
        roiPvSpin.setValue(float(RDEF.get("ROI_PV", 0.5)))

        qntzCombo = qt.QComboBox()
        qntzCombo.addItems(["Uniform", "Lloyd-Max"])
        self._set_combo_safe(qntzCombo, RDEF.get("qntz", "Uniform"))

        ivhType = qt.QSpinBox()
        ivhType.setRange(0, 10**9)
        ivhType.setValue(int(RDEF.get("IVH_Type", 3)))

        ivhDisc = qt.QSpinBox()
        ivhDisc.setRange(0, 10**9)
        ivhDisc.setValue(int(RDEF.get("IVH_DiscCont", 1)))

        ivhBin = qt.QDoubleSpinBox()
        ivhBin.setRange(0.0, 1e12)
        ivhBin.setSingleStep(0.1)
        ivhBin.setValue(float(RDEF.get("IVH_binSize", 2.0)))

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

        settingsTab.addWidget(settingsGroup)

        # Feature subset
        DIM_OPTIONS = ["all", "1st", "2D", "2_5D", "3D"]
        CAT_OPTIONS = ["diag", "morph", "ip", "stat", "ih", "ivh", "glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm", "mi"]
        DIM_TO_CATS = {
            "1st": ["morph", "ip", "stat", "ih", "ivh"],
            "2d": ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
            "2_5d": ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
            "3d": ["glcm", "glrlm", "glszm", "gldzm", "ngtdm", "ngldm"],
        }

        selGroup = qt.QGroupBox("Feature Subset")
        selGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        selGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        selLay = qt.QHBoxLayout(selGroup)
        selLay.setContentsMargins(6, 6, 6, 6)
        selLay.setSpacing(15)

        cats_default = str(RDEF.get("categories", "all"))
        catWidget, checks = self._build_categories_panel(CAT_OPTIONS, cats_default)
        self.categoryChecks = checks

        dims_default = str(RDEF.get("dimensions", "all"))
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

        # Extraction mode
        deepGroup = qt.QGroupBox("Feature Extraction Mode")
        deepGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        deepGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)
        deepLay = qt.QVBoxLayout(deepGroup)
        deepLay.setSpacing(10)

        extrMode = qt.QComboBox()
        extrMode.addItems(["handcrafted feature", "deep feature"])
        pretty_default = "handcrafted feature" if str(RDEF.get("extraction_mode", "handcrafted_feature")).replace("_", " ") == "handcrafted feature" else "deep feature"
        self._set_combo_safe(extrMode, pretty_default)

        deepModel = qt.QComboBox()
        deepModel.addItems(["resnet50", "vgg16", "densenet121", "none"])
        self._set_combo_safe(deepModel, RDEF.get("deep_learning_model", "none"))

        optParams = qt.QLineEdit()
        optParams.setPlaceholderText("key1=val1; key2=val2 ... (optional)")
        optParams.setText(str(RDEF.get("optional_params", "")))

        row = qt.QWidget()
        rowLay = qt.QHBoxLayout(row)
        rowLay.setContentsMargins(0, 0, 0, 0)
        rowLay.setSpacing(12)
        rowLay.addWidget(qt.QLabel("Extraction Mode"))
        rowLay.addWidget(self._shrink_editor(extrMode))
        rowLay.addSpacing(10)
        rowLay.addWidget(qt.QLabel("Deep Model"))
        rowLay.addWidget(self._shrink_editor(deepModel))
        rowLay.addStretch(1)
        deepLay.addWidget(row)

        deepLay.addWidget(qt.QLabel("Optional Params"))
        deepLay.addWidget(optParams)

        deepTab.addWidget(deepGroup)

        self.param_widgets.update({
            "radiomics_extraction_mode": extrMode,
            "radiomics_deep_learning_model": deepModel,
            "radiomics_optional_params": optParams,
        })

        def _toggle_for_mode():
            pretty = self._combo_text_safe(extrMode).strip().lower()
            canonical = "handcrafted_feature" if "handcrafted" in pretty else "deep_feature"
            is_hand = (canonical == "handcrafted_feature")
            hcGroup.setEnabled(is_hand)
            selGroup.setEnabled(is_hand)

        _toggle_for_mode()
        extrMode.currentIndexChanged.connect(lambda *_: _toggle_for_mode())

        # Run & Results
        runGroup = qt.QGroupBox("Run and Results")
        runGroup.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        runGroup.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay = qt.QVBoxLayout(runGroup)
        runLay.setSpacing(10)

        topRow = qt.QWidget()
        topLay = qt.QHBoxLayout(topRow)
        topLay.setContentsMargins(0, 0, 0, 0)
        topLay.setSpacing(10)

        self.computeButton = qt.QPushButton("Apply")
        self.computeButton.setMinimumHeight(30)
        self.computeButton.clicked.connect(self.onCompute)

        self.statusLabel = qt.QLabel("Ready.")
        self.statusLabel.setStyleSheet("color: green; font-weight: bold; font-size: 12px;")
        self.statusLabel.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Maximum)

        topLay.addWidget(self.computeButton)
        topLay.addWidget(self.statusLabel, 1)
        runLay.addWidget(topRow)

        self.summaryTable = qt.QTableWidget()
        self.summaryTable.setColumnCount(2)
        self.summaryTable.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.summaryTable.verticalHeader().setVisible(False)
        self.summaryTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.summaryTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.summaryTable.setAlternatingRowColors(True)
        self.summaryTable.setMaximumHeight(140)
        runLay.addWidget(qt.QLabel("Summary:"))
        runLay.addWidget(self.summaryTable)
        self._apply_two_column_widths(self.summaryTable, left_min=260, right_width=220)

        # Extracted Features: EXACTLY two columns, read-only
        self.featureTable = qt.QTableWidget()
        self.featureTable.setColumnCount(2)
        self.featureTable.setHorizontalHeaderLabels(["Feature", "Value"])
        self.featureTable.verticalHeader().setVisible(False)
        self.featureTable.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        self.featureTable.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        self.featureTable.setAlternatingRowColors(True)
        self.featureTable.setMinimumHeight(220)
        self.featureTable.setSizePolicy(qt.QSizePolicy.Expanding, qt.QSizePolicy.Expanding)
        runLay.addWidget(qt.QLabel("Extracted Features:"))
        runLay.addWidget(self.featureTable, 1)
        self._apply_two_column_widths(self.featureTable, left_min=320, right_width=160)

        runTab.addWidget(runGroup)

    def onCompute(self):
        image_path = self.imagePathEdit.currentPath
        mask_path = self.maskPathEdit.currentPath

        if not image_path:
            self.statusLabel.setText("Please select an image.")
            self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
            logger.warning("No image selected.")
            return
        if not mask_path:
            self.statusLabel.setText("Please select a mask.")
            self.statusLabel.setStyleSheet("color: red; font-weight: bold;")
            logger.warning("No mask selected.")
            return

        params = {}
        params["radiomics_destination_folder"] = self.outputDirEdit.currentPath or RDEF.get("destination_folder", "./output_result")
        params["radiomics_temporary_files_path"] = self.tmpDirEdit.currentPath or RDEF.get("temporary_files_path", "./temporary_files_path")

        total = len(getattr(self, "categoryChecks", []))
        selected = [self._wtext(cb) for cb in getattr(self, "categoryChecks", []) if cb.isChecked()]
        params["radiomics_categories"] = "all" if (not selected or (total and len(selected) == total)) else ",".join(selected)

        dtotal = len(getattr(self, "dimensionChecks", []))
        dselected = [self._wtext(cb) for cb in getattr(self, "dimensionChecks", []) if cb.isChecked()]
        params["radiomics_dimensions"] = "all" if (not dselected or (dtotal and len(dselected) == dtotal)) else ",".join(dselected)

        for key, widget in self.param_widgets.items():
            if widget is None:
                continue
            params[key] = self._val_from_widget(widget)

        pretty = str(params.get("radiomics_extraction_mode", "handcrafted feature")).strip().lower()
        params["radiomics_extraction_mode"] = "handcrafted_feature" if "handcrafted" in pretty else "deep_feature"

        self.statusLabel.setText("Computing features...")
        self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
        qt.QApplication.processEvents()

        try:
            t0 = time.time()
            output_csv, result = self.logic.run_single_pair(image_path, mask_path, params)
            dt = time.time() - t0

            # Summary (always)
            self.summaryTable.setRowCount(0)

            processed_files = (result.get("processed_files", "N/A") if isinstance(result, dict) else "N/A")
            fx_summary = (result.get("features_extracted", "N/A") if isinstance(result, dict) else "N/A")

            # shrink large values in display, keep full in tooltip
            fx_disp, fx_tip = self._shorten_for_cell(fx_summary, max_len=140)

            summary_data = [
                ("output_path", output_csv, output_csv),
                ("processed_files", processed_files, processed_files),
                ("features_extracted", fx_disp, fx_tip),
                ("processing_time (s)", round(dt, 3), round(dt, 3)),
            ]

            for i, (k, v_disp, v_tip) in enumerate(summary_data):
                self.summaryTable.insertRow(i)
                self.summaryTable.setItem(i, 0, self._make_item(k, tooltip=k, align_right=False))
                self.summaryTable.setItem(i, 1, self._make_item(v_disp, tooltip=v_tip, align_right=False))

            self._apply_two_column_widths(self.summaryTable, left_min=260, right_width=220)

            # Extracted Features (PRIMARY: from result['features_extracted'])
            rows = self.logic.feature_rows_from_result(result)
            if rows:
                self._fill_extracted_features_table(rows)
                self.statusLabel.setText(f"Done. Features saved to: {output_csv}")
                self.statusLabel.setStyleSheet("color: green; font-weight: bold;")

                print(f"[PySera] Done. Extracted {len(rows)} features. Output: {output_csv}")
                logger.info(f"Done. Extracted {len(rows)} features. Output: {output_csv}")
                return

            # Fallback: poll CSV asynchronously
            self._fill_extracted_features_table([["Info", "Waiting for CSV to load..."]])
            self.statusLabel.setText(f"Processing finished. Waiting for CSV: {output_csv}")
            self.statusLabel.setStyleSheet("color: blue; font-weight: bold;")
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
            print(f"[PySera] TEST FAILED: {e}")
