import sys
from pathlib import Path

if len(sys.argv) > 1 and sys.argv[1] == "--snapshot":
    from sbeach.snapshot import run

    run(Path(sys.argv[2] if len(sys.argv) > 2 else "snapshots"))
else:
    from sbeach.app import main

    main()
