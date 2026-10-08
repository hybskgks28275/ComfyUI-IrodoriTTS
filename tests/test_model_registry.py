import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('irodori_registry_tests', Path(__file__).parents[1] / 'src' / 'modules' / 'models.py')
models = importlib.util.module_from_spec(spec)
spec.loader.exec_module(models)

class RegistryTests(unittest.TestCase):
    def load(self, config):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'models.json'
            path.write_text(json.dumps(config), encoding='utf-8-sig')
            return models.load_model_config(path)

    def config(self):
        return {'default_model':'Custom', 'models':[{'model_name':'Custom','url':'https://huggingface.co/owner/repo'}], 'codec':{'url':'https://huggingface.co/owner/codec'}}

    def test_manual_model_download_uses_configured_url(self):
        default, specs, _, _ = self.load(self.config())
        self.assertEqual(default, 'Custom')
        with tempfile.TemporaryDirectory() as tmp, patch.object(models,'MODEL_SPECS',specs), patch.object(models,'snapshot_download') as download, patch.object(models,'hf_hub_download'):
            checkpoint,_=models.resolve_models(Path(tmp),True,'Custom')
            self.assertEqual(checkpoint,Path(tmp)/'Custom/model.safetensors')
            download.assert_called_once_with('owner/repo',revision='main',allow_patterns=['model.safetensors','tokenizer/*'],local_dir=str(Path(tmp)/'Custom'))

    def test_quantized_variants_and_revision(self):
        config=self.config();config['models'][0].update(variants=['int8-dynamic','int4-weight-only'], revision='release-v1')
        config['default_model']='Custom/int8-dynamic'
        _,specs,_,_=self.load(config)
        self.assertEqual(list(specs),['Custom/int8-dynamic','Custom/int4-weight-only'])
        self.assertEqual(specs['Custom/int4-weight-only'],('owner/repo','release-v1'))

    def test_invalid_entries_rejected_with_config_path(self):
        mutations=[{'model_name':'../outside'},{'model_name':'C:outside'},{'model_name':'CON'}, {'url':'https://example.org/owner/repo'}, {'url':'https://huggingface.co/owner/repo/tree/main'}, {'variants':['unknown']}, {'variants':['int8-dynamic','int8-dynamic']}, {'revision':''}]
        for values in mutations:
            config=self.config();config['models'][0].update(values)
            with self.subTest(values=values), self.assertRaisesRegex(ValueError,'models.json'):
                self.load(config)

    def test_duplicate_and_missing_default_rejected(self):
        config=self.config();config['models'].append({'model_name':'custom','url':'https://huggingface.co/owner/other'})
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.load(config)
        config=self.config();config['default_model']='missing'
        with self.assertRaisesRegex(ValueError,'default_model'):self.load(config)

    def test_shipped_registry_keeps_existing_choices(self):
        self.assertEqual(len(models.MODEL_SPECS),12)
        self.assertEqual(models.DEFAULT_MODEL,'Irodori-TTS-v4.1-Small')
        self.assertEqual(models.MODEL_SPECS['Irodori-TTS-v4-Large'][0],'Aratako/Irodori-TTS-v4-Large')

if __name__=='__main__':unittest.main()
