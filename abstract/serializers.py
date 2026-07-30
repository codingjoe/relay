"""DRF serializers for chart data API."""

from rest_framework import serializers


class ChartSeriesSerializer(serializers.Serializer):
    """Single chart series (e.g. one status/disposition)."""

    key = serializers.CharField()
    label = serializers.CharField()
    color = serializers.CharField()


class ChartDataSerializer(serializers.Serializer):
    """Series metadata and data rows for a chart."""

    series = ChartSeriesSerializer(many=True)
    rows = serializers.ListField(child=serializers.DictField())
