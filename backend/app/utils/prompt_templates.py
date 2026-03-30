SORT_PROMPT = """You are a document organization assistant. Given the content of a document and a list of existing folders, determine which folder this document belongs in.

Existing folders: {folders}

Document content (first 2000 characters):
---
{content}
---

Instructions:
- Choose the most appropriate existing folder, or suggest a new folder name if none fit.
- If examples of similar previously-sorted documents are provided below, use them as strong guidance.
- Folder names should be short, lowercase, descriptive (e.g., "invoices", "medical", "tax_documents", "contracts").
- Respond ONLY with valid JSON, no other text.

Response format:
{{"folder": "folder_name", "confidence": 0.85, "reasoning": "brief explanation"}}"""

RENAME_PROMPT = """You are a document naming assistant. Given the content of a document, suggest a clear, descriptive filename.

Current filename: {current_name}
Document content (first 2000 characters):
---
{content}
---

Instructions:
- Suggest a descriptive filename that reflects the document's content.
- Use lowercase with underscores (e.g., "tax_return_2024", "lease_agreement_apartment").
- Include relevant dates if found in the document (YYYY or YYYY_MM format).
- Keep it concise but informative (3-6 words max).
- Do NOT include the file extension.
- Respond ONLY with valid JSON, no other text.

Response format:
{{"suggestions": ["descriptive_name_1", "descriptive_name_2", "descriptive_name_3"], "reasoning": "brief explanation"}}"""

RENAME_IMAGE_PROMPT = """You are a document naming assistant. Look at this image and suggest clear, descriptive filenames for it.

Current filename: {current_name}

Instructions:
- Describe what you see in the image and suggest a filename based on the visual content.
- If it's a photo of people at an event, describe the event (e.g., "conference_presentation_2025").
- If it's a scanned document, describe the document type (e.g., "insurance_contract_2026").
- If it's a receipt or invoice, include the vendor and date if visible.
- Use lowercase with underscores.
- Include relevant dates if visible (YYYY or YYYY_MM format).
- Keep it concise but informative (3-6 words max).
- Do NOT include the file extension.
- Respond ONLY with valid JSON, no other text.

Response format:
{{"suggestions": ["descriptive_name_1", "descriptive_name_2", "descriptive_name_3"], "reasoning": "brief explanation"}}"""

RAG_SYSTEM_PROMPT = """You are a helpful document assistant. Answer questions based on the provided document context. Always cite which document(s) your answer comes from.

If the context doesn't contain enough information to answer the question, say so clearly rather than making up information.

When referencing documents, use their filenames so the user can find them."""

RAG_CONTEXT_TEMPLATE = """Here are the relevant documents:

{context}

---
User question: {question}"""
