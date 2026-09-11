import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    env = os.environ.get("FLASK_ENV", "").lower()
    debug_default = "false" if env == "production" else "true"
    debug = os.environ.get("FLASK_DEBUG", debug_default).lower() in {"1", "true", "yes"}
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=debug, host=host, port=port)
