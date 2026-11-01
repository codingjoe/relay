from unittest import mock

from abstract import proxy

HEADER = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT"
)

ROUTES = f"""{HEADER}
eth0\t00000000\t0100F40A\t0003\t0\t0\t0\t00000000\t0\t0\t0
eth0\t0000F40A\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0
"""

ROUTES_WITH_TWO_DEFAULTS = f"""{HEADER}
eth0\t00000000\t0100F40A\t0003\t0\t0\t100\t00000000\t0\t0\t0
eth1\t00000000\t0200F40A\t0003\t0\t0\t0\t00000000\t0\t0\t0
"""


def test_get_default_gateway__reads_the_default_route(tmp_path):
    route_table = tmp_path / "route"
    route_table.write_text(ROUTES)

    with mock.patch.object(proxy, "ROUTE_TABLE", route_table):
        assert proxy.get_default_gateway() == "10.244.0.1"


def test_get_default_gateway__reads_the_lowest_metric(tmp_path):
    route_table = tmp_path / "route"
    route_table.write_text(ROUTES_WITH_TWO_DEFAULTS)

    with mock.patch.object(proxy, "ROUTE_TABLE", route_table):
        assert proxy.get_default_gateway() == "10.244.0.2"


def test_get_default_gateway__without_a_route_table(tmp_path):
    with mock.patch.object(proxy, "ROUTE_TABLE", tmp_path / "missing"):
        assert proxy.get_default_gateway() is None


def test_get_trusted_proxy_hosts__adds_the_gateway(settings):
    settings.TRUSTED_PROXY_HOSTS = ["127.0.0.1"]

    with mock.patch.object(proxy, "get_default_gateway", return_value="10.244.0.1"):
        assert proxy.get_trusted_proxy_hosts() == ["127.0.0.1", "10.244.0.1"]
