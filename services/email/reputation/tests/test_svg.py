from services.email.reputation import svg


class TestWeek:
    def test_week__draws_the_tallest_day_at_full_height(self):
        assert svg.week([1, 2]) == (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 44"'
            ' width="600" height="44">'
            '<rect x="0" y="22" width="296" height="22" rx="4" fill="#8b5cf6"/>'
            '<rect x="304" y="0" width="296" height="44" rx="4" fill="#8b5cf6"/>'
            "</svg>"
        )

    def test_week__caps_the_chart_at_a_month_of_days(self):
        assert svg.week(list(range(40))).count("<rect") == 31

    def test_week__drops_the_days_older_than_a_month(self):
        chart = svg.week([9] + [0] * 30 + [5])

        # The dropped oldest day must not scale the newest day's bar.
        assert '<rect x="0" y="44" width="11" height="0"' in chart
        assert '<rect x="570" y="0" width="11" height="44"' in chart

    def test_week__draws_flat_bars_when_the_kept_window_has_no_activity(self):
        chart = svg.week([5] + [0] * 31)

        assert chart.count("<rect") == 31
        assert chart.count('height="0"') == 31
