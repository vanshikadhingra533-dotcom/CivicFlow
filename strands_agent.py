"""
CivicFlow Strands Agent

Uses the Strands Agents SDK with a local Ollama model.
"""

try:
    from strands import Agent, tool
    from strands.models.ollama import OllamaModel

    STRANDS_AVAILABLE = True

except ImportError:
    STRANDS_AVAILABLE = False


# ============================================================
# CIVICFLOW TOOL
# ============================================================

@tool
def civic_analysis_tool(
    category: str,
    location: str,
    priority: str,
    department: str,
    evidence_score: int,
    missing_information: str
) -> str:
    """
    Provide structured CivicFlow analysis to the AI agent.

    Args:
        category: Detected civic issue category.
        location: Detected complaint location.
        priority: Calculated complaint priority.
        department: Department selected for routing.
        evidence_score: Evidence score from 0 to 100.
        missing_information: Information that may still be missing.

    Returns:
        The exact structured information that the agent should explain.
    """

    return f"""
Category: {category}
Location: {location}
Priority: {priority}
Department: {department}
Evidence Score: {evidence_score}/100
Missing Information: {missing_information}
"""


# ============================================================
# FALLBACK REASONING
# ============================================================

def fallback_reasoning(
    category,
    location,
    priority,
    department,
    evidence_score,
    missing_information
):
    """
    Fallback explanation if Strands is unavailable.
    """

    reasons = []

    reasons.append(
        f"Category: The complaint was classified as {category}."
    )

    if location and location != "Not specified":
        reasons.append(
            f"Location: The reported location is {location}."
        )
    else:
        reasons.append(
            "Location: No specific location was provided."
        )

    reasons.append(
        f"Priority: The complaint was assigned {priority} priority."
    )

    reasons.append(
        f"Department: The complaint was routed to {department}."
    )

    reasons.append(
        f"Evidence: The calculated evidence score is {evidence_score}/100."
    )

    if (
        missing_information
        and missing_information != "No major information missing"
    ):
        reasons.append(
            f"Missing information: {missing_information}."
        )
    else:
        reasons.append(
            "Missing information: No major information is missing."
        )

    return "\n".join(
        f"• {reason}"
        for reason in reasons
    )


# ============================================================
# STRANDS AI REASONING
# ============================================================

def generate_ai_reasoning(
    category,
    location,
    priority,
    department,
    evidence_score,
    missing_information
):
    """
    Generate a concise explanation using Strands + Ollama.

    Returns:
        (reasoning_text, agent_used)
    """

    fallback = fallback_reasoning(
        category,
        location,
        priority,
        department,
        evidence_score,
        missing_information
    )

    if not STRANDS_AVAILABLE:
        return fallback, False

    try:

        # ----------------------------------------------------
        # Local Ollama model
        # ----------------------------------------------------

        ollama_model = OllamaModel(
            host="http://localhost:11434",
            model_id="llama3.2:3b",
            temperature=0.1
        )


        # ----------------------------------------------------
        # CivicFlow Strands Agent
        # ----------------------------------------------------

        agent = Agent(

            model=ollama_model,

            system_prompt="""
You are CivicFlow's AI explanation agent.

Your job is ONLY to explain the structured analysis
already produced by CivicFlow.

STRICT RULES:

1. Use ONLY the information provided to you.

2. NEVER invent facts.

3. NEVER add information about the complaint that
   was not provided.

4. NEVER say that you physically inspected or verified
   the problem.

5. NEVER change the category, priority, department,
   evidence score, or missing information.

6. Do not describe a department as "responsible",
   "official", or "authorized" unless that information
   is explicitly provided.

7. Do not call the evidence "credible", "verified",
   or "confirmed".

8. Do not create new reasons for the priority.

9. Simply explain the values that CivicFlow calculated.

10. Return EXACTLY 5 bullet points.

Use this format:

• Category: [explain the detected category]
• Priority: [state the assigned priority]
• Department: [state the selected department]
• Evidence: [state the evidence score]
• Missing information: [state whether information is missing]

Keep every bullet short and professional.
Do not add an introduction.
Do not add a conclusion.
Do not add extra bullets.
""",

            tools=[civic_analysis_tool]
        )


        # ----------------------------------------------------
        # Input to the agent
        # ----------------------------------------------------

        prompt = f"""
Explain this CivicFlow analysis:

Category: {category}

Location: {location}

Priority: {priority}

Department: {department}

Evidence Score: {evidence_score}/100

Missing Information: {missing_information}

Follow the exact five-bullet format from your instructions.
"""


        # ----------------------------------------------------
        # Run Strands agent
        # ----------------------------------------------------

        result = agent(prompt)


        # ----------------------------------------------------
        # Extract output
        # ----------------------------------------------------

        output = getattr(
            result,
            "output",
            None
        )

        if output:

            return (
                str(output).strip(),
                True
            )


        text = str(result).strip()

        if text:

            return (
                text,
                True
            )


        return fallback, False


    except Exception as e:

        print(
            "Strands + Ollama unavailable:",
            e
        )

        return fallback, False