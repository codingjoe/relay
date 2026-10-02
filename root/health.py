from django.conf import settings
from django.urls import path
from health_check.views import HealthCheckView
from redis.asyncio import Redis

node_checks = [
    "health_check.contrib.psutil.Disk",
    "health_check.contrib.psutil.Memory",
]

application_checks = [
    "health_check.Database",
    "health_check.Cache",
    (
        "health_check.contrib.redis.Redis",
        {"client_factory": lambda: Redis.from_url(settings.REDIS_URL)},
    ),
    (
        "health_check.contrib.redis.Redis",
        {"client_factory": lambda: Redis.from_url(settings.TASK_REDIS_URL)},
    ),
    *(
        ("health_check.contrib.threadmill.Threadmill", {"queue_name": queue_name})
        for queue_name in settings.TASK_QUEUES
    ),
    "health_check.contrib.crontask.Scheduler",
    "health_check.Storage",
    "health_check.Mail",
    (
        "health_check.DNS",
        {"hostname": "mail.relay.open.relays.to", "record_type": "MX"},
    ),
]

pipeline_checks = [
    "health_check.contrib.rss.Hetzner",
    "health_check.contrib.rss.GoogleCloud",
    # CI, the image registry, the source checkout, and the API the runner
    # talks to.
    ("health_check.contrib.atlassian.GitHub", {"component": "Actions"}),
    ("health_check.contrib.atlassian.GitHub", {"component": "Packages"}),
    ("health_check.contrib.atlassian.GitHub", {"component": "Git Operations"}),
    ("health_check.contrib.atlassian.GitHub", {"component": "API Requests"}),
    "health_check.contrib.atlassian.Sentry",
    "health_check.contrib.atlassian.Npm",
    "health_check.contrib.atlassian.PyPI",
]

urlpatterns = [
    path("node/", HealthCheckView.as_view(checks=node_checks), name="health-node"),
    path(
        "application/",
        HealthCheckView.as_view(checks=application_checks),
        name="health-application",
    ),
    path(
        "pipeline/",
        HealthCheckView.as_view(checks=pipeline_checks),
        name="health-pipeline",
    ),
]
