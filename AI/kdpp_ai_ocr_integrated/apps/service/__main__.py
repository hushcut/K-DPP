import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "apps.service.main:app",
        host=os.getenv("KDPP_AI_HOST", "127.0.0.1"),
        port=int(os.getenv("KDPP_AI_PORT", "8100")),
        reload=False,
    )
