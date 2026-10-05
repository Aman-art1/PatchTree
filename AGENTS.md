# Agent Instructions for PatchTree

## Before marking any task done
1. Run the code yourself (start the server, run the test, run the build) — don't just write it and assume it works.
2. If there's an error, fix it and run it again before reporting back.
3. Never guess a library's function names — check the installed version in package.json / requirements.txt first, or look it up with the docs tool if unsure.
4. Keep changes scoped to what was asked. Don't refactor unrelated files unless told to.

## Project context
- Backend: Python + FastAPI
- Frontend: React + Vite + TypeScript
- Database: Supabase (hosted Postgres) — not local Docker Postgres
- AI calls and sandboxing go through Nebius Token Factory + Contree SDK
- See /docs for full architecture, risks, and build plan before making structural changes