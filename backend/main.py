import argparse
import os

import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Load env from .env.bak instead of .env (points the app at the backup Supabase project).",
    )
    args = parser.parse_args()

    if args.backup:
        os.environ["ENV_FILE"] = ".env.bak"
        print("[main] --backup set, using .env.bak")

    uvicorn.run("app.api.serv:app", host="0.0.0.0", port=5000, log_level="info", reload=True)
