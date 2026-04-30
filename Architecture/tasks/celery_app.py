"""Celery application and async floor plan generation task."""

import os
import sys
from pathlib import Path

# Ensure Architecture/ is on sys.path for all Celery worker subprocesses.
# On Windows, prefork workers do not inherit the parent's sys.path.
_arch_dir = str(Path(__file__).resolve().parent.parent)
if _arch_dir not in sys.path:
    sys.path.insert(0, _arch_dir)

from dotenv import load_dotenv

# Worker process loads its own .env — independent of the API process.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from celery import Celery

from utils.logger import get_logger

_logger = get_logger("celery_app")

_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "c01_tasks",
    broker=_redis_url,
    backend=_redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="c01_tasks.generate_floor_plan_async", bind=True)
def generate_floor_plan_async(
    self,
    buildable_zone: dict,
    user_requirements: dict,
) -> list[dict]:
    """Runs the Stage 3 pipeline asynchronously: RAG retrieval, LLM generation,
    validation, and scoring.

    Args:
        buildable_zone: Output dict from Stage 2 BuildableZoneCalculator.
        user_requirements: User form input dict with room types, floors, style, etc.

    Returns:
        list[dict]: List of 3 scored floor plan alternatives, each containing
            quality_scores. Returns ``[{"error": str}]`` on failure.
    """
    try:
        from stages.stage3_floor_plan.rag_retriever import RAGRetriever
        from stages.stage3_floor_plan.prompt_builder import PromptBuilder
        from stages.stage3_floor_plan.llm_generator import FloorPlanGenerator
        from stages.stage3_floor_plan.validator import LayoutValidator
        from stages.stage3_floor_plan.scorer import LayoutScorer

        _logger.info("Stage 3 async task started, task_id=%s", self.request.id)

        retrieved = RAGRetriever().retrieve(buildable_zone, user_requirements)
        prompt = PromptBuilder().build(buildable_zone, user_requirements, retrieved)
        alternatives = FloorPlanGenerator().generate(prompt)

        validator = LayoutValidator()
        scorer = LayoutScorer()
        results: list[dict] = []

        for plan in alternatives:
            is_valid, violations = validator.validate(plan, buildable_zone)
            scores = scorer.score(plan)
            plan["is_valid"] = is_valid
            plan["violations"] = violations
            plan["quality_scores"] = scores
            results.append(plan)

        _logger.info(
            "Stage 3 async task complete, task_id=%s, alternatives=%d",
            self.request.id,
            len(results),
        )
        return results

    except Exception as exc:
        _logger.error(
            "Stage 3 async task failed, task_id=%s, error=%s",
            self.request.id,
            str(exc),
        )
        return [{"error": str(exc)}]
