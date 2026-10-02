"""Health checks for third-party status pages without a bundled check."""

import dataclasses
import datetime

from health_check.contrib.atlassian import AtlassianStatusPage


@dataclasses.dataclass
class Codecov(AtlassianStatusPage):
    """Check Codecov status via its public status page."""

    timeout: datetime.timedelta = dataclasses.field(
        default=datetime.timedelta(seconds=10), repr=False
    )
    base_url: str = dataclasses.field(
        default="https://status.codecov.com", init=False, repr=False
    )


@dataclasses.dataclass
class Npm(AtlassianStatusPage):
    """Check the npm registry status via its public status page."""

    timeout: datetime.timedelta = dataclasses.field(
        default=datetime.timedelta(seconds=10), repr=False
    )
    base_url: str = dataclasses.field(
        default="https://status.npmjs.org", init=False, repr=False
    )
    component: str = "Package installation"


@dataclasses.dataclass
class PythonPackageIndex(AtlassianStatusPage):
    """Check the Python package index status via its public status page."""

    timeout: datetime.timedelta = dataclasses.field(
        default=datetime.timedelta(seconds=10), repr=False
    )
    base_url: str = dataclasses.field(
        default="https://status.python.org", init=False, repr=False
    )
    component: str = "PyPI"
