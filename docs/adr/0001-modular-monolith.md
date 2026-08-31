# ADR 0001: Modular monolith

Status: Accepted — 2026-08-31

Use a Python modular monolith with dependency direction toward domain and calculation
code. It provides transactional consistency and simple operations while preserving
ports that can later be separated. Microservices are rejected until measured scaling
or ownership constraints justify them.

