from pocketflow import Node

from utils import (
    call_llm,
    format_context,
    infer_intent,
    log_step,
    load_skills,
    parse_yaml_block,
    retrieve_context,
)


SKILL_BY_INTENT = {
    "draft_workpackage": "draft_workpackage",
    "review_workpackage": "review_workpackage",
    "assign_partners": "assign_partners",
    "check_call_alignment": "check_call_alignment",
    "design_deliverables": "design_deliverables",
    "proposal_strategy": "proposal_strategy",
}


class ClassifyIntent(Node):
    def prep(self, shared):
        return shared["task"]

    def exec(self, task):
        heuristic_intent = infer_intent(task)
        prompt = f"""
Classify this Horizon Europe proposal-assistant request.

Task: {task}

Valid intents:
- draft_workpackage
- review_workpackage
- assign_partners
- check_call_alignment
- design_deliverables
- proposal_strategy

Return ONLY YAML:
```yaml
intent: one_valid_intent
why: brief reason
```
"""
        try:
            raw_response = call_llm(prompt)
            parsed = parse_yaml_block(raw_response)
            intent = parsed.get("intent", heuristic_intent)
            if intent not in SKILL_BY_INTENT:
                intent = heuristic_intent
            parsed["intent"] = intent
            return {
                "intent": parsed["intent"],
                "why": parsed.get("why", ""),
                "heuristic_intent": heuristic_intent,
                "prompt": prompt,
                "raw_response": raw_response,
                "parsed": parsed,
                "fallback": False,
            }
        except Exception as exc:
            return {
                "intent": heuristic_intent,
                "why": f"Heuristic fallback after classification error: {exc}",
                "heuristic_intent": heuristic_intent,
                "prompt": prompt,
                "raw_response": "",
                "parsed": {},
                "fallback": True,
            }

    def post(self, shared, prep_res, exec_res):
        shared["intent"] = exec_res["intent"]
        shared["intent_reason"] = exec_res.get("why", "")
        log_step(
            shared,
            "ClassifyIntent",
            {
                "task": prep_res,
                "heuristic_intent": exec_res.get("heuristic_intent"),
                "selected_intent": exec_res["intent"],
                "explicit_reason": exec_res.get("why", ""),
                "fallback": exec_res.get("fallback", False),
                "prompt": exec_res.get("prompt", ""),
                "raw_response": exec_res.get("raw_response", ""),
                "parsed_response": exec_res.get("parsed", {}),
            },
        )
        print(f"🧭 Intent: {shared['intent']}")
        return "default"


class RetrieveProposalContext(Node):
    def prep(self, shared):
        return shared["memory"], shared["task"]

    def exec(self, inputs):
        memory, task = inputs
        return retrieve_context(memory, task, top_k=8)

    def post(self, shared, prep_res, exec_res):
        shared["retrieved_context"] = exec_res
        log_step(
            shared,
            "RetrieveProposalContext",
            {
                "task": shared["task"],
                "retrieved_count": len(exec_res),
                "retrieved_context": exec_res,
            },
        )
        print(f"📚 Retrieved {len(exec_res)} context passages")
        return "default"


class SelectSkill(Node):
    def prep(self, shared):
        return shared["intent"], shared["skills_dir"]

    def exec(self, inputs):
        intent, skills_dir = inputs
        skills = load_skills(skills_dir)
        skill_name = SKILL_BY_INTENT.get(intent, "proposal_strategy")
        if skill_name not in skills:
            skill_name = "proposal_strategy"
        return skill_name, skills[skill_name], sorted(skills.keys())

    def post(self, shared, prep_res, exec_res):
        skill_name, skill_content, available_skills = exec_res
        shared["selected_skill"] = skill_name
        shared["selected_skill_content"] = skill_content
        log_step(
            shared,
            "SelectSkill",
            {
                "intent": prep_res[0],
                "available_skills": available_skills,
                "selected_skill": skill_name,
                "skill_instructions": skill_content,
            },
        )
        print(f"🧩 Skill: {skill_name}")
        return "default"


