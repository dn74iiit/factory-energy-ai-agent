"""
Unified Application CLI Launcher.
Provides single-command entry points for Development, Testing, Evaluation, and Execution.
Usage:
    python run.py --mode ui       # Starts Streamlit Dashboard (:8501)
    python run.py --mode api      # Starts FastAPI Backend (:8000)
    python run.py --mode all      # Starts both API and Streamlit UI
    python run.py --mode test     # Runs Pytest test suite
    python run.py --mode eval     # Runs 22-case benchmark evaluation
    python run.py --mode setup    # Generates and loads factory energy dataset
"""

import os
import sys
import argparse
import subprocess

def main():
    parser = argparse.ArgumentParser(description="Factory Energy Agent Unified Launcher")
    parser.add_argument(
        "--mode",
        choices=["ui", "api", "all", "test", "eval", "setup"],
        default="ui",
        help="Execution mode (default: ui)"
    )
    parser.add_argument("--host", default="0.0.0.0", help="API Host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="API Port (default: 8000)")
    parser.add_argument("--ui-port", type=int, default=8501, help="UI Port (default: 8501)")
    args = parser.parse_args()

    project_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(project_dir)

    if args.mode == "setup":
        print("=== Initializing DuckDB and Loading Clean Factory Dataset ===")
        subprocess.run([sys.executable, "data/loader.py"], check=True)
        subprocess.run([sys.executable, "data/validate_data.py"], check=True)
        print("=== Setup & Validation Complete [OK] ===")

    elif args.mode == "test":
        print("=== Executing Test Suite ===")
        subprocess.run([sys.executable, "-m", "pytest", "-v"], check=True)

    elif args.mode == "eval":
        print("=== Running Evaluation Benchmark Suite ===")
        subprocess.run([sys.executable, "eval/run_eval.py"], check=True)

    elif args.mode == "api":
        print(f"=== Starting FastAPI Backend on {args.host}:{args.port} ===")
        import uvicorn
        uvicorn.run("src.api.main:app", host=args.host, port=args.port, reload=False)

    elif args.mode == "ui":
        print(f"=== Starting Streamlit Dashboard on port {args.ui_port} ===")
        subprocess.run([
            sys.executable, "-m", "streamlit", "run",
            "src/ui/app.py",
            "--server.port", str(args.ui_port),
            "--server.headless", "true"
        ])

    elif args.mode == "all":
        import multiprocessing
        import time

        def run_api():
            import uvicorn
            uvicorn.run("src.api.main:app", host=args.host, port=args.port, reload=False)

        def run_ui():
            time.sleep(1.5)
            subprocess.run([
                sys.executable, "-m", "streamlit", "run",
                "src/ui/app.py",
                "--server.port", str(args.ui_port),
                "--server.headless", "true"
            ])

        print(f"=== Starting Dual Services: API (:{args.port}) and UI (:{args.ui_port}) ===")
        p_api = multiprocessing.Process(target=run_api)
        p_ui = multiprocessing.Process(target=run_ui)

        try:
            p_api.start()
            p_ui.start()
            p_api.join()
            p_ui.join()
        except KeyboardInterrupt:
            print("\nShutting down services...")
            p_api.terminate()
            p_ui.terminate()

if __name__ == "__main__":
    main()
