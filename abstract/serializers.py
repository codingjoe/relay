"""DRF serializers for chart data API."""

from rest_framework import serializers


class ChartSeriesSerializer(serializers.Serializer):
    """A single chart series (e.g. one status/disposition)."""

    key = serializers.CharField()
    label = serializers.CharField()
    color = serializers.CharField()


class ChartDataSerializer(serializers.Serializer):
    """Chart data payload: series metadata + data rows."""

    series = ChartSeriesSerializer(many=True)
    rows = serializers.ListField(child=serializers.DictField())
