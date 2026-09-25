"""Print the OpenAPI schema (used by the frontend's `npm run gen:api`)."""

import json

from app.main import app

if __name__ == "__main__":
    print(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False))
