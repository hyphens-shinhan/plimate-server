# API docs

## Swagger UI (view API as Swagger)

**Option A – Server running**  
Start the app, then open: **http://localhost:8000/docs**

**Option B – From `openapi.json` (no server)**  
1. From the `plimate-server` directory run:  
   `python -m http.server 8080`  
2. Open: **http://localhost:8080/docs/swagger-ui.html**

**Option C – Online**  
Open https://editor.swagger.io/ → File → Import file → choose `openapi.json`.
