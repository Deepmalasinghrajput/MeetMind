"""Action items, decisions, questions, follow-up email."""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda

from core.llm import get_llm


def build_chain(system_prompt: str):
    llm = get_llm()
    return (
        RunnablePassthrough()
        | RunnableLambda(lambda x: {"text": x})
        | ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{text}"),
            ]
        )
        | llm
        | StrOutputParser()
    )


def extract_action_items(transcript: str) -> str:
    chain = build_chain(
        "You are an expert meeting analyst. From the meeting transcript, "
        "extract all action items. For each provide:\n"
        "- Task description\n"
        "- Owner (who is responsible)\n"
        "- Deadline (if mentioned, else write 'Not specified')\n\n"
        "Format as a numbered list. If none found say 'No action items found.'"
    )
    return chain.invoke(transcript)


def extract_key_decisions(transcript: str) -> str:
    chain = build_chain(
        "You are an expert meeting analyst. From the meeting transcript, "
        "extract all key decisions made. Format as a numbered list. "
        "If none found say 'No key decisions found.'"
    )
    return chain.invoke(transcript)


def extract_questions(transcript: str) -> str:
    chain = build_chain(
        "From the meeting transcript, extract all unresolved questions "
        "or topics needing follow-up. Format as a numbered list. "
        "If none found say 'No open questions found.'"
    )
    return chain.invoke(transcript)


def generate_follow_up_email(
    title: str,
    summary: str,
    action_items: str,
    key_decisions: str,
    open_questions: str,
) -> str:
    """Draft a professional follow-up email from meeting insights."""
    context = (
        f"Meeting title: {title}\n\n"
        f"Summary:\n{summary}\n\n"
        f"Action items:\n{action_items}\n\n"
        f"Key decisions:\n{key_decisions}\n\n"
        f"Open questions:\n{open_questions}\n"
    )
    chain = build_chain(
        "You are an executive assistant. Write a clear professional follow-up "
        "email after a meeting. Include: subject line, short greeting, "
        "key outcomes, action items with owners if known, open questions, "
        "and a polite closing. Keep it concise. Do not invent facts not in "
        "the provided notes."
    )
    return chain.invoke(context)
