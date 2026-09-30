from services.email.reputation import chart


class TestWeek:
    def test_week__draws_the_tallest_day_at_full_height(self):
        mark = chart.week([1, 2])

        assert mark.count(f'bgcolor="{chart.COLUMN}"') == 2
        assert 'height="22"' in mark
        assert 'height="44"' in mark

    def test_week__draws_no_embedded_svg(self):
        assert "<svg" not in chart.week([1, 2, 3])

    def test_week__caps_the_chart_at_a_month_of_days(self):
        assert chart.week(list(range(40))).count('valign="bottom"') == 31

    def test_week__drops_the_days_older_than_a_month(self):
        mark = chart.week([9] + [0] * 30 + [5])

        # The dropped oldest day must not scale the newest day's bar.
        assert mark.count('valign="bottom"') == 31
        assert mark.count(f'bgcolor="{chart.COLUMN}"') == 1
        assert 'height="44"' in mark

    def test_week__draws_flat_bars_when_the_kept_window_has_no_activity(self):
        mark = chart.week([5] + [0] * 31)

        assert mark.count('valign="bottom"') == 31
        assert "bgcolor" not in mark

    def test_week__spaces_the_days_but_not_after_the_last(self):
        assert chart.week([1, 1, 1]).count("padding-right:8px") == 2
