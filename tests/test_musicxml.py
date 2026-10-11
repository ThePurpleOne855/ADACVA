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


def measures(*contents):
    xml = score(contents[0])
    rest = ''.join(f'<measure number="X{i}">{content}</measure>' for i, content in enumerate(contents[1:], 2))
    return xml.replace('</part></score-partwise>', rest+'</part></score-partwise>')


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

    def test_written_order_reads_repeats_and_endings_once(self):
        xml = measures('<barline><repeat direction="forward"/></barline>' + note(),
                       '<barline><ending number="1" type="start"/></barline>' + note('D'),
                       note('E') + '<barline><ending number="1" type="stop"/><repeat direction="backward"/></barline>')
        with self.assertRaisesRegex(ValueError, 'repeat'):
            self.load(xml)
        result = self.load(xml, written_order=True)
        self.assertEqual(result.notes, (60, 62, 64))
        self.assertEqual([e.onset for e in result.events], [0, 1, 2])
        self.assertIn('written order', result.title)
        self.assertEqual(self.load(xml, start_measure=3, written_order=True).notes, (64,))
        with self.assertRaisesRegex(ValueError, 'repeat ending'):
            self.load(xml, start_measure=3)

    def test_written_order_still_rejects_pitch_changes_and_jumps(self):
        for feature in ('<attributes><transpose><chromatic>2</chromatic></transpose></attributes>',
                        '<direction><sound dacapo="yes"/></direction>'):
            with self.subTest(feature=feature), self.assertRaises(ValueError):
                self.load(score(feature + note()), written_order=True)

    def test_voice_selection(self):
        content=note(extra='<voice>1</voice><staff>1</staff>')
        content+='<backup><duration>1</duration></backup>'+note('E',extra='<voice>2</voice><staff>2</staff>')
        self.assertEqual(self.load(score(content)).events[0].pitches,(60,64))
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

    def test_measure_range_is_inclusive_and_uses_positions(self):
        xml=measures(note(),note('D'),note('E'))
        result=self.load(xml,start_measure=2,end_measure=3)
        self.assertEqual(result.notes,(62,64))
        self.assertIn('score labels X2–X3',result.title)
        self.assertEqual(self.load(xml,end_measure=1).notes,(60,))
        self.assertEqual(self.load(xml,start_measure=3).notes,(64,))
        self.assertEqual(self.load(xml,start_measure=2,end_measure=2).notes,(62,))

    def test_range_excludes_later_unsupported_features(self):
        xml=measures(note(),note('D'),'<barline><repeat direction="backward"/></barline>'+note(extra='<chord/>'))
        self.assertEqual(self.load(xml,end_measure=2).notes,(60,62))
        with self.assertRaisesRegex(ValueError,'repeat'):
            self.load(xml,end_measure=3)

    def test_invalid_ranges_and_json_selection(self):
        for start,end in [(0,1),(-1,1),(2,1),(1,4),(True,2),(1,1.5)]:
            with self.subTest(start=start,end=end),self.assertRaisesRegex(ValueError,'range'):
                self.load(measures(note(),note()),start_measure=start,end_measure=end)
        path=Path(self.temp.name)/'test.json'
        path.write_text('{"title":"Test","notes":[60]}')
        with self.assertRaisesRegex(ValueError,'only to MusicXML'):
            load_exercise(path,end_measure=1)

    def test_inherited_divisions_and_pitch_state(self):
        # First two notes use inherited divisions=2, next uses new divisions=1.
        # A backup of 2 then puts another selected note exactly after them.
        content=note()+note('D')+'<attributes><divisions>1</divisions></attributes>'+note('E').replace('<duration>1','<duration>2')+'<backup><duration>2</duration></backup>'+note('F')
        xml=measures('<attributes><divisions>2</divisions></attributes>'+note(),content)
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.load(xml,start_measure=2,voice='1')
        for tag in ['<transpose><chromatic>2</chromatic></transpose>','<octave-shift type="up"/>']:
            with self.subTest(tag=tag),self.assertRaisesRegex(ValueError,'inherited'):
                self.load(measures('<attributes>'+tag+'</attributes>'+note(),note()),start_measure=2)

    def test_range_does_not_silently_cut_ties(self):
        xml=measures(note(extra='<tie type="start"/>'),note(extra='<tie type="stop"/>'))
        self.assertEqual(self.load(xml,start_measure=1,end_measure=2).notes,(60,))
        with self.assertRaisesRegex(ValueError,'extend the end'):
            self.load(xml,end_measure=1)
        with self.assertRaisesRegex(ValueError,'extend its start'):
            self.load(xml,start_measure=2)

    def test_range_cli(self):
        self.load(measures(note(),note('D'),note('E')))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['sheet','--exercise',str(self.path),'--start-measure','2','--end-measure','2']),0)
            self.assertEqual(main(['demo','--exercise',str(self.path),'--start-measure','2','--end-measure','2','--notes','62']),0)
        self.assertIn('measure positions 2–2',out.getvalue())
        self.assertIn('Exercise complete',out.getvalue())