class GenerateProposalAnswer(Node):
    def prep(self, shared):
        return {
            "task": shared["task"],
            "intent": shared["intent"],
            "memory": shared["memory"],
            "retrieved_context": shared["retrieved_context"],
            "skill_name": shared["selected_skill"],
            "skill_content": shared["selected_skill_content"],
            "feedback": shared.get("judge_feedback", ""),
            "attempt": shared.get("attempt", 1),
        }

    def exec(self, data):
        context = format_context(data["memory"], data["retrieved_context"])
        feedback_block = ""
        if data["feedback"]:
            feedback_block = f"\nReviewer feedback to address:\n{data['feedback']}\n"

        prompt = f"""
You are a senior Horizon Europe proposal co-writer helping draft and review the DAIMON proposal.

Task intent: {data['intent']}
Skill selected: {data['skill_name']}

Skill instructions:
---
{data['skill_content']}
---

Context:
---
{context}
---
{feedback_block}
User request:
{data['task']}

Write the best possible response. Be concrete, proposal-oriented, and careful about source freshness.
If information is uncertain or missing, say so and propose a practical assumption.
"""
        answer = call_llm(prompt)
        return {
            "prompt": prompt,
            "answer": answer,
            "attempt": data["attempt"],
            "context_preview": context[:3000],
            "feedback_used": data["feedback"],
        }

    def post(self, shared, prep_res, exec_res):
        shared["draft_answer"] = exec_res["answer"]
        log_step(
            shared,
            "GenerateProposalAnswer",
            {
                "attempt": exec_res["attempt"],
                "intent": prep_res["intent"],
                "selected_skill": prep_res["skill_name"],
                "feedback_used": exec_res["feedback_used"],
                "prompt": exec_res["prompt"],
                "answer": exec_res["answer"],
            },
        )
        print(f"✍️ Generated answer attempt {shared.get('attempt', 1)}")
        return "default"


class JudgeProposalAnswer(Node):
    def prep(self, shared):
        return {
            "task": shared["task"],
            "answer": shared["draft_answer"],
            "attempt": shared.get("attempt", 1),
            "max_attempts": shared.get("max_attempts", 2),
        }

    def exec(self, data):
        prompt = f"""
You are reviewing an answer from a Horizon Europe proposal assistant.

Check whether the answer:
- follows the user's request
- aligns with the Horizon call requirements
- avoids inventing partner facts, especially where researcher profiles are unresolved
- gives actionable WP/proposal guidance

User request:
{data['task']}

Answer:
{data['answer']}

Return ONLY YAML:
```yaml
decision: pass_or_revise
feedback: |
  concise, specific feedback if revision is needed; otherwise short approval reason
```
"""
        try:
            raw_response = call_llm(prompt)
            parsed = parse_yaml_block(raw_response)
            decision = parsed.get("decision", "pass_or_revise")
            if decision not in {"pass", "revise", "pass_or_revise"}:
                decision = "revise"
            if decision == "pass_or_revise":
                decision = "pass"
            return {
                "decision": decision,
                "feedback": parsed.get("feedback", ""),
                "prompt": prompt,
                "raw_response": raw_response,
                "parsed": parsed,
                "fallback": False,
            }
        except Exception as exc:
            return {
                "decision": "pass",
                "feedback": f"Judge fallback after parsing error: {exc}",
                "prompt": prompt,
                "raw_response": "",
                "parsed": {},
                "fallback": True,
            }

    def post(self, shared, prep_res, exec_res):
        shared["judge_feedback"] = exec_res.get("feedback", "")
        attempt = shared.get("attempt", 1)
        max_attempts = shared.get("max_attempts", 2)
        log_step(
            shared,
            "JudgeProposalAnswer",
            {
                "attempt": attempt,
                "max_attempts": max_attempts,
                "decision": exec_res["decision"],
                "explicit_feedback": exec_res.get("feedback", ""),
                "fallback": exec_res.get("fallback", False),
                "prompt": exec_res.get("prompt", ""),
                "raw_response": exec_res.get("raw_response", ""),
                "parsed_response": exec_res.get("parsed", {}),
            },
        )

        if exec_res["decision"] == "revise" and attempt < max_attempts:
            shared["attempt"] = attempt + 1
            print("🔎 Reviewer requested a revision")
            return "revise"

        shared["result"] = shared["draft_answer"]
        shared["review_status"] = exec_res["decision"]
        print(f"✅ Review: {exec_res['decision']}")
        return "done"


class Done(Node):
    def prep(self, shared):
        return None

    def exec(self, prep_res):
        return None

    def post(self, shared, prep_res, exec_res):
        return "default"
