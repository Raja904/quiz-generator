from app.models.schemas import QuizQuestion


def deduplicate_questions(questions: list[QuizQuestion]) -> list[QuizQuestion]:
    """
    Removes exact duplicate questions from the list (case-insensitive string match).
    Keeps the first occurrence.
    """
    seen: set[str] = set()
    deduped: list[QuizQuestion] = []

    for q in questions:
        normalized_q = q.question.strip().lower()
        if normalized_q not in seen:
            seen.add(normalized_q)
            deduped.append(q)

    return deduped
