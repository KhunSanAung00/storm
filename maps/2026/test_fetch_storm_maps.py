import unittest
from datetime import datetime, timezone

from fetch_storm_maps import (
    insert_readme_entry,
    model_label,
    parse_active_basins,
    parse_model_time,
)


TRACKER_HTML = """
<th colspan="4" class="top">Current Data</th>
<tr><th colspan="4">18 Nov, 2026 9:48 GMT</th></tr>
<tr>
  <td align=center><a href=
  ./202604P.html
  >
  XAVIER
  </a></td>
  <td align=center><a href=
  ./P.html
  >
  SW Pacific
  </a></td>
</tr>
<tr>
  <td align=center><a href=./202605B.html>AKVAN</a></td>
  <td align=center><a href=./I.html>N Indian</a></td>
</tr>
"""


class FetchStormMapsTests(unittest.TestCase):
    def test_extracts_model_time_and_active_basins(self):
        self.assertEqual(
            parse_model_time(TRACKER_HTML),
            datetime(2026, 11, 18, 9, 48, tzinfo=timezone.utc),
        )
        self.assertEqual(parse_active_basins(TRACKER_HTML), ["I", "P"])

    def test_inserts_timestamped_maps_once(self):
        readme = "# 2026 Events\n\n## Global Current Active Storms\n\n### Older entry\n"
        timestamp = datetime(2026, 11, 18, 9, 48, tzinfo=timezone.utc)
        images = ["2026-11-18-0948-globe.png", "2026-11-18-0948-I.png"]

        updated = insert_readme_entry(readme, timestamp, images)

        self.assertIn("### 18 Nov, 2026 9:48 GMT", updated)
        self.assertLess(updated.index(images[0]), updated.index("### Older entry"))
        self.assertEqual(insert_readme_entry(updated, timestamp, images), updated)
        self.assertEqual(model_label(timestamp), "18 Nov, 2026 9:48 GMT")


if __name__ == "__main__":
    unittest.main()
