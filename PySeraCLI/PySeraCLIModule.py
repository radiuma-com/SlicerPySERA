import os
import sys
import argparse
import importlib


def _log(prefix: str, msg: str):
    print(f"[{prefix}] {msg}")
    try:
        slicer = importlib.import_module("slicer")
        slicer.app.processEvents()
    except Exception:
        pass


def log_info(msg): _log("INFO", msg)
def log_debug(msg): _log("DEBUG", msg)
def log_warning(msg): _log("WARNING", msg)
def log_error(msg): _log("ERROR", msg)


def _ensure_pysera_available():
    try:
        importlib.import_module("pysera")
        return
    except Exception:
        pass

    try:
        slicer = importlib.import_module("slicer")
        log_info("Installing 'pysera' via slicer.util.pip_install ...")
        slicer.util.pip_install("pysera")
        importlib.import_module("pysera")
        log_info("'pysera' installed and importable.")
    except Exception as e:
        raise ImportError(
            "Python package 'pysera' is not available and auto-install failed."
        ) from e


def _import_pysera():
    _ensure_pysera_available()
    return importlib.import_module("pysera")


def _load_default_params():
    thisdir = os.path.dirname(__file__)
    libdir = os.path.join(thisdir, "pysera_cli_lib")
    yaml_path = os.path.join(libdir, "parameters.yaml")
    json_path = os.path.join(libdir, "parameters.json")

    if os.path.exists(yaml_path):
        try:
            yaml = importlib.import_module("yaml")
        except Exception as e:
            raise ImportError(
                "PyYAML is required to read parameters.yaml. "
                "Install it (pip install PyYAML) or provide parameters.json."
            ) from e

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        log_debug(f"Loaded default parameters from {yaml_path}")
        return data

    if os.path.exists(json_path):
        import json
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        log_debug(f"Loaded default parameters from {json_path}")
        return data

    log_warning("No default parameter file found (parameters.yaml/json). Using empty defaults.")
    return {}


def _coerce_value(val: str, typ: str):
    typ = (typ or "").lower()
    if typ in {"bool", "boolean"}:
        return str(val).strip().lower() in {"true", "1", "yes", "y", "on"}
    if typ == "int":
        return int(val)
    if typ == "float":
        return float(val)
    if typ == "list":
        return [float(x.strip()) for x in str(val).split(",") if x.strip() != ""]
    return val


def main(argv=None):
    argv = argv or sys.argv[1:]
    default_specs = _load_default_params()

    parser = argparse.ArgumentParser(description="Run pysera radiomics extraction")
    parser.add_argument("--image", required=True, help="Input image file path")
    parser.add_argument("--mask", required=False, help="Input mask file path")
    parser.add_argument("--out", required=False, default="pysera_features.csv", help="Output CSV path")

    for key, entry in (default_specs or {}).items():
        default_val = entry.get("value", None) if isinstance(entry, dict) else None
        parser.add_argument(f"--{key}", required=False, help=f"Override default ({default_val})")

    args = parser.parse_args(argv)

    params = {}
    for key, entry in (default_specs or {}).items():
        if not isinstance(entry, dict):
            continue
        raw_cli_val = getattr(args, key, None)
        default_val = entry.get("value", None)
        typ = entry.get("type", "")

        if raw_cli_val is not None:
            params[key] = _coerce_value(raw_cli_val, typ)
        else:
            params[key] = default_val

    out_dir = os.path.dirname(args.out) or "."
    os.makedirs(out_dir, exist_ok=True)
    log_debug(f"Output directory ensured: {out_dir}")

    pysera = _import_pysera()

    try:
        log_info(f"Running pysera.process_batch with image: {args.image}, mask: {args.mask}")
        pysera.process_batch(
            image_input=args.image,
            mask_input=args.mask,
            output_path=args.out,
            report=True,
            **params
        )
        log_info(f"Features successfully saved to: {args.out}")
    except Exception as e:
        log_error(f"pysera.process_batch failed: {e}")
        raise


if __name__ == "__main__":
    main()
