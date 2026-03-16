import sys

from .main import run_server, run_cli

if len(sys.argv) > 1 and sys.argv[1] == "cli":
    run_cli()
else:
    run_server()
