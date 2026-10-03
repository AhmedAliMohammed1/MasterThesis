"""Lossless candidate validation and unique geometric matching controls."""
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from kitti_reference import match_rows,read_rows

ROW=(10.,0.,1.,4.,2.,2.,0.,0.,.9)
class ReferenceTests(unittest.TestCase):
    def test_unique_duplicates_cannot_claim_one_reference(self):
        result=match_rows([ROW,ROW],[ROW])
        self.assertEqual((result['matched'],result['unmatched_left']),(1,1))
    def test_yaw_wrap_and_order(self):
        a=list(ROW);a[6]=math.pi-.0001
        b=list(ROW);b[6]=-math.pi+.0001
        self.assertEqual(match_rows([a,ROW],[ROW,b])['matched'],2)
    def test_class_and_components_enforced(self):
        other=list(ROW);other[7]=1
        self.assertEqual(match_rows([ROW],[other])['matched'],0)
        other=list(ROW);other[2]+=.01
        self.assertEqual(match_rows([ROW],[other])['matched'],0)
    def test_augmenting_path_maximizes_unique_matches(self):
        a=list(ROW);b=list(ROW);c=list(ROW);d=list(ROW)
        a[0]=0.;b[0]=-.0008;c[0]=-.0002;d[0]=.0008
        self.assertEqual(match_rows([a,b],[c,d])['matched'],2)
    def test_lossless_float_reader_rejects_truncation_nan_class_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'raw.bin';p.write_bytes(struct.pack('<9f',*ROW))
            self.assertEqual(len(read_rows(p)),1)
            for data in [b'x',struct.pack('<9f',*(ROW[:7]+(3.,ROW[8]))),struct.pack('<9f',*(ROW[:3]+(-1.,)+ROW[4:])),struct.pack('<9f',*(ROW[:2]+(math.nan,)+ROW[3:]))]:
                p.write_bytes(data)
                with self.assertRaises(ValueError):read_rows(p)
    def test_empty_and_spatial_boundary(self):
        self.assertEqual(match_rows([],[])['match_fraction_of_larger'],1)
        a=list(ROW);b=list(ROW);a[0]=-.00001;b[0]=.00001
        self.assertEqual(match_rows([a],[b])['matched'],1)
        with self.assertRaises(ValueError):match_rows([a],[b],0)

from kitti_voxel_control import capped_cloud,voxel_key
class VoxelControlTests(unittest.TestCase):
    ATTR={'point_cloud_range':[0.,0.,0.,4.,4.,4.],'voxel_size':[1.,1.,4.],
          'max_voxels':1,'max_num_points_per_voxel':2}
    def test_caps_preserve_original_bits_and_point_order(self):
        rows=[(.1,.1,1.,.2),(.2,.2,1.,.3),(.3,.3,1.,.4),(2.,2.,1.,.5),(-1.,0.,1.,.6)]
        data=b''.join(struct.pack('<4f',*r) for r in rows)
        result,stats=capped_cloud(data,self.ATTR)
        self.assertEqual(result,data[:32]);self.assertEqual(stats,{'retained_points':2,'retained_voxels':1,'outside_range_points':1,'capacity_discarded_points':2})
    def test_half_open_range_and_float32_boundary(self):
        self.assertIsNone(voxel_key((4.,0.,0.,1.),self.ATTR))
        self.assertEqual(voxel_key((1.,1.,1.,1.),self.ATTR),(1,1))
    def test_nonfinite_points_are_refused(self):
        with self.assertRaises(ValueError):capped_cloud(struct.pack('<4f',math.nan,0.,0.,0.),self.ATTR)

if __name__=='__main__':unittest.main()
