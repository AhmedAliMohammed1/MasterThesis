"""Controls for same-XYZ feature adaptation and raw numerical-failure reporting."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
import numpy as np

TOOLS=Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0,str(TOOLS))
from ouster_features import feature_values, packed_variant, converted_message
from compare_ouster_features import raw_summary


class OusterFeatureTests(unittest.TestCase):
    def test_documented_code_and_fraction_mappings(self):
        signal=np.array([0,65535,10],dtype='<f4')
        reflectivity=np.array([0,100,255],dtype='<u2')
        np.testing.assert_array_equal(feature_values(signal,reflectivity,'raw_signal'),signal)
        np.testing.assert_allclose(feature_values(signal,reflectivity,'signal_div65535'),[0,1,10/65535])
        np.testing.assert_allclose(feature_values(signal,reflectivity,'reflectivity_div255'),[0,100/255,1])
        np.testing.assert_allclose(feature_values(signal,reflectivity,'reflectivity_fraction'),[0,1,1])
        with self.assertRaisesRegex(ValueError,'8-bit'):
            feature_values(signal,[0,100,256],'reflectivity_div255')

    def test_conversion_preserves_xyz_bits_order_and_count(self):
        payload=bytearray(2*24)
        xyz=np.ndarray((2,3),dtype='<f4',buffer=payload,strides=(24,4))
        xyz[:]=[[1,-0.0,3],[4,5,6]]
        np.ndarray((2,),dtype='<f4',buffer=payload,offset=12,strides=(24,))[:]=[9000,100]
        np.ndarray((2,),dtype='<u2',buffer=payload,offset=16,strides=(24,))[:]=[100,255]
        fields=[SimpleNamespace(name=n,offset=i*4,datatype=7,count=1) for i,n in enumerate(('x','y','z','intensity'))]
        fields.append(SimpleNamespace(name='reflectivity',offset=16,datatype=4,count=1))
        msg=SimpleNamespace(data=payload,width=2,height=1,row_step=48,point_step=24,fields=fields,is_bigendian=False)
        raw=packed_variant(msg,'raw_signal')
        adapted=packed_variant(msg,'reflectivity_div255')
        self.assertEqual(raw[:,:3].tobytes(),adapted[:,:3].tobytes())
        self.assertEqual(len(raw),len(adapted))
        self.assertEqual(payload,msg.data)

    def test_failure_report_identifies_components_and_whole_frame_rejection(self):
        rows=np.array([[1,2,3,4,2,1,0,0,.9],[1,2,3,float('inf'),2,1,0,0,.9],
                       [1,2,3,4,0,1,0,0,.9]],dtype='<f4')
        summary=raw_summary(rows)
        self.assertEqual(summary['invalid_rows'],2)
        self.assertEqual(summary['nonfinite_by_component']['length'],1)
        self.assertEqual(summary['nonpositive_dimensions']['width'],1)
        self.assertEqual(summary['invalid_class_rows'],0)

    def test_ros_conversion_preserves_header_padding_and_other_channels(self):
        payload=bytearray(range(52))
        np.ndarray((2,),dtype='<f4',buffer=payload,offset=12,strides=(24,))[:]=[9000,100]
        np.ndarray((2,),dtype='<u2',buffer=payload,offset=16,strides=(24,))[:]=[100,255]
        fields=[SimpleNamespace(name=n,offset=i*4,datatype=7,count=1) for i,n in enumerate(('x','y','z','intensity'))]
        fields.append(SimpleNamespace(name='reflectivity',offset=16,datatype=4,count=1))
        msg=SimpleNamespace(data=payload,width=2,height=1,row_step=52,point_step=24,fields=fields,
                            is_bigendian=False,header=SimpleNamespace(frame_id='sensor',stamp=123))
        before=bytes(msg.data)
        adapted=converted_message(msg,'reflectivity_div255')
        self.assertEqual(msg.header,adapted.header)
        self.assertEqual(bytes(msg.data),before)
        allowed=set(range(12,16))|set(range(36,40))
        self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(before,adapted.data)) if i not in allowed))


if __name__=='__main__':
    unittest.main()
