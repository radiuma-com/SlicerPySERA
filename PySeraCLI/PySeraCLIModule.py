import os
import sys
import argparse
import yaml
import pysera  # pip-installed pysera
import slicer  # Slicer utility

# -------------------------------
# Logging wrappers for Slicer
# -------------------------------
def log_info(msg):
    print(f"[INFO] {msg}")
    slicer.app.processEvents()

def log_debug(msg):
    print(f"[DEBUG] {msg}")
    slicer.app.processEvents()

def log_error(msg):
    print(f"[ERROR] {msg}")
    slicer.app.processEvents()

def log_warning(msg):
    print(f"[WARNING] {msg}")
    slicer.app.processEvents()


# -------------------------------
# Path to parameters.yaml
# -------------------------------
thisdir = os.path.dirname(__file__)
project_root = os.path.dirname(thisdir)
params_file = os.path.join(project_root, "pysera_lib", "parameters.yaml")

# -------------------------------
# Load default parameters
# -------------------------------
with open(params_file, 'r') as f:
    DEFAULT_PARAMS = yaml.safe_load(f)
log_debug(f"Loaded default parameters from {params_file}")


# -------------------------------
# CLI main
# -------------------------------
def main(argv=None):
    argv = argv or sys.argv[1:]
    parser = argparse.ArgumentParser(description="Run pysera radiomics extraction")

    parser.add_argument("--image", required=True, help="Input image file path")
    parser.add_argument("--mask", required=False, help="Input mask file path")
    parser.add_argument("--out", required=False, default="pysera_features.csv", help="Output CSV path")

    # Add optional parameters from YAML
    for key in DEFAULT_PARAMS.keys():
        parser.add_argument(f"--{key}", required=False, help=f"Override default ({DEFAULT_PARAMS[key]['value']})")

    args = parser.parse_args(argv)

    # Merge CLI args with YAML defaults
    params = {}
    for key, entry in DEFAULT_PARAMS.items():
        val = getattr(args, key, None)
        default_val = entry['value']
        if val is not None:
            typ = entry['type']
            if typ == 'bool':
                params[key] = str(val).lower() in ['true', '1', 'yes']
            elif typ == 'int':
                params[key] = int(val)
            elif typ == 'float':
                params[key] = float(val)
            elif typ == 'list':
                params[key] = [float(x.strip()) for x in val.split(',')]
            else:
                params[key] = val
        else:
            params[key] = default_val

    # Ensure output folder exists
    out_dir = os.path.dirname(args.out) or "."
    os.makedirs(out_dir, exist_ok=True)
    log_debug(f"Output directory ensured: {out_dir}")

    # Run pysera
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


if __name__ == "__main__":
    main()
