"""Serve the production ASGI app with a deterministic model response for the Invoice fixture."""
import json
import os

import uvicorn

import main
from app import jobs
from app.generator import DocGenerator


class InvoiceModel:
    def complete(self, system, messages):
        prompt = messages[0]["content"]
        assert "Code analysis of file 'src/main/java/acme/Invoice.java'" in prompt
        summary = ("Calculates invoice totals with tax." if "Includes tax in the total." in prompt
                   else "Calculates invoice totals.")
        return json.dumps({
            "overview": summary,
            "overview_evidence": ["E1"],
            "classes": [{
                "name": "Invoice",
                "summary": summary,
                "evidence": ["E1"],
                "confidence": 0.8,
                "methods": [],
            }],
            "functions": [],
            "endpoints": [],
        })


def fixture_generator():
    return DocGenerator(InvoiceModel(), max_attempts=1, backoff_seconds=0)


if __name__ == "__main__":
    main.get_generator = fixture_generator
    jobs.get_generator = fixture_generator
    uvicorn.run(main.app, host=os.environ.get("LIVINGDOCS_E2E_AI_HOST", "127.0.0.1"),
                port=int(os.environ.get("LIVINGDOCS_E2E_AI_PORT", "8001")))
