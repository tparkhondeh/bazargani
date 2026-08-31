# ADR 0003: Evidence-first acquisition

Status: Accepted — 2026-08-31

Acquisition is implemented through provider ports and every material observation
retains provenance and evidence class. Generic arbitrary-URL scraping is rejected.
The first adapter consumes validated evidence bundles; network adapters require
source-specific approval, SSRF controls, and contract tests.

