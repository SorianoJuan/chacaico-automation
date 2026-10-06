"""Upload verification rejects wrong identity/stale files without hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('chacaico_verify_build', REPO/'firmware/verify-build.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class BuildIdentityTest(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix='chacaico-public-build-test-')
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.folder = self.root/'firmware/nodes/node_1'
        self.build = self.folder/'build'
        self.build.mkdir(parents=True)
        profile = json.loads((REPO/'firmware/nodes/node_1/profile.json').read_text())
        (self.folder/'profile.json').write_text(json.dumps(profile))
        (self.folder/'node_config.h').write_text('PUBLIC TEST HEADER, NOT A KEY\n')
        sources = ('firmware/nodes/node_1/node_1.ino',
                   'firmware/libraries/ChacaicoNode/src/ChacaicoNode.h',
                   'firmware/libraries/ChacaicoNode/library.properties')
        for name in sources:
            path = self.root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('PUBLIC TEST SOURCE\n')
        image = self.build/'CubeCell_Board_REGION_AU915_RGB_1.cyacd'
        image.write_text('PUBLIC TEST IMAGE, NOT FIRMWARE\n')
        sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        self.manifest = {**profile,'frequency_hz':profile['frequency_hz'],
                         'image':image.name,'image_sha256':sha(image),
                         'private_header_sha256':sha(self.folder/'node_config.h'),
                         'source_sha256':{name:sha(self.root/name) for name in sources}}
        self.save()

    def save(self):
        (self.build/'build-manifest.json').write_text(json.dumps(self.manifest))

    def corrupt(self, relative):
        path = self.root/relative
        path.write_text(path.read_text()+'ALTERED\n')

    def test_matching_identity_and_unchanged_files_pass(self):
        self.assertEqual(verifier.verify(self.root,1)['node_id'],1)

    def test_other_node_build_is_rejected(self):
        self.manifest['node_id'] = 2
        self.save()
        with self.assertRaisesRegex(ValueError,'Wrong node identity'):
            verifier.verify(self.root,1)

    def test_changed_private_header_is_rejected(self):
        self.corrupt('firmware/nodes/node_1/node_config.h')
        with self.assertRaisesRegex(ValueError,'Settings changed'):
            verifier.verify(self.root,1)

    def test_changed_shared_application_is_rejected(self):
        self.corrupt('firmware/libraries/ChacaicoNode/src/ChacaicoNode.h')
        with self.assertRaisesRegex(ValueError,'Sources changed'):
            verifier.verify(self.root,1)

    def test_changed_upload_image_is_rejected(self):
        self.corrupt('firmware/nodes/node_1/build/'+self.manifest['image'])
        with self.assertRaisesRegex(ValueError,'Upload image changed'):
            verifier.verify(self.root,1)

    def test_incomplete_source_checks_are_rejected(self):
        self.manifest['source_sha256'].pop('firmware/libraries/ChacaicoNode/src/ChacaicoNode.h')
        self.save()
        with self.assertRaisesRegex(ValueError,'Missing or unexpected source checks'):
            verifier.verify(self.root,1)


if __name__ == '__main__':
    unittest.main()
