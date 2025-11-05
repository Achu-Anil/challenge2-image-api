# Copilot Instructions for AIQ Backend Engineer Assignment

This repository contains the solution for **Challenge 2** from the AIQ Backend Engineer assignment. Only Challenge 2 will be implemented here; however, we include a summary of our work on Challenge 1 to provide Copilot with context and to ensure continuity in coding style and architectural decisions. Throughout this project, our goal is to **reflect the professionalism and thoughtfulness expected of a senior software engineer**. The code should be clean, well‑documented, tested, and easy to maintain. GitHub Copilot will be used extensively to scaffold boilerplate and accelerate development, but we will guide it with clear comments and review its output for correctness and performance.

---

## Challenge 1 – TypeScript API for US Power Plants (Context Only)

**Scope recap (for context only):** We previously built a TypeScript backend to power a map that shows annual net generation of US power plants. Requirements from the assignment included displaying the **top N plants**, showing each plant’s absolute net generation and its **percentage share of its state**, and enabling **filtering by state**. The data comes from the eGRID2021 Excel file.

### What we delivered (for context)

1. **Data ingestion & modelling** – Wrote a Node.js/TypeScript script to download and parse the eGRID Excel workbook. Extracted plant and state data, normalised it into `Plant`, `State`, and `Generation` tables, and loaded it into PostgreSQL using Prisma. Indexes were created on commonly filtered columns (e.g., `state_code`, `net_generation`) to support efficient queries.
2. **API design** – Implemented a REST API using NestJS. The API exposes:
   - `GET /plants?top=N&state=XX`: returns the top N plants globally or within a state, including each plant’s net generation and its percentage of the state total.
   - `GET /states`: returns aggregated generation per state and each state’s percentage of the national total.
   - `GET /states/{code}`: returns details for a single state, including all plants and summary statistics.
3. **Validation & error handling** – Used DTOs and class‑validator to ensure query parameters are correct. Implemented global exception filters and unified error responses.
4. **Documentation & testing** – Added Swagger/OpenAPI docs and wrote unit and integration tests with Jest. Tests cover service logic (aggregation, percentage calculations) and controller behaviour.
5. **Performance & caching** – Pre‑computed per‑state totals during ingestion, cached frequently requested query results in Redis, and ensured endpoints are stateless and idempotent.
6. **Containerisation** – Provided a multi‑stage Dockerfile and docker‑compose configuration for the API and database. Continuous integration builds the image and runs tests on every commit.

> **Note:** This new repository **does not include** the code from Challenge 1; the summary above is provided so that Copilot understands our standards and previous design decisions. This foundation demonstrates our ability to ingest data, model it correctly, design clear API contracts, handle validation and security, and containerise the solution. We will apply the same care and structure to Challenge 2.

---

## Challenge 2 – Python Image Frames API

### Goal

Process a CSV file where the first column `depth` references the depth value and the next 200 columns represent pixel intensities (0‑255) for a single row of a grayscale image. For each row:

1. **Resize** the image width from **200 → 150**.
2. **Apply a custom colour map** to convert grayscale values into RGB.
3. **Store** the resized, colourised image in a database, keyed by `depth`.
4. **Expose an API** that returns image frames in a `depth_min`–`depth_max` range.
5. **Containerise** the solution.

### Principles & Best Practices

- **Write clean, modular Python** using FastAPI for the API layer and SQLAlchemy (or an ORM of your choice) for the persistence layer. Organise code into directories (`app/`, `db/`, `api/`, `scripts/`, `tests/`) for clarity.
- **Type annotations and Pydantic models** must be used throughout for validation and maintainability.
- **Vectorise operations** using NumPy rather than Python loops. Precompute a colour map lookup table (LUT) to map 0‑255 intensity values to RGB triples.
- **Chunked processing** when ingesting the CSV to avoid high memory usage. Use pandas to stream rows and process them in batches.
- **Idempotency** – ensure that re-running the ingestion script does not duplicate rows; use an `UPSERT` pattern based on the depth as primary key.
- **Testing** – implement unit tests for the LUT generation, the resize function, the DB layer, and the API endpoints using pytest and httpx. Tests should assert both correctness and performance characteristics.
- **Documentation** – annotate API endpoints with docstrings and use FastAPI’s built-in OpenAPI/Swagger docs. Provide usage examples and assumptions in README.
- **Containerisation** – use a slim Python base image and multi-stage builds to reduce image size. Provide a docker‑compose file to run the API and database together.

### Detailed Execution Steps

