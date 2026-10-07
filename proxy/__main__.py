"""`python -m proxy` starts the server (HOST / PORT env vars override the defaults)."""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "proxy.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
