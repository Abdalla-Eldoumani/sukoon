from sukoon.cli.main import main

# The worker process re-imports the main module under spawn; the guard keeps it from starting a
# second app.
if __name__ == "__main__":
    raise SystemExit(main())
