from .models import JobSpec, NodeSpec


def build_sequence_nodes(job: JobSpec) -> list[tuple[str, str, NodeSpec]]:
    """
    Returns linear sequence as:
    [(group_id, "original"|"effect", node), ...]
    """
    sequence: list[tuple[str, str, NodeSpec]] = []
    for group in job.groups:
        sequence.append((group.group_id, "original", group.original))
        for effect in group.effects:
            sequence.append((group.group_id, "effect", effect))
    return sequence
