from pocketflow import Flow

from nodes import (
    ClassifyIntent,
    GenerateProposalAnswer,
    JudgeProposalAnswer,
    RetrieveProposalContext,
    SelectSkill,
    Done,
)


def create_flow():
    classify = ClassifyIntent()
    retrieve = RetrieveProposalContext()
    select_skill = SelectSkill()
    generate = GenerateProposalAnswer()
    judge = JudgeProposalAnswer()
    done = Done()

    classify >> retrieve >> select_skill >> generate >> judge
    judge - "revise" >> generate
    judge - "done" >> done

    return Flow(start=classify)
