"""
parse_workout.py
Parses shorthand workout .txt files in logs/raw/ into JSON in logs/json/.

Handles both STRENGTH and ENDURANCE (RUN) formats for SPARTAN.
Automatically sorts output files into logs/json/strength/ or logs/json/run/.

Strength Format:
  2026-04-15 | strength | Optional notes here
  Squat: 100x5, 100x5, 102.5x5

Run Format:
  2026-04-16 | run | tempo | Optional notes here
  5mi | 25:00 | 160 | 7:48
  Intervals: 8x400m fast pacing
"""

import json
import sys
from pathlib import Path

# Input directories (scans all three to support old flat-folder logs and new subfolders)
RAW_DIRS = [
    Path("logs/raw"),
    Path("logs/raw/strength"),
    Path("logs/raw/run")
]

# Output directories
JSON_STRENGTH_DIR = Path("logs/json/strength")
JSON_RUN_DIR = Path("logs/json/run")

# Ensure output directories exist
JSON_STRENGTH_DIR.mkdir(parents=True, exist_ok=True)
JSON_RUN_DIR.mkdir(parents=True, exist_ok=True)

def parse_set(set_str: str) -> dict:
    set_str = set_str.strip()
    if "x" not in set_str:
        raise ValueError(f"Invalid set '{set_str}' — expected weightxreps e.g. 100x5")
    weight_str, reps_str = set_str.split("x", 1)
    return {
        "weight_kg": float(weight_str.strip()),
        "reps": int(reps_str.strip())
    }

def group_consecutive_sets(sets: list) -> list:
    if not sets:
        return []
    grouped = []
    current = dict(sets[0])
    run = 1
    for s in sets[1:]:
        if s["weight_kg"] == current["weight_kg"] and s["reps"] == current["reps"]:
            run += 1
        else:
            entry = {"weight_kg": current["weight_kg"], "reps": current["reps"]}
            if run > 1:
                entry["count"] = run
            grouped.append(entry)
            current = dict(s)
            run = 1
    entry = {"weight_kg": current["weight_kg"], "reps": current["reps"]}
    if run > 1:
        entry["count"] = run
    grouped.append(entry)
    return grouped

def parse_exercise_line(line: str) -> dict:
    if ":" not in line:
        raise ValueError(f"Exercise line missing colon: '{line}'")
    name, sets_str = line.split(":", 1)
    raw_sets = [parse_set(s) for s in sets_str.split(",") if s.strip()]
    if not raw_sets:
        raise ValueError(f"No sets found for '{name.strip()}'")
    grouped = group_consecutive_sets(raw_sets)
    return {"name": name.strip(), "sets": grouped}

def parse_run_body(lines: list) -> dict:
    if not lines:
        return {"distance": "", "time": "", "heartrate": "", "pace": "", "intervals": []}
    
    # First line of body represents core metrics split by pipe
    metrics_line = lines[0]
    metrics = [m.strip() for m in metrics_line.split("|")]
    
    distance = metrics[0] if len(metrics) > 0 else ""
    time = metrics[1] if len(metrics) > 1 else ""
    heartrate = metrics[2] if len(metrics) > 2 else ""
    pace = metrics[3] if len(metrics) > 3 else ""
    
    # Any subsequent lines are saved as details/intervals
    intervals = []
    if len(lines) > 1:
        intervals = [l.strip() for l in lines[1:] if l.strip()]
        
    return {
        "distance": distance,
        "time": time,
        "heartrate": heartrate,
        "pace": pace,
        "intervals": intervals
    }

def parse_workout(text: str) -> dict:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    if not lines:
        raise ValueError("Empty document")

    parts = [p.strip() for p in lines[0].split("|")]
    if len(parts) < 2:
        raise ValueError(f"Header requires at least 2 segments separated by pipe.\nGot: {lines[0]}")

    date = parts[0]
    workout_type = parts[1].lower()

    if workout_type == "run":
        run_type = parts[2] if len(parts) > 2 else ""
        notes = parts[3] if len(parts) > 3 else ""
        
        body_data = parse_run_body(lines[1:])
        return {
            "date": date,
            "type": "run",
            "run_type": run_type,
            "notes": notes,
            **body_data
        }
    elif workout_type == "strength":
        notes = parts[2] if len(parts) > 2 else ""

        exercises = []
        errors = []
        for line in lines[1:]:
            if not line or line.startswith("#"):
                continue
            try:
                exercises.append(parse_exercise_line(line))
            except Exception as e:
                errors.append(f"  '{line}': {e}")

        if errors:
            raise ValueError("Parse errors:\n" + "\n".join(errors))

        return {
            "date": date, 
            "type": "weights", 
            "notes": notes, 
            "exercises": exercises
        }
    else:
        # Fallback to handle legacy formats that used week_num | phase
        try:
            week = int(parts[1])
            phase = parts[2] if len(parts) > 2 else ""
            notes = parts[3] if len(parts) > 3 else ""
            
            exercises = []
            for line in lines[1:]:
                if not line or line.startswith("#"): continue
                exercises.append(parse_exercise_line(line))
            
            return {
                "date": date, 
                "type": "weights", 
                "week": week,
                "phase": phase,
                "notes": notes, 
                "exercises": exercises
            }
        except Exception:
            raise ValueError(f"Unknown workout type '{parts[1]}'. Expected 'run' or 'strength'")

def main():
    raw_files = []
    
    # Collect all txt files from the root raw directory and new subdirectories
    for d in RAW_DIRS:
        if d.exists():
            for f in d.iterdir():
                if f.is_file() and f.suffix == ".txt":
                    raw_files.append(f)

    if not raw_files:
        print("No .txt files found in logs/raw/, logs/raw/strength/, or logs/raw/run/")
        return

    parsed = skipped = errors = 0
    force = "--force" in sys.argv

    for txt_path in raw_files:
        try:
            text = txt_path.read_text(encoding="utf-8")
            workout = parse_workout(text)
            
            # Determine correct output folder based on the parsed data type
            target_dir = JSON_RUN_DIR if workout["type"] == "run" else JSON_STRENGTH_DIR
            json_path = target_dir / (txt_path.stem + ".json")
            
            # Skip if it already exists in the correct folder, unless forced
            if json_path.exists() and not force:
                skipped += 1
                continue

            print(f"Parsing {txt_path.name} -> {target_dir.name}/")
            json_path.write_text(json.dumps(workout, indent=2), encoding="utf-8")
            print(f"  ✓ {json_path.name}")
            parsed += 1
            
        except Exception as e:
            print(f"  ✗ Error in {txt_path.name}: {e}", file=sys.stderr)
            errors += 1

    print(f"\nParsed: {parsed}  Skipped: {skipped}  Errors: {errors}")
    if errors:
        sys.exit(1)

if __name__ == "__main__":
    main()