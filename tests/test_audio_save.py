import importlib.util
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
import av
import soundfile as sf
import torch

spec = importlib.util.spec_from_file_location('irodori_audio_save_tests', Path(__file__).parents[1] / 'src' / 'nodes' / 'audio_save.py')
save = importlib.util.module_from_spec(spec)
spec.loader.exec_module(save)

class SaveAudioTests(unittest.TestCase):
    def test_templates_and_paths(self):
        with tempfile.TemporaryDirectory() as root:
            now = datetime(2026, 9, 29, 15, 30, 45)
            path, prefix = save.output_location(root, '{yyyymmdd}/take', 'voice_{yyyymmddhhmmss}', now)
            self.assertEqual(path, Path(root) / 'audio/20260929/take')
            self.assertEqual(prefix, 'voice_20260929153045')
            for directory, prefix in [('../escape','ok'),('C:/escape','ok'),('/escape','ok'),('ok','../x'),('ok','CON'),('ok','a.'),('ok','')]:
                with self.subTest(directory=directory,prefix=prefix), self.assertRaises(ValueError):
                    save.output_location(root,directory,prefix,now)

    def test_encode_decode_all_formats_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            rate = 48000
            tone = torch.sin(torch.arange(rate) * (2 * torch.pi * 440 / rate)) * .2
            for channels in (1,2):
                audio = {'sample_rate': rate, 'waveform': tone.repeat(2,channels,1)}
                for fmt in ('wav','flac','mp3'):
                    for bits in ('16','24') if fmt != 'mp3' else ('16',):
                        with self.subTest(channels=channels,fmt=fmt,bits=bits):
                            results=save.save_audio(audio,root,'test','',fmt,'192',bits)
                            self.assertEqual(len(results),2)
                            for result in results:
                                path=Path(root)/result['subfolder']/result['filename']
                                with av.open(str(path)) as container:
                                    stream=container.streams.audio[0]
                                    self.assertEqual(stream.sample_rate,rate)
                                    self.assertEqual(stream.channels,channels)
                                    frames=list(container.decode(audio=0))
                                    self.assertTrue(frames)
                                    self.assertLess(abs(sum(f.samples for f in frames)-rate),2048)
                                    if fmt=='mp3': self.assertEqual(stream.bit_rate,192000)
                                if fmt!='mp3':
                                    actual, actual_rate=sf.read(path,always_2d=True)
                                    self.assertEqual(actual.shape,(rate,channels))
                                    self.assertEqual(sf.info(path).subtype,'PCM_'+bits)
                                    self.assertLess(abs(actual[:,0]-tone.numpy()).max(),.00004)
            self.assertEqual(len(list((Path(root)/'audio').glob('*'))),20)

    def test_invalid_audio_creates_no_file(self):
        with tempfile.TemporaryDirectory() as root:
            for waveform in (torch.zeros(1,3,10),torch.full((1,1,10),float('nan')),torch.zeros(1,1,0)):
                with self.assertRaises(ValueError): save.save_audio({'sample_rate':48000,'waveform':waveform},root,'test','','wav','192','16')
            self.assertEqual(list(Path(root).iterdir()),[])

if __name__=='__main__': unittest.main()
