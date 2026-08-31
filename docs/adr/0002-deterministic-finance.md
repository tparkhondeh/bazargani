# ADR 0002: Deterministic financial engine

Status: Accepted — 2026-08-31

All monetary, FX, quantity, tax, and scenario calculations use reviewed code,
`Decimal`, explicit currency, and reproducible inputs. LLM output may propose or
explain assumptions but can never calculate or silently commit financial values.

