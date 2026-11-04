# AI Service API Contract

## Overview
The AI Service processes analysis payloads to render explanations and confidence scores.

## Endpoints

### POST `/ai/explain`
- **Request Body:**
  ```json
  {
    "code": "string",
    "issues": []
  }
