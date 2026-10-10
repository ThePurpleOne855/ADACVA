import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from ada_piano.cli import main
from ada_piano.music_sheet import load_exercise


def note(step="C", octave=4, extra="", alter=""):
    return f'<note>{extra}<pitch><step>{step}</step>{alter}<octave>{octave}</octave></pitch><duration>1</duration></note>'


def score(content, namespace=""):
    return f'<score-partwise {namespace}><work><work-title>Imported melody</work-title></work><part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions></attributes>{content}</measure></part></score-partwise>'


class MusicXMLTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.musicxml"

    def load(self, xml, **kwargs):
        self.path.write_text(xml, encoding="utf-8")
        return load_exercise(self.path, **kwargs)

    def test_pitches_rests_namespaces_and_ties(self):
        content = note(extra='<tie type="start"/>') + note(extra='<tie type="stop"/>')
        content += '<note><rest/><duration>1</duration></note>'
        content += note("F", alter='<alter>1</alter>') + note("B", alter='<alter>-1</alter>')
        result = self.load(score(content, 'xmlns="http://www.musicxml.org/ns/musicxml"'))
        self.assertEqual(result.notes, (60, 66, 70))
        self.assertEqual(result.title, "Imported melody")

    def test_key_signature_does_not_double_apply_pitch_alter(self):
        content='<attributes><key><fifths>1</fifths></key></attributes>'
        self.assertEqual(self.load(score(content+note("F", alter='<alter>1</alter>'))).notes, (66,))

    def test_voice_selection(self):
        content=note(extra='<voice>1</voice><staff>1</staff>')
        content+='<backup><duration>1</duration></backup>'+note('E',extra='<voice>2</voice><staff>2</staff>')
        with self.assertRaisesRegex(ValueError, "select"):
            self.load(score(content))
        self.assertEqual(self.load(score(content), staff="2", voice="2").notes,(64,))
        with self.assertRaisesRegex(ValueError, "No playable"):
            self.load(score(content),staff="3")

    def test_multiple_parts_require_choice(self):
        xml=score(note()).replace('</score-partwise>', '<part id="P2"><measure number="1">'+note('D')+'</measure></part></score-partwise>')
        with self.assertRaisesRegex(ValueError, '--part'):
            self.load(xml)
        self.assertEqual(self.load(xml,part="P2").notes,(62,))

    def test_overlap_is_not_silently_flattened_after_selection(self):
        content=note()+'<backup><duration>1</duration></backup>'+note('E')
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.load(score(content),voice='1')

    def test_invalid_duration(self):
        with self.assertRaisesRegex(ValueError,'duration'):
            self.load(score(note().replace('<duration>1</duration>','<duration>0</duration>')))

    def test_rejects_unsupported_and_invalid_scores(self):
        for content in [note(extra='<chord/>'),note(extra='<grace/>'),note(alter='<alter>0.5</alter>'),
                        note(octave=10),note(extra='<tie type="stop"/>'),note(extra='<tie type="start"/>'),
                        '<barline><repeat direction="backward"/></barline>'+note(),
                        '<attributes><transpose><chromatic>2</chromatic></transpose></attributes>'+note()]:
            with self.subTest(content=content),self.assertRaises(ValueError):
                self.load(score(content))
        for xml in ['<broken', '<score-timewise/>', '<!DOCTYPE x [<!ENTITY a "x">]>'+score(note())]:
            with self.subTest(xml=xml),self.assertRaises(ValueError):
                self.load(xml)

    def test_compressed_musicxml(self):
        archive=Path(self.temp.name)/'song.mxl'
        with ZipFile(archive,'w') as z:
            z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="scores/song.xml" media-type="application/vnd.recordare.musicxml+xml"/></rootfiles></container>')
            z.writestr('scores/song.xml',score(note()))
        self.assertEqual(load_exercise(archive).notes,(60,))
        with ZipFile(archive,'w') as z:
            z.writestr('unrelated.xml',score(note()))
        with self.assertRaisesRegex(ValueError,'Invalid MXL'):
            load_exercise(archive)

    def test_cli_sheet_and_demo(self):
        self.load(score(note()+note('D')))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['sheet','--exercise',str(self.path)]),0)
            self.assertEqual(main(['demo','--exercise',str(self.path),'--notes','60','62']),0)
        self.assertIn('C4, D4',out.getvalue())
        self.assertIn('Exercise complete',out.getvalue())
        self.assertIn('rhythm and rests are not graded',out.getvalue().lower())
