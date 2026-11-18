import unittest
from datetime import datetime, timezone

from fetch_storm_maps import (
    himawari_product,
    insert_himawari_entry,
    insert_readme_entry,
    model_label,
    parse_active_basins,
    parse_jma_snapshot,
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

JMA_HTML = """
<select name="slt_time">
  <option value=0950>10:00 UTC 18 November 2026</option>
  <option value=0940>09:50 UTC 18 November 2026</option>
</select>
"""


class FetchStormMapsTests(unittest.TestCase):
    def test_extracts_model_time_and_active_basins(self):
        self.assertEqual(
            parse_model_time(TRACKER_HTML),
            datetime(2026, 11, 18, 9, 48, tzinfo=timezone.utc),
        )
        self.assertEqual(parse_active_basins(TRACKER_HTML), ["I", "P"])
        self.assertEqual(parse_active_basins("<html>No current storms</html>"), [])

    def test_selects_latest_jma_color_product(self):
        slot, image_time = parse_jma_snapshot(JMA_HTML)
        self.assertEqual(slot, "0950")
        self.assertEqual(
            image_time,
            datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(himawari_product(image_time), ("ngt", "Night Microphysics RGB"))
        self.assertEqual(
            himawari_product(datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)),
            ("trm", "True Color Reproduction"),
        )

    def test_inserts_timestamped_maps_once(self):
        readme = "# 2026 Events\n\n## Global Current Active Storms\n\n### Older entry\n"
        timestamp = datetime(2026, 11, 18, 9, 48, tzinfo=timezone.utc)
        images = ["2026-11-18-0948-globe.png", "2026-11-18-0948-I.png"]

        updated = insert_readme_entry(readme, timestamp, images)

        self.assertIn("### 18 Nov, 2026 9:48 GMT", updated)
        self.assertLess(updated.index(images[0]), updated.index("### Older entry"))
        self.assertEqual(insert_readme_entry(updated, timestamp, images), updated)
        self.assertEqual(model_label(timestamp), "18 Nov, 2026 9:48 GMT")

    def test_inserts_himawari_entry_before_references_once(self):
        readme = "# 2026 Events\n\n## References\n[1] JMA\n"
        image_time = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
        image_name = "2026-11-18-1000-Himawari-Japan-ngt.jpg"

        updated = insert_himawari_entry(
            readme, image_time, image_name, "Night Microphysics RGB"
        )

        self.assertIn("### 18 Nov, 2026 10:00 UTC", updated)
        self.assertLess(updated.index(image_name), updated.index("## References"))
        self.assertEqual(
            insert_himawari_entry(
                updated, image_time, image_name, "Night Microphysics RGB"
            ),
            updated,
        )


if __name__ == "__main__":
    unittest.main()
