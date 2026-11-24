"""Model-independent checks for the optional NumPy/PyTorch offline runner."""
import argparse, hashlib, importlib.util, json, math, subprocess, tempfile, unittest
from pathlib import Path
try:
    import numpy as np
    import torch
except ImportError as error:
    raise unittest.SkipTest("Optional offline runner requires NumPy and PyTorch") from error
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('experimental',ROOT/'tools/experimental_pointpillars.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

class ExperimentalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.points=self.root/'points.bin';np.array([[1,2,3,.5],[0,0,0,0],[float('nan'),2,3,1]],dtype='<f4').tofile(self.points)
        self.manifest=self.root/'manifest.json';self.manifest.write_text(json.dumps({'inputs':[{'input':str(self.points),'sha256':e.sha(self.points)}]}))
    def test_frozen_snapshot_and_original_invalid_mask(self):
        entries=e.validate_inputs(self.manifest,[str(self.points)])
        pts,count=e.stable_points(*entries[0]);self.assertEqual(count,3);np.testing.assert_array_equal(pts,[[1,2,3,.5]])
        self.points.write_bytes(b'changed')
        with self.assertRaises(ValueError):e.stable_points(*entries[0])
    def test_manifest_rejects_duplicate_missing_hash_and_truncated_records(self):
        with self.assertRaises(ValueError):e.validate_inputs(self.manifest,[str(self.points),str(self.points)])
        with self.assertRaises(ValueError):e.validate_inputs(self.manifest,[])
        self.points.write_bytes(b'123')
        with self.assertRaises(ValueError):e.validate_inputs(self.manifest,[str(self.points)])
    def test_source_pin_and_dirty_tree(self):
        repo=self.root/'source';repo.mkdir()
        subprocess.run(['git','init','-q',str(repo)],check=True)
        (repo/'model.py').write_text('original')
        subprocess.run(['git','-C',str(repo),'add','model.py'],check=True)
        subprocess.run(['git','-C',str(repo),'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture'],check=True)
        commit=e.git(repo,'rev-parse','HEAD')
        from unittest.mock import patch
        with patch.object(e,'PINNED_SOURCE_COMMIT',commit):
            self.assertIn('model.py',e.validate_source(repo,commit))
            (repo/'pointpillars').mkdir();(repo/'.git/info/exclude').write_text('shadow.py\n')
            (repo/'pointpillars/shadow.py').write_text('ignored shadow')
            with self.assertRaisesRegex(ValueError,'Untracked executable'):e.validate_source(repo,commit)
            (repo/'pointpillars/shadow.py').unlink()
            (repo/'model.py').write_text('modified')
            with self.assertRaises(ValueError):e.validate_source(repo,commit)
        with self.assertRaises(ValueError):e.validate_source(repo,'bad')
    def test_workflow_failure_and_existing_output(self):
        from unittest.mock import patch
        output=self.root/'result';checkpoint=self.root/'weights';checkpoint.write_bytes(b'weights')
        args=argparse.Namespace(repeats=1,threads=1,source=self.root,checkpoint=checkpoint,
            expected_source_commit=e.PINNED_SOURCE_COMMIT,expected_checkpoint_sha256=e.sha(checkpoint),
            input_manifest=self.manifest,input=[str(self.points)],output=output,full360=False)
        with patch.object(e,'validate_source',return_value={'model.py':'hash'}), patch.object(e,'load_model',side_effect=RuntimeError('injected failure')):
            with self.assertRaisesRegex(RuntimeError,'injected'):e.run(args)
            self.assertFalse((output/'complete.json').exists())
            self.assertEqual(json.loads((output/'failure.json').read_text())['completed_records'],0)
            saved=(output/'checkpoint.json').read_bytes()
            with self.assertRaises(FileExistsError):e.run(args)
            self.assertEqual((output/'checkpoint.json').read_bytes(),saved)
        args.output=self.root/'mismatch';args.expected_checkpoint_sha256='0'*64
        with patch.object(e,'validate_source',return_value={}):
            with self.assertRaisesRegex(ValueError,'Checkpoint hash'):e.run(args)
            self.assertFalse(args.output.exists())
    def test_workflow_detects_source_mutation_after_inference(self):
        from unittest.mock import patch
        checkpoint=self.root/'weights';checkpoint.write_bytes(b'weights');output=self.root/'mutation'
        args=argparse.Namespace(repeats=1,threads=1,source=self.root,checkpoint=checkpoint,
            expected_source_commit=e.PINNED_SOURCE_COMMIT,expected_checkpoint_sha256=e.sha(checkpoint),
            input_manifest=self.manifest,input=[str(self.points)],output=output,full360=False)
        with patch.object(e,'validate_source',side_effect=[{'model.py':'before'},{'model.py':'after'}]), patch.object(e,'load_model',return_value=object()), patch.object(e,'infer',return_value=[]):
            with self.assertRaisesRegex(ValueError,'changed during inference'):e.run(args)
        self.assertFalse((output/'complete.json').exists());self.assertTrue((output/'failure.json').exists())
        self.assertEqual(len(json.loads((output/'checkpoint.json').read_text())['records']),1)
    def test_voxel_capacity_boundaries_and_first_arrival(self):
        p=np.array([[.1,.1,0,1],[.1,.1,0,2],[.1,.1,0,3],[1.1,.1,0,4],[2.1,.1,0,5],[-1,0,0,6],[3,0,0,7],[float('nan'),0,0,8]],np.float32)
        v,c,n=e.voxel_numpy(p,[1,1,1],[0,0,0,3,1,1],2,2)
        np.testing.assert_array_equal(c,[[0,0,0],[1,0,0]]);np.testing.assert_array_equal(n,[2,1]);np.testing.assert_array_equal(v[0,:,3],[1,2]);self.assertEqual(v[1,0,3],4)
    def test_rotated_nms_and_ties(self):
        boxes=torch.tensor([[0.,0.,2.,1.,.4],[0.,0.,2.,1.,.4],[10.,0.,12.,1.,.4]])
        np.testing.assert_array_equal(e.nms_cuda(boxes,torch.tensor([.9,.9,.7]),.01).numpy(),[0,2])
    def test_box_origin_yaw_and_inverse_transform(self):
        b=np.array([10,2,-1,.6,1.7,1.8,.4],np.float32);out=e.adapt_box(b)
        self.assertAlmostEqual(out[2],-.1,places=6);self.assertAlmostEqual(out[6],-.4,places=6)
        self.assertEqual(out[3:6],list(map(float,b[3:6])))
        for angle in [0,90,180,270]:
            p=np.array([[out[0],out[1],out[2],1]],np.float32);rot=e.rotate_points(p,angle)
            local=[float(rot[0,0]),float(rot[0,1]),*out[2:6],out[6]+math.radians(angle)]
            np.testing.assert_allclose(e.inverse_box(local,angle),out,atol=1e-6)
    def test_repeat_bounds_fail_before_artifacts(self):
        args=argparse.Namespace(repeats=0,threads=4)
        with self.assertRaises(ValueError):e.run(args)
    def test_atomic_checkpoint_and_no_partial_final(self):
        destination=self.root/'result';destination.mkdir()
        e.atomic_json(destination/'checkpoint.json',{'status':'partial'})
        self.assertFalse((destination/'complete.json').exists());self.assertFalse((destination/'checkpoint.tmp').exists())
        with self.assertRaises(FileExistsError):destination.mkdir()
if __name__=='__main__':unittest.main()
