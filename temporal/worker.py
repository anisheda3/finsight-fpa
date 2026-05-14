"""Temporal worker — registers workflows and activities."""
from __future__ import annotations

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import get_settings
from app.core.db import init_db
from app.core.logging import configure_logging
from app.core.redis import init_redis
from agents.hooks import set_redis_client
from agents.memory import init_memory
from temporal.activities import (
    forecast_metric_activity,
    ingest_actuals_activity,
    run_analysis_workflow_activity,
    run_anomaly_activity,
    run_insights_workflow_activity,
    run_scenario_activity,
    run_variance_activity,
    send_hitl_slack_activity,
    write_final_status_activity,
)
from temporal.forecast_rerun_saga import ForecastRerunSaga
from temporal.month_end_saga import MonthEndAnalysisSaga
from temporal.scenario_saga import ScenarioAnalysisSaga

logger = logging.getLogger(__name__)


async def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)

    pool = await init_db(s.postgres_url)
    init_memory(pool)
    set_redis_client(init_redis(s.redis_url))

    client = await Client.connect(s.temporal_address, namespace=s.temporal_namespace)
    worker = Worker(
        client,
        task_queue=s.temporal_task_queue,
        workflows=[MonthEndAnalysisSaga, ScenarioAnalysisSaga, ForecastRerunSaga],
        activities=[
            ingest_actuals_activity,
            forecast_metric_activity,
            run_variance_activity,
            run_anomaly_activity,
            run_analysis_workflow_activity,
            run_insights_workflow_activity,
            run_scenario_activity,
            send_hitl_slack_activity,
            write_final_status_activity,
        ],
    )
    logger.info("temporal worker starting on %s queue=%s",
                s.temporal_address, s.temporal_task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
