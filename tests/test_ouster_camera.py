"""Camera timeline and merged-topic preservation controls."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from export_ouster_camera import timeline
from prepare_ouster_visual import rows


class CameraTimelineTests(unittest.TestCase):
    def test_preserves_initial_offset_intervals_and_last_hold(self):
        result=timeline([1_250_000_000,1_750_000_000],1_000_000_000,2_000_000_000)
        self.assertIn("file 'black.png'",result)
        self.assertEqual([line for line in result.splitlines() if line.startswith('duration')],
                         ['duration 0.250000000','duration 0.500000000','duration 0.250000000'])
        self.assertEqual(result.count("file '000001.png'"),2)

    def test_outside_or_nonmonotonic_record_times_rejected(self):
        for values in ([999_000_000],[1_250_000_000,1_250_000_000],[2_100_000_000]):
            with self.assertRaises(ValueError):timeline(values,1_000_000_000,2_000_000_000)

    def test_camera_iterator_preserves_original_payload_timestamps_and_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.db3'
            with sqlite3.connect(path) as db:
                db.execute('CREATE TABLE topics(id INTEGER,name TEXT)')
                db.executemany('INSERT INTO topics VALUES(?,?)',[(1,'/points'),(2,'/image'),(3,'/camera_info')])
                db.execute('CREATE TABLE messages(id INTEGER,timestamp INTEGER,topic_id INTEGER,data BLOB)')
                db.executemany('INSERT INTO messages VALUES(?,?,?,?)',[(1,20,2,b'image1'),(2,10,1,b'cloud'),(3,20,2,b'image2'),(4,20,3,b'calibration')])
            self.assertEqual(list(rows(path,['/image','/camera_info'])),[(20,'/image',b'image1'),(20,'/image',b'image2'),(20,'/camera_info',b'calibration')])


if __name__=='__main__':unittest.main()
