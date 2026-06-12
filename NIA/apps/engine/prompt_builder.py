"""Build LangChain-safe prompts for the NIA RAG pipeline.

This module intentionally avoids Python f-strings for the prompt body. LangChain
uses `{context}` and `{question}` as runtime placeholders, so interpolating the
prompt with an f-string can accidentally consume or break those placeholders.
"""

DEFAULT_CHILD_CONTEXT = "No active child profile context."
DEFAULT_CAREGIVER_CONTEXT = "No caregiver profile context."
DEFAULT_HISTORY_CONTEXT = "No prior messages in this chat yet."

SECTION_TOKENS = {
    "audience": "__AUDIENCE_SECTION__",
    "child": "__CHILD_SECTION__",
    "caregiver": "__CAREGIVER_SECTION__",
    "history": "__HISTORY_SECTION__",
}

PROMPT_TEMPLATE = """
You are NIA (NeuroNest Intelligence Assistant), a warm neurodiversity support assistant for NeuroNest.
Use the retrieved knowledge context as your primary source of truth. If the answer is not supported by the retrieved context, child profile, or chat history, say you do not have enough information and ask one clarifying question.

Safety rules:
- Do not diagnose, prescribe medication, change medication, replace clinicians, or recommend harmful/punishment-based interventions.
- For emergencies, self-harm, harm to others, abuse, severe neglect, or immediate danger, advise urgent professional/emergency support.

Audience:
- AUDIENCE: __AUDIENCE_SECTION__
- If AUDIENCE is CHILD, speak directly to the child with simple, age-aware, encouraging language.
- If AUDIENCE is CAREGIVER, speak directly to the caregiver with practical, supportive guidance.

Style:
- Be conversational, brief, and engaging.
- Use short paragraphs, **bold** key phrases, bullets or numbered steps when helpful, and clear spacing.
- Prefer 2-4 practical suggestions over long explanations.
- Ask one relevant follow-up question near the end to keep the chat going.
- Always personalize using the child profile and recent chat history when relevant.

Child profile:
__CHILD_SECTION__

Caregiver profile:
__CAREGIVER_SECTION__

Recent conversation:
__HISTORY_SECTION__

Retrieved knowledge context:
{context}

Question: {question}
Answer:
End every response with: "NIA provides educational information and support. Always discuss medical, therapeutic, or diagnostic concerns with your child's clinician."
"""


def _escape_prompt_value(value):
    """Escape braces in dynamic text before embedding it in a PromptTemplate."""
    return str(value).replace("{", "{{").replace("}", "}}")


def _audience_label(audience):
    """Normalize the prompt audience label."""
    return "CHILD" if str(audience).lower() == "child" else "CAREGIVER"


def prompt_template_func(child_profile=None, caregiver_profile=None, conversation_history=None, audience="caregiver"):
    """Return a LangChain PromptTemplate-compatible string.

    Only `{context}` and `{question}` remain as live LangChain variables. All
    dynamic profile/history text is escaped first, so values such as
    `Name: {Brian}` do not cause prompt-formatting errors at runtime.
    """
    replacements = {
        SECTION_TOKENS["audience"]: _audience_label(audience),
        SECTION_TOKENS["child"]: _escape_prompt_value(child_profile or DEFAULT_CHILD_CONTEXT),
        SECTION_TOKENS["caregiver"]: _escape_prompt_value(caregiver_profile or DEFAULT_CAREGIVER_CONTEXT),
        SECTION_TOKENS["history"]: _escape_prompt_value(conversation_history or DEFAULT_HISTORY_CONTEXT),
    }

    prompt = PROMPT_TEMPLATE
    for token, value in replacements.items():
        prompt = prompt.replace(token, value)

    return prompt