1. **Project Bootstrap (30–45 min)**  
   Create a new repository (e.g., `challenge2-image-api`). Scaffold a minimal FastAPI application with a health check endpoint. Use environment variables for configuration (database URL, chunk size). Document the directory structure and required dependencies. **Use Copilot** to generate the initial project skeleton, including `main.py`, `models.py` for SQLAlchemy, and a `requirements.txt` or `pyproject.toml`.

2. **Data Understanding & Ingestion Pipeline (45–60 min)**  
   Use pandas to inspect the CSV shape and column names. Write an ingestion script (`scripts/ingest.py`) that reads the CSV in chunks (e.g., 500 rows at a time) and processes each chunk into numpy arrays. Convert each row to a 1×200 uint8 array, resize to 1×150 via bilinear interpolation (using Pillow or cv2), apply the colour map LUT, encode to PNG bytes with Pillow, and upsert into the `frames` table (`depth` as primary key). **Use Copilot** to scaffold the ingestion function, but review its implementation to ensure vectorisation and error handling.

3. **Colour Map LUT & Resize Functions (30–45 min)**  
   Define a function to build a 256×3 LUT that smoothly maps grayscale values to a gradient (e.g., dark blue → green → yellow → red). Vectorise the application of this LUT to grayscale arrays via NumPy indexing. Implement a resize function that resizes a 1×200 grayscale array to 1×150 using bilinear interpolation. Unit test both functions. **Use Copilot** to draft these functions, but adjust the colour stops and interpolation to your specifications.

4. **Database Schema & Persistence Layer (45–60 min)**  
   Define a SQLAlchemy model `Frame` with columns `depth` (primary key), `width`, `height`, `image_png` (blob), and `created_at` (timestamp). Configure a session factory and implement an upsert function that inserts or updates rows based on `depth`. Choose SQLite for simplicity (or Postgres if you prefer). **Use Copilot** to scaffold the model and upsert function.

5. **FastAPI Endpoints (60–90 min)**  
   Implement `GET /frames?depth_min=&depth_max=&limit=` to return frames within the specified depth range. Validate query parameters with Pydantic. Optionally add a `POST /frames/reload` endpoint to trigger re‑ingestion. Use dependency injection to provide DB sessions. **Use Copilot** to generate route definitions and Pydantic schemas, but ensure proper response models and base64 encoding of image binaries.

6. **Testing & Validation (45–60 min)**  
   Write tests using pytest for the LUT, resize function, DB upsert, and API endpoints. Use FastAPI’s TestClient or httpx for API tests. Aim for clear, deterministic tests. **Use Copilot** to generate test templates, then fill in assertions.

7. **Containerisation & Deployment (30–45 min)**  
   Create a multi‑stage Dockerfile that installs dependencies, copies the source, and launches the Uvicorn server. Write a docker‑compose file to run the API and a database together. Test that `docker compose up` brings up the service and `/docs` returns the OpenAPI spec. **Use Copilot** to generate Dockerfile and compose snippets, but verify that the final image is lean and environment variables are correctly passed.

8. **Documentation & README (30–45 min)**  
   Prepare a clear README that explains how to set up the environment, run the ingestion script, start the API (locally and via Docker), and make requests. Mention assumptions (e.g., each CSV row represents a single pixel row of an image), performance characteristics, and possible extensions (async DB, storing grayscale and colour variants, deploying to Kubernetes). Emphasise that the solution follows **best practices**, adheres to assignment requirements, and demonstrates readiness for production. **Use Copilot** to draft the README but refine to match your voice and highlight your senior‑level decisions.

### Tone & Copilot Guidance

Throughout the project:

- **Lead Copilot**: Write clear function signatures and descriptive comments first; then let Copilot auto‑complete. For example, include comments like “// Copilot, implement bilinear resize for a 1×200 gray array to 1×150” or “# Generate SQLAlchemy model for frames table with depth as PK” to guide the assistant.
- **Review & Refactor**: Treat Copilot as a collaborator that generates drafts. Always review its output for accuracy, performance, security, and adherence to the assignment requirements. Refactor code to improve readability and maintainability.
- **Follow best practices**: Use PEP 8 for Python code, proper error handling, logging, and type annotations. Structure the repository logically. Write meaningful commit messages and document any assumptions or deviations from the assignment brief.

By following this plan and leveraging Copilot strategically, you will produce a polished solution that not only satisfies the assignment’s requirements but also showcases your senior engineering expertise, attention to detail, and ability to anticipate future needs.
