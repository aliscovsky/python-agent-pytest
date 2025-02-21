import logging
from typing import List, Optional

from _pytest.nodes import Item
from _pytest.reports import TestReport

from pytest_zebrunner.api.client import ZebrunnerAPI
from pytest_zebrunner.api.models import (
    CorrelationDataModel,
    FinishTestModel,
    FinishTestSessionModel,
    MilestoneModel,
    NotificationsType,
    NotificationTargetModel,
    StartTestModel,
    StartTestRunModel,
    StartTestSessionModel,
    TestRunConfigModel,
    TestStatus,
)
from pytest_zebrunner.ci_loaders import resolve_ci_context
from pytest_zebrunner.context import Test, TestRun, zebrunner_context
from pytest_zebrunner.zebrunner_logging import ZebrunnerHandler

logger = logging.getLogger(__name__)


class ReportingService:
    def __init__(self) -> None:
        self.api = ZebrunnerAPI(
            zebrunner_context.settings.server.hostname, zebrunner_context.settings.server.access_token
        )

    def authorize(self) -> None:
        if not self.api.authenticated:
            self.api.auth()

    def get_notification_configurations(self) -> Optional[List[NotificationTargetModel]]:
        settings = zebrunner_context.settings
        if settings.notifications:
            configs = []
            if settings.notifications.emails:
                configs.append(
                    NotificationTargetModel(
                        type=NotificationsType.EMAIL_RECIPIENTS.value, value=settings.notifications.emails
                    )
                )
            if settings.notifications.slack_channels:
                configs.append(
                    NotificationTargetModel(
                        type=NotificationsType.SLACK_CHANNELS.value, value=settings.notifications.slack_channels
                    )
                )
            if settings.notifications.ms_teams_channels:
                configs.append(
                    NotificationTargetModel(
                        type=NotificationsType.MS_TEAMS_CHANNELS.value, value=settings.notifications.ms_teams_channels
                    )
                )
            return configs
        else:
            return None

    def start_test_run(self) -> None:
        self.authorize()
        settings = zebrunner_context.settings
        test_run = TestRun(settings.run.display_name, settings.run.environment, settings.run.build)
        zebrunner_context.test_run = test_run
        milestone = (
            MilestoneModel(id=settings.milestone.id, name=settings.milestone.name) if settings.milestone else None
        )
        test_run.zebrunner_id = self.api.start_test_run(
            settings.project_key,
            StartTestRunModel(
                name=test_run.name,
                framework="pytest",
                config=TestRunConfigModel(environment=test_run.environment, build=test_run.build),
                milestone=milestone,
                ci_context=resolve_ci_context(),
                notification_targets=self.get_notification_configurations(),
            ),
        )
        if settings.send_logs:
            logging.root.addHandler(ZebrunnerHandler())

    def start_test(self, report: TestReport, item: Item) -> None:
        self.authorize()
        test = Test(
            name=item.name,
            file=item.nodeid.split("::")[1],
            maintainers=[mark.args[0] for mark in item.iter_markers("maintainer")],
            labels=[(str(mark.args[0]), str(mark.args[1])) for mark in item.iter_markers("label")],
        )
        zebrunner_context.test = test

        if zebrunner_context.test_run_is_active:
            test.zebrunner_id = self.api.start_test(
                zebrunner_context.test_run_id,
                StartTestModel(
                    name=test.name,
                    class_name=test.file,
                    method_name=test.name,
                    maintainer=",".join(test.maintainers),
                    labels=[{"key": label[0], "value": label[1]} for label in test.labels],
                    correlation_data=CorrelationDataModel(name=test.name).json(),
                ),
            )

        if report.skipped and zebrunner_context.test_is_active:
            skip_markers = list(filter(lambda x: x.name == "skip", item.own_markers))
            skip_reason = skip_markers[0].kwargs.get("reason") if skip_markers else None
            self.api.finish_test(
                zebrunner_context.test_run_id,
                zebrunner_context.test_id,
                FinishTestModel(reason=skip_reason, result=TestStatus.SKIPPED.value),
            )
            zebrunner_context.test = None

    def finish_test(self, report: TestReport, item: Item) -> None:
        if zebrunner_context.test_is_active:
            self.authorize()
            xfail_markers = list(item.iter_markers("xfail"))
            fail_reason = None
            is_strict = False
            if xfail_markers:
                fail_reason = xfail_markers[0].kwargs.get("reason")
                is_strict = xfail_markers[0].kwargs.get("strict", False)

            if report.passed:
                status = TestStatus.PASSED
                if xfail_markers:
                    if is_strict:
                        status = TestStatus.FAILED
                        fail_reason = report.longreprtext
                    else:
                        status = TestStatus.SKIPPED
            else:
                status = TestStatus.FAILED
                fail_reason = report.longreprtext
                if xfail_markers:
                    status = TestStatus.SKIPPED
                    fail_reason = xfail_markers[0].kwargs.get("reason")

            self.api.finish_test(
                zebrunner_context.test_run_id,
                zebrunner_context.test_id,
                FinishTestModel(
                    result=status.value,
                    reason=fail_reason,
                ),
            )
            zebrunner_context.test = None
            return

    def finish_test_run(self) -> None:
        self.authorize()
        if zebrunner_context.test_run_is_active:
            self.api.finish_test_run(zebrunner_context.test_run_id)

            handlers = list(filter(lambda x: isinstance(x, ZebrunnerHandler), logging.root.handlers))
            if len(handlers) > 0:
                zebrunner_handler: ZebrunnerHandler = handlers[0]  # type: ignore
                zebrunner_handler.push_logs()

        self.api.close()

    def start_test_session(self, session_id: str, capabilities: dict, desired_capabilities: dict) -> Optional[str]:
        self.authorize()
        if zebrunner_context.test_run_is_active:
            zebrunner_session_id = self.api.start_test_session(
                zebrunner_context.test_run_id,
                StartTestSessionModel(
                    session_id=session_id, desired_capabilities=desired_capabilities, capabilities=capabilities
                ),
            )
            return zebrunner_session_id
        return None

    def finish_test_session(self, zebrunner_session_id: str, related_tests: List[str]) -> None:
        self.authorize()
        if zebrunner_context.test_run_is_active:
            self.api.finish_test_session(
                zebrunner_context.test_run_id,
                zebrunner_session_id,
                FinishTestSessionModel(test_ids=related_tests),
            )

    def filter_test_items(self, items: List[Item]) -> List[Item]:
        run_context = zebrunner_context.settings.run.context
        if run_context is not None:
            self.authorize()
            context_data = self.api.get_rerun_tests(run_context)
            rerun_names = {x.correlation_data.name for x in context_data.tests if x.correlation_data is not None}
            return list(filter(lambda x: x.name in rerun_names, items))
        else:
            return items
